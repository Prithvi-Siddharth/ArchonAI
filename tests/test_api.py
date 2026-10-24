"""Tests for the FastAPI layer (api/).

The LLM layer is mocked exactly as in test_graph.py, so these run the real
LangGraph workflow end-to-end through the HTTP API without a GROQ_API_KEY or
network access. The error-mapping tests make the LLM layer raise each kind
of failure and check that the API returns the right status code -- and never
leaks the raw exception text to the client.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from groq import APIStatusError, APITimeoutError, RateLimitError

from agents import llm as llm_module
from api.main import app
from graph.state import MAX_REVISIONS

from .test_graph import _patch_llm

client = TestClient(app)

ARCHITECTURES_URL = "/api/v1/architectures"
VALID_BODY = {"user_request": "Design a blogging platform for 10,000 users."}

# Embedded in every simulated failure; must never appear in an API response.
SECRET_DETAIL = "SECRET-INTERNAL-DETAIL"

_REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def _raise_from_llm(monkeypatch, exc: BaseException) -> None:
    """Make every structured LLM call raise `exc`."""

    def failing_invoke_structured(llm, schema, prompt):
        raise exc

    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
    monkeypatch.setattr(llm_module, "invoke_structured", failing_invoke_structured)


# --- Health & examples -----------------------------------------------------------


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_examples_returns_all_prompts_with_label_and_text():
    response = client.get(f"{ARCHITECTURES_URL}/examples")
    assert response.status_code == 200
    examples = response.json()
    assert len(examples) == 6
    for example in examples:
        assert set(example) == {"label", "prompt"}
        assert example["label"] and example["prompt"]


def test_docs_and_openapi_are_served():
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/health", ARCHITECTURES_URL, f"{ARCHITECTURES_URL}/examples"} <= set(paths)


# --- Successful runs ---------------------------------------------------------------


def test_create_architecture_returns_full_serialized_result(monkeypatch):
    _patch_llm(monkeypatch, critic_verdicts=[True])

    response = client.post(ARCHITECTURES_URL, json=VALID_BODY)

    assert response.status_code == 200
    data = response.json()
    assert data["approved"] is True
    assert data["max_revisions_reached"] is False
    assert data["revision_count"] == 0
    for key in (
        "requirements",
        "architecture_plan",
        "architecture",
        "compute_analysis",
        "database_analysis",
        "networking_analysis",
        "security_analysis",
        "reliability_analysis",
        "cost_analysis",
        "validation_results",
        "critic_review",
        "final_report",
    ):
        assert data[key], f"{key} missing from response"
    assert data["architecture"]["services"], "architecture services were not serialized"
    nodes = [entry["node"] for entry in data["execution_trace"]]
    assert nodes[0] == "Requirements Analyzer"
    assert nodes[-1] == "Final Report"


def test_create_architecture_reports_revision_loop(monkeypatch):
    _patch_llm(monkeypatch, critic_verdicts=[False, True])

    data = client.post(ARCHITECTURES_URL, json=VALID_BODY).json()

    assert data["approved"] is True
    assert data["revision_count"] == 1
    assert data["architecture"]["version"] == 2


def test_create_architecture_flags_max_revisions_reached(monkeypatch):
    _patch_llm(monkeypatch, critic_verdicts=[False])

    response = client.post(ARCHITECTURES_URL, json=VALID_BODY)

    assert response.status_code == 200
    data = response.json()
    assert data["approved"] is False
    assert data["max_revisions_reached"] is True
    assert data["revision_count"] == MAX_REVISIONS
    # Enums serialize as plain strings, not Python objects.
    assert data["critic_review"]["issues"][0]["severity"] == "high"


def test_create_architecture_strips_surrounding_whitespace(monkeypatch):
    seen = {}

    def fake_run_workflow(user_request):
        seen["user_request"] = user_request
        raise RuntimeError("stop here")

    monkeypatch.setattr("api.routes.architectures.run_workflow", fake_run_workflow)
    client_no_raise = TestClient(app, raise_server_exceptions=False)
    client_no_raise.post(ARCHITECTURES_URL, json={"user_request": "   Design a blog for 10k users   "})

    assert seen["user_request"] == "Design a blog for 10k users"


# --- Invalid input -----------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"user_request": ""},
        {"user_request": "     "},
        {"user_request": "too short"},
        {"user_request": "x" * 4001},
        {"user_request": 12345},
        {},
    ],
)
def test_invalid_input_is_rejected_without_running_the_workflow(monkeypatch, body):
    def must_not_run(user_request):
        raise AssertionError("workflow should not run for invalid input")

    monkeypatch.setattr("api.routes.architectures.run_workflow", must_not_run)

    response = client.post(ARCHITECTURES_URL, json=body)

    assert response.status_code == 422


# --- Workflow failures -------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (llm_module.MissingAPIKeyError(SECRET_DETAIL), 503),
        (RateLimitError(SECRET_DETAIL, response=httpx.Response(429, request=_REQUEST), body=None), 429),
        (APIStatusError(SECRET_DETAIL, response=httpx.Response(413, request=_REQUEST), body=None), 429),
        (APITimeoutError(request=_REQUEST), 504),
        (llm_module.LLMInvocationError(SECRET_DETAIL), 502),
        (APIStatusError(SECRET_DETAIL, response=httpx.Response(500, request=_REQUEST), body=None), 502),
        (RuntimeError(SECRET_DETAIL), 500),
    ],
    ids=["missing-key", "rate-limit", "http-413", "timeout", "llm-error", "provider-500", "unexpected"],
)
def test_workflow_failures_map_to_http_errors_without_leaking_details(monkeypatch, exc, expected_status):
    _raise_from_llm(monkeypatch, exc)

    response = client.post(ARCHITECTURES_URL, json=VALID_BODY)

    assert response.status_code == expected_status
    assert set(response.json()) == {"detail"}
    assert SECRET_DETAIL not in response.text
    assert "Traceback" not in response.text


def test_rate_limit_wrapped_in_llm_invocation_error_still_maps_to_429(monkeypatch):
    # This is how a real exhausted rate limit arrives: invoke_structured
    # wraps the groq error as LLMInvocationError(...) from RateLimitError.
    try:
        raise RateLimitError(SECRET_DETAIL, response=httpx.Response(429, request=_REQUEST), body=None)
    except RateLimitError as rate_limit:
        try:
            raise llm_module.LLMInvocationError(SECRET_DETAIL) from rate_limit
        except llm_module.LLMInvocationError as wrapped:
            exc = wrapped

    _raise_from_llm(monkeypatch, exc)

    response = client.post(ARCHITECTURES_URL, json=VALID_BODY)

    assert response.status_code == 429
    assert SECRET_DETAIL not in response.text

"""Tests for the FastAPI layer (api/) and the shared failure rules (api/errors.py).

Job submission and status are covered in test_jobs.py. Here: the
non-job endpoints, the absence of the removed synchronous endpoint, and the
rules that turn a workflow failure into a client-safe status code and
message -- which the worker stores on every failed job. The helpers at the
top are shared with test_jobs.py and test_observability.py.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from groq import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from agents import llm as llm_module
from api.errors import classify_workflow_error
from api.main import app
from graph.workflow import WorkflowError

client = TestClient(app)

ARCHITECTURES_URL = "/api/v1/architectures"

# Embedded in every simulated failure; must never appear in an API response.
SECRET_DETAIL = "SECRET-INTERNAL-DETAIL"

_REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def _raise_from_llm(monkeypatch, exc: BaseException) -> None:
    """Make every structured LLM call raise `exc`."""

    def failing_invoke_structured(llm, schema, prompt):
        raise exc

    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
    monkeypatch.setattr(llm_module, "invoke_structured", failing_invoke_structured)


def _wrapped(exc: BaseException) -> WorkflowError:
    """`exc` as it reaches callers: run_workflow raises WorkflowError(...) from it."""
    try:
        raise exc
    except BaseException as original:
        try:
            raise WorkflowError(f"ArchonAI workflow failed: {original}") from original
        except WorkflowError as wrapped:
            return wrapped


# --- Health, examples, docs --------------------------------------------------------


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
    paths = set(client.get("/openapi.json").json()["paths"])
    assert {
        "/health",
        f"{ARCHITECTURES_URL}/examples",
        f"{ARCHITECTURES_URL}/jobs",
        f"{ARCHITECTURES_URL}/jobs/{{job_id}}",
    } <= paths


def test_synchronous_endpoint_was_removed(monkeypatch):
    # Designs only run in the background worker now; the API must never run the
    # workflow itself, even if someone calls the old synchronous route.
    def must_not_run(user_request):
        raise AssertionError("the API must not run the workflow")

    monkeypatch.setattr("graph.workflow.run_workflow", must_not_run)

    response = client.post(ARCHITECTURES_URL, json={"user_request": "Design a blogging platform for 10,000 users."})

    assert response.status_code in (404, 405)
    assert ARCHITECTURES_URL not in client.get("/openapi.json").json()["paths"]


# --- Failure classification (stored on failed jobs) --------------------------------


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_retryable"),
    [
        (llm_module.MissingAPIKeyError(SECRET_DETAIL), 503, False),
        (RateLimitError(SECRET_DETAIL, response=httpx.Response(429, request=_REQUEST), body=None), 429, True),
        (APIStatusError(SECRET_DETAIL, response=httpx.Response(413, request=_REQUEST), body=None), 429, True),
        (APITimeoutError(request=_REQUEST), 504, True),
        (APIConnectionError(message=SECRET_DETAIL, request=_REQUEST), 502, True),
        (llm_module.LLMInvocationError(SECRET_DETAIL), 502, False),
        (APIStatusError(SECRET_DETAIL, response=httpx.Response(500, request=_REQUEST), body=None), 502, False),
        (RuntimeError(SECRET_DETAIL), 500, False),
    ],
    ids=["missing-key", "rate-limit", "http-413", "timeout", "connection", "llm-error", "provider-500", "unexpected"],
)
def test_workflow_failures_are_classified_without_leaking_details(exc, expected_status, expected_retryable):
    failure = classify_workflow_error(_wrapped(exc))

    assert failure.status_code == expected_status
    assert failure.retryable is expected_retryable
    assert SECRET_DETAIL not in failure.message
    assert "Traceback" not in failure.message


def test_rate_limit_wrapped_in_llm_invocation_error_is_still_a_retryable_429():
    # This is how a real exhausted rate limit arrives: invoke_structured
    # wraps the groq error as LLMInvocationError(...) from RateLimitError.
    try:
        raise RateLimitError(SECRET_DETAIL, response=httpx.Response(429, request=_REQUEST), body=None)
    except RateLimitError as rate_limit:
        try:
            raise llm_module.LLMInvocationError(SECRET_DETAIL) from rate_limit
        except llm_module.LLMInvocationError as llm_error:
            exc = llm_error

    failure = classify_workflow_error(_wrapped(exc))

    assert failure.status_code == 429
    assert failure.retryable is True
    assert SECRET_DETAIL not in failure.message


def _gemini(error_type_name: str, code: int, status: str) -> BaseException:
    from .test_resilience import _gemini_error

    return _gemini_error(error_type_name, code, status)


@pytest.mark.parametrize(
    ("make_exc", "expected_status", "expected_retryable"),
    [
        (lambda: _gemini("GoogleRateLimitError", 429, "RESOURCE_EXHAUSTED"), 429, True),
        (lambda: _gemini("GoogleAPIError", 503, "UNAVAILABLE"), 502, True),
        (lambda: _gemini("GoogleAuthenticationError", 401, "UNAUTHENTICATED"), 502, False),
        (lambda: _gemini("GoogleInvalidRequestError", 400, "INVALID_ARGUMENT"), 502, False),
        (lambda: httpx.ReadTimeout(SECRET_DETAIL), 504, True),
        (lambda: httpx.ConnectError(SECRET_DETAIL), 502, True),
    ],
    ids=["gemini-rate-limit", "gemini-overloaded", "gemini-bad-key", "gemini-bad-request", "timeout", "connection"],
)
def test_gemini_failures_get_the_same_classification_as_groq(make_exc, expected_status, expected_retryable):
    try:
        raise llm_module.LLMInvocationError(SECRET_DETAIL) from make_exc()
    except llm_module.LLMInvocationError as llm_error:
        failure = classify_workflow_error(_wrapped(llm_error))

    assert (failure.status_code, failure.retryable) == (expected_status, expected_retryable)
    assert SECRET_DETAIL not in failure.message

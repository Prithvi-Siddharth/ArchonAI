"""Architecture Designer digest mode (DESIGNER_RESEARCH_MODE=digest, Optimization 5).

Instead of LLM tool-calling research, the design call gets a compact digest
of the whole AWS knowledge base (26 services): no research LLM calls, and
every candidate is visible. Optional categories are left out only when the
plan says plainly they are not needed. The default ("llm") is unchanged.
The design call, its prompt and its limits are unchanged. No LLM.
"""

from __future__ import annotations

import json

import pytest

from agents import architecture as designer
from agents import llm as llm_module
from graph.state import create_initial_state
from models.schemas import Architecture
from tools.aws_service_search import list_categories, service_digest

from .conftest import make_architecture, make_architecture_plan, make_requirements

with open("data/aws_services.json", encoding="utf-8") as _f:
    KB = json.load(_f)


@pytest.fixture
def digest_mode(monkeypatch):
    monkeypatch.setenv(designer.RESEARCH_MODE_ENV, "digest")


def _run_designer(monkeypatch, caplog=None, **plan_overrides):
    """Run the Designer with every LLM call recorded; research must never be called in digest mode."""
    llm_calls: list[dict] = []
    prompts: list[tuple[type, str]] = []

    def fake_get_llm(temperature=0.2, max_tokens=750):
        llm_calls.append({"temperature": temperature, "max_tokens": max_tokens})
        return object()

    def fake_invoke_structured(llm, schema, prompt):
        prompts.append((schema, prompt))
        return make_architecture()

    monkeypatch.setattr(llm_module, "get_llm", fake_get_llm)
    monkeypatch.setattr(llm_module, "invoke_structured", fake_invoke_structured)
    state = create_initial_state("Design an e-commerce platform.")
    state.update(requirements=make_requirements(), architecture_plan=make_architecture_plan(**plan_overrides))
    if caplog is not None:
        with caplog.at_level("INFO"):
            result = designer.run(state)
    else:
        result = designer.run(state)
    return result, llm_calls, prompts


# ---------------------------------------------------------------------------
# The digest
# ---------------------------------------------------------------------------


def test_digest_covers_the_whole_knowledge_base_compactly():
    digest = service_digest()
    lines = digest.splitlines()
    assert len(lines) == len(KB) == 26
    for service, line in zip(KB, lines, strict=True):
        assert line.startswith(f"- {service['name']} ({service['category']}): {service['description']}")
        assert f"Strength: {service['strengths'][0]}." in line
        assert f"Limitation: {service['limitations'][0]}." in line
    assert len(digest) < 6500  # ~1,400 tokens for every candidate service


def test_digest_can_be_limited_to_categories():
    digest = service_digest(["Security", "Caching"])
    names = {s["name"] for s in KB if s["category"] in ("Security", "Caching")}
    assert {line.split(" (")[0][2:] for line in digest.splitlines()} == names


# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "llm"), ("", "llm"), ("llm", "llm"), ("search", "llm"), ("digest", "digest"), (" DIGEST ", "digest")],
)
def test_research_mode_setting(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv(designer.RESEARCH_MODE_ENV, raising=False)
    else:
        monkeypatch.setenv(designer.RESEARCH_MODE_ENV, value)
    assert designer.research_mode() == expected


def test_llm_mode_still_runs_the_tool_calling_research(monkeypatch):
    monkeypatch.setenv(designer.RESEARCH_MODE_ENV, "llm")
    monkeypatch.setattr(designer, "_run_tool_calling_research", lambda requirements, plan: ("LLM RESEARCH NOTES", False))

    result, _, prompts = _run_designer(monkeypatch)

    ((_, prompt),) = prompts
    assert "LLM RESEARCH NOTES" in prompt and designer.DIGEST_HEADER not in prompt
    assert result["execution_trace"][0]["action"].startswith("Searched the AWS service knowledge base")


# ---------------------------------------------------------------------------
# Digest mode
# ---------------------------------------------------------------------------


def test_digest_mode_makes_only_the_design_call(monkeypatch, digest_mode, caplog):
    def research_must_not_run(*args, **kwargs):
        raise AssertionError("research LLM call in digest mode")

    monkeypatch.setattr(designer, "_run_tool_calling_research", research_must_not_run)

    result, llm_calls, prompts = _run_designer(monkeypatch, caplog)

    assert llm_calls == [{"temperature": 0.3, "max_tokens": llm_module.ARCHITECTURE_MAX_TOKENS}]  # the design only
    ((schema, prompt),) = prompts
    assert schema is Architecture
    research = prompt.split("AWS service research gathered:\n")[1].split("\n\nProduce a complete architecture")[0]
    assert research == f"{designer.DIGEST_HEADER}\n{service_digest()}"  # every service, nothing skipped
    for name in ("AWS WAF", "AWS Secrets Manager", "Amazon ElastiCache", "Amazon SQS"):
        assert f"- {name} (" in research
    # The rest of the design prompt is unchanged.
    assert "Hard size limits" in prompt and "At most 7 services" in prompt
    assert result["architecture"].version == 1
    assert result["execution_trace"][0]["action"] == (
        "Designed the initial architecture with 4 services from the AWS service knowledge base digest."
    )
    (event,) = [r.event_fields for r in caplog.records if getattr(r, "event_fields", {}).get("event") == "designer_research"]
    assert (event["mode"], event["services"]) == ("digest", 26) and "skipped_categories" not in event


def test_a_concern_the_plan_says_is_not_needed_is_left_out(monkeypatch, digest_mode, caplog):
    _, _, prompts = _run_designer(monkeypatch, caplog, messaging="No async messaging required for this workload.")

    research = prompts[0][1]
    for name in ("Amazon SQS", "Amazon SNS", "Amazon EventBridge"):
        assert f"- {name} (" not in research
    assert "(Not listed: Messaging -- the plan says these are not needed.)" in research
    assert "- Amazon ElastiCache (" in research  # other categories stay
    (event,) = [r.event_fields for r in caplog.records if getattr(r, "event_fields", {}).get("event") == "designer_research"]
    assert event["skipped_categories"] == "Messaging" and event["services"] == 23


@pytest.mark.parametrize(
    "text",
    [
        "Queue required to absorb flash-sale write spikes.",  # a need, not a negation
        "Async processing is needed for order confirmation emails.",
        "Not much caching: a small in-memory cache for sessions.",  # no "required/needed"
    ],
)
def test_needed_concerns_are_never_left_out(monkeypatch, digest_mode, text):
    _, _, prompts = _run_designer(monkeypatch, messaging=text, caching=text)
    research = prompts[0][1]
    assert "- Amazon SQS (" in research and "- Amazon ElastiCache (" in research
    assert "Not listed:" not in research


def test_core_categories_are_always_listed(monkeypatch, digest_mode):
    not_needed = "Not required for this workload."
    _, _, prompts = _run_designer(
        monkeypatch, security=not_needed, compute=not_needed, database=not_needed, networking=not_needed,
        reliability=not_needed, storage=not_needed,
    )
    research = prompts[0][1]
    for category in ("Security", "Compute", "Database", "Networking", "Reliability"):
        assert f"({category}):" in research
    assert "(Storage):" not in research  # storage is optional and was marked not needed
    assert set(designer._OPTIONAL_CATEGORIES.values()) < set(list_categories())


def test_design_failures_still_propagate_in_digest_mode(monkeypatch, digest_mode):
    def failing(llm, schema, prompt):
        raise llm_module.LLMInvocationError("simulated")

    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
    monkeypatch.setattr(llm_module, "invoke_structured", failing)
    state = create_initial_state("x")
    state.update(requirements=make_requirements(), architecture_plan=make_architecture_plan())

    with pytest.raises(llm_module.LLMInvocationError):
        designer.run(state)

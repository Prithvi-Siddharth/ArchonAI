"""Tests for graceful degradation when an LLM call fails inside the
critic/revision/report nodes specifically.

These nodes get extra fallback handling because they sit at the end of a
long, expensive chain of prior agent calls: crashing the whole run over one
failed call at this point would throw away everything already computed. The
rest of the agents intentionally do NOT have this fallback -- an early
failure (e.g. in Requirements Analysis) has nothing valuable to preserve, so
letting it propagate as a clear WorkflowError is the right behavior there.
"""

from __future__ import annotations

import httpx
import pytest
from groq import APIStatusError, RateLimitError

from agents import critic as critic_agent
from agents import llm as llm_module
from agents import report as report_agent
from agents import revision as revision_agent
from graph.state import create_initial_state

from .conftest import (
    make_analysis,
    make_architecture,
    make_cost_analysis,
    make_critic_review,
    make_requirements,
)


def _base_state(**overrides) -> dict:
    state = create_initial_state("Design a small internal tool.")
    state.update(
        requirements=make_requirements(),
        architecture=make_architecture(),
        compute_analysis=make_analysis("Compute"),
        database_analysis=make_analysis("Database"),
        networking_analysis=make_analysis("Networking"),
        security_analysis=make_analysis("Security"),
        reliability_analysis=make_analysis("Reliability"),
        cost_analysis=make_cost_analysis(),
        validation_results=None,
        revision_count=0,
    )
    state.update(overrides)
    return state


def test_critic_falls_back_to_rejected_review_on_llm_failure(monkeypatch):
    def failing_invoke_structured(llm, schema, prompt):
        raise llm_module.LLMInvocationError("simulated outage")

    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
    monkeypatch.setattr(llm_module, "invoke_structured", failing_invoke_structured)

    result = critic_agent.run(_base_state())

    review = result["critic_review"]
    assert review.approved is False
    assert review.score == 0
    assert "simulated outage" in review.issues[0].issue
    assert result["execution_trace"][0]["node"] == "Architecture Critic"


def test_revision_falls_back_to_unchanged_architecture_on_llm_failure(monkeypatch):
    def failing_invoke_structured(llm, schema, prompt):
        raise llm_module.LLMInvocationError("simulated outage")

    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.3, max_tokens=900: object())
    monkeypatch.setattr(llm_module, "invoke_structured", failing_invoke_structured)

    original_architecture = make_architecture()
    state = _base_state(
        architecture=original_architecture,
        critic_review=make_critic_review(approved=False),
        revision_count=1,
    )

    result = revision_agent.run(state)

    # The architecture is kept as-is (same object/version) rather than the
    # graph crashing, and revision_count still advances so max-revision
    # protection keeps working correctly even through a failed attempt.
    assert result["architecture"] is original_architecture
    assert result["revision_count"] == 2
    assert "failed" in result["execution_trace"][0]["action"].lower()


def test_report_falls_back_to_manual_report_on_llm_failure(monkeypatch):
    def failing_invoke_structured(llm, schema, prompt):
        raise llm_module.LLMInvocationError("simulated outage")

    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
    monkeypatch.setattr(llm_module, "invoke_structured", failing_invoke_structured)

    state = _base_state(critic_review=make_critic_review(approved=True), revision_count=0)

    result = report_agent.run(state)

    report = result["final_report"]
    assert report is not None
    assert report.executive_summary  # non-empty, assembled without an LLM call
    assert make_architecture().summary in report.architecture_overview
    assert "failed" in result["execution_trace"][0]["action"].lower()


def _fake_response(status_code: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        headers=headers or {},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )


class TestRetryOnHttp413:
    """Groq's SDK maps HTTP 429 to RateLimitError but a plain 413 (also used
    for "too large for this rolling window" rejections) falls through to the
    generic APIStatusError. Both must get the same retry treatment, or a 413
    fails on the very first attempt no matter how small later requests get."""

    def test_retries_and_recovers_on_413(self, monkeypatch):
        monkeypatch.setattr(llm_module.time, "sleep", lambda seconds: None)
        calls = {"n": 0}

        def flaky_call():
            calls["n"] += 1
            if calls["n"] < 3:
                raise APIStatusError(
                    "Request too large", response=_fake_response(413), body={"error": {"code": "rate_limit_exceeded"}}
                )
            return "ok"

        result = llm_module._invoke_with_retry(flaky_call, max_attempts=5)

        assert result == "ok"
        assert calls["n"] == 3

    def test_gives_up_after_max_attempts_on_persistent_413(self, monkeypatch):
        monkeypatch.setattr(llm_module.time, "sleep", lambda seconds: None)

        def always_413():
            raise APIStatusError("Request too large", response=_fake_response(413), body={})

        with pytest.raises(APIStatusError):
            llm_module._invoke_with_retry(always_413, max_attempts=3)

    def test_does_not_retry_unrelated_status_errors(self, monkeypatch):
        monkeypatch.setattr(llm_module.time, "sleep", lambda seconds: None)
        calls = {"n": 0}

        def teapot():
            calls["n"] += 1
            raise APIStatusError("I'm a teapot", response=_fake_response(418), body={})

        with pytest.raises(APIStatusError):
            llm_module._invoke_with_retry(teapot, max_attempts=5)

        # A status code we don't recognize as a rate-limit-shaped failure
        # should fail immediately, not burn through every retry attempt.
        assert calls["n"] == 1

    def test_still_retries_real_rate_limit_error(self, monkeypatch):
        monkeypatch.setattr(llm_module.time, "sleep", lambda seconds: None)
        calls = {"n": 0}

        def flaky_call():
            calls["n"] += 1
            if calls["n"] < 2:
                raise RateLimitError("slow down", response=_fake_response(429), body={})
            return "ok"

        result = llm_module._invoke_with_retry(flaky_call, max_attempts=5)

        assert result == "ok"
        assert calls["n"] == 2

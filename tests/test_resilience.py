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
from models.schemas import Requirements

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


SECRET = "SECRET-PROMPT-AND-GENERATION"


def _llm_failures(caplog) -> list[dict]:
    return [r.event_fields for r in caplog.records if getattr(r, "event_fields", {}).get("event") == "llm_request_failed"]


class _FailingStructuredLLM:
    """A stand-in chat model whose structured call raises the given errors in turn."""

    temperature = 0.2

    def __init__(self, *errors: BaseException):
        self._errors = list(errors)

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        raise self._errors.pop(0) if len(self._errors) > 1 else self._errors[0]

    def model_copy(self, update):
        return self


class TestProviderErrorLogging:
    """Failed provider calls log their HTTP status and error code -- never
    the message, body, prompt or generated content."""

    def test_permanent_error_logs_status_and_code_once_and_keeps_exception_types(self, caplog):
        error = APIStatusError(
            SECRET,
            response=_fake_response(401),
            body={"error": {"message": SECRET, "type": "invalid_request_error", "code": "invalid_api_key"}},
        )

        with caplog.at_level("WARNING"), pytest.raises(llm_module.LLMInvocationError) as raised:
            llm_module.invoke_structured(_FailingStructuredLLM(error), Requirements, SECRET)

        assert raised.value.__cause__ is error  # unchanged: classification still sees the provider error
        (failure,) = _llm_failures(caplog)  # not retried, logged exactly once
        assert failure["provider_status"] == 401
        assert failure["provider_error_code"] == "invalid_api_key"
        assert failure["error_type"] == "APIStatusError"
        assert failure["will_retry"] is False
        assert failure["schema"] == "Requirements"
        assert SECRET not in caplog.text

    def test_tool_use_failures_log_each_attempt_with_their_code(self, caplog):
        error = APIStatusError(
            "Error code: 400 - tool_use_failed " + SECRET,
            response=_fake_response(400),
            body={"error": {"message": SECRET, "code": "tool_use_failed", "failed_generation": SECRET}},
        )

        with caplog.at_level("WARNING"), pytest.raises(llm_module.LLMInvocationError):
            llm_module.invoke_structured(_FailingStructuredLLM(error), Requirements, "prompt")

        failures = _llm_failures(caplog)
        assert [(f["provider_status"], f["provider_error_code"], f["call_attempt"]) for f in failures] == [
            (400, "tool_use_failed", 1),
            (400, "tool_use_failed", 2),
            (400, "tool_use_failed", 3),
        ]
        assert [f["will_retry"] for f in failures] == [True, True, False]
        assert SECRET not in caplog.text

    def test_error_without_a_body_code_logs_only_the_status(self, caplog):
        error = APIStatusError(SECRET, response=_fake_response(500), body=None)

        def provider_error():
            raise error

        with caplog.at_level("WARNING"), pytest.raises(APIStatusError):
            llm_module.invoke_with_retry(provider_error)

        (failure,) = _llm_failures(caplog)
        assert failure["provider_status"] == 500
        assert "provider_error_code" not in failure  # None fields are dropped from the event
        assert SECRET not in caplog.text

    @pytest.mark.parametrize(
        "code",
        [SECRET + " with spaces", "x" * 65, {"nested": "object"}, 42],
        ids=["free-text", "too-long", "dict", "number"],
    )
    def test_error_code_that_is_not_a_short_identifier_is_not_logged(self, code):
        error = APIStatusError("x", response=_fake_response(400), body={"error": {"code": code}})

        assert llm_module._provider_error_fields(error)["provider_error_code"] is None

    def test_network_error_has_no_status_or_code(self):
        from groq import APIConnectionError

        fields = llm_module._provider_error_fields(APIConnectionError(request=_fake_response(500).request))

        assert fields == {"error_type": "APIConnectionError", "provider_status": None, "provider_error_code": None}

    def test_retried_rate_limit_logs_each_wait_then_the_final_failure(self, monkeypatch, caplog):
        monkeypatch.setattr(llm_module.time, "sleep", lambda seconds: None)
        monkeypatch.setattr(llm_module, "_random", lambda: 0.0)
        error = RateLimitError(
            SECRET, response=_fake_response(429, {"retry-after": "4"}), body={"error": {"code": "rate_limit_exceeded"}}
        )

        def always_rate_limited():
            raise error

        with caplog.at_level("WARNING"), pytest.raises(RateLimitError):
            llm_module.invoke_with_retry(always_rate_limited)

        failures = _llm_failures(caplog)
        assert [(f["will_retry"], f.get("retry_in_ms")) for f in failures] == [(True, 5000)] * 4 + [(False, None)]
        assert {(f["provider_status"], f["provider_error_code"]) for f in failures} == {(429, "rate_limit_exceeded")}


class TestRateLimitJitter:
    """Rate-limit waits get bounded, additive random jitter so parallel agents
    don't all retry at the same instant."""

    def test_retry_after_is_honored_and_jitter_only_adds(self, monkeypatch):
        error = RateLimitError("x", response=_fake_response(429, {"retry-after": "10"}), body=None)

        monkeypatch.setattr(llm_module, "_random", lambda: 0.0)
        assert llm_module._rate_limit_backoff_seconds(error, 0) == 11.0  # Retry-After + 1 s, as before
        monkeypatch.setattr(llm_module, "_random", lambda: 0.5)
        assert llm_module._rate_limit_backoff_seconds(error, 0) == 11.0 + 0.5 * llm_module.RATE_LIMIT_JITTER_SECONDS

    def test_parallel_agents_with_the_same_retry_after_wait_different_times(self, monkeypatch):
        error = RateLimitError("x", response=_fake_response(429, {"retry-after": "10"}), body=None)
        draws = iter([0.1, 0.9])
        monkeypatch.setattr(llm_module, "_random", lambda: next(draws))

        first, second = (llm_module._rate_limit_backoff_seconds(error, 0) for _ in range(2))

        assert first != second
        assert 11.0 <= min(first, second) and max(first, second) <= 11.0 + llm_module.RATE_LIMIT_JITTER_SECONDS

    @pytest.mark.parametrize(
        ("headers", "attempt", "base"),
        [
            ({"retry-after": "3600"}, 0, 60.0),  # a long quota reset is still capped
            ({}, 0, 15.0),
            ({}, 10, 60.0),
            ({"retry-after": "soon"}, 1, 30.0),  # unparseable header: linear fallback
        ],
        ids=["capped-retry-after", "no-header", "no-header-capped", "bad-header"],
    )
    def test_wait_stays_within_the_cap_plus_jitter(self, monkeypatch, headers, attempt, base):
        monkeypatch.setattr(llm_module, "_random", lambda: 0.999999)
        error = RateLimitError("x", response=_fake_response(429, headers), body=None)

        delay = llm_module._rate_limit_backoff_seconds(error, attempt)

        assert base <= delay < base + llm_module.RATE_LIMIT_JITTER_SECONDS
        assert delay < llm_module.MAX_RATE_LIMIT_BACKOFF_SECONDS + llm_module.RATE_LIMIT_JITTER_SECONDS

    def test_retry_loop_sleeps_the_jittered_delay_and_stays_bounded(self, monkeypatch):
        slept: list[float] = []
        monkeypatch.setattr(llm_module.time, "sleep", slept.append)
        monkeypatch.setattr(llm_module, "_random", lambda: 0.5)
        calls = {"n": 0}

        def always_rate_limited():
            calls["n"] += 1
            raise RateLimitError("x", response=_fake_response(429, {"retry-after": "2"}), body=None)

        with pytest.raises(RateLimitError):
            llm_module._invoke_with_retry(always_rate_limited, max_attempts=5)

        assert calls["n"] == 5  # retry limit unchanged
        assert slept == [3.0 + 1.5] * 4  # Retry-After + 1 s + jitter, between attempts only

    def test_network_errors_keep_their_existing_backoff(self, monkeypatch):
        from groq import APITimeoutError

        slept: list[float] = []
        monkeypatch.setattr(llm_module.time, "sleep", slept.append)
        monkeypatch.setattr(llm_module, "_random", lambda: 0.5)

        def always_timing_out():
            raise APITimeoutError(request=_fake_response(500).request)

        with pytest.raises(APITimeoutError):
            llm_module._invoke_with_retry(always_timing_out, max_attempts=3)

        assert slept == [1.0, 2.0]

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
    # A safe, fixed description -- never the exception's own text.
    assert review.issues[0].issue == "Critic review failed: the LLM call failed."
    assert "simulated outage" not in review.issues[0].issue
    assert "simulated outage" not in result["execution_trace"][0]["action"]
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


def _groq_with_fake_http(max_tokens: int, response: dict):
    """A real ChatGroq whose HTTP calls are answered locally -- nothing reaches Groq."""
    import httpx as _httpx
    from langchain_groq import ChatGroq

    transport = _httpx.MockTransport(lambda request: _httpx.Response(200, json=response))
    return ChatGroq(
        model="test-model",
        api_key="test-key",
        max_tokens=max_tokens,
        callbacks=[llm_module._UsageLogger(max_tokens)],
        http_client=_httpx.Client(transport=transport),
    )


def _tool_call_completion(usage: dict | None, finish_reason: str = "tool_calls") -> dict:
    import json as _json

    arguments = {"domain": "Security", "recommendations": [SECRET], "reasoning": SECRET, "risks": [SECRET]}
    completion = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "AnalysisResult", "arguments": _json.dumps(arguments)},
                        }
                    ],
                },
            }
        ],
    }
    if usage is not None:
        completion["usage"] = usage
    return completion


def _usage_events(caplog) -> list[dict]:
    return [r.event_fields for r in caplog.records if getattr(r, "event_fields", {}).get("event") == "llm_call_finished"]


class TestTokenUsageLogging:
    """Each successful call logs its real token usage next to its max_tokens cap
    (Groq reserves the cap against the output-tokens-per-minute budget)."""

    def test_structured_call_logs_usage_cap_and_node(self, caplog):
        from graph.observability import timed_node
        from models.schemas import AnalysisResult

        usage = {
            "prompt_tokens": 812,
            "completion_tokens": 311,
            "total_tokens": 1123,
            "completion_tokens_details": {"reasoning_tokens": 120},
        }
        llm = _groq_with_fake_http(750, _tool_call_completion(usage))
        node = timed_node("security_agent", lambda state: {"r": llm_module.invoke_structured(llm, AnalysisResult, SECRET)})

        with caplog.at_level("INFO"):
            node({})

        (event,) = _usage_events(caplog)
        assert {k: event[k] for k in ("node", "max_tokens", "input_tokens", "output_tokens", "reasoning_tokens")} == {
            "node": "security_agent",
            "max_tokens": 750,
            "input_tokens": 812,
            "output_tokens": 311,
            "reasoning_tokens": 120,
        }
        assert event["finish_reason"] == "tool_calls"
        assert SECRET not in caplog.text  # counts only, never the prompt or the answer

    def test_answer_cut_off_at_the_cap_shows_finish_reason_length(self, caplog):
        from models.schemas import AnalysisResult

        usage = {"prompt_tokens": 900, "completion_tokens": 400, "total_tokens": 1300}
        llm = _groq_with_fake_http(400, _tool_call_completion(usage, finish_reason="length"))

        with caplog.at_level("INFO"):
            llm_module.invoke_structured(llm, AnalysisResult, "prompt")

        (event,) = _usage_events(caplog)
        assert (event["output_tokens"], event["max_tokens"], event["finish_reason"]) == (400, 400, "length")
        assert "reasoning_tokens" not in event  # not reported by this response, so left out
        assert "node" not in event  # called outside a graph node

    def test_missing_or_malformed_usage_is_left_out(self):
        from langchain_core.outputs import ChatGeneration, LLMResult
        from langchain_core.messages import AIMessage

        generation = ChatGeneration(message=AIMessage(content=""), generation_info={"finish_reason": "a b c"})
        response = LLMResult(
            generations=[[generation]],
            llm_output={"token_usage": {"prompt_tokens": "812", "completion_tokens": True, "completion_tokens_details": 5}},
        )

        assert llm_module._usage_fields(response) == {
            "input_tokens": None,
            "output_tokens": None,
            "reasoning_tokens": None,
            "finish_reason": None,
        }
        assert llm_module._usage_fields(LLMResult(generations=[], llm_output=None))["output_tokens"] is None

    def test_usage_logging_never_breaks_a_call(self):
        llm_module._UsageLogger(750).on_llm_end(object())  # not an LLMResult: must not raise

    def test_get_llm_attaches_the_usage_logger_with_its_cap(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        monkeypatch.setenv("LLM_PROVIDER", "groq")

        llm = llm_module.get_llm(max_tokens=420)

        (usage_logger,) = [cb for cb in llm.callbacks if isinstance(cb, llm_module._UsageLogger)]
        assert usage_logger.max_tokens == 420

    def test_failure_log_names_the_node_it_happened_in(self, caplog):
        from graph.observability import timed_node

        error = APIStatusError("x", response=_fake_response(500), body=None)

        def failing_node(state):
            def provider_error():
                raise error

            llm_module.invoke_with_retry(provider_error)

        with caplog.at_level("WARNING"), pytest.raises(APIStatusError):
            timed_node("cost_agent", failing_node)({})

        (failure,) = _llm_failures(caplog)
        assert failure["node"] == "cost_agent"


def _gemini_error(error_type_name: str, code: int, status: str, details: list | None = None) -> BaseException:
    """A Gemini error as LangChain raises it: a classified type raised *from* the SDK error."""
    from google.genai.errors import ClientError, ServerError
    from langchain_google_genai import chat_models as gemini

    body = {"error": {"code": code, "message": SECRET, "status": status, "details": details or []}}
    sdk_error = (ServerError if code >= 500 else ClientError)(code, body)
    if code >= 500:
        error = gemini.GoogleAPIError(code=code, response_json=body)
    else:
        error = getattr(gemini, error_type_name)(f"Error calling model ({status}): {SECRET}")
    try:
        raise error from sdk_error
    except BaseException as raised:
        return raised


class TestGeminiProvider:
    """LLM_PROVIDER=gemini builds a Gemini chat model, and Gemini's errors get
    the same retry rules and job classification as Groq's. No real API calls."""

    def test_get_llm_builds_gemini_with_cap_low_thinking_and_usage_logger(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
        monkeypatch.delenv("GEMINI_THINKING_LEVEL", raising=False)

        llm = llm_module.get_llm(temperature=0.1, max_tokens=420)

        assert type(llm).__name__ == "ChatGoogleGenerativeAI"
        assert (llm.model, llm.max_output_tokens, llm.temperature) == ("gemini-test-model", 420, 0.1)
        assert llm.reasoning_effort == "low"  # thinking counts toward max_tokens, so keep it light
        assert llm.max_retries == 2
        assert [cb.max_tokens for cb in llm.callbacks if isinstance(cb, llm_module._UsageLogger)] == [420]

    def test_thinking_level_default_leaves_the_models_own_setting(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("GEMINI_THINKING_LEVEL", "default")

        assert llm_module.get_llm().reasoning_effort is None

    def test_missing_gemini_key_is_a_configuration_error(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "  ")

        with pytest.raises(llm_module.MissingAPIKeyError):
            llm_module.get_llm()

    def test_rate_limit_honors_gemini_retry_delay_and_is_logged_with_its_status(self, monkeypatch, caplog):
        slept: list[float] = []
        monkeypatch.setattr(llm_module.time, "sleep", slept.append)
        monkeypatch.setattr(llm_module, "_random", lambda: 0.0)
        retry_info = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "17s"}]
        error = _gemini_error("GoogleRateLimitError", 429, "RESOURCE_EXHAUSTED", retry_info)
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise error
            return "ok"

        with caplog.at_level("WARNING"):
            assert llm_module._invoke_with_retry(flaky) == "ok"

        assert slept == [18.0]  # retryDelay + 1 s, like Retry-After
        (failure,) = _llm_failures(caplog)
        assert (failure["provider_status"], failure["provider_error_code"]) == (429, "RESOURCE_EXHAUSTED")
        assert SECRET not in caplog.text

    def test_overloaded_model_503_is_retried(self, monkeypatch):
        monkeypatch.setattr(llm_module.time, "sleep", lambda seconds: None)
        error = _gemini_error("GoogleAPIError", 503, "UNAVAILABLE")
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise error
            return "ok"

        assert llm_module._invoke_with_retry(flaky) == "ok"
        assert calls["n"] == 3

    @pytest.mark.parametrize(
        ("type_name", "code", "status"),
        [
            ("GoogleInvalidRequestError", 400, "INVALID_ARGUMENT"),
            ("GoogleAuthenticationError", 401, "UNAUTHENTICATED"),
            ("GooglePermissionDeniedError", 403, "PERMISSION_DENIED"),
            ("GoogleModelNotFoundError", 404, "NOT_FOUND"),
        ],
        ids=["bad-request", "bad-key", "no-permission", "unknown-model"],
    )
    def test_permanent_errors_are_not_retried(self, monkeypatch, type_name, code, status):
        monkeypatch.setattr(llm_module.time, "sleep", lambda seconds: pytest.fail("must not wait to retry"))
        error = _gemini_error(type_name, code, status)
        calls = {"n": 0}

        def failing():
            calls["n"] += 1
            raise error

        with pytest.raises(type(error)):
            llm_module._invoke_with_retry(failing)
        assert calls["n"] == 1

    def test_network_timeout_is_retried(self, monkeypatch):
        import httpx as _httpx

        monkeypatch.setattr(llm_module.time, "sleep", lambda seconds: None)
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise _httpx.ReadTimeout("timed out")
            return "ok"

        assert llm_module._invoke_with_retry(flaky) == "ok"

    def test_invalid_json_answer_gets_the_corrective_retry(self):
        from langchain_core.exceptions import OutputParserException

        class _FlakyJsonLLM(_FailingStructuredLLM):
            def __init__(self):
                self.calls = 0
                self.prompts: list[str] = []

            def invoke(self, prompt):
                self.calls += 1
                self.prompts.append(prompt)
                if self.calls == 1:
                    raise OutputParserException("Invalid json output: {\"domain\": \"Sec" + SECRET * 50)
                return Requirements.model_construct()

        flaky = _FlakyJsonLLM()

        llm_module.invoke_structured(flaky, Requirements, "prompt")

        assert flaky.calls == 2
        assert "Invalid json output" in flaky.prompts[1]
        assert len(flaky.prompts[1]) < len("prompt") + 1000  # the cut-off answer isn't pasted back in

    def test_usage_is_read_from_gemini_usage_metadata(self):
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, LLMResult

        message = AIMessage(
            content="",
            usage_metadata={
                "input_tokens": 49,
                "output_tokens": 154,
                "total_tokens": 203,
                "output_token_details": {"reasoning": 40},
            },
        )
        response = LLMResult(
            generations=[[ChatGeneration(message=message, generation_info={"finish_reason": "MAX_TOKENS"})]],
            llm_output=None,
        )

        assert llm_module._usage_fields(response) == {
            "input_tokens": 49,
            "output_tokens": 154,
            "reasoning_tokens": 40,
            "finish_reason": "MAX_TOKENS",
        }


# ---------------------------------------------------------------------------
# Per-call accounting: one llm_call_summary per logical call
# ---------------------------------------------------------------------------

USAGE = {"prompt_tokens": 800, "completion_tokens": 300, "total_tokens": 1100, "completion_tokens_details": {"reasoning_tokens": 90}}


def _summaries(caplog) -> list[dict]:
    return [r.event_fields for r in caplog.records if getattr(r, "event_fields", {}).get("event") == "llm_call_summary"]


@pytest.fixture
def fake_time(monkeypatch):
    """A fake monotonic clock that only moves when something sleeps.

    Both the Groq SDK's retry sleeps and our own retry sleeps go through
    time.sleep, so every measured wait is exact and nothing really waits.
    """
    from graph import observability

    clock = {"t": 1000.0}
    sleeps: list[float] = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["t"] += seconds

    monkeypatch.setattr(observability, "_clock", lambda: clock["t"])
    monkeypatch.setattr("time.sleep", fake_sleep)
    monkeypatch.setattr(llm_module, "_random", lambda: 0.0)
    return sleeps


def _groq_scripted(*steps, max_tokens: int = 750):
    """A real ChatGroq (real SDK retry logic) behind the instrumented client.

    Each step answers one HTTP request: an httpx.Response, or an exception
    to raise as if the network failed. Requests seen are recorded.
    """
    from langchain_groq import ChatGroq

    remaining = list(steps)
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        step = remaining.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    llm = ChatGroq(
        model="test-model",
        api_key="test-key-SHOULD-NOT-BE-LOGGED",
        max_tokens=max_tokens,
        callbacks=[llm_module._UsageLogger(max_tokens, model="test-model", provider="groq")],
        http_client=llm_module._instrumented_http_client(httpx.MockTransport(handler)),
    )
    return llm, seen


def _ok():
    return httpx.Response(200, json=_tool_call_completion(USAGE))


def _rate_limited():
    body = {"error": {"message": SECRET, "type": "tokens", "code": "rate_limit_exceeded"}}
    return httpx.Response(429, headers={"retry-after": "2"}, json=body)


def _tool_use_failed():
    body = {"error": {"message": "bad", "type": "invalid_request_error", "code": "tool_use_failed", "failed_generation": SECRET}}
    return httpx.Response(400, json=body)


class TestCallSummary:
    """Every logical LLM call logs exactly one llm_call_summary with real
    counts: HTTP requests, SDK retries (read from the SDK's retry-count
    header), application and tool_use retries, separate waits, tokens."""

    def _run(self, llm, caplog):
        from models.schemas import AnalysisResult

        with caplog.at_level("INFO"):
            return llm_module.invoke_structured(llm, AnalysisResult, SECRET)

    def test_first_try_success(self, fake_time, caplog):
        llm, _ = _groq_scripted(_ok())

        self._run(llm, caplog)

        (summary,) = _summaries(caplog)
        assert summary | {"call_id": None} == {
            "event": "llm_call_summary",
            "call_id": None,
            "call_type": "structured",
            "schema": "AnalysisResult",
            "provider": "groq",
            "model": "test-model",
            "max_tokens": 750,
            "outcome": "success",
            "total_ms": 0,
            "http_requests": 1,
            "sdk_retries": 0,
            "sdk_retry_wait_ms": 0,
            "app_retries": 0,
            "app_retry_wait_ms": 0,
            "tool_use_retries": 0,
            "llm_responses": 1,
            "input_tokens": 800,
            "output_tokens": 300,
            "reasoning_tokens": 90,
            "finish_reason": "tool_calls",
            "usage_available": "true",
        }
        (finished,) = _usage_events(caplog)
        assert finished["call_id"] == summary["call_id"]
        assert (finished["model"], finished["provider"], finished["request_ms"]) == ("test-model", "groq", 0)

    def test_sdk_retry_on_429_is_counted_from_the_retry_header(self, fake_time, caplog):
        llm, seen = _groq_scripted(_rate_limited(), _ok())

        self._run(llm, caplog)

        assert [r.headers["x-stainless-retry-count"] for r in seen] == ["0", "1"]
        (summary,) = _summaries(caplog)
        assert (summary["http_requests"], summary["sdk_retries"], summary["sdk_retry_wait_ms"]) == (2, 1, 2000)
        assert (summary["app_retries"], summary["app_retry_wait_ms"]) == (0, 0)
        assert summary["total_ms"] == 2000
        assert summary["usage_available"] == "true"  # a 429 is rejected before generating anything
        assert not _llm_failures(caplog)  # the SDK retried it; our code never saw an error

    @pytest.mark.parametrize(
        "network_error",
        [httpx.ReadTimeout("t"), httpx.ConnectError("c")],
        ids=["timeout", "connection-error"],
    )
    def test_sdk_retry_after_timeout_or_connection_error(self, fake_time, caplog, network_error):
        llm, seen = _groq_scripted(network_error, _ok())

        self._run(llm, caplog)

        assert [r.headers["x-stainless-retry-count"] for r in seen] == ["0", "1"]
        (summary,) = _summaries(caplog)
        assert (summary["http_requests"], summary["sdk_retries"]) == (2, 1)
        # No response, so the SDK picks its own backoff; the measured wait is exactly what it slept.
        assert summary["sdk_retry_wait_ms"] == int(round(sum(fake_time) * 1000)) > 0
        assert summary["usage_available"] == "partial"  # the failed attempt may have generated tokens

    def test_sdk_and_application_retries_and_waits_are_kept_separate(self, fake_time, caplog):
        # The SDK tries 3 times (1 + max_retries=2), then gives up with RateLimitError;
        # our retry loop waits (Retry-After 2 + 1, jitter 0) and the next SDK request succeeds.
        llm, seen = _groq_scripted(_rate_limited(), _rate_limited(), _rate_limited(), _ok())

        self._run(llm, caplog)

        assert [r.headers["x-stainless-retry-count"] for r in seen] == ["0", "1", "2", "0"]
        (summary,) = _summaries(caplog)
        assert summary["http_requests"] == 4
        assert (summary["sdk_retries"], summary["sdk_retry_wait_ms"]) == (2, 4000)
        assert (summary["app_retries"], summary["app_retry_wait_ms"]) == (1, 3000)
        assert summary["total_ms"] == 7000
        (failure,) = _llm_failures(caplog)
        assert failure["call_id"] == summary["call_id"]
        assert (failure["provider_status"], failure["model"], failure["max_tokens"]) == (429, "test-model", 750)
        assert (failure["sdk_retries"], failure["usage_available"]) == (2, False)

    def test_tool_use_retry_is_counted_and_usage_marked_partial(self, fake_time, caplog):
        llm, _ = _groq_scripted(_tool_use_failed(), _ok())

        self._run(llm, caplog)

        (summary,) = _summaries(caplog)
        assert (summary["tool_use_retries"], summary["http_requests"], summary["sdk_retries"]) == (1, 2, 0)
        assert (summary["outcome"], summary["llm_responses"], summary["output_tokens"]) == ("success", 1, 300)
        # Groq reports no usage for the rejected generation, so the totals may be low.
        assert summary["usage_available"] == "partial"
        (failure,) = _llm_failures(caplog)
        assert (failure["provider_error_code"], failure["call_id"]) == ("tool_use_failed", summary["call_id"])

    def test_provider_error_summary_reports_the_root_error(self, fake_time, caplog):
        llm, _ = _groq_scripted(_tool_use_failed(), _tool_use_failed(), _tool_use_failed())

        with pytest.raises(llm_module.LLMInvocationError):
            self._run(llm, caplog)

        (summary,) = _summaries(caplog)
        assert summary["outcome"] == "failure"
        assert (summary["error_type"], summary["provider_status"], summary["provider_error_code"]) == (
            "BadRequestError",
            400,
            "tool_use_failed",
        )
        assert (summary["tool_use_retries"], summary["llm_responses"], summary["usage_available"]) == (2, 0, "false")
        assert "input_tokens" not in summary  # nothing reported, nothing estimated

    def test_parsing_failure_logs_one_summary(self, caplog):
        from langchain_core.exceptions import OutputParserException

        llm = _FailingStructuredLLM(OutputParserException("not json"))

        with caplog.at_level("INFO"), pytest.raises(llm_module.LLMInvocationError):
            llm_module.invoke_structured(llm, Requirements, SECRET)

        (summary,) = _summaries(caplog)
        assert (summary["outcome"], summary["error_type"], summary["tool_use_retries"]) == (
            "failure",
            "OutputParserException",
            2,
        )
        # A stand-in model has no instrumented HTTP client (like Gemini): not measured, so not guessed.
        assert (summary["http_requests"], summary["sdk_retries"], summary["sdk_retry_wait_ms"]) == ("unavailable",) * 3

    @pytest.mark.parametrize("error", [ValueError("boom"), KeyboardInterrupt()], ids=["exception", "base-exception"])
    def test_unexpected_errors_log_one_summary(self, caplog, error):
        llm = _FailingStructuredLLM(error)

        with caplog.at_level("INFO"), pytest.raises((llm_module.LLMInvocationError, KeyboardInterrupt)):
            llm_module.invoke_structured(llm, Requirements, "prompt")

        (summary,) = _summaries(caplog)
        assert (summary["outcome"], summary["error_type"]) == ("failure", type(error).__name__)

    def test_invoke_with_retry_logs_one_summary(self, fake_time, caplog):
        llm, _ = _groq_scripted(_rate_limited(), _ok())

        with caplog.at_level("INFO"):
            llm_module.invoke_with_retry(lambda: llm.invoke("hi"))

        (summary,) = _summaries(caplog)
        assert (summary["call_type"], summary["sdk_retries"], summary["outcome"]) == ("invoke", 1, "success")
        assert "schema" not in summary

    def test_nested_calls_log_only_the_outer_summary(self, caplog):
        with caplog.at_level("INFO"), llm_module._LLMCall("invoke") as outer:
            with llm_module._LLMCall("structured", "X") as inner:
                assert inner is outer

        assert len(_summaries(caplog)) == 1

    def test_nothing_sensitive_is_logged(self, fake_time, caplog):
        llm, _ = _groq_scripted(_rate_limited(), _rate_limited(), _rate_limited(), _tool_use_failed(), _ok())

        self._run(llm, caplog)

        assert SECRET not in caplog.text  # neither the prompt nor any response body
        assert "SHOULD-NOT-BE-LOGGED" not in caplog.text  # nor the API key
        ours = "\n".join(r.getMessage() for r in caplog.records if r.name == "agents.llm")
        assert "api.groq.com" not in ours  # our events carry no URLs (httpx's own INFO line already did)

    def test_sdk_counts_are_unavailable_without_the_retry_header(self):
        stats = llm_module._CallStats("structured", None)
        first = stats.start_http_attempt(0)
        first.finish()
        stats.start_http_attempt(None).finish()

        assert stats.sdk_fields() == {"http_requests": 2, "sdk_retries": "unavailable", "sdk_retry_wait_ms": "unavailable"}

    def test_sdk_wait_is_unavailable_when_an_attempt_end_was_not_seen(self):
        stats = llm_module._CallStats("structured", None)
        stats.start_http_attempt(0)  # never finished
        stats.start_http_attempt(1).finish()

        assert stats.sdk_fields() == {"http_requests": 2, "sdk_retries": 1, "sdk_retry_wait_ms": "unavailable"}

    def test_transport_outside_a_call_only_passes_through(self):
        client = llm_module._instrumented_http_client(httpx.MockTransport(lambda r: httpx.Response(204)))

        assert client.get("https://example.invalid/").status_code == 204

    def test_get_llm_wires_the_counting_transport_and_model(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        monkeypatch.setenv("LLM_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_MODEL", "some-model")

        llm = llm_module.get_llm(max_tokens=420)

        assert isinstance(llm.http_client._transport, llm_module._CountingTransport)
        assert llm.max_retries == 2 and llm.request_timeout == llm_module.REQUEST_TIMEOUT_SECONDS  # unchanged
        (usage_logger,) = [cb for cb in llm.callbacks if isinstance(cb, llm_module._UsageLogger)]
        assert (usage_logger.model, usage_logger.provider, usage_logger.max_tokens) == ("some-model", "groq", 420)


# ---------------------------------------------------------------------------
# Output size limits in the critic and report prompts
# ---------------------------------------------------------------------------


def _capture_prompt(monkeypatch, result) -> list[str]:
    prompts: list[str] = []

    def capturing_invoke_structured(llm, schema, prompt):
        prompts.append(prompt)
        return result

    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
    monkeypatch.setattr(llm_module, "invoke_structured", capturing_invoke_structured)
    return prompts


def test_critic_prompt_sets_hard_item_limits(monkeypatch):
    prompts = _capture_prompt(monkeypatch, make_critic_review(approved=True))

    critic_agent.run(_base_state())

    (prompt,) = prompts
    assert "issues: at most 4" in prompt
    assert "required_changes: at most 4" in prompt
    assert "strengths: at most 3" in prompt
    assert "at most 15 words" in prompt


def test_report_prompt_sets_hard_size_limits_and_asks_for_specifics(monkeypatch):
    from .conftest import make_final_report

    prompts = _capture_prompt(monkeypatch, make_final_report())

    report_agent.run(_base_state(critic_review=make_critic_review(approved=True)))

    (prompt,) = prompts
    assert "Every prose field: 1-2 sentences, at most 35 words" in prompt
    assert "at most 3 items each, at most 12 words per item" in prompt
    assert "name the actual AWS services, numbers" in prompt  # keep technical detail
    assert "3-5 sentences" not in prompt and "2-4 sentences" not in prompt  # the old, oversized asks


def test_successful_critic_and_report_are_unchanged(monkeypatch):
    from .conftest import make_report_synthesis

    review = make_critic_review(approved=True)
    _capture_prompt(monkeypatch, review)
    assert critic_agent.run(_base_state())["critic_review"] is review

    synthesis = make_report_synthesis()
    _capture_prompt(monkeypatch, synthesis)
    report = report_agent.run(_base_state(critic_review=review))["final_report"]
    # Every synthesized field is passed through untouched; the rest are built from the data.
    for name in type(synthesis).model_fields:
        assert getattr(report, name) == getattr(synthesis, name)


# ---------------------------------------------------------------------------
# Safe error handling: provider text never reaches traces, issues or prompts
# ---------------------------------------------------------------------------

FAILED_GENERATION = "<tool_call><function=CriticReview><parameter=issues>LEAKED-MODEL-OUTPUT"


def _tool_use_failed_error() -> APIStatusError:
    body = {
        "error": {
            "message": "Failed to call a function. Please adjust your prompt.",
            "type": "invalid_request_error",
            "code": "tool_use_failed",
            "failed_generation": FAILED_GENERATION,
        }
    }
    # Like the real SDK: the exception's text embeds the whole body.
    return APIStatusError(f"Error code: 400 - {body}", response=_fake_response(400), body=body)


def _real_invoke_with_failing_llm(monkeypatch, error: BaseException):
    """Agents call the real invoke_structured; the model always fails with `error`."""
    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: _FailingStructuredLLM(error))


class TestSafeErrorHandling:
    @pytest.mark.parametrize(
        "error, reason",
        [
            (_tool_use_failed_error(), llm_module.FAILURE_INVALID_OUTPUT),
            (RateLimitError(SECRET, response=_fake_response(429), body=None), llm_module.FAILURE_RATE_LIMITED),
            (APIStatusError(SECRET, response=_fake_response(413), body=None), llm_module.FAILURE_RATE_LIMITED),
            (APIStatusError(SECRET, response=_fake_response(401), body=None), llm_module.FAILURE_PROVIDER_ERROR),
            (httpx.ReadTimeout(SECRET), llm_module.FAILURE_TIMEOUT),
            (ValueError(SECRET), llm_module.FAILURE_UNKNOWN),
        ],
        ids=["tool-use-failed", "rate-limit", "413", "auth", "timeout", "unexpected"],
    )
    def test_llm_invocation_error_message_is_a_fixed_reason(self, monkeypatch, error, reason):
        monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)

        with pytest.raises(llm_module.LLMInvocationError) as raised:
            llm_module.invoke_structured(_FailingStructuredLLM(error), Requirements, "prompt")

        exc = raised.value
        assert exc.reason == reason
        assert str(exc) == f"LLM call failed while producing Requirements: {reason}"
        assert SECRET not in str(exc) and FAILED_GENERATION not in str(exc)
        assert exc.__cause__ is error  # kept for classification and DEBUG tracebacks
        assert llm_module.safe_failure_message(exc) == f"{reason} (ref {exc.call_id})"

    def test_parse_failure_is_invalid_output(self):
        from langchain_core.exceptions import OutputParserException

        with pytest.raises(llm_module.LLMInvocationError) as raised:
            llm_module.invoke_structured(_FailingStructuredLLM(OutputParserException(SECRET)), Requirements, "p")

        assert raised.value.reason == llm_module.FAILURE_INVALID_OUTPUT
        assert SECRET not in str(raised.value)

    def test_safe_message_never_uses_exception_text(self):
        assert llm_module.safe_failure_message(llm_module.LLMInvocationError(SECRET)) == "the LLM call failed"
        assert llm_module.safe_failure_message(RuntimeError(SECRET)) == "the LLM call failed"

    def test_corrective_retry_prompt_never_contains_the_failed_generation(self):
        llm = _FailingStructuredLLM(_tool_use_failed_error())
        prompts: list[str] = []
        original_invoke = llm.invoke
        llm.invoke = lambda prompt: (prompts.append(prompt), original_invoke(prompt))[1]

        with pytest.raises(llm_module.LLMInvocationError):
            llm_module.invoke_structured(llm, Requirements, "base prompt")

        assert len(prompts) == 3  # retry count unchanged
        assert all(FAILED_GENERATION not in p for p in prompts)
        assert "Failed to call a function" in prompts[1]  # the short validation message is still fed back
        # A provider error without a parsed body: its text (which embeds the body) is never used.
        bare = APIStatusError(f"tool_use_failed {FAILED_GENERATION}", response=_fake_response(400), body=None)
        assert FAILED_GENERATION not in llm_module._tool_call_reinforcement(bare)

    def test_critic_fallback_issue_trace_and_revision_prompt_are_safe(self, monkeypatch, caplog):
        _real_invoke_with_failing_llm(monkeypatch, _tool_use_failed_error())

        from graph.observability import timed_node

        with caplog.at_level("INFO"):
            result = timed_node("architecture_critic", critic_agent.run)(_base_state())

        review = result["critic_review"]
        (summary,) = _summaries(caplog)
        expected = f"{llm_module.FAILURE_INVALID_OUTPUT} (ref {summary['call_id']})"
        assert review.issues[0].issue == f"Critic review failed: {expected}."
        assert expected in result["execution_trace"][0]["action"]
        stored = review.model_dump_json() + str(result["execution_trace"])
        assert FAILED_GENERATION not in stored and "Error code" not in stored
        # Internal logs keep the diagnostics, matched by the same call id.
        assert (summary["node"], summary["provider_status"], summary["provider_error_code"]) == (
            "architecture_critic",
            400,
            "tool_use_failed",
        )
        assert FAILED_GENERATION not in caplog.text

        # The fallback review feeds the revision prompt: still nothing leaked.
        prompts = _capture_prompt(monkeypatch, make_architecture())
        revision_agent.run(_base_state(critic_review=review, revision_count=0))
        assert FAILED_GENERATION not in prompts[0]

    def test_revision_and_report_fallback_traces_are_safe(self, monkeypatch):
        _real_invoke_with_failing_llm(monkeypatch, _tool_use_failed_error())

        revision = revision_agent.run(_base_state(critic_review=make_critic_review(approved=False)))
        report = report_agent.run(_base_state(critic_review=make_critic_review(approved=True)))

        for result in (revision, report):
            action = result["execution_trace"][0]["action"]
            assert llm_module.FAILURE_INVALID_OUTPUT in action and "(ref " in action
            assert FAILED_GENERATION not in action and "Error code" not in action
        assert FAILED_GENERATION not in report["final_report"].model_dump_json()

    def test_workflow_error_keeps_only_the_exception_type(self):
        from graph.workflow import _safe_workflow_error

        raw = _tool_use_failed_error()
        assert _safe_workflow_error(raw) == "ArchonAI workflow failed: APIStatusError"
        wrapped = llm_module.LLMInvocationError("LLM call failed while producing X: the LLM call failed")
        assert _safe_workflow_error(wrapped).endswith("the LLM call failed")

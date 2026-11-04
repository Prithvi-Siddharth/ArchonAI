"""Specialist output limits and the shorter-answer retry correction.

The specialist analyses (Compute, Database, Networking, Security,
Reliability) share one block of hard output limits, so their answers fit
well under the 750-token cap. When a structured call is rejected with
tool_use_failed, the corrective retry asks for a substantially shorter
answer -- without changing the retry count, the handling of other errors,
or what gets logged. No live LLM calls.
"""

from __future__ import annotations

import pytest
from groq import APIStatusError, RateLimitError

from agents import compute, database, networking, reliability, security
from agents import llm as llm_module
from agents.specialist_prompt import SPECIALIST_OUTPUT_LIMITS
from models.schemas import AnalysisResult, Architecture, Requirements

from .conftest import make_analysis
from .test_resilience import (
    FAILED_GENERATION,
    _base_state,
    _fake_response,
    _FailingStructuredLLM,
    _llm_failures,
    _summaries,
    _tool_use_failed_error,
)

SPECIALISTS = {
    "Compute": compute,
    "Database": database,
    "Networking": networking,
    "Security": security,
    "Reliability": reliability,
}

LIMIT_LINES = (
    "STRICT limits, not suggestions",
    "recommendations: at most 4 items. Each item at most 15 words.",
    "risks: at most 3 items. Each item at most 15 words.",
    "reasoning: at most 2 sentences and at most 50 words in total.",
    "most important, actionable recommendations",
    "Do not add items just to reach the maximum",
    "matching the AnalysisResult schema exactly",
)


def _capture_specialist_call(monkeypatch) -> list[tuple[type, str]]:
    calls: list[tuple[type, str]] = []

    def capturing_invoke_structured(llm, schema, prompt):
        calls.append((schema, prompt))
        return make_analysis("placeholder")

    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
    monkeypatch.setattr(llm_module, "invoke_structured", capturing_invoke_structured)
    return calls


class _RecordingFailingLLM(_FailingStructuredLLM):
    """Records every prompt it is sent, then fails like _FailingStructuredLLM."""

    def __init__(self, *errors):
        super().__init__(*errors)
        self.prompts: list[str] = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return super().invoke(prompt)


class _FailThenSucceedLLM(_RecordingFailingLLM):
    def __init__(self, error, result):
        super().__init__(error)
        self._result = result

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            raise self._errors[0]
        return self._result


# ---------------------------------------------------------------------------
# 1-2. The shared prompt block, and every specialist receives it
# ---------------------------------------------------------------------------


def test_shared_block_contains_every_limit():
    for line in LIMIT_LINES:
        assert line in SPECIALIST_OUTPUT_LIMITS
    assert "{" not in SPECIALIST_OUTPUT_LIMITS  # safe inside str.format templates


@pytest.mark.parametrize("domain", SPECIALISTS)
def test_every_specialist_prompt_ends_with_the_shared_limits(monkeypatch, domain):
    calls = _capture_specialist_call(monkeypatch)

    result = SPECIALISTS[domain].run(_base_state())

    ((schema, prompt),) = calls
    assert schema is AnalysisResult
    assert prompt.endswith(SPECIALIST_OUTPUT_LIMITS)
    assert prompt.count("at most 4 items") == 1  # included once, not duplicated
    # The old, soft wording is gone; the agent's own focus list is kept.
    assert "short bullet phrases" not in prompt and "2-3 sentences" not in prompt
    assert "Specifically address:" in prompt
    # The requirements and architecture are still filled in.
    assert "{requirements}" not in prompt and "{architecture}" not in prompt
    assert result[f"{domain.lower()}_analysis"].domain == domain


def test_other_agents_do_not_get_the_specialist_limits():
    from agents import cost, critic, report, revision

    for module in (cost, critic, report, revision):
        assert SPECIALIST_OUTPUT_LIMITS not in module.PROMPT_TEMPLATE


# ---------------------------------------------------------------------------
# 3. The retry correction asks for a shorter answer
# ---------------------------------------------------------------------------


def test_analysis_retry_asks_for_fewer_and_shorter_items():
    text = llm_module._tool_call_reinforcement(_tool_use_failed_error(), AnalysisResult)

    assert "previous attempt was rejected" in text
    assert "substantially shorter" in text
    assert "fewer recommendations and fewer risks" in text
    assert "make every item shorter" in text
    assert "reasoning to one or two brief sentences" in text
    assert "Follow the AnalysisResult schema exactly" in text
    assert "valid structured output" in text
    assert "Failed to call a function" in text  # Groq's short message is still fed back
    assert FAILED_GENERATION not in text


@pytest.mark.parametrize("schema", [Architecture, Requirements])
def test_other_schemas_are_told_to_shorten_without_dropping_items(schema):
    text = llm_module._tool_call_reinforcement(_tool_use_failed_error(), schema)

    assert "substantially shorter" in text
    assert "keep the same items" in text
    assert "fewer" not in text  # e.g. never "fewer services" for an Architecture
    assert f"Follow the {schema.__name__} schema exactly" in text


def test_retry_prompts_are_the_original_plus_the_shorter_correction():
    llm = _RecordingFailingLLM(_tool_use_failed_error())

    with pytest.raises(llm_module.LLMInvocationError):
        llm_module.invoke_structured(llm, AnalysisResult, "base prompt")

    first, *retries = llm.prompts
    assert first == "base prompt"  # the first attempt is unchanged
    for retry in retries:
        assert retry.startswith("base prompt\n\nIMPORTANT:")
        assert "fewer recommendations and fewer risks" in retry
        assert retry.count("IMPORTANT:") == 1  # corrections never pile up
        assert FAILED_GENERATION not in retry


# ---------------------------------------------------------------------------
# 4. Retry count unchanged
# ---------------------------------------------------------------------------


def test_tool_use_failures_still_make_exactly_three_attempts(caplog):
    llm = _RecordingFailingLLM(_tool_use_failed_error())

    with caplog.at_level("WARNING"), pytest.raises(llm_module.LLMInvocationError) as raised:
        llm_module.invoke_structured(llm, AnalysisResult, "prompt")

    assert len(llm.prompts) == 3
    assert raised.value.reason == llm_module.FAILURE_INVALID_OUTPUT
    assert [f["will_retry"] for f in _llm_failures(caplog)] == [True, True, False]


def test_a_successful_retry_returns_the_result_after_one_correction():
    expected = make_analysis("Networking")
    llm = _FailThenSucceedLLM(_tool_use_failed_error(), expected)

    assert llm_module.invoke_structured(llm, AnalysisResult, "prompt") is expected
    assert len(llm.prompts) == 2
    assert "fewer recommendations" in llm.prompts[1]


# ---------------------------------------------------------------------------
# 5. Non-tool_use errors are handled exactly as before
# ---------------------------------------------------------------------------


def test_permanent_errors_are_not_retried_and_get_no_correction(caplog):
    error = APIStatusError(
        "bad key",
        response=_fake_response(401),
        body={"error": {"message": "bad key", "code": "invalid_api_key"}},
    )
    llm = _RecordingFailingLLM(error)

    with caplog.at_level("WARNING"), pytest.raises(llm_module.LLMInvocationError) as raised:
        llm_module.invoke_structured(llm, AnalysisResult, "prompt")

    assert llm.prompts == ["prompt"]
    assert raised.value.__cause__ is error
    (failure,) = _llm_failures(caplog)
    assert failure["will_retry"] is False and failure["provider_status"] == 401


def test_rate_limits_keep_their_backoff_and_never_get_the_correction(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(llm_module.time, "sleep", slept.append)
    error = RateLimitError("slow down", response=_fake_response(429, {"retry-after": "1"}), body=None)
    llm = _RecordingFailingLLM(error)

    with pytest.raises(llm_module.LLMInvocationError) as raised:
        llm_module.invoke_structured(llm, AnalysisResult, "prompt")

    assert raised.value.reason == llm_module.FAILURE_RATE_LIMITED
    assert len(llm.prompts) == 5  # _invoke_with_retry's 5 attempts, unchanged
    assert all(p == "prompt" for p in llm.prompts)
    assert len(slept) == 4


# ---------------------------------------------------------------------------
# 6. AnalysisResult schema unchanged
# ---------------------------------------------------------------------------


def test_analysis_result_schema_is_unchanged():
    assert list(AnalysisResult.model_fields) == ["domain", "recommendations", "reasoning", "risks"]
    valid = AnalysisResult(domain="Networking", recommendations=["Use private subnets"], reasoning="Short.")
    assert valid.risks == []
    with pytest.raises(Exception):
        AnalysisResult(domain="Networking", reasoning="missing recommendations")
    # Older, longer stored analyses still load: the limits are prompt-only.
    long_one = AnalysisResult(
        domain="Networking", recommendations=[f"item {i}" for i in range(12)], reasoning="x" * 600, risks=["r"] * 8
    )
    assert len(long_one.recommendations) == 12


# ---------------------------------------------------------------------------
# 7. Logging and observability unchanged
# ---------------------------------------------------------------------------


def test_call_summary_fields_and_safety_are_unchanged(caplog):
    with caplog.at_level("INFO"), pytest.raises(llm_module.LLMInvocationError):
        llm_module.invoke_structured(_RecordingFailingLLM(_tool_use_failed_error()), AnalysisResult, "prompt")

    (summary,) = _summaries(caplog)
    assert summary["schema"] == "AnalysisResult"
    assert summary["tool_use_retries"] == 2
    assert summary["outcome"] == "failure"
    assert summary["provider_error_code"] == "tool_use_failed"
    assert [f["call_attempt"] for f in _llm_failures(caplog)] == [1, 2, 3]
    # The correction text and the failed generation are never logged.
    assert "substantially shorter" not in caplog.text
    assert FAILED_GENERATION not in caplog.text

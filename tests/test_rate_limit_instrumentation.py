"""Rate-limit and failed-generation instrumentation (additive, numbers only).

Every HTTP 429/413 -- including the ones the Groq SDK retries by itself and
never raises -- logs one `llm_http_rate_limited` event with the quota facts
Groq provides (limit type, limit/used/requested, Retry-After, x-ratelimit-*
headers). Failed requests gain a fixed failure category and, for
tool_use_failed, the *length* of the rejected generation. Nothing else
about a call changes. A real ChatGroq + Groq SDK runs against a mock
transport; nothing reaches a provider.
"""

from __future__ import annotations

import gzip
import json

import httpx
import pytest

from agents import llm as llm_module
from models.schemas import AnalysisResult

from .test_resilience import (  # noqa: F401 - fake_time is a fixture
    SECRET,
    _groq_scripted,
    _llm_failures,
    _ok,
    _summaries,
    fake_time,
)

# A fake clock: the SDK's and our own retry sleeps take no real time.
pytestmark = pytest.mark.usefixtures("fake_time")

API_KEY = "test-key-SHOULD-NOT-BE-LOGGED"
ORG = "org_SECRET_ORGANIZATION_ID"
OTPM_MESSAGE = (
    f"Rate limit reached for model `qwen/qwen3.8-27b` in organization `{ORG}` service tier `on_demand` "
    "on output tokens per minute (OTPM): Limit 1000, Used 572, Requested 743. "
    "Please try again in 18.9s. Need more tokens? Upgrade to Dev Tier today."
)
FULL_HEADERS = {
    "retry-after": "19",
    "x-ratelimit-limit-requests": "1000",
    "x-ratelimit-limit-tokens": "6000",
    "x-ratelimit-remaining-requests": "998",
    "x-ratelimit-remaining-tokens": "5120",
    "x-ratelimit-reset-requests": "1m26.4s",
    "x-ratelimit-reset-tokens": "7.66s",
}


def _rejected(status: int = 429, message: str = OTPM_MESSAGE, headers: dict | None = None, error_type="tokens"):
    body = {"error": {"message": message, "type": error_type, "code": "rate_limit_exceeded"}}
    return httpx.Response(status, headers=FULL_HEADERS if headers is None else headers, json=body)


def _rate_limit_events(caplog) -> list[dict]:
    return [
        r.event_fields for r in caplog.records if getattr(r, "event_fields", {}).get("event") == "llm_http_rate_limited"
    ]


def _run(llm, caplog):
    with caplog.at_level("INFO"):
        return llm_module.invoke_structured(llm, AnalysisResult, SECRET)


def _assert_nothing_sensitive(caplog):
    for secret in (API_KEY, ORG, SECRET, "Rate limit reached", "Upgrade to Dev Tier", "Authorization", "Bearer"):
        assert secret not in caplog.text


# ---------------------------------------------------------------------------
# 429 quota details
# ---------------------------------------------------------------------------


def test_429_with_all_quota_metadata(caplog):
    llm, seen = _groq_scripted(_rejected(), _ok())

    _run(llm, caplog)

    assert len(seen) == 2  # the SDK retried by itself -- no exception reached our code
    (event,) = _rate_limit_events(caplog)
    assert event | {"call_id": None} == {
        "event": "llm_http_rate_limited",
        "call_id": None,
        "model": "test-model",
        "max_tokens": 750,
        "http_attempt": 1,
        "sdk_retry_count": 0,
        "http_status": 429,
        "provider_error_code": "rate_limit_exceeded",
        "provider_error_type": "tokens",
        "rate_limit_type": "OTPM",
        "quota_limit": 1000,
        "quota_used": 572,
        "quota_requested": 743,
        "retry_after_ms": 19000,
        "message_retry_in_ms": 18900,
        "limit_requests": 1000,
        "limit_tokens": 6000,
        "remaining_requests": 998,
        "remaining_tokens": 5120,
        "reset_requests_ms": 86400,
        "reset_tokens_ms": 7660,
        "quota_details": "full",
    }
    (summary,) = _summaries(caplog)
    assert summary["outcome"] == "success"
    assert summary["rate_limited_responses"] == 1 and summary["rate_limit_types"] == "OTPM"
    assert summary["sdk_retries"] == 1  # existing accounting unchanged
    _assert_nothing_sensitive(caplog)


def test_429_with_partial_metadata(caplog):
    # No x-ratelimit-* headers (as observed for OTPM rejections), and no "Used" number.
    partial = _rejected(
        message=f"Rate limit reached in organization `{ORG}` on tokens per minute (TPM): Limit 6000, Requested 7000.",
        headers={"retry-after": "2"},
    )
    llm, _ = _groq_scripted(partial, _ok())

    _run(llm, caplog)

    (event,) = _rate_limit_events(caplog)
    assert event["rate_limit_type"] == "TPM"
    assert event["quota_limit"] == 6000 and event["quota_requested"] == 7000
    assert "quota_used" not in event  # unavailable fields are left out (null), never guessed
    assert event["retry_after_ms"] == 2000
    assert not any(k in event for k in ("limit_tokens", "remaining_tokens", "reset_tokens_ms", "message_retry_in_ms"))
    assert event["quota_details"] == "partial"
    _assert_nothing_sensitive(caplog)


def test_429_without_any_quota_numbers(caplog):
    llm, _ = _groq_scripted(_rejected(message="Too many requests.", headers={}), _ok())

    _run(llm, caplog)

    (event,) = _rate_limit_events(caplog)
    assert event["quota_details"] == "unavailable"
    assert event["http_status"] == 429 and event["provider_error_code"] == "rate_limit_exceeded"
    assert not any(k in event for k in ("rate_limit_type", "quota_limit", "retry_after_ms"))


def test_missing_or_malformed_headers_and_body(caplog):
    malformed = httpx.Response(
        429,
        headers={
            "retry-after": "soon",
            "x-ratelimit-limit-tokens": "abc",
            "x-ratelimit-remaining-tokens": "-5",
            "x-ratelimit-reset-tokens": "7.66 seconds",
        },
        content=b"<html>RAW-BODY-MARKER</html>",
    )
    llm, _ = _groq_scripted(malformed, _ok())

    result = _run(llm, caplog)  # instrumentation never breaks the call

    assert result is not None
    (event,) = _rate_limit_events(caplog)
    assert {k: v for k, v in event.items() if k not in ("call_id", "model", "max_tokens")} == {
        "event": "llm_http_rate_limited",
        "http_attempt": 1,
        "sdk_retry_count": 0,
        "http_status": 429,
        "quota_details": "unavailable",
    }
    assert "RAW-BODY-MARKER" not in caplog.text  # the raw body is never logged


def test_sdk_and_app_level_429s_are_all_counted_and_the_sdk_still_sees_the_body(caplog):
    # Three 429s: two absorbed by the SDK's own retries, the third raised and retried by our code.
    llm, seen = _groq_scripted(_rejected(), _rejected(), _rejected(), _ok())

    _run(llm, caplog)

    assert len(seen) == 4
    events = _rate_limit_events(caplog)
    assert [e["sdk_retry_count"] for e in events] == [0, 1, 2]
    assert [e["http_attempt"] for e in events] == [1, 2, 3]
    (failure,) = _llm_failures(caplog)
    # The SDK parsed the same body we inspected: the code still reaches its exception.
    assert failure["provider_status"] == 429 and failure["provider_error_code"] == "rate_limit_exceeded"
    assert failure["failure_category"] == "rate_limited"
    (summary,) = _summaries(caplog)
    assert summary["rate_limited_responses"] == 3 and summary["app_retries"] == 1
    _assert_nothing_sensitive(caplog)


def test_compressed_rejection_bodies_are_passed_through_unchanged(caplog):
    body = json.dumps({"error": {"message": OTPM_MESSAGE, "type": "tokens", "code": "rate_limit_exceeded"}})
    gzipped = httpx.Response(
        429, headers={**FULL_HEADERS, "content-encoding": "gzip"}, content=gzip.compress(body.encode())
    )
    llm, _ = _groq_scripted(gzipped, gzipped, gzipped, _ok())

    _run(llm, caplog)

    assert _rate_limit_events(caplog)[0]["quota_used"] == 572
    (failure,) = _llm_failures(caplog)
    assert failure["provider_error_code"] == "rate_limit_exceeded"  # the SDK decoded it too


def test_413_is_recorded_as_request_too_large(caplog):
    too_large = _rejected(
        413, message=f"Request too large in `{ORG}` on tokens per minute (TPM): Limit 6000, Requested 9000.", headers={}
    )
    llm, _ = _groq_scripted(too_large, _ok())

    _run(llm, caplog)

    (event,) = _rate_limit_events(caplog)
    assert event["http_status"] == 413 and event["quota_requested"] == 9000
    (failure,) = _llm_failures(caplog)
    assert failure["failure_category"] == "request_too_large"


# ---------------------------------------------------------------------------
# Other failures and failed generations
# ---------------------------------------------------------------------------


def test_non_429_failure_gets_a_category_and_no_rate_limit_event(caplog):
    unauthorized = httpx.Response(401, json={"error": {"message": "Invalid API Key", "type": "invalid_request_error",
                                                       "code": "invalid_api_key"}})
    llm, _ = _groq_scripted(unauthorized)

    with pytest.raises(llm_module.LLMInvocationError):
        _run(llm, caplog)

    assert _rate_limit_events(caplog) == []
    (failure,) = _llm_failures(caplog)
    assert failure["failure_category"] == "auth"
    assert failure["provider_error_type"] == "invalid_request_error"
    assert "failed_generation_chars" not in failure
    (summary,) = _summaries(caplog)
    assert "rate_limited_responses" not in summary


def test_tool_use_failed_records_category_and_generation_length_only(caplog):
    generation = SECRET + " <tool_call>{\"recommendations\": [\"cut off"
    failed = httpx.Response(400, json={"error": {"message": "Failed to call a function.", "type": "invalid_request_error",
                                                 "code": "tool_use_failed", "failed_generation": generation}})
    llm, _ = _groq_scripted(failed, _ok())

    _run(llm, caplog)

    (failure,) = _llm_failures(caplog)
    assert failure["failure_category"] == "invalid_output"
    assert failure["provider_error_code"] == "tool_use_failed"
    assert failure["provider_error_type"] == "invalid_request_error"
    assert failure["failed_generation_chars"] == len(generation)  # a length, never the text
    assert generation not in caplog.text and "cut off" not in caplog.text
    assert _rate_limit_events(caplog) == []  # a 400 is not a rate limit


def test_failed_request_never_reports_invented_token_usage(caplog):
    failed = httpx.Response(400, json={"error": {"message": "x", "type": "invalid_request_error",
                                                 "code": "tool_use_failed", "failed_generation": "abc"}})
    llm, _ = _groq_scripted(failed, _ok())

    _run(llm, caplog)

    (failure,) = _llm_failures(caplog)
    assert failure["usage_available"] is False
    assert not any(k in failure for k in ("input_tokens", "output_tokens", "finish_reason"))
    (summary,) = _summaries(caplog)
    assert summary["output_tokens"] == 300  # only the successful response's reported usage
    assert summary["usage_available"] == "partial"


# ---------------------------------------------------------------------------
# Unchanged: successful calls, and nothing sensitive is logged
# ---------------------------------------------------------------------------


def test_successful_call_logging_is_unchanged(caplog):
    llm, _ = _groq_scripted(_ok())

    _run(llm, caplog)

    assert _rate_limit_events(caplog) == []
    (summary,) = _summaries(caplog)
    assert "rate_limited_responses" not in summary and "rate_limit_types" not in summary
    assert summary["http_requests"] == 1 and summary["output_tokens"] == 300


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("7.66s", 7660), ("2m59.56s", 179560), ("120ms", 120), ("1h2m", 3720000), ("", None), ("7.66 s", None),
     ("abc", None), (None, None), ("5", None)],
)
def test_duration_parsing(value, expected):
    assert llm_module._duration_ms(value) == expected


def test_rejection_details_ignore_untrusted_shapes():
    details = llm_module._rejection_details(
        429,
        {"retry-after": "inf"},
        {"error": {"code": "not an identifier!", "type": ["x"], "message": 42}},
    )
    assert details["provider_error_code"] is None and details["provider_error_type"] is None
    assert details["retry_after_ms"] is None
    assert details["quota_details"] == "unavailable"
    assert llm_module._rejection_details(429, None, "not a dict")["quota_details"] == "unavailable"

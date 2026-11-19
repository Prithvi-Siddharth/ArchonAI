"""Modular LLM provider layer for all ArchonAI agents.

Groq (via `langchain-groq`) is the primary and default provider, chosen for
its fast inference which keeps the multi-agent workflow responsive. The
provider is resolved through a single factory function (`get_llm`) so a
future provider such as Amazon Bedrock can be added later by extending
`_build_llm` without touching any agent code.
"""

from __future__ import annotations

import logging
import math
import os
import random
import re
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional, TypeVar

import httpx
from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import LLMResult
from pydantic import BaseModel

from graph.observability import current_node, elapsed_ms, log_event, now

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# Indirection so tests can make the jitter deterministic.
_random: Callable[[], float] = random.random

DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_GEMINI_THINKING_LEVEL = "low"

# Groq's models can be verbose (long markdown explanations, tables) even when
# asked for structured output, which can blow well past a free-tier
# tokens-per-minute budget in a single call. Some models (e.g. qwen3.8-27b)
# also enforce their own, much tighter output-tokens-per-minute ceiling
# (observed at 1000/min) independent of the general TPM limit. Capping
# completion length keeps responses information-dense instead of padded, and
# keeps individual requests safely under the tightest limit we've seen.
DEFAULT_MAX_TOKENS = 750

# Groq's OSS models are reasoning models (they generate hidden "thinking"
# tokens before the visible answer), so a single call can legitimately take
# longer than a typical chat completion. Without an explicit timeout, the
# underlying HTTP client can block far longer than that on a slow/stalled
# connection, which looks exactly like a hung UI. This bounds every call so
# a stall fails fast (and can be retried) instead of blocking indefinitely.
REQUEST_TIMEOUT_SECONDS = 90

# A full Architecture (many services + an ordered data flow) needs more room
# than a single analysis or review; used by the Architecture Designer/Revision
# agents specifically. Kept under the observed 1000/min output-token ceiling
# (see DEFAULT_MAX_TOKENS) -- 1400 was still occasionally rejected outright.
ARCHITECTURE_MAX_TOKENS = 900

# Longest wait honored for one rate-limit retry, before jitter.
MAX_RATE_LIMIT_BACKOFF_SECONDS = 60.0

# Random extra wait (0 to this many seconds) added to every rate-limit
# backoff. Parallel agents that hit the same rolling window get the same
# Retry-After, and without jitter they all retry at the same instant and
# trip the limit again together. Only ever added -- never subtracted from
# Retry-After -- and small next to the wait itself, so the worst case grows
# by at most this much per retry.
RATE_LIMIT_JITTER_SECONDS = 3.0

# Provider error codes are short identifiers like "rate_limit_exceeded" or
# "tool_use_failed"; anything else isn't logged, so free text from a
# response body can never end up in the logs.
_ERROR_CODE_PATTERN = re.compile(r"[A-Za-z0-9_.\-]{1,64}")

T = TypeVar("T", bound=BaseModel)


class MissingAPIKeyError(RuntimeError):
    """Raised when the configured LLM provider has no usable API key."""


class LLMInvocationError(RuntimeError):
    """Raised when an LLM call fails or returns output that doesn't match schema.

    Its message is always safe to show or store: a fixed description of the
    kind of failure (`reason`), never the provider's error text -- that can
    echo the prompt or carry the model's whole failed generation. The
    original error stays chained as __cause__ for classification, and the
    details (status, error code, node, call id) are in the internal logs.
    """

    def __init__(self, message: str, *, reason: Optional[str] = None, call_id: Optional[str] = None):
        super().__init__(message)
        self.reason = reason
        self.call_id = call_id


# Fixed, client-safe descriptions of why an LLM call failed.
FAILURE_INVALID_OUTPUT = "the model's structured answer was incomplete or invalid"
FAILURE_RATE_LIMITED = "the LLM provider's rate limit was reached"
FAILURE_TIMEOUT = "the LLM request timed out"
FAILURE_UNAVAILABLE = "the LLM provider was unreachable or temporarily unavailable"
FAILURE_PROVIDER_ERROR = "the LLM provider returned an error"
FAILURE_UNKNOWN = "the LLM call failed"


def _failure_reason(exc: BaseException) -> str:
    """Classify a failure into one of the fixed FAILURE_* descriptions (by type, never by text)."""
    from groq import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
    from langchain_core.exceptions import (
        ModelConnectionError,
        ModelError,
        ModelRateLimitError,
        ModelTimeoutError,
        OutputParserException,
    )

    if isinstance(exc, OutputParserException) or _provider_error_fields(exc)["provider_error_code"] == "tool_use_failed":
        return FAILURE_INVALID_OUTPUT
    if isinstance(exc, (RateLimitError, ModelRateLimitError)) or (
        isinstance(exc, APIStatusError) and exc.status_code == 413
    ):
        return FAILURE_RATE_LIMITED
    if isinstance(exc, (APITimeoutError, ModelTimeoutError, httpx.TimeoutException)):
        return FAILURE_TIMEOUT
    if isinstance(exc, (APIConnectionError, ModelConnectionError, httpx.TransportError)) or is_temporary_server_error(exc):
        return FAILURE_UNAVAILABLE
    if isinstance(exc, (APIStatusError, ModelError)):
        return FAILURE_PROVIDER_ERROR
    return FAILURE_UNKNOWN


def safe_failure_message(exc: BaseException) -> str:
    """A client-safe one-line description of a failed LLM call, for traces and fallbacks.

    Includes the call id (when known) so it can be matched to the internal
    llm_call_summary / llm_request_failed logs. Never includes exception text.
    """
    reason = getattr(exc, "reason", None) or FAILURE_UNKNOWN
    call_id = getattr(exc, "call_id", None)
    return f"{reason} (ref {call_id})" if call_id else reason


def _rate_limit_backoff_seconds(exc: Exception, attempt: int) -> float:
    """Best-effort backoff delay for a rate-limited call, plus jitter.

    Honors Groq's `Retry-After` header when present (Groq's free tier enforces
    a rolling tokens-per-minute window and tells you exactly how long is left
    in it); otherwise falls back to a capped linear backoff. Either way, up
    to RATE_LIMIT_JITTER_SECONDS of random delay is added on top.
    """
    return _base_rate_limit_backoff_seconds(exc, attempt) + _random() * RATE_LIMIT_JITTER_SECONDS


def _google_retry_delay(exc: BaseException) -> str | None:
    """Gemini's equivalent of Retry-After: a RetryInfo entry such as {"retryDelay": "17s"}.

    LangChain raises Gemini errors from the SDK's ClientError, whose parsed
    JSON body (`details`) carries it.
    """
    details = getattr(exc.__cause__, "details", None) or getattr(exc, "details", None)
    error = details.get("error") if isinstance(details, dict) else None
    for item in (error.get("details") if isinstance(error, dict) else None) or []:
        delay = item.get("retryDelay") if isinstance(item, dict) else None
        if isinstance(delay, str) and delay.endswith("s"):
            return delay[:-1]
    return None


def _base_rate_limit_backoff_seconds(exc: Exception, attempt: int) -> float:
    response = getattr(exc, "response", None)
    retry_after = getattr(response, "headers", {}).get("retry-after") if response is not None else None
    retry_after = retry_after or _google_retry_delay(exc)
    if retry_after:
        try:
            # Cap what we'll honor: this is meant for a rolling per-minute
            # window, not a long-window quota reset that could be hours away.
            return min(float(retry_after) + 1.0, MAX_RATE_LIMIT_BACKOFF_SECONDS)
        except ValueError:
            pass
    # No Retry-After header (observed for output-tokens-per-minute
    # rejections): we're waiting for a shared rolling window to age out, not
    # backing off from our own aggressive retries, so scale linearly toward
    # a full minute rather than a short exponential curve.
    return min(15.0 * (attempt + 1), MAX_RATE_LIMIT_BACKOFF_SECONDS)


def _provider_error_fields(exc: BaseException) -> dict[str, Any]:
    """Safe-to-log facts about a provider error: exception type, HTTP status, error code.

    Never the message, body, prompt or output -- provider errors can echo
    request content (a tool_use_failed body includes the model's generation).
    """
    status_code = code = None
    # Groq's errors carry status_code and a JSON body; Gemini's (raised by
    # LangChain *from* the SDK's ClientError) carry an int `code` and a
    # `status` such as RESOURCE_EXHAUSTED on the underlying error.
    for source in (exc, exc.__cause__):
        if source is None:
            continue
        body = getattr(source, "body", None)
        error = body.get("error") if isinstance(body, dict) else None
        candidates_status = (getattr(source, "status_code", None), getattr(source, "code", None))
        candidates_code = (error.get("code") if isinstance(error, dict) else None, getattr(source, "status", None))
        status_code = status_code or next((s for s in candidates_status if _int_or_none(s) is not None), None)
        code = code or next((c for c in candidates_code if isinstance(c, str) and _ERROR_CODE_PATTERN.fullmatch(c)), None)
    return {"error_type": type(exc).__name__, "provider_status": status_code, "provider_error_code": code}


# ---------------------------------------------------------------------------
# Rate-limit and failed-generation details (numbers and identifiers only)
#
# Groq answers a rejected request with structured headers (Retry-After and,
# when present, x-ratelimit-*) and a JSON error body whose `type`/`code`
# are identifiers. The quota numbers (which limit, used, requested) exist
# only inside the body's free-text `message`, so that one field is parsed
# defensively for those numbers and a short upper-case limit name -- the
# message itself (which names the organization and model) is never kept.
# ---------------------------------------------------------------------------

_LIMIT_NUMBERS = re.compile(
    r"\((?P<type>[A-Z]{2,8})\)\s*:\s*Limit\s+(?P<limit>\d+)"
    r"(?:\s*,\s*Used\s+(?P<used>\d+))?(?:\s*,\s*Requested\s+(?P<requested>\d+))?"
)
_TRY_AGAIN = re.compile(r"try again in\s+(?P<duration>(?:\d+(?:\.\d+)?(?:ms|h|m|s))+)", re.IGNORECASE)
_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
_DURATION_MS = {"ms": 1, "s": 1000, "m": 60_000, "h": 3_600_000}
_MAX_REJECTION_BODY_BYTES = 64 * 1024


def _duration_ms(value: Any) -> int | None:
    """'7.66s' / '2m59.56s' / '120ms' / '1h2m' -> milliseconds; None if not that shape."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    parts = _DURATION_PART.findall(text)
    if not parts or "".join(n + u for n, u in parts) != text:
        return None
    return round(sum(float(n) * _DURATION_MS[u] for n, u in parts))


def _seconds_header_ms(value: Any) -> int | None:
    """A Retry-After value in seconds ('2', '1.5') -> milliseconds; None if absent or malformed."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return round(seconds * 1000) if math.isfinite(seconds) and seconds >= 0 else None


def _int_header(value: Any) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _identifier(value: Any) -> str | None:
    return value if isinstance(value, str) and _ERROR_CODE_PATTERN.fullmatch(value) else None


def _error_object(body: Any) -> dict:
    error = body.get("error") if isinstance(body, dict) else None
    return error if isinstance(error, dict) else {}


def _rejection_details(status: int, headers: Any, body: Any) -> dict[str, Any]:
    """Numeric quota facts from a 429/413 response. Missing or malformed values are None.

    `body` is the parsed JSON body (or anything else, which is ignored). The
    error message is only scanned for numbers and the limit's short name.
    """
    get = headers.get if hasattr(headers, "get") else (lambda _name: None)
    error = _error_object(body)
    message = error.get("message") if isinstance(error.get("message"), str) else ""
    numbers = _LIMIT_NUMBERS.search(message)
    try_again = _TRY_AGAIN.search(message)
    details = {
        "http_status": status,
        "provider_error_code": _identifier(error.get("code")),
        "provider_error_type": _identifier(error.get("type")),
        "rate_limit_type": numbers.group("type") if numbers else None,
        "quota_limit": int(numbers.group("limit")) if numbers else None,
        "quota_used": int(numbers.group("used")) if numbers and numbers.group("used") else None,
        "quota_requested": int(numbers.group("requested")) if numbers and numbers.group("requested") else None,
        "retry_after_ms": _seconds_header_ms(get("retry-after")),
        "message_retry_in_ms": _duration_ms(try_again.group("duration")) if try_again else None,
        "limit_requests": _int_header(get("x-ratelimit-limit-requests")),
        "limit_tokens": _int_header(get("x-ratelimit-limit-tokens")),
        "remaining_requests": _int_header(get("x-ratelimit-remaining-requests")),
        "remaining_tokens": _int_header(get("x-ratelimit-remaining-tokens")),
        "reset_requests_ms": _duration_ms(get("x-ratelimit-reset-requests")),
        "reset_tokens_ms": _duration_ms(get("x-ratelimit-reset-tokens")),
    }
    quota = ("rate_limit_type", "quota_limit", "quota_used", "quota_requested")
    found = sum(details[k] is not None for k in quota)
    details["quota_details"] = "full" if found == len(quota) else "partial" if found else "unavailable"
    return details


def _failure_category(exc: BaseException) -> str:
    """A short, fixed category for a failed request (by type, status and error code -- never text)."""
    from groq import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        AuthenticationError,
        RateLimitError,
    )
    from langchain_core.exceptions import OutputParserException

    fields = _provider_error_fields(exc)
    status = _int_or_none(fields["provider_status"])
    if fields["provider_error_code"] == "tool_use_failed":
        return "invalid_output"
    if isinstance(exc, OutputParserException):
        return "parse_error"
    if isinstance(exc, RateLimitError) or status == 429:
        return "rate_limited"
    if status == 413:
        return "request_too_large"
    if isinstance(exc, (APITimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(exc, (APIConnectionError, httpx.TransportError)):
        return "connection"
    if isinstance(exc, AuthenticationError) or status in (401, 403):
        return "auth"
    if status is not None and status >= 500:
        return "server_error"
    if isinstance(exc, APIStatusError) or status is not None:
        return "client_error"
    return "other"


def _failed_generation_fields(exc: BaseException) -> dict[str, Any]:
    """For a failed generation: its error type and the *length* of what the model wrote.

    Groq's tool_use_failed body carries the rejected generation; only its
    character count is kept (never its text). Providers report no token
    usage for a failed request, so none is logged.
    """
    for source in (exc, exc.__cause__):
        if source is None:
            continue
        error = _error_object(getattr(source, "body", None))
        if error:
            generation = error.get("failed_generation")
            return {
                "provider_error_type": _identifier(error.get("type")),
                "failed_generation_chars": len(generation) if isinstance(generation, str) else None,
            }
    return {}


def _log_llm_failure(exc: BaseException, will_retry: bool, **fields: Any) -> None:
    stats = _current_call.get()
    if stats is not None:
        stats.note_failure(exc)
    log_event(
        logger,
        "llm_request_failed",
        logging.WARNING,
        node=current_node(),
        **_provider_error_fields(exc),
        failure_category=_failure_category(exc),
        **_failed_generation_fields(exc),
        will_retry=will_retry,
        **fields,
        **(stats.failure_fields() if stats is not None else {}),
    )


# ---------------------------------------------------------------------------
# Per-call accounting
#
# One *logical call* is one invoke_structured() or invoke_with_retry(). It
# can make many HTTP requests, through three nested retry loops:
#   - tool_use retries   (invoke_structured, corrective prompt, no wait)
#   - application retries (_invoke_with_retry, our own jittered waits)
#   - SDK retries         (inside the Groq SDK, invisible to the code above)
# _CallStats collects all of them for that call, and _LLMCall logs exactly
# one `llm_call_summary` when the call ends, however it ends.
#
# SDK retries are *read*, not inferred: the Groq SDK stamps every request
# with an `x-stainless-retry-count` header (0 for a first try, n for its
# n-th retry), and _CountingTransport records it per HTTP attempt. That
# covers all three of the SDK's retry paths -- retryable statuses, timeouts
# and connection errors. Only the request's timing and status are recorded;
# never its URL, headers (which carry the API key) or body.
# ---------------------------------------------------------------------------

UNAVAILABLE = "unavailable"
_SDK_RETRY_HEADER = "x-stainless-retry-count"
# Statuses where the provider rejected the request before generating anything.
_REJECTED_BEFORE_GENERATION = frozenset({413, 429})


class _HttpAttempt:
    """One HTTP request as seen by _CountingTransport."""

    __slots__ = ("retry_count", "started", "ended", "status", "error_type")

    def __init__(self, retry_count: Optional[int], started: float):
        self.retry_count = retry_count
        self.started = started
        self.ended: Optional[float] = None
        self.status: Optional[int] = None
        self.error_type: Optional[str] = None

    def finish(self, error_type: Optional[str] = None) -> None:
        if self.ended is None:  # the first end (body read or error) is the real one
            self.ended = now()
            self.error_type = self.error_type or error_type


class _CallStats:
    """Counters for one logical LLM call. Numbers, ids and type names only."""

    def __init__(self, call_type: str, schema: Optional[str]):
        self.call_id = uuid.uuid4().hex[:12]
        self.call_type = call_type
        self.schema = schema
        self.started = now()
        self.provider: Optional[str] = None
        self.model: Optional[str] = None
        self.max_tokens: Optional[int] = None
        self.http_instrumented = False
        self.http_attempts: list[_HttpAttempt] = []
        self.app_retries = 0
        self.app_retry_wait_seconds = 0.0
        self.tool_use_retries = 0
        self.llm_responses = 0
        self.responses_without_usage = 0
        self.failures_with_unreported_usage = 0
        self.input_tokens: Optional[int] = None
        self.output_tokens: Optional[int] = None
        self.reasoning_tokens: Optional[int] = None
        self.finish_reason: Optional[str] = None
        self.rate_limited_responses = 0  # HTTP 429/413 responses, including ones the SDK retried
        self.rate_limit_types: list[str] = []

    def note_model(self, provider: Optional[str], model: Optional[str], max_tokens: Optional[int]) -> None:
        self.provider = provider or self.provider
        self.model = model or self.model
        self.max_tokens = max_tokens if max_tokens is not None else self.max_tokens

    def start_http_attempt(self, retry_count: Optional[int]) -> _HttpAttempt:
        self.http_instrumented = True
        attempt = _HttpAttempt(retry_count, now())
        self.http_attempts.append(attempt)
        return attempt

    def last_request_ms(self) -> Optional[int]:
        attempt = self.http_attempts[-1] if self.http_attempts else None
        if attempt is None or attempt.ended is None:
            return None
        return int(round((attempt.ended - attempt.started) * 1000))

    def add_usage(self, usage: dict[str, Any]) -> None:
        self.llm_responses += 1
        if usage.get("output_tokens") is None:
            self.responses_without_usage += 1
        for name in ("input_tokens", "output_tokens", "reasoning_tokens"):
            value = usage.get(name)
            if value is not None:
                setattr(self, name, (getattr(self, name) or 0) + value)
        self.finish_reason = usage.get("finish_reason") or self.finish_reason

    def note_failure(self, exc: BaseException) -> None:
        """Count failures where the provider may have generated tokens it never reported.

        A 429/413 is rejected before generation, and a parse failure comes
        after a response whose usage *was* reported -- neither hides usage.
        Anything else (tool_use_failed 400s, 5xx, timeouts) may have.
        """
        from langchain_core.exceptions import OutputParserException

        if isinstance(exc, OutputParserException):
            return
        if _int_or_none(_provider_error_fields(exc)["provider_status"]) in _REJECTED_BEFORE_GENERATION:
            return
        self.failures_with_unreported_usage += 1

    def note_rejection(self, details: dict[str, Any]) -> None:
        self.rate_limited_responses += 1
        limit_type = details.get("rate_limit_type")
        if limit_type and limit_type not in self.rate_limit_types:
            self.rate_limit_types.append(limit_type)

    def note_app_retry(self, waited_seconds: float) -> None:
        self.app_retries += 1
        self.app_retry_wait_seconds += waited_seconds

    def sdk_fields(self) -> dict[str, Any]:
        """HTTP request count, SDK retries and SDK wait -- or "unavailable" when not measurable.

        Unavailable when the provider's HTTP traffic isn't instrumented
        (Gemini), or when any attempt lacks the SDK's retry-count header, so
        a number is only ever logged when it was actually observed. The SDK
        wait is the gap between an attempt ending and its retry starting;
        if any attempt's end wasn't seen, the whole wait is unavailable
        rather than undercounted.
        """
        if not self.http_instrumented:
            return {"http_requests": UNAVAILABLE, "sdk_retries": UNAVAILABLE, "sdk_retry_wait_ms": UNAVAILABLE}
        attempts = self.http_attempts
        if any(a.retry_count is None for a in attempts):
            return {"http_requests": len(attempts), "sdk_retries": UNAVAILABLE, "sdk_retry_wait_ms": UNAVAILABLE}
        wait: Optional[float] = 0.0
        for previous, current in zip(attempts, attempts[1:]):
            if current.retry_count == 0:
                continue  # a fresh SDK request (app or tool_use retry): not an SDK wait
            if current.retry_count != previous.retry_count + 1 or previous.ended is None:
                wait = None
                break
            wait += max(current.started - previous.ended, 0.0)
        return {
            "http_requests": len(attempts),
            "sdk_retries": sum(1 for a in attempts if a.retry_count > 0),
            "sdk_retry_wait_ms": UNAVAILABLE if wait is None else int(round(wait * 1000)),
        }

    def http_failures_with_unreported_usage(self) -> int:
        return sum(
            1
            for a in self.http_attempts
            if a.error_type is not None or (a.status is not None and a.status >= 400 and a.status not in _REJECTED_BEFORE_GENERATION)
        )

    def usage_available(self) -> str:
        """true: every generation's usage was reported. partial: some may be missing. false: none reported."""
        if self.llm_responses == self.responses_without_usage:
            return "false"
        if (
            self.responses_without_usage
            or self.failures_with_unreported_usage
            or self.http_failures_with_unreported_usage()
        ):
            return "partial"
        return "true"

    def failure_fields(self) -> dict[str, Any]:
        """Extra fields for an llm_request_failed event inside this call."""
        sdk = self.sdk_fields()
        return {
            "call_id": self.call_id,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "sdk_retries": sdk["sdk_retries"],
            # Providers don't report token usage for a failed request.
            "usage_available": False,
        }


_current_call: ContextVar[Optional[_CallStats]] = ContextVar("archonai_llm_call", default=None)


class _LLMCall:
    """Context manager around one logical LLM call: logs exactly one llm_call_summary.

    The summary is written in __exit__, so it is logged once whether the
    call succeeds, fails with a provider or parsing error, or is interrupted
    by anything else (even a BaseException such as a worker time limit).
    A call nested inside another reuses the outer call's stats and logs nothing.
    """

    def __init__(self, call_type: str, schema: Optional[str] = None):
        self._call_type = call_type
        self._schema = schema
        self._token = None
        self.stats: Optional[_CallStats] = None

    def __enter__(self) -> _CallStats:
        outer = _current_call.get()
        if outer is not None:
            return outer
        self.stats = _CallStats(self._call_type, self._schema)
        self._token = _current_call.set(self.stats)
        return self.stats

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is None:
            return None
        _current_call.reset(self._token)
        try:
            _log_call_summary(self.stats, exc)
        except Exception:  # noqa: BLE001 - accounting must never break an LLM call
            pass
        return None


def _log_call_summary(stats: _CallStats, exc: Optional[BaseException]) -> None:
    # invoke_structured wraps the real error in LLMInvocationError; report the root.
    root = exc.__cause__ if isinstance(exc, LLMInvocationError) and exc.__cause__ is not None else exc
    error_fields = _provider_error_fields(root) if root is not None else {}
    log_event(
        logger,
        "llm_call_summary",
        logging.INFO if exc is None else logging.WARNING,
        call_id=stats.call_id,
        node=current_node(),
        call_type=stats.call_type,
        schema=stats.schema,
        provider=stats.provider,
        model=stats.model,
        max_tokens=stats.max_tokens,
        outcome="success" if exc is None else "failure",
        **error_fields,
        total_ms=elapsed_ms(stats.started),
        **stats.sdk_fields(),
        app_retries=stats.app_retries,
        app_retry_wait_ms=int(round(stats.app_retry_wait_seconds * 1000)),
        tool_use_retries=stats.tool_use_retries,
        llm_responses=stats.llm_responses,
        input_tokens=stats.input_tokens,
        output_tokens=stats.output_tokens,
        reasoning_tokens=stats.reasoning_tokens,
        finish_reason=stats.finish_reason,
        usage_available=stats.usage_available(),
        rate_limited_responses=stats.rate_limited_responses or None,
        rate_limit_types=",".join(stats.rate_limit_types) or None,
    )


def _retry_count_header(request: httpx.Request) -> Optional[int]:
    value = request.headers.get(_SDK_RETRY_HEADER)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


class _TimedStream(httpx.SyncByteStream):
    """Response body wrapper: an attempt ends when its body is fully read or closed."""

    def __init__(self, inner: Any, attempt: _HttpAttempt):
        self._inner = inner
        self._attempt = attempt

    def __iter__(self) -> Iterator[bytes]:
        try:
            yield from self._inner
        except BaseException as exc:
            self._attempt.finish(type(exc).__name__)  # e.g. a read timeout mid-body
            raise

    def close(self) -> None:
        try:
            close = getattr(self._inner, "close", None)
            if close is not None:
                close()
        finally:
            self._attempt.finish()


class _CountingTransport(httpx.BaseTransport):
    """Records each HTTP attempt (SDK retry number, status, timing) for the current call.

    It only observes: the request is passed through unchanged, and errors
    are re-raised untouched, so the SDK's own retry decisions are the same
    as without it. Outside a logical call it does nothing at all.
    """

    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        stats = _current_call.get()
        if stats is None:
            return self._inner.handle_request(request)
        attempt = stats.start_http_attempt(_retry_count_header(request))
        try:
            response = self._inner.handle_request(request)
        except BaseException as exc:  # timeouts and connection errors
            attempt.finish(type(exc).__name__)
            raise
        attempt.status = response.status_code
        if response.status_code in _REJECTED_BEFORE_GENERATION:
            return _inspect_rejection(response, stats, attempt)
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            stream=_TimedStream(response.stream, attempt),
            extensions=response.extensions,
        )

    def close(self) -> None:
        self._inner.close()


def _inspect_rejection(response: httpx.Response, stats: _CallStats, attempt: _HttpAttempt) -> httpx.Response:
    """Log the quota details of a 429/413, then hand the SDK an identical response.

    The (small) body is read here so its numbers can be logged even when the
    SDK retries the request itself and never raises. The raw, still-encoded
    bytes are passed on unchanged with the same headers, so the SDK sees
    exactly what it would have; inspection errors never affect the call.
    """
    try:
        raw = b"".join(response.stream)
    except BaseException as exc:
        attempt.finish(type(exc).__name__)
        raise
    finally:
        close = getattr(response.stream, "close", None)
        if close is not None:
            close()
    attempt.finish()
    try:
        body: Any = None
        if len(raw) <= _MAX_REJECTION_BODY_BYTES:
            try:
                body = httpx.Response(response.status_code, headers=response.headers, content=raw).json()
            except Exception:  # noqa: BLE001 - a non-JSON body just has no details
                body = None
        details = _rejection_details(response.status_code, response.headers, body)
        stats.note_rejection(details)
        log_event(
            logger,
            "llm_http_rate_limited",
            logging.WARNING,
            call_id=stats.call_id,
            node=current_node(),
            model=stats.model,
            max_tokens=stats.max_tokens,
            http_attempt=len(stats.http_attempts),
            sdk_retry_count=attempt.retry_count,
            **details,
        )
    except Exception:  # noqa: BLE001 - instrumentation must never break an LLM call
        pass
    return httpx.Response(
        status_code=response.status_code,
        headers=response.headers,
        content=raw,
        extensions=response.extensions,
    )


def _instrumented_http_client(inner: Optional[httpx.BaseTransport] = None) -> httpx.Client:
    """The Groq SDK's own default HTTP client, with _CountingTransport in front.

    DefaultHttpxClient keeps the SDK's defaults (timeouts, redirects); the
    connection limits go on the inner transport, since httpx ignores
    `limits` when a transport is passed in.
    """
    import groq

    inner = inner or httpx.HTTPTransport(limits=groq.DEFAULT_CONNECTION_LIMITS)
    return groq.DefaultHttpxClient(transport=_CountingTransport(inner))


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _usage_fields(response: LLMResult) -> dict[str, Any]:
    """Token counts and finish reason from a completed call (numbers and an identifier only).

    Groq reports OpenAI-style `token_usage`; Gemini only fills the message's
    standard `usage_metadata` (its output_tokens include thinking tokens).
    """
    usage = (response.llm_output or {}).get("token_usage") or {}
    details = usage.get("completion_tokens_details") or {}
    generation = response.generations[0][0] if response.generations and response.generations[0] else None
    finish_reason = (generation.generation_info or {}).get("finish_reason") if generation is not None else None
    if not usage:
        metadata = getattr(getattr(generation, "message", None), "usage_metadata", None) or {}
        output_details = metadata.get("output_token_details") or {}
        usage = {"prompt_tokens": metadata.get("input_tokens"), "completion_tokens": metadata.get("output_tokens")}
        details = {"reasoning_tokens": output_details.get("reasoning")} if isinstance(output_details, dict) else {}
    return {
        "input_tokens": _int_or_none(usage.get("prompt_tokens")),
        "output_tokens": _int_or_none(usage.get("completion_tokens")),
        "reasoning_tokens": _int_or_none(details.get("reasoning_tokens")) if isinstance(details, dict) else None,
        "finish_reason": finish_reason
        if isinstance(finish_reason, str) and _ERROR_CODE_PATTERN.fullmatch(finish_reason)
        else None,
    }


class _UsageLogger(BaseCallbackHandler):
    """Logs each successful LLM call's real token usage next to its max_tokens cap.

    Groq's output-tokens-per-minute limit reserves a request's max_tokens
    from the budget up front, so the gap between `max_tokens` and
    `output_tokens` is budget held back for nothing -- these numbers are what
    per-agent caps should be set from. finish_reason=length means the answer
    hit the cap and was cut off. Counts only; never prompt or output text.
    """

    def __init__(self, max_tokens: int, model: Optional[str] = None, provider: Optional[str] = None):
        self.max_tokens = max_tokens
        self.model = model
        self.provider = provider

    def on_chat_model_start(self, serialized: Any, messages: Any, **kwargs: Any) -> None:
        # Fires before the request is sent, so the call's summary names its
        # model and cap even when every request then fails.
        try:
            stats = _current_call.get()
            if stats is not None:
                stats.note_model(self.provider, self.model, self.max_tokens)
        except Exception:  # noqa: BLE001
            pass

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            usage = _usage_fields(response)
            stats = _current_call.get()
            if stats is not None:
                stats.add_usage(usage)
            log_event(
                logger,
                "llm_call_finished",
                node=current_node(),
                max_tokens=self.max_tokens,
                **usage,
                call_id=stats.call_id if stats is not None else None,
                provider=self.provider,
                model=self.model,
                # Time from sending this (final, successful) HTTP request to
                # its body being read; excludes earlier attempts and waits.
                request_ms=stats.last_request_ms() if stats is not None else None,
            )
        except Exception:  # noqa: BLE001 - usage logging must never break an LLM call
            pass


def _invoke_with_retry(call: Callable[[], T], max_attempts: int = 5) -> T:
    """Retry an LLM call with backoff on transient rate-limit or network errors.

    ArchonAI's graph runs several agents in parallel (twice per design run),
    which can briefly burst past a free-tier tokens-per-minute limit even
    though total usage for a run is modest. Rather than fail the whole
    workflow, wait out the rolling window and retry a bounded number of
    times. A request timeout or connection error gets the same short-backoff
    treatment, since those are usually a transient network blip rather than
    a permanent failure -- but every call has a hard REQUEST_TIMEOUT_SECONDS
    ceiling (see get_llm), so a stall can never block longer than that.

    Groq's SDK only maps HTTP 429 to RateLimitError; an "input/output tokens
    per minute" rejection can also arrive as a plain 413, which the SDK maps
    to the generic APIStatusError instead. Both mean the same thing (this
    request doesn't fit in the current rolling window), so both get the same
    retry treatment here -- a 413 that fell through uncaught would otherwise
    never be retried at all, no matter how small later requests get.

    Gemini's errors arrive as LangChain's provider-neutral types
    (ModelRateLimitError, ModelTimeoutError, ...) or, for network failures,
    as raw httpx errors -- both get the same treatment as Groq's.
    """
    import httpx
    from groq import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
    from langchain_core.exceptions import ModelAPIError, ModelConnectionError, ModelRateLimitError, ModelTimeoutError

    # Only retries are logged here; the final failure is logged once by the
    # caller (invoke_structured / invoke_with_retry), so it never appears twice.
    for attempt in range(max_attempts):
        try:
            return call()
        except (RateLimitError, ModelRateLimitError) as exc:
            if attempt == max_attempts - 1:
                raise
            _sleep_before_retry(exc, attempt, _rate_limit_backoff_seconds(exc, attempt))
        except APIStatusError as exc:
            if exc.status_code != 413 or attempt == max_attempts - 1:
                raise
            _sleep_before_retry(exc, attempt, _rate_limit_backoff_seconds(exc, attempt))
        except ModelAPIError as exc:
            # Gemini answers 503 UNAVAILABLE ("high demand") when a model is
            # overloaded -- temporary, like a rate limit, so it gets the same
            # longer wait. (Groq's server errors are retried inside its SDK.)
            if not is_temporary_server_error(exc) or attempt == max_attempts - 1:
                raise
            _sleep_before_retry(exc, attempt, _rate_limit_backoff_seconds(exc, attempt))
        except (
            APITimeoutError,
            APIConnectionError,
            ModelTimeoutError,
            ModelConnectionError,
            httpx.TransportError,
        ) as exc:
            if attempt == max_attempts - 1:
                raise
            _sleep_before_retry(exc, attempt, min(2.0**attempt, 15.0))
    raise AssertionError("unreachable")  # pragma: no cover


TEMPORARY_SERVER_STATUS_CODES = frozenset({500, 502, 503, 504})


def is_temporary_server_error(exc: BaseException) -> bool:
    """A provider-side failure (overloaded or briefly down) that a later retry may get past."""
    return _int_or_none(getattr(exc, "code", None)) in TEMPORARY_SERVER_STATUS_CODES


_INVALID_KEY_REASON = "API_KEY_INVALID"


def is_credential_rejection(exc: BaseException) -> bool:
    """The provider refused the API key itself (401/403, or Gemini's invalid-key answer).

    Decided from status codes and Google's fixed error-reason code only, never
    from the message text. Used to tell a user their key is wrong instead of
    reporting a generic provider error.
    """
    if _int_or_none(_provider_error_fields(exc)["provider_status"]) in (401, 403):
        return True
    # Gemini answers an invalid key with 400 INVALID_ARGUMENT plus a machine-readable reason.
    for source in (exc, exc.__cause__):
        details = getattr(source, "details", None)
        error = details.get("error") if isinstance(details, dict) else None
        entries = error.get("details") if isinstance(error, dict) else None
        if isinstance(entries, list) and any(isinstance(e, dict) and e.get("reason") == _INVALID_KEY_REASON for e in entries):
            return True
    return False


def _sleep_before_retry(exc: BaseException, attempt: int, delay_seconds: float) -> None:
    _log_llm_failure(exc, True, call_attempt=attempt + 1, retry_in_ms=int(round(delay_seconds * 1000)))
    started = now()
    try:
        time.sleep(delay_seconds)
    finally:
        stats = _current_call.get()
        if stats is not None:
            stats.note_app_retry(now() - started)  # measured, not the planned delay


def _build_groq_llm(
    temperature: float, max_tokens: int, *, api_key: Optional[str] = None, model: Optional[str] = None
) -> BaseChatModel:
    # `api_key` is a user's own key (see LLMCredentials); without it the server's .env key is used.
    own_key = api_key is not None
    if not own_key:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key or api_key == "your_groq_api_key_here":
            raise MissingAPIKeyError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and set a real "
                "Groq API key from https://console.groq.com/keys."
            )
    from langchain_groq import ChatGroq

    # The server's GROQ_MODEL belongs to the server's key; a user's own key gets their model or the default.
    model = model or ("" if own_key else os.getenv("GROQ_MODEL", "").strip()) or DEFAULT_GROQ_MODEL
    return ChatGroq(
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=REQUEST_TIMEOUT_SECONDS,
        # Attached to the model, so it also covers structured-output and
        # tool-calling wrappers (and the temperature-bumped copies used on retry).
        callbacks=[_UsageLogger(max_tokens, model=model, provider="groq")],
        # Same SDK defaults, plus per-attempt accounting (see _CountingTransport).
        http_client=_instrumented_http_client(),
    )


def _build_gemini_llm(
    temperature: float, max_tokens: int, *, api_key: Optional[str] = None, model: Optional[str] = None
) -> BaseChatModel:
    own_key = api_key is not None
    if not own_key:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise MissingAPIKeyError(
                "GEMINI_API_KEY is not set. Create a key at https://aistudio.google.com/apikey "
                "and add it to .env, or set LLM_PROVIDER=groq."
            )
    from langchain_google_genai import ChatGoogleGenerativeAI

    model = model or ("" if own_key else os.getenv("GEMINI_MODEL", "").strip()) or DEFAULT_GEMINI_MODEL
    # Gemini 3 models think before answering by default, and the thinking
    # tokens count toward max_tokens -- at our small caps, deep thinking can
    # use up the whole budget and cut the JSON answer off. "default" leaves
    # the model's own setting.
    thinking_level = os.getenv("GEMINI_THINKING_LEVEL", "").strip().lower() or DEFAULT_GEMINI_THINKING_LEVEL
    thinking = {} if thinking_level == "default" else {"thinking_level": thinking_level}
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=REQUEST_TIMEOUT_SECONDS,
        # The SDK's own per-request retries (default 6); _invoke_with_retry
        # adds the longer, jittered waits on top. Matches Groq's SDK default.
        max_retries=2,
        # Gemini's HTTP traffic is not instrumented, so its summaries log
        # http_requests / sdk_retries / sdk_retry_wait_ms as "unavailable".
        callbacks=[_UsageLogger(max_tokens, model=model, provider="gemini")],
        **thinking,
    )


@dataclass(frozen=True)
class LLMCredentials:
    """A user's own provider, API key and (optional) model, for one job run.

    The key is excluded from repr() so a stray log line or traceback can't print it.
    """

    provider: str
    api_key: str = field(repr=False)
    model: Optional[str] = None


# The credentials for the run in progress. A ContextVar (like the job id in
# graph/observability.py) so they follow the run into LangGraph's parallel
# nodes without any agent having to pass them along, and never leak into
# another job running in the same process.
_credentials: ContextVar[Optional[LLMCredentials]] = ContextVar("archonai_llm_credentials", default=None)


@contextmanager
def use_llm_credentials(credentials: Optional[LLMCredentials]) -> Iterator[None]:
    """Make get_llm() use these credentials inside the block; None keeps the server's own setup."""
    if credentials is None:
        yield
        return
    token = _credentials.set(credentials)
    try:
        yield
    finally:
        _credentials.reset(token)


def get_llm(temperature: float = 0.2, max_tokens: int = DEFAULT_MAX_TOKENS) -> BaseChatModel:
    """Return the configured chat model.

    A job run with a user's own credentials (use_llm_credentials) gets that
    user's provider and key. Otherwise it is controlled by the LLM_PROVIDER
    environment variable: "groq" (the
    default) or "gemini". Adding Amazon Bedrock support later only requires
    a new branch here.
    `max_tokens` bounds completion length -- most agents use the default, but
    the Architecture Designer/Revision agents request more room since a full
    service list and data flow naturally need more tokens than, say, a single
    analysis (see DEFAULT_MAX_TOKENS for why this is capped at all).
    """
    credentials = _credentials.get()
    if credentials is not None:
        if credentials.provider == "groq":
            return _build_groq_llm(temperature, max_tokens, api_key=credentials.api_key, model=credentials.model)
        if credentials.provider == "gemini":
            return _build_gemini_llm(temperature, max_tokens, api_key=credentials.api_key, model=credentials.model)
        raise ValueError(f"Unknown provider '{credentials.provider}'. Supported providers: groq, gemini.")

    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    if provider == "groq":
        return _build_groq_llm(temperature, max_tokens)
    if provider == "gemini":
        return _build_gemini_llm(temperature, max_tokens)
    if provider == "bedrock":
        raise NotImplementedError(
            "Amazon Bedrock support is not implemented yet. Set LLM_PROVIDER=groq or gemini."
        )
    raise ValueError(f"Unknown LLM_PROVIDER '{provider}'. Supported providers: groq, gemini.")


def invoke_with_retry(call: Callable[[], T]) -> T:
    """Public retry wrapper for call sites that invoke the LLM directly
    (e.g. the Architecture Designer's tool-calling loop) rather than through
    invoke_structured."""
    with _LLMCall("invoke"):
        try:
            return _invoke_with_retry(call)
        except Exception as exc:
            _log_llm_failure(exc, False)
            raise


def _is_tool_use_failure(exc: Exception) -> bool:
    """Groq's OSS models occasionally ignore a required tool call (answering
    in prose instead) or call it with a value that fails schema validation
    (e.g. paraphrasing an enum instead of picking a literal). Both surface as
    a 400 with code 'tool_use_failed'. Neither is a permanent failure -- a
    retry that tells the model exactly what was wrong usually succeeds.

    Gemini answers in native JSON mode instead of a tool call; the same kind
    of failure (invalid or cut-off JSON) surfaces there as an
    OutputParserException, and gets the same corrective retry."""
    from langchain_core.exceptions import OutputParserException

    if isinstance(exc, OutputParserException):
        return True
    message = str(exc)
    return "tool_use_failed" in message or "did not call a tool" in message


def _tool_use_failure_detail(exc: Exception) -> str:
    """Extract the concise validation message from a tool-use failure,
    dropping the verbose `failed_generation` echo so the retry prompt we
    build from it doesn't re-inflate to the same size that likely caused the
    original failure."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            # Only the short validation message -- never `failed_generation`,
            # the model's whole rejected output, which sits beside it.
            return str(error["message"])[:300]
    from langchain_core.exceptions import OutputParserException

    if isinstance(exc, OutputParserException):
        # Its message embeds the whole invalid output; the first line says what was wrong.
        return str(exc).splitlines()[0][:300] if str(exc) else "The response was not valid JSON for the schema."
    # str() of a provider error can include its full body (failed_generation
    # and all), so it never goes into a prompt.
    return "The response was not a valid call to the required tool."


# A common cause of tool_use_failed is an answer cut off at max_tokens --
# and a retry that asks for the same amount of output is cut off again. So
# the correction asks for a substantially shorter answer. Only the specialist
# analyses (AnalysisResult) are told to drop items: for other schemas, fewer
# items could mean dropping something essential (e.g. a service from an
# Architecture), so they keep their items and shorten each one.
_SHORTER_ANALYSIS = (
    "Make this response substantially shorter than your previous one: return fewer "
    "recommendations and fewer risks, make every item shorter, and keep reasoning to "
    "one or two brief sentences."
)
_SHORTER_GENERIC = (
    "Make this response substantially shorter than your previous one: keep the same "
    "items, but make every text value shorter, and keep any reasoning or narrative "
    "text to one or two brief sentences."
)


def _tool_call_reinforcement(exc: Exception, schema: Optional[type[BaseModel]] = None) -> str:
    from models.schemas import AnalysisResult

    shorter = _SHORTER_ANALYSIS if schema is AnalysisResult else _SHORTER_GENERIC
    schema_name = schema.__name__ if schema is not None else "required"
    return (
        "\n\nIMPORTANT: Your previous attempt was rejected with this exact error: "
        f"{_tool_use_failure_detail(exc)}\n"
        "The response may have been too long and cut off. "
        f"{shorter}\n"
        f"Follow the {schema_name} schema exactly -- the same fields, with valid values -- "
        "and return valid structured output. "
        "Call the required structured-output tool again with a corrected response "
        "that fixes this specific error. Respond ONLY via that tool call -- no prose, "
        "no markdown, no commentary outside of it."
    )


def invoke_structured(llm: BaseChatModel, schema: type[T], prompt: str, max_attempts: int = 3) -> T:
    """Invoke the LLM and parse its response into the given Pydantic schema.

    Centralizes structured-output error handling so a malformed or failed
    LLM response surfaces as a single well-typed exception instead of
    crashing a graph node with a raw provider error. Retries with an
    increasingly explicit instruction when the model ignores the required
    tool call (see _is_tool_use_failure), and separately retries with
    backoff on transient rate-limit errors (see _invoke_with_retry).
    Logs exactly one llm_call_summary for the whole call (see _LLMCall).
    """
    with _LLMCall("structured", schema.__name__) as stats:
        return _invoke_structured(llm, schema, prompt, max_attempts, stats)


def _invoke_structured(llm: BaseChatModel, schema: type[T], prompt: str, max_attempts: int, stats: _CallStats) -> T:
    current_prompt = prompt
    current_llm = llm

    for attempt in range(max_attempts):
        structured_llm = current_llm.with_structured_output(schema)
        try:
            result = _invoke_with_retry(lambda: structured_llm.invoke(current_prompt))
        except Exception as exc:  # noqa: BLE001 - normalize any provider/parsing failure
            retry_tool_use = _is_tool_use_failure(exc) and attempt < max_attempts - 1
            _log_llm_failure(exc, retry_tool_use, schema=schema.__name__, call_attempt=attempt + 1)
            if retry_tool_use:
                stats.tool_use_retries += 1
                current_prompt = prompt + _tool_call_reinforcement(exc, schema)
                # A near-zero temperature is close to deterministic, so simply
                # retrying the identical call tends to reproduce the exact
                # same invalid output. Nudge sampling up on each retry so the
                # model actually has a chance to produce something different.
                base_temp = getattr(llm, "temperature", None) or 0.2
                bumped_temp = min(base_temp + 0.25 * (attempt + 1), 1.0)
                current_llm = llm.model_copy(update={"temperature": bumped_temp})
                continue
            reason = _failure_reason(exc)
            raise LLMInvocationError(
                f"LLM call failed while producing {schema.__name__}: {reason}",
                reason=reason,
                call_id=stats.call_id,
            ) from exc

        if not isinstance(result, schema):
            raise LLMInvocationError(
                f"LLM returned unexpected type for {schema.__name__}: {type(result).__name__}",
                reason=FAILURE_INVALID_OUTPUT,
                call_id=stats.call_id,
            )
        return result

    raise LLMInvocationError(  # pragma: no cover - unreachable, loop always returns or raises
        f"LLM failed to produce valid {schema.__name__} after {max_attempts} attempts",
        reason=FAILURE_UNKNOWN,
        call_id=stats.call_id,
    )

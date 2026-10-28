"""Modular LLM provider layer for all ArchonAI agents.

Groq (via `langchain-groq`) is the primary and default provider, chosen for
its fast inference which keeps the multi-agent workflow responsive. The
provider is resolved through a single factory function (`get_llm`) so a
future provider such as Amazon Bedrock can be added later by extending
`_build_llm` without touching any agent code.
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from typing import Any, Callable, TypeVar

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import LLMResult
from pydantic import BaseModel

from graph.observability import current_node, log_event

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# Indirection so tests can make the jitter deterministic.
_random: Callable[[], float] = random.random

DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"

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
    """Raised when an LLM call fails or returns output that doesn't match schema."""


def _rate_limit_backoff_seconds(exc: Exception, attempt: int) -> float:
    """Best-effort backoff delay for a rate-limited call, plus jitter.

    Honors Groq's `Retry-After` header when present (Groq's free tier enforces
    a rolling tokens-per-minute window and tells you exactly how long is left
    in it); otherwise falls back to a capped linear backoff. Either way, up
    to RATE_LIMIT_JITTER_SECONDS of random delay is added on top.
    """
    return _base_rate_limit_backoff_seconds(exc, attempt) + _random() * RATE_LIMIT_JITTER_SECONDS


def _base_rate_limit_backoff_seconds(exc: Exception, attempt: int) -> float:
    response = getattr(exc, "response", None)
    retry_after = getattr(response, "headers", {}).get("retry-after") if response is not None else None
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
    body = getattr(exc, "body", None)
    error = body.get("error") if isinstance(body, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    status_code = getattr(exc, "status_code", None)
    return {
        "error_type": type(exc).__name__,
        "provider_status": status_code if isinstance(status_code, int) else None,
        "provider_error_code": code if isinstance(code, str) and _ERROR_CODE_PATTERN.fullmatch(code) else None,
    }


def _log_llm_failure(exc: BaseException, will_retry: bool, **fields: Any) -> None:
    log_event(
        logger,
        "llm_request_failed",
        logging.WARNING,
        node=current_node(),
        **_provider_error_fields(exc),
        will_retry=will_retry,
        **fields,
    )


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _usage_fields(response: LLMResult) -> dict[str, Any]:
    """Token counts and finish reason from a completed call (numbers and an identifier only)."""
    usage = (response.llm_output or {}).get("token_usage") or {}
    details = usage.get("completion_tokens_details") or {}
    generation = response.generations[0][0] if response.generations and response.generations[0] else None
    finish_reason = (generation.generation_info or {}).get("finish_reason") if generation is not None else None
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

    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            log_event(
                logger,
                "llm_call_finished",
                node=current_node(),
                max_tokens=self.max_tokens,
                **_usage_fields(response),
            )
        except Exception:  # noqa: BLE001 - usage logging must never break an LLM call
            pass


def _invoke_with_retry(call: Callable[[], T], max_attempts: int = 5) -> T:
    """Retry a Groq call with backoff on transient rate-limit or network errors.

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
    """
    from groq import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

    # Only retries are logged here; the final failure is logged once by the
    # caller (invoke_structured / invoke_with_retry), so it never appears twice.
    for attempt in range(max_attempts):
        try:
            return call()
        except RateLimitError as exc:
            if attempt == max_attempts - 1:
                raise
            _sleep_before_retry(exc, attempt, _rate_limit_backoff_seconds(exc, attempt))
        except APIStatusError as exc:
            if exc.status_code != 413 or attempt == max_attempts - 1:
                raise
            _sleep_before_retry(exc, attempt, _rate_limit_backoff_seconds(exc, attempt))
        except (APITimeoutError, APIConnectionError) as exc:
            if attempt == max_attempts - 1:
                raise
            _sleep_before_retry(exc, attempt, min(2.0**attempt, 15.0))
    raise AssertionError("unreachable")  # pragma: no cover


def _sleep_before_retry(exc: BaseException, attempt: int, delay_seconds: float) -> None:
    _log_llm_failure(exc, True, call_attempt=attempt + 1, retry_in_ms=int(round(delay_seconds * 1000)))
    time.sleep(delay_seconds)


def _build_groq_llm(temperature: float, max_tokens: int) -> BaseChatModel:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "your_groq_api_key_here":
        raise MissingAPIKeyError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and set a real "
            "Groq API key from https://console.groq.com/keys."
        )
    from langchain_groq import ChatGroq

    model = os.getenv("GROQ_MODEL", "").strip() or DEFAULT_GROQ_MODEL
    return ChatGroq(
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=REQUEST_TIMEOUT_SECONDS,
        # Attached to the model, so it also covers structured-output and
        # tool-calling wrappers (and the temperature-bumped copies used on retry).
        callbacks=[_UsageLogger(max_tokens)],
    )


def get_llm(temperature: float = 0.2, max_tokens: int = DEFAULT_MAX_TOKENS) -> BaseChatModel:
    """Return the configured chat model.

    Controlled by the LLM_PROVIDER environment variable (defaults to "groq").
    Adding Amazon Bedrock support later only requires a new branch here.
    `max_tokens` bounds completion length -- most agents use the default, but
    the Architecture Designer/Revision agents request more room since a full
    service list and data flow naturally need more tokens than, say, a single
    analysis (see DEFAULT_MAX_TOKENS for why this is capped at all).
    """
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    if provider == "groq":
        return _build_groq_llm(temperature, max_tokens)
    if provider == "bedrock":
        raise NotImplementedError(
            "Amazon Bedrock support is not implemented yet. Set LLM_PROVIDER=groq."
        )
    raise ValueError(f"Unknown LLM_PROVIDER '{provider}'. Supported providers: groq.")


def invoke_with_retry(call: Callable[[], T]) -> T:
    """Public retry wrapper for call sites that invoke the LLM directly
    (e.g. the Architecture Designer's tool-calling loop) rather than through
    invoke_structured."""
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
    retry that tells the model exactly what was wrong usually succeeds."""
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
            return str(error["message"])
    return str(exc)


def _tool_call_reinforcement(exc: Exception) -> str:
    return (
        "\n\nIMPORTANT: Your previous attempt was rejected with this exact error: "
        f"{_tool_use_failure_detail(exc)}\n"
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
    """
    current_prompt = prompt
    current_llm = llm
    last_exc: Exception | None = None

    for attempt in range(max_attempts):
        structured_llm = current_llm.with_structured_output(schema)
        try:
            result = _invoke_with_retry(lambda: structured_llm.invoke(current_prompt))
        except Exception as exc:  # noqa: BLE001 - normalize any provider/parsing failure
            last_exc = exc
            retry_tool_use = _is_tool_use_failure(exc) and attempt < max_attempts - 1
            _log_llm_failure(exc, retry_tool_use, schema=schema.__name__, call_attempt=attempt + 1)
            if retry_tool_use:
                current_prompt = prompt + _tool_call_reinforcement(exc)
                # A near-zero temperature is close to deterministic, so simply
                # retrying the identical call tends to reproduce the exact
                # same invalid output. Nudge sampling up on each retry so the
                # model actually has a chance to produce something different.
                base_temp = getattr(llm, "temperature", None) or 0.2
                bumped_temp = min(base_temp + 0.25 * (attempt + 1), 1.0)
                current_llm = llm.model_copy(update={"temperature": bumped_temp})
                continue
            raise LLMInvocationError(
                f"LLM call failed while producing {schema.__name__}: {exc}"
            ) from exc

        if not isinstance(result, schema):
            raise LLMInvocationError(
                f"LLM returned unexpected type for {schema.__name__}: {type(result)!r}"
            )
        return result

    raise LLMInvocationError(  # pragma: no cover - unreachable, loop always returns or raises
        f"LLM failed to produce valid {schema.__name__} after {max_attempts} attempts: {last_exc}"
    )

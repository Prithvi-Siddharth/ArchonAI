"""Structured logging and execution timing for ArchonAI.

Every event is one log line of `key=value` pairs, always starting with
`event=<name>`, e.g.

    event=node_finished job_id=3f2a... node=compute_agent iteration=0 outcome=success duration_ms=4120

The same fields are attached to the LogRecord as `record.event_fields`, so a
JSON formatter or log shipper can be added later without touching call sites.

Durations use a monotonic clock (time.perf_counter), so they're unaffected
by wall-clock changes. The current job id travels in a ContextVar: set it
once with job_context(), and every event logged inside -- including from
LangGraph's parallel node threads, which inherit the context -- carries it.

Only metadata is logged (ids, node names, durations, status codes,
exception *types*). Never log request text, LLM output, or exception
messages here: provider errors can echo request details.
"""

from __future__ import annotations

import functools
import json
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional

# Indirection so tests can substitute a fake clock.
_clock: Callable[[], float] = time.perf_counter

_current_job_id: ContextVar[Optional[str]] = ContextVar("archonai_job_id", default=None)

_logger = logging.getLogger("archonai.timing")


def now() -> float:
    """A monotonic timestamp in seconds (only meaningful as a difference)."""
    return _clock()


def elapsed_ms(start: float) -> int:
    """Whole milliseconds since `start` (a value from now())."""
    return int(round((_clock() - start) * 1000))


@contextmanager
def job_context(job_id: str) -> Iterator[None]:
    """Attach `job_id` to every event logged inside this block."""
    token = _current_job_id.set(job_id)
    try:
        yield
    finally:
        _current_job_id.reset(token)


def current_job_id() -> Optional[str]:
    return _current_job_id.get()


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    # Quote anything that would break key=value parsing.
    if not text or any(ch in text for ch in ' ="'):
        return json.dumps(text)
    return text


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Log one structured event. The current job id is added automatically."""
    if "job_id" not in fields and current_job_id() is not None:
        fields = {"job_id": current_job_id(), **fields}
    fields = {k: v for k, v in fields.items() if v is not None}
    message = " ".join([f"event={event}", *(f"{k}={_format_value(v)}" for k, v in fields.items())])
    logger.log(level, message, extra={"event_fields": {"event": event, **fields}})


def timed_node(name: str, func: Callable[[dict], dict]) -> Callable[[dict], dict]:
    """Wrap a LangGraph node so each run logs its duration and outcome.

    The node itself is untouched: the wrapper starts a monotonic timer, calls
    it, and logs `node_finished` with outcome=success, or outcome=failure
    plus the exception type before re-raising. Parallel nodes each run their
    own wrapper in their own thread, so their timings never mix.
    """

    @functools.wraps(func)
    def wrapper(state: dict) -> dict:
        iteration = state.get("revision_count", 0) if isinstance(state, dict) else None
        start = now()
        try:
            result = func(state)
        except BaseException as exc:
            log_event(
                _logger,
                "node_finished",
                logging.WARNING,
                node=name,
                iteration=iteration,
                outcome="failure",
                error_type=type(exc).__name__,
                duration_ms=elapsed_ms(start),
            )
            raise
        log_event(
            _logger, "node_finished", node=name, iteration=iteration, outcome="success", duration_ms=elapsed_ms(start)
        )
        return result

    return wrapper

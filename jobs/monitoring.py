"""Turn one job's CloudWatch log lines into a monitoring report. No AWS access here.

ArchonAI logs structured lines (graph/observability.py): `event=<name> job_id=... key=value ...`.
This module parses them and builds the numbers the Monitoring page shows.

Safety: nothing from a log line is passed on as free text. Only events and fields on the
allow-lists below are kept, each field is parsed as the kind it should be (a number, a
true/false, or a short identifier-like word), and anything that doesn't fit is dropped. So
even if some future log line carried a prompt, an error body or a key, it could not reach a
user through this page.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from graph.workflow import NODE_DISPLAY_NAMES

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
MAX_TIMELINE = 500
MAX_LLM_CALLS = 200

INT, BOOL, WORD = "int", "bool", "word"

# event -> {field: kind}. Kinds: int, bool, or WORD (letters, digits and _ . : / , - only, up to 80 characters).
ALLOWED_EVENTS: dict[str, dict[str, str]] = {
    "job_started": {"attempt": INT, "redelivered": BOOL},
    "job_resumed_after_crash": {"previous_attempts": INT},
    "job_skipped": {"reason": WORD, "status": WORD, "attempt": INT},
    "job_succeeded": {"attempt": INT, "duration_ms": INT},
    "job_failed": {"attempt": INT, "status_code": INT, "error_type": WORD, "will_retry": BOOL, "duration_ms": INT, "reason": WORD},
    "workflow_started": {},
    "workflow_finished": {"outcome": WORD, "approved": BOOL, "revision_count": INT, "duration_ms": INT, "error_type": WORD},
    "node_finished": {"node": WORD, "iteration": INT, "outcome": WORD, "duration_ms": INT, "error_type": WORD},
    "llm_call_summary": {
        "call_id": WORD, "node": WORD, "call_type": WORD, "schema": WORD, "provider": WORD, "model": WORD,
        "max_tokens": INT, "outcome": WORD, "provider_status": INT, "provider_error_code": WORD, "error_type": WORD,
        "total_ms": INT, "http_requests": INT, "sdk_retries": INT, "sdk_retry_wait_ms": INT, "app_retries": INT,
        "app_retry_wait_ms": INT, "tool_use_retries": INT, "llm_responses": INT, "input_tokens": INT,
        "output_tokens": INT, "reasoning_tokens": INT, "finish_reason": WORD, "rate_limited_responses": INT,
        "rate_limit_types": WORD,
    },
    "llm_request_failed": {
        "node": WORD, "call_id": WORD, "error_type": WORD, "provider_status": INT, "provider_error_code": WORD,
        "provider_error_type": WORD, "failure_category": WORD, "failed_generation_chars": INT, "will_retry": BOOL,
        "call_attempt": INT, "retry_in_ms": INT, "schema": WORD, "sdk_retries": INT, "model": WORD,
    },
}

_WORD = re.compile(r"^[A-Za-z0-9_.:/,\-]{1,80}$")
_INT = re.compile(r"^-?\d{1,12}$")
# Whatever the logging format puts before the event (CloudWatch: "INFO graph.observability: ",
# Celery's console: "[2026-11-14 18:06:19,437: INFO/ForkPoolWorker-1] ", or nothing) is skipped.
_EVENT = re.compile(r"(?:^|\s)event=(?P<event>[A-Za-z_][A-Za-z0-9_]*)")
_LEVEL = re.compile(r"\b(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b")
_PAIR = re.compile(r'\s+(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>"(?:[^"\\]|\\.)*"|\S*)')


@dataclass(frozen=True)
class RawEvent:
    """One log line as CloudWatch returned it."""

    timestamp_ms: int
    service: str  # "api" or "worker"
    message: str


@dataclass(frozen=True)
class LogEvent:
    timestamp_ms: int
    service: str
    level: str
    event: str
    fields: dict[str, Any] = field(default_factory=dict)


def _value(kind: str, raw: str) -> Any:
    if kind == INT:
        return int(raw) if _INT.match(raw) else None
    if kind == BOOL:
        return {"true": True, "false": False}.get(raw)
    return raw if _WORD.match(raw) else None


def parse_event(raw: RawEvent, job_id: str) -> Optional[LogEvent]:
    """The allow-listed content of one log line, or None if it is not a known event for this job."""
    text = raw.message.strip()
    match = _EVENT.search(text)
    if match is None or match["event"] not in ALLOWED_EVENTS:
        return None
    spec = ALLOWED_EVENTS[match["event"]]
    pairs: dict[str, str] = {}
    for pair in _PAIR.finditer(text[match.end() :]):
        value = pair["value"]
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                continue
        pairs[pair["key"]] = value
    if pairs.get("job_id") != job_id:  # the search is a substring match; be exact
        return None
    fields: dict[str, Any] = {}
    for name, kind in spec.items():
        if name in pairs:
            value = _value(kind, pairs[name])
            if value is not None:  # "unavailable", odd text and the like are simply left out
                fields[name] = value
    found = _LEVEL.search(text[: match.start()])
    return LogEvent(raw.timestamp_ms, raw.service, found.group(1) if found else "INFO", match["event"], fields)


def _label(node: str) -> str:
    return NODE_DISPLAY_NAMES.get(node, node)


def _ints(events: list[LogEvent], name: str) -> int:
    return sum(v for e in events if isinstance(v := e.fields.get(name), int) and not isinstance(v, bool))


@dataclass
class Report:
    summary: dict[str, Any]
    agents: list[dict[str, Any]]
    llm_calls: list[dict[str, Any]]
    timeline: list[LogEvent]
    truncated: bool


def build_report(events: list[LogEvent]) -> Report:
    """Summary figures, a per-agent table, an LLM-call table and a timeline, from parsed events."""
    events = sorted(events, key=lambda e: e.timestamp_ms)
    calls = [e for e in events if e.event == "llm_call_summary"]
    workflow = [e for e in events if e.event == "workflow_finished"]
    jobs = [e for e in events if e.event in ("job_succeeded", "job_failed")]

    nodes: dict[str, dict[str, Any]] = {}
    for event in (e for e in events if e.event == "node_finished"):
        node = event.fields.get("node")
        if node is None:
            continue
        row = nodes.setdefault(node, {"node": node, "label": _label(node), "runs": 0, "total_ms": 0, "failures": 0, "last_outcome": None})
        row["runs"] += 1
        row["total_ms"] += event.fields.get("duration_ms", 0)
        row["failures"] += 1 if event.fields.get("outcome") == "failure" else 0
        row["last_outcome"] = event.fields.get("outcome")
    spent = sum(row["total_ms"] for row in nodes.values())
    agents = [{**row, "share": round(row["total_ms"] / spent, 3) if spent else 0.0} for row in nodes.values()]

    summary = {
        "attempts": sum(1 for e in events if e.event == "job_started"),
        "job_duration_ms": jobs[-1].fields.get("duration_ms") if jobs else None,
        "workflow_duration_ms": workflow[-1].fields.get("duration_ms") if workflow else None,
        "revisions": workflow[-1].fields.get("revision_count") if workflow else None,
        "approved": workflow[-1].fields.get("approved") if workflow else None,
        "llm_calls": len(calls),
        "llm_failures": sum(1 for e in calls if e.fields.get("outcome") == "failure"),
        "input_tokens": _ints(calls, "input_tokens"),
        "output_tokens": _ints(calls, "output_tokens"),
        "reasoning_tokens": _ints(calls, "reasoning_tokens"),
        "retries": _ints(calls, "app_retries") + _ints(calls, "tool_use_retries") + _ints(calls, "sdk_retries"),
        "rate_limited_responses": _ints(calls, "rate_limited_responses"),
    }

    llm_rows = []
    for e in calls[:MAX_LLM_CALLS]:
        f = e.fields
        llm_rows.append(
            {
                "timestamp_ms": e.timestamp_ms,
                "node": f.get("node"),
                "label": _label(f["node"]) if "node" in f else None,
                "call_type": f.get("call_type"),
                "provider": f.get("provider"),
                "model": f.get("model"),
                "outcome": f.get("outcome"),
                "total_ms": f.get("total_ms"),
                "input_tokens": f.get("input_tokens"),
                "output_tokens": f.get("output_tokens"),
                "reasoning_tokens": f.get("reasoning_tokens"),
                "retries": sum(f.get(k, 0) for k in ("app_retries", "tool_use_retries", "sdk_retries")),
                "rate_limited_responses": f.get("rate_limited_responses", 0),
                "finish_reason": f.get("finish_reason"),
                "provider_status": f.get("provider_status"),
                "error_type": f.get("error_type"),
            }
        )
    return Report(
        summary=summary,
        agents=agents,
        llm_calls=llm_rows,
        timeline=events[:MAX_TIMELINE],
        truncated=len(events) > MAX_TIMELINE or len(calls) > MAX_LLM_CALLS,
    )

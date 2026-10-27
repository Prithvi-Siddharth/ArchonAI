"""Tests for structured logging and execution timing (graph/observability.py).

Exact durations are checked against a fake clock, never real time. Full
workflow and job runs use the mocked LLM layer from test_graph.py, so no
Groq key or network access is needed.
"""

from __future__ import annotations

import logging

import httpx
import pytest
from groq import RateLimitError

from agents import llm as llm_module
from graph import observability
from graph.observability import job_context, log_event, timed_node
from graph.workflow import ALL_NODES_IN_ORDER, ARCHITECTURE_REVISION, WorkflowError, run_workflow
from jobs import db, repository
from jobs.runner import execute_job

from .test_api import SECRET_DETAIL, _raise_from_llm
from .test_graph import _patch_llm

USER_REQUEST = "Design a private payroll system for ACME-CONFIDENTIAL with 10,000 users."


@pytest.fixture
def job_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.reset_engine()
    yield
    db.reset_engine()


@pytest.fixture
def fake_clock(monkeypatch):
    """Make the monotonic clock return the given readings in order."""

    def install(*readings: float) -> None:
        values = iter(readings)
        monkeypatch.setattr(observability, "_clock", lambda: next(values))

    return install


def _events(caplog, name: str) -> list[dict]:
    return [r.event_fields for r in caplog.records if getattr(r, "event_fields", {}).get("event") == name]


def _records(caplog, name: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event_fields", {}).get("event") == name]


# --- Timing a single node (exact durations via the fake clock) ---------------------


def test_timed_node_logs_success_and_duration(caplog, fake_clock):
    caplog.set_level(logging.INFO)
    fake_clock(10.0, 10.25)
    node = timed_node("compute_agent", lambda state: {"compute_analysis": "ok"})

    result = node({"revision_count": 0})

    assert result == {"compute_analysis": "ok"}  # the node's return value is untouched
    (event,) = _events(caplog, "node_finished")
    assert event == {
        "event": "node_finished",
        "node": "compute_agent",
        "iteration": 0,
        "outcome": "success",
        "duration_ms": 250,
    }
    assert caplog.records[-1].getMessage() == (
        "event=node_finished node=compute_agent iteration=0 outcome=success duration_ms=250"
    )


def test_timed_node_logs_failure_and_reraises(caplog, fake_clock):
    caplog.set_level(logging.INFO)
    fake_clock(5.0, 6.5)

    def broken(state):
        raise ValueError(SECRET_DETAIL)

    with pytest.raises(ValueError):
        timed_node("database_agent", broken)({"revision_count": 1})

    (record,) = _records(caplog, "node_finished")
    assert record.levelno == logging.WARNING
    assert record.event_fields["outcome"] == "failure"
    assert record.event_fields["error_type"] == "ValueError"
    assert record.event_fields["duration_ms"] == 1500
    assert record.event_fields["iteration"] == 1
    assert SECRET_DETAIL not in caplog.text  # exception type only, never its message


# --- Event formatting and job context ----------------------------------------------


def test_log_event_formats_fields_and_adds_job_id_from_context(caplog):
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test.observability")

    log_event(logger, "outside", flag=True)
    with job_context("job-123"):
        log_event(logger, "inside", reason="two words", skipped=None, flag=False)

    outside, inside = caplog.records
    assert outside.getMessage() == "event=outside flag=true"
    assert inside.getMessage() == 'event=inside job_id=job-123 reason="two words" flag=false'
    assert "skipped" not in inside.event_fields  # None values are omitted


# --- Whole workflow (mocked LLM) ---------------------------------------------------


def test_workflow_logs_every_node_including_parallel_ones(caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    _patch_llm(monkeypatch, critic_verdicts=[True])

    with job_context("job-abc"):
        run_workflow(USER_REQUEST)

    nodes = _events(caplog, "node_finished")
    # Approved on the first review, so every node except revision runs exactly once.
    expected = [n for n in ALL_NODES_IN_ORDER if n != ARCHITECTURE_REVISION]
    assert sorted(e["node"] for e in nodes) == sorted(expected)
    # Parallel nodes run in LangGraph's worker threads; they still get the job id.
    for event in nodes:
        assert event["job_id"] == "job-abc"
        assert event["outcome"] == "success"
        assert isinstance(event["duration_ms"], int) and event["duration_ms"] >= 0

    (finished,) = _events(caplog, "workflow_finished")
    assert finished["outcome"] == "success"
    assert finished["job_id"] == "job-abc"
    assert finished["approved"] is True
    assert USER_REQUEST not in caplog.text


def test_failed_workflow_logs_failing_node_and_failure_outcome(caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    _raise_from_llm(monkeypatch, llm_module.LLMInvocationError(SECRET_DETAIL))

    with pytest.raises(WorkflowError):
        run_workflow(USER_REQUEST)

    (node,) = _events(caplog, "node_finished")  # the first node fails; nothing else runs
    assert node["node"] == "requirements_analyzer"
    assert node["outcome"] == "failure"
    assert node["error_type"] == "LLMInvocationError"
    (finished,) = _events(caplog, "workflow_finished")
    assert finished["outcome"] == "failure"
    assert finished["error_type"] == "LLMInvocationError"
    assert SECRET_DETAIL not in caplog.text


# --- Background jobs ----------------------------------------------------------------


def test_successful_job_logs_start_and_completion_with_job_id(caplog, monkeypatch, job_db):
    caplog.set_level(logging.INFO)
    _patch_llm(monkeypatch, critic_verdicts=[True])
    job_id = repository.create_job(USER_REQUEST)

    execute_job(job_id)

    (started,) = _events(caplog, "job_started")
    assert started == {"event": "job_started", "job_id": job_id, "attempt": 1, "redelivered": False}
    (succeeded,) = _events(caplog, "job_succeeded")
    assert succeeded["job_id"] == job_id
    assert isinstance(succeeded["duration_ms"], int)
    # Every event logged during the job -- including node timings -- carries its id.
    assert {r.event_fields.get("job_id") for r in caplog.records if hasattr(r, "event_fields")} == {job_id}
    assert USER_REQUEST not in caplog.text


def test_failed_job_logs_failure_without_sensitive_details(caplog, monkeypatch, job_db):
    caplog.set_level(logging.INFO)
    _raise_from_llm(monkeypatch, llm_module.MissingAPIKeyError(SECRET_DETAIL))
    job_id = repository.create_job(USER_REQUEST)

    execute_job(job_id, allow_retry=True)

    (record,) = _records(caplog, "job_failed")
    assert record.levelno == logging.ERROR
    assert record.event_fields["job_id"] == job_id
    assert record.event_fields["status_code"] == 503
    assert record.event_fields["error_type"] == "MissingAPIKeyError"
    assert record.event_fields["will_retry"] is False  # a missing key is never retried
    assert _events(caplog, "job_succeeded") == []
    assert SECRET_DETAIL not in caplog.text
    assert USER_REQUEST not in caplog.text


def test_temporary_job_failure_is_logged_as_will_retry(caplog, monkeypatch, job_db):
    caplog.set_level(logging.INFO)
    request = httpx.Request("POST", "https://api.groq.com")
    _raise_from_llm(monkeypatch, RateLimitError("rate limited", response=httpx.Response(429, request=request), body=None))
    job_id = repository.create_job(USER_REQUEST)

    execute_job(job_id, allow_retry=True)

    (record,) = _records(caplog, "job_failed")
    assert record.levelno == logging.WARNING
    assert record.event_fields["status_code"] == 429
    assert record.event_fields["will_retry"] is True

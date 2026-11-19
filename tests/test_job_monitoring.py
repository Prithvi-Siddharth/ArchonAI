"""Job monitoring: parsing a job's CloudWatch log lines, the report built from them, and the endpoint.

CloudWatch is replaced by a fake client that records every call. No AWS account, network or
LLM is involved; jobs are written straight to an in-memory store.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi.testclient import TestClient
from sqlalchemy import update

import api.routes.monitoring as monitoring_route
from api.main import app
from auth import passwords
from graph import cloudwatch_reader
from graph.observability import _format_value, job_context, log_event
from jobs import db, repository
from jobs.models import ArchitectureJob, JobStatus, utcnow
from jobs.monitoring import MAX_LLM_CALLS, MAX_TIMELINE, RawEvent, build_report, parse_event

TEST_SECRET = "test-secret-" + "x" * 40
JOB = "11111111-2222-3333-4444-555555555555"
BASE_MS = 1_700_000_000_000


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("CLOUDWATCH_ENABLED", "true")  # the reader is only used when logging is on
    monkeypatch.setattr(passwords, "SCRYPT_N", 2**10)
    monkeypatch.setattr(passwords, "SCRYPT_P", 1)
    db.reset_engine()
    monitoring_route.clear_cache()
    cloudwatch_reader.reset_client()
    yield
    db.reset_engine()
    monitoring_route.clear_cache()
    cloudwatch_reader.reset_client()


def _line(event: str, level: str = "INFO", logger: str = "graph.observability", job_id: str = JOB, **fields: Any) -> str:
    """A log line exactly as the CloudWatch handler formats it ("%(levelname)s %(name)s: %(message)s")."""
    pairs = " ".join(f"{k}={_format_value(v)}" for k, v in {"job_id": job_id, **fields}.items() if v is not None)
    return f"{level} {logger}: event={event} {pairs}"


def _raw(event: str, offset_s: float = 0, service: str = "worker", **kw) -> RawEvent:
    job_id = kw.get("job_id", JOB)
    return RawEvent(BASE_MS + int(offset_s * 1000), service, _line(event, **kw) if job_id else _line(event, **kw))


def _parsed(*raws: RawEvent):
    return [e for e in (parse_event(r, JOB) for r in raws) if e is not None]


# --- Parsing -----------------------------------------------------------------------------


def test_lines_written_by_the_real_log_event_are_understood():
    captured: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record):
            captured.append(logging.Formatter("%(levelname)s %(name)s: %(message)s").format(record))

    logger = logging.getLogger("agents.llm.test_probe")
    logger.setLevel(logging.INFO)
    handler = Capture()
    logger.addHandler(handler)
    try:
        with job_context(JOB):
            log_event(
                logger, "llm_call_summary", logging.WARNING, call_id="abc123", node="compute_agent", call_type="structured",
                provider="groq", model="qwen/qwen3.8-27b", outcome="failure", total_ms=4120, sdk_retries="unavailable",
                input_tokens=900, output_tokens=120, reasoning_tokens=30, rate_limited_responses=2, rate_limit_types="TPM,RPM",
                finish_reason="stop", app_retries=1,
            )
    finally:
        logger.removeHandler(handler)

    event = parse_event(RawEvent(BASE_MS, "worker", captured[0]), JOB)
    assert event is not None
    assert (event.event, event.level, event.service) == ("llm_call_summary", "WARNING", "worker")
    assert event.fields["node"] == "compute_agent" and event.fields["model"] == "qwen/qwen3.8-27b"
    assert event.fields["total_ms"] == 4120 and event.fields["rate_limit_types"] == "TPM,RPM"
    assert "sdk_retries" not in event.fields  # "unavailable" is not a number, so it is left out


@pytest.mark.parametrize(
    "prefix, level",
    [
        ("WARNING graph.observability: ", "WARNING"),  # what the CloudWatch handler writes
        ("[2026-11-14 18:06:19,437: WARNING/ForkPoolWorker-1] ", "WARNING"),  # Celery's own console format (real worker logs)
        ("2026-11-19 12:55:52,350 WARNING agents.llm: ", "WARNING"),  # logging.basicConfig's format
        ("worker-1  | [2026-11-14 18:06:19,437: WARNING/ForkPoolWorker-1] ", "WARNING"),  # as printed by docker compose logs
        ("", "INFO"),  # no prefix at all
        ("some framework text without a level ", "INFO"),
    ],
)
def test_the_line_prefix_can_be_in_any_logging_format(prefix, level):
    message = f"{prefix}event=node_finished job_id={JOB} node=compute_agent iteration=0 outcome=success duration_ms=1964"
    event = parse_event(RawEvent(BASE_MS, "worker", message), JOB)
    assert event is not None
    assert (event.level, event.event, event.fields["node"], event.fields["duration_ms"]) == (level, "node_finished", "compute_agent", 1964)


def test_a_word_that_looks_like_a_level_inside_a_value_is_not_the_level():
    message = f"INFO x: event=job_skipped job_id={JOB} reason=ERROR status=running"
    event = parse_event(RawEvent(BASE_MS, "worker", message), JOB)
    assert event is not None and event.level == "INFO" and event.fields["reason"] == "ERROR"


def test_a_quoted_value_is_read_back_as_one_word():
    event = parse_event(RawEvent(BASE_MS, "worker", _line("job_skipped", reason="not queued", status="running")), JOB)
    assert event is not None and event.fields == {"status": "running"}  # "not queued" has a space: dropped


def test_unknown_events_and_other_jobs_are_ignored():
    assert parse_event(RawEvent(BASE_MS, "api", _line("cloudwatch_enabled", service="api")), JOB) is None
    assert parse_event(RawEvent(BASE_MS, "api", "INFO root: nothing structured here"), JOB) is None
    assert parse_event(RawEvent(BASE_MS, "worker", _line("node_finished", job_id="99999999-aaaa-bbbb-cccc-dddddddddddd", node="x")), JOB) is None


def test_only_allow_listed_fields_survive_and_odd_values_are_dropped():
    line = _line(
        "node_finished", node="compute_agent", duration_ms=12.5, outcome="success",
        prompt="Design a bank for secret-customer", api_key="gsk_SECRET1234567890", error_type='bad "quote"',
    )
    event = parse_event(RawEvent(BASE_MS, "worker", line), JOB)
    assert event is not None
    assert event.fields == {"node": "compute_agent", "outcome": "success"}  # float duration, quoted junk: dropped
    assert "secret" not in repr(event).lower()


def test_ints_bools_and_levels():
    ok = parse_event(RawEvent(BASE_MS, "worker", _line("job_failed", level="ERROR", attempt=2, status_code=429, will_retry=True, duration_ms=-5)), JOB)
    assert ok is not None and ok.level == "ERROR"
    assert (ok.fields["attempt"], ok.fields["status_code"], ok.fields["will_retry"]) == (2, 429, True)
    bad = parse_event(RawEvent(BASE_MS, "worker", _line("job_failed", attempt="abc", will_retry="maybe", status_code=99999999999999)), JOB)
    assert bad is not None and bad.fields == {}
    no_level = parse_event(RawEvent(BASE_MS, "worker", f"event=job_started job_id={JOB} attempt=1"), JOB)
    assert no_level is not None and no_level.level == "INFO"


# --- Report ------------------------------------------------------------------------------


def _story():
    return _parsed(
        _raw("job_started", 0, attempt=1),
        _raw("workflow_started", 1),
        _raw("node_finished", 5, node="requirements_analyzer", iteration=0, outcome="success", duration_ms=4000),
        _raw("llm_call_summary", 5, node="requirements_analyzer", call_type="structured", provider="groq", model="m1", outcome="success", total_ms=3900, input_tokens=500, output_tokens=100, reasoning_tokens=20, app_retries=0, rate_limited_responses=0, finish_reason="stop"),
        _raw("node_finished", 12, node="compute_agent", iteration=0, outcome="success", duration_ms=6000),
        _raw("node_finished", 12, node="database_agent", iteration=0, outcome="success", duration_ms=2000),
        _raw("llm_call_summary", 12, node="compute_agent", call_type="structured", provider="groq", model="m1", outcome="success", total_ms=5900, input_tokens=700, output_tokens=300, app_retries=1, tool_use_retries=1, sdk_retries=2, rate_limited_responses=1),
        _raw("llm_call_summary", 13, level="WARNING", node="database_agent", call_type="structured", provider="groq", model="m1", outcome="failure", total_ms=1900, provider_status=429, error_type="RateLimitError"),
        _raw("node_finished", 30, node="architecture_critic", iteration=0, outcome="success", duration_ms=3000),
        _raw("node_finished", 40, node="architecture_critic", iteration=1, outcome="failure", duration_ms=1000, error_type="LLMInvocationError"),
        _raw("workflow_finished", 41, outcome="success", approved=True, revision_count=1, duration_ms=40000),
        _raw("job_succeeded", 41, attempt=1, duration_ms=41000),
    )


def test_the_summary_is_worked_out_from_the_events():
    summary = build_report(_story()).summary
    assert summary == {
        "attempts": 1, "job_duration_ms": 41000, "workflow_duration_ms": 40000, "revisions": 1, "approved": True,
        "llm_calls": 3, "llm_failures": 1, "input_tokens": 1200, "output_tokens": 400, "reasoning_tokens": 20,
        "retries": 4, "rate_limited_responses": 1,
    }


def test_agents_are_grouped_in_the_order_they_first_ran_with_a_share_of_the_time():
    agents = build_report(_story()).agents
    assert [a["node"] for a in agents] == ["requirements_analyzer", "compute_agent", "database_agent", "architecture_critic"]
    assert agents[0]["label"] == "Requirements Analyzer"
    critic = agents[3]
    assert (critic["runs"], critic["total_ms"], critic["failures"], critic["last_outcome"]) == (2, 4000, 1, "failure")
    assert sum(a["share"] for a in agents) == pytest.approx(1.0, abs=0.01)
    assert agents[1]["share"] == pytest.approx(6000 / 16000, abs=0.001)


def test_llm_calls_are_listed_with_their_retries_and_errors():
    calls = build_report(_story()).llm_calls
    assert [c["label"] for c in calls] == ["Requirements Analyzer", "Compute Agent", "Database Agent"]
    assert calls[1]["retries"] == 4 and calls[1]["rate_limited_responses"] == 1
    assert (calls[2]["outcome"], calls[2]["provider_status"], calls[2]["error_type"]) == ("failure", 429, "RateLimitError")


def test_the_timeline_is_in_time_order_across_both_services():
    events = _parsed(
        _raw("job_succeeded", 9, service="worker", attempt=1, duration_ms=1),
        _raw("job_started", 0, service="worker", attempt=1),
        _raw("workflow_started", 1, service="api"),
    )
    assert [(e.event, e.service) for e in build_report(events).timeline] == [("job_started", "worker"), ("workflow_started", "api"), ("job_succeeded", "worker")]


def test_an_empty_story_gives_zeros_and_nulls_not_made_up_numbers():
    report = build_report([])
    assert report.summary["llm_calls"] == 0 and report.summary["input_tokens"] == 0
    assert report.summary["job_duration_ms"] is None and report.summary["approved"] is None
    assert report.agents == [] and report.llm_calls == [] and report.timeline == [] and report.truncated is False


def test_big_reports_are_capped_and_say_so():
    many = _parsed(*[_raw("node_finished", i, node="compute_agent", iteration=i, outcome="success", duration_ms=1) for i in range(MAX_TIMELINE + 5)])
    report = build_report(many)
    assert len(report.timeline) == MAX_TIMELINE and report.truncated is True
    assert report.agents[0]["runs"] == MAX_TIMELINE + 5  # the figures still use every event
    calls = _parsed(*[_raw("llm_call_summary", i, node="compute_agent", outcome="success", total_ms=1) for i in range(MAX_LLM_CALLS + 1)])
    assert len(build_report(calls).llm_calls) == MAX_LLM_CALLS


# --- Endpoint ----------------------------------------------------------------------------


class FakeLogs:
    """A CloudWatch Logs client that only allows FilterLogEvents and records every call."""

    def __init__(self, pages: Optional[dict[str, list[dict]]] = None, errors: Optional[dict[str, Exception]] = None):
        self.pages = pages or {}
        self.errors = errors or {}
        self.calls: list[dict] = []

    def filter_log_events(self, **params):
        self.calls.append(params)
        group = params["logGroupName"]
        if group in self.errors:
            raise self.errors[group]
        pages = self.pages.get(group, [{"events": []}])
        index = 0 if "nextToken" not in params else int(params["nextToken"])
        page = dict(pages[index])
        if index + 1 < len(pages):
            page["nextToken"] = str(index + 1)
        return page

    def __getattr__(self, name):  # anything but FilterLogEvents would be a write or a wider read
        raise AssertionError(f"monitoring must only call filter_log_events, not {name}")


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "arn:aws:logs:ap-south-1:123456789012:log-group:/archonai/worker is secret-detail"}}, "FilterLogEvents")


def _events(*raws: RawEvent) -> list[dict]:
    return [{"timestamp": r.timestamp_ms, "message": r.message} for r in raws]


def _signed_in(email: str = "ada@example.com") -> tuple[TestClient, str]:
    client = TestClient(app)
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "test password"})
    assert response.status_code == 201, response.text
    return client, response.json()["id"]


def _job(owner_id, *, status=JobStatus.SUCCEEDED, minutes_ago: float = 60, took_minutes: float = 5) -> str:
    job_id = repository.create_job("Design a blog for 10k users", owner_id=owner_id)
    created = utcnow() - timedelta(minutes=minutes_ago)
    values: dict[str, Any] = {"status": status, "created_at": created, "updated_at": created, "attempts": 1}
    if status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
        values["finished_at"] = created + timedelta(minutes=took_minutes)
    with db.session_scope() as session:
        session.execute(update(ArchitectureJob).where(ArchitectureJob.id == job_id).values(**values))
    return job_id


def _story_for(job_id: str) -> list[dict]:
    global JOB
    raws = [
        RawEvent(BASE_MS, "worker", _line("job_started", job_id=job_id, attempt=1)),
        RawEvent(BASE_MS + 5000, "worker", _line("node_finished", job_id=job_id, node="compute_agent", iteration=0, outcome="success", duration_ms=4000)),
        RawEvent(BASE_MS + 5100, "worker", _line("llm_call_summary", job_id=job_id, node="compute_agent", provider="groq", model="m1", outcome="success", total_ms=3900, input_tokens=500, output_tokens=100)),
        RawEvent(BASE_MS + 9000, "worker", _line("job_succeeded", job_id=job_id, attempt=1, duration_ms=9000)),
    ]
    return _events(*raws)


def _install(monkeypatch, job_id: str, **kwargs) -> FakeLogs:
    fake = FakeLogs(pages={"/archonai/worker": [{"events": _story_for(job_id)}]}, **kwargs)
    monkeypatch.setattr(cloudwatch_reader, "_client", fake)
    return fake


def _get(client: TestClient, job_id: str):
    return client.get(f"/api/v1/architectures/jobs/{job_id}/monitoring")


def test_signed_out_gets_401():
    assert _get(TestClient(app), JOB).status_code == 401


def test_a_job_that_isnt_yours_or_doesnt_exist_is_404_and_aws_is_never_asked(monkeypatch):
    ada, _ = _signed_in("ada@example.com")
    grace, grace_id = _signed_in("grace@example.com")
    graces = _job(grace_id)
    legacy = _job(None)
    fake = FakeLogs()
    monkeypatch.setattr(cloudwatch_reader, "_client", fake)
    for job_id in (graces, legacy, "00000000-0000-0000-0000-000000000000", "not-a-uuid'; drop"):
        response = _get(ada, job_id)
        assert response.status_code == 404 and response.json() == {"detail": "Job not found."}
    assert fake.calls == []


def test_the_owner_gets_the_report(monkeypatch):
    client, user_id = _signed_in()
    job_id = _job(user_id)
    fake = _install(monkeypatch, job_id)

    response = _get(client, job_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "ok" and body["job_status"] == "succeeded" and body["message"] is None
    assert body["summary"]["llm_calls"] == 1 and body["summary"]["input_tokens"] == 500 and body["summary"]["job_duration_ms"] == 9000
    assert [a["label"] for a in body["agents"]] == ["Compute Agent"]
    assert body["llm_calls"][0]["model"] == "m1" and body["llm_calls"][0]["label"] == "Compute Agent"
    assert [e["event"] for e in body["timeline"]] == ["job_started", "node_finished", "llm_call_summary", "job_succeeded"]
    assert body["timeline"][0]["service"] == "worker" and body["timeline"][0]["fields"] == {"attempt": 1}
    assert body["may_still_arrive"] is False and body["truncated"] is False
    assert {c["logGroupName"] for c in fake.calls} == {"/archonai/worker", "/archonai/api"}


def test_the_search_is_for_exactly_this_job_in_a_window_around_its_run(monkeypatch):
    client, user_id = _signed_in()
    job_id = _job(user_id, minutes_ago=60, took_minutes=5)
    fake = _install(monkeypatch, job_id)
    _get(client, job_id)

    call = fake.calls[0]
    assert call["filterPattern"] == f'"job_id={job_id}"'
    with db.session_scope() as session:
        job = session.get(ArchitectureJob, job_id)
    created_ms = int(job.created_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
    finished_ms = int(job.finished_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
    assert call["startTime"] == created_ms - 2 * 60 * 1000
    assert call["endTime"] == finished_ms + 10 * 60 * 1000


def test_a_running_job_is_marked_as_still_changing(monkeypatch):
    client, user_id = _signed_in()
    job_id = _job(user_id, status=JobStatus.RUNNING, minutes_ago=3)
    _install(monkeypatch, job_id)
    body = _get(client, job_id).json()
    assert body["job_status"] == "running" and body["may_still_arrive"] is True and body["finished_at"] is None


def test_a_job_that_just_finished_may_still_get_lines(monkeypatch):
    client, user_id = _signed_in()
    job_id = _job(user_id, minutes_ago=3, took_minutes=2)  # finished about a minute ago
    _install(monkeypatch, job_id)
    assert _get(client, job_id).json()["may_still_arrive"] is True


def test_every_page_is_read_and_the_total_is_capped(monkeypatch):
    client, user_id = _signed_in()
    job_id = _job(user_id)
    story = _story_for(job_id)
    fake = FakeLogs(pages={"/archonai/worker": [{"events": story[:2]}, {"events": story[2:]}]})
    monkeypatch.setattr(cloudwatch_reader, "_client", fake)
    body = _get(client, job_id).json()
    assert [e["event"] for e in body["timeline"]] == ["job_started", "node_finished", "llm_call_summary", "job_succeeded"]
    assert sum(1 for c in fake.calls if c["logGroupName"] == "/archonai/worker") == 2
    assert [c["nextToken"] for c in fake.calls if "nextToken" in c] == ["1"]  # the second page was asked for with the token

    monitoring_route.clear_cache()
    monkeypatch.setattr(cloudwatch_reader, "MAX_EVENTS", 3)
    fake2 = FakeLogs(pages={"/archonai/worker": [{"events": story[:2]}, {"events": story[2:]}]})
    monkeypatch.setattr(cloudwatch_reader, "_client", fake2)
    assert len(_get(client, job_id).json()["timeline"]) == 3


def test_a_missing_log_group_is_not_an_error(monkeypatch):
    client, user_id = _signed_in()
    job_id = _job(user_id)
    fake = FakeLogs(pages={"/archonai/worker": [{"events": _story_for(job_id)}]}, errors={"/archonai/api": _client_error("ResourceNotFoundException")})
    monkeypatch.setattr(cloudwatch_reader, "_client", fake)
    assert _get(client, job_id).json()["state"] == "ok"

    monitoring_route.clear_cache()
    both = FakeLogs(errors={"/archonai/api": _client_error("ResourceNotFoundException"), "/archonai/worker": _client_error("ResourceNotFoundException")})
    monkeypatch.setattr(cloudwatch_reader, "_client", both)
    body = _get(client, job_id).json()
    assert body["state"] == "empty" and "No log lines were found" in body["message"] and body["summary"] is None


def test_no_lines_for_this_job_is_empty(monkeypatch):
    client, user_id = _signed_in()
    job_id = _job(user_id)
    monkeypatch.setattr(cloudwatch_reader, "_client", FakeLogs())
    body = _get(client, job_id).json()
    assert body["state"] == "empty" and body["timeline"] == [] and body["agents"] == []


def test_lines_of_other_jobs_that_match_the_search_are_ignored(monkeypatch):
    client, user_id = _signed_in()
    job_id = _job(user_id)
    other = _events(RawEvent(BASE_MS, "worker", _line("node_finished", job_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", node="compute_agent", outcome="success", duration_ms=1)))
    monkeypatch.setattr(cloudwatch_reader, "_client", FakeLogs(pages={"/archonai/worker": [{"events": other}]}))
    assert _get(client, job_id).json()["state"] == "empty"


def test_nothing_but_allow_listed_fields_reaches_the_response(monkeypatch):
    client, user_id = _signed_in()
    job_id = _job(user_id)
    risky = _events(
        RawEvent(BASE_MS, "worker", _line("node_finished", job_id=job_id, node="compute_agent", outcome="success", duration_ms=5, prompt="TOP-SECRET-PROMPT", api_key="gsk_LEAKED1234567890", user_request="Design a bank for Mr Smith")),
        RawEvent(BASE_MS + 1, "worker", _line("llm_call_summary", job_id=job_id, node="compute_agent", provider="groq with spaces and TOP-SECRET-PROVIDER", model="m1", outcome="success", total_ms=5)),
        RawEvent(BASE_MS + 2, "worker", f"ERROR agents.llm: Traceback TOP-SECRET-TRACE job_id={job_id}"),
    )
    monkeypatch.setattr(cloudwatch_reader, "_client", FakeLogs(pages={"/archonai/worker": [{"events": risky}]}))
    text = _get(client, job_id).text
    for secret in ("TOP-SECRET", "gsk_LEAKED", "Mr Smith", "Traceback", "api_key", "user_request", "prompt"):
        assert secret not in text, secret


def test_only_the_read_call_is_ever_made(monkeypatch):
    client, user_id = _signed_in()
    job_id = _job(user_id)
    fake = _install(monkeypatch, job_id)  # any other client method raises AssertionError
    assert _get(client, job_id).status_code == 200
    assert {tuple(sorted(c)) for c in fake.calls} <= {tuple(sorted(["logGroupName", "startTime", "endTime", "filterPattern", "limit"])), tuple(sorted(["logGroupName", "startTime", "endTime", "filterPattern", "limit", "nextToken"]))}


@pytest.mark.parametrize(
    "error, state",
    [
        (_client_error("AccessDeniedException"), "forbidden"),
        (_client_error("ThrottlingException"), "throttled"),
        (_client_error("InternalFailure"), "unreachable"),
        (EndpointConnectionError(endpoint_url="https://logs.ap-south-1.amazonaws.com"), "unreachable"),
    ],
)
def test_failures_become_a_short_reason_without_aws_details(monkeypatch, caplog, error, state):
    client, user_id = _signed_in()
    job_id = _job(user_id)
    monkeypatch.setattr(cloudwatch_reader, "_client", FakeLogs(errors={"/archonai/worker": error, "/archonai/api": error}))
    with caplog.at_level(logging.DEBUG):
        response = _get(client, job_id)
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == state and body["message"] and body["summary"] is None
    for leaked in ("123456789012", "arn:aws", "secret-detail", "amazonaws.com"):
        assert leaked not in response.text and leaked not in caplog.text, leaked
    if state == "forbidden":
        assert "logs-read policy" in body["message"]


def test_without_credentials_the_reason_is_no_credentials(monkeypatch):
    import boto3

    client, user_id = _signed_in()
    job_id = _job(user_id)
    monkeypatch.setattr(boto3.session.Session, "get_credentials", lambda self: None)
    body = _get(client, job_id).json()
    assert body["state"] == "no_credentials"


def test_when_cloudwatch_logging_is_off_nothing_is_asked(monkeypatch):
    client, user_id = _signed_in()
    job_id = _job(user_id)
    fake = _install(monkeypatch, job_id)
    monkeypatch.setenv("CLOUDWATCH_ENABLED", "false")
    body = _get(client, job_id).json()
    assert body["state"] == "disabled" and "switched off" in body["message"]
    assert fake.calls == []


def test_failed_reads_are_not_cached_but_good_ones_are(monkeypatch):
    client, user_id = _signed_in()
    job_id = _job(user_id)
    broken = FakeLogs(errors={"/archonai/worker": _client_error("ThrottlingException"), "/archonai/api": _client_error("ThrottlingException")})
    monkeypatch.setattr(cloudwatch_reader, "_client", broken)
    assert _get(client, job_id).json()["state"] == "throttled"

    fake = _install(monkeypatch, job_id)
    assert _get(client, job_id).json()["state"] == "ok"  # asked again straight away
    after_first = len(fake.calls)
    assert _get(client, job_id).json()["state"] == "ok"
    assert len(fake.calls) == after_first  # the second good answer came from the cache


def test_the_cache_lasts_longer_for_a_finished_job_than_a_live_one(monkeypatch):
    client, user_id = _signed_in()
    settled = _job(user_id, minutes_ago=600, took_minutes=5)
    live = _job(user_id, status=JobStatus.RUNNING, minutes_ago=3)
    clock = {"now": 1000.0}
    monkeypatch.setattr(monitoring_route.time, "monotonic", lambda: clock["now"])
    fake = FakeLogs(pages={"/archonai/worker": [{"events": _story_for(settled) + _story_for(live)}]})
    monkeypatch.setattr(cloudwatch_reader, "_client", fake)

    def asks() -> int:
        return len(fake.calls)

    _get(client, settled), _get(client, live)
    base = asks()
    clock["now"] += 5  # within the live job's cache time
    _get(client, settled), _get(client, live)
    assert asks() == base
    clock["now"] += 10  # past 8 s: the live job is asked again, the finished one is not
    _get(client, settled), _get(client, live)
    assert asks() == base + 2
    clock["now"] += 400  # past 5 minutes: the finished job is asked again too
    _get(client, settled)
    assert asks() == base + 4


def test_one_users_cached_report_is_never_given_to_another(monkeypatch):
    ada, ada_id = _signed_in("ada@example.com")
    grace, _ = _signed_in("grace@example.com")
    job_id = _job(ada_id)
    _install(monkeypatch, job_id)
    assert _get(ada, job_id).status_code == 200  # now cached
    assert _get(grace, job_id).status_code == 404


def test_a_database_outage_is_503_without_details(monkeypatch, caplog):
    client, _ = _signed_in()

    def broken(*args, **kwargs):
        from sqlalchemy.exc import OperationalError

        raise OperationalError("SELECT secret-statement", {}, Exception("driver-detail"))

    monkeypatch.setattr(repository, "get_owned_job", broken)
    with caplog.at_level(logging.DEBUG):
        response = _get(client, JOB)
    assert response.status_code == 503
    assert response.json() == {"detail": "Job store is unavailable. Please retry later."}
    assert "secret-statement" not in caplog.text and "driver-detail" not in caplog.text


def test_the_iam_policy_only_allows_reading_the_two_log_groups():
    import json
    from pathlib import Path

    policy = json.loads(Path("monitoring/iam/archonai-logs-read-policy.json").read_text())
    (statement,) = policy["Statement"]
    assert statement["Effect"] == "Allow" and statement["Action"] == "logs:FilterLogEvents"
    assert all(arn.endswith(("/archonai/api:*", "/archonai/worker:*")) for arn in statement["Resource"])

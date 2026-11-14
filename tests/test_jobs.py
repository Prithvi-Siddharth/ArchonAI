"""Tests for the background job system (jobs/ + the /jobs endpoints).

Nothing external is needed: the job store is in-memory SQLite (via
DATABASE_URL), Celery runs tasks eagerly inside the test instead of through
Redis and a worker, and the LLM layer is mocked exactly as in test_graph.py.
"""

from __future__ import annotations

import httpx
import pytest
from celery.exceptions import SoftTimeLimitExceeded
from fastapi.testclient import TestClient
from groq import RateLimitError
from kombu.exceptions import OperationalError

from agents import llm as llm_module
from graph.state import MAX_REVISIONS
from api.main import app
from jobs import db, repository
from jobs.celery_app import celery_app
from jobs.models import JobStatus
from jobs.runner import execute_job
from jobs.tasks import run_architecture_job

from .test_api import SECRET_DETAIL, _raise_from_llm
from .test_graph import _patch_llm

client = TestClient(app)

JOBS_URL = "/api/v1/architectures/jobs"
VALID_BODY = {"user_request": "Design a blogging platform for 10,000 users."}

_REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


@pytest.fixture(autouse=True)
def job_env(monkeypatch):
    """Fresh in-memory job store and eager Celery for every test."""
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JOB_MAX_RETRIES", "1")
    db.reset_engine()
    previous = (celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates)
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    yield
    celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates = previous
    db.reset_engine()


def _rate_limit_error() -> RateLimitError:
    return RateLimitError(SECRET_DETAIL, response=httpx.Response(429, request=_REQUEST), body=None)


def _fail_first_llm_call_then_succeed(monkeypatch, exc: BaseException) -> None:
    """The first structured LLM call raises `exc`; every later call succeeds."""
    _patch_llm(monkeypatch, critic_verdicts=[True])
    succeed = llm_module.invoke_structured
    state = {"raised": False}

    def flaky(llm, schema, prompt):
        if not state["raised"]:
            state["raised"] = True
            raise exc
        return succeed(llm, schema, prompt)

    monkeypatch.setattr(llm_module, "invoke_structured", flaky)


def _submit() -> str:
    response = client.post(JOBS_URL, json=VALID_BODY)
    assert response.status_code == 202, response.text
    return response.json()["job_id"]


# --- Submission & status lookup ---------------------------------------------------


def test_submit_returns_202_with_job_id_and_stores_queued_job(monkeypatch):
    # Don't run the job: this test is only about what submission stores and returns.
    monkeypatch.setattr(run_architecture_job, "apply_async", lambda *args, **kwargs: None)

    response = client.post(JOBS_URL, json=VALID_BODY)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["status_url"] == f"{JOBS_URL}/{body['job_id']}"
    job = repository.get_job(body["job_id"])
    assert job.status is JobStatus.QUEUED
    assert job.user_request == VALID_BODY["user_request"]
    assert job.attempts == 0


def test_submitted_request_is_stored_without_surrounding_whitespace(monkeypatch):
    monkeypatch.setattr(run_architecture_job, "apply_async", lambda *args, **kwargs: None)

    response = client.post(JOBS_URL, json={"user_request": "   Design a blog for 10k users   "})

    assert repository.get_job(response.json()["job_id"]).user_request == "Design a blog for 10k users"


@pytest.mark.parametrize(
    "body",
    [
        {"user_request": ""},
        {"user_request": "   "},
        {"user_request": "short"},
        {"user_request": "x" * 4001},
        {"user_request": 12345},
        {},
    ],
)
def test_invalid_submission_is_rejected_and_nothing_is_stored(monkeypatch, body):
    def must_not_be_called(*args, **kwargs):
        raise AssertionError("no job should be stored for invalid input")

    monkeypatch.setattr(repository, "create_job", must_not_be_called)

    assert client.post(JOBS_URL, json=body).status_code == 422


def test_unknown_job_id_returns_404():
    response = client.get(f"{JOBS_URL}/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found."}


# --- Successful execution ---------------------------------------------------------


def test_successful_job_stores_and_returns_full_result(monkeypatch):
    _patch_llm(monkeypatch, critic_verdicts=[True])

    job_id = _submit()
    response = client.get(f"{JOBS_URL}/{job_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "succeeded"
    assert data["attempts"] == 1
    assert data["error"] is None
    assert data["started_at"] and data["finished_at"]
    assert data["created_at"].endswith("Z")  # stored as naive UTC, returned marked as UTC
    result = data["result"]
    assert result["approved"] is True
    assert result["architecture"]["services"]
    assert result["final_report"]["executive_summary"]
    assert [entry["node"] for entry in result["execution_trace"]][-1] == "Final Report"


def test_job_result_reports_the_revision_loop(monkeypatch):
    _patch_llm(monkeypatch, critic_verdicts=[False, True])

    result = client.get(f"{JOBS_URL}/{_submit()}").json()["result"]

    assert result["approved"] is True
    assert result["revision_count"] == 1
    assert result["architecture"]["version"] == 2


def test_job_result_flags_max_revisions_reached(monkeypatch):
    _patch_llm(monkeypatch, critic_verdicts=[False])

    data = client.get(f"{JOBS_URL}/{_submit()}").json()

    # Not being approved is still a successful run: the report lists open items.
    assert data["status"] == "succeeded"
    result = data["result"]
    assert result["approved"] is False
    assert result["max_revisions_reached"] is True
    assert result["revision_count"] == MAX_REVISIONS
    assert result["critic_review"]["issues"][0]["severity"] == "high"  # enums serialize as plain strings


def test_job_api_never_returns_provider_error_text_from_agent_fallbacks(monkeypatch, caplog):
    """Critic, revision and report all fail with a tool_use_failed error carrying the
    model's failed generation; the job still succeeds via the fallbacks, and neither
    the stored result nor the API response contains any of the provider's text."""
    from groq import APIStatusError

    from models.schemas import Architecture, CriticReview, FinalReport, ReportSynthesis

    leaked = "LEAKED-FAILED-GENERATION"
    body = {"error": {"message": "Failed to call a function.", "code": "tool_use_failed", "failed_generation": leaked}}
    error = APIStatusError(
        f"Error code: 400 - {body}", response=httpx.Response(400, request=_REQUEST), body=body
    )
    real_invoke_structured = llm_module.invoke_structured
    _patch_llm(monkeypatch, critic_verdicts=[True])  # the critic always fails, so revisions run
    mocked = llm_module.invoke_structured

    class _Failing:
        temperature = 0.2

        def with_structured_output(self, schema):
            return self

        def invoke(self, prompt):
            raise error

        def model_copy(self, update):
            return self

    def invoke(llm, schema, prompt):
        from graph.observability import current_node

        failing = schema in (CriticReview, FinalReport, ReportSynthesis) or current_node() == "architecture_revision"
        if failing and not isinstance(llm, _Failing):
            return real_invoke_structured(_Failing(), schema, prompt)
        return mocked(llm, schema, prompt)

    monkeypatch.setattr(llm_module, "invoke_structured", invoke)
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)

    with caplog.at_level("INFO"):
        response = client.get(f"{JOBS_URL}/{_submit()}")

    data = response.json()
    assert data["status"] == "succeeded"
    assert leaked not in response.text and "Error code" not in response.text
    actions = [entry["action"] for entry in data["result"]["execution_trace"]]
    assert any("Critic review call failed (the model's structured answer was incomplete" in a for a in actions)
    assert any(a.startswith("Revision call failed (") for a in actions)
    assert any(a.startswith("LLM synthesis failed (") for a in actions)
    # Internal logs keep the diagnostics (status, code, node, call id), still without the text.
    failures = [r.event_fields for r in caplog.records if getattr(r, "event_fields", {}).get("event") == "llm_call_summary"
                and r.event_fields.get("outcome") == "failure"]
    assert {f["node"] for f in failures} == {"architecture_critic", "architecture_revision", "final_report"}
    assert all(f["provider_status"] == 400 and f["provider_error_code"] == "tool_use_failed" and f["call_id"] for f in failures)
    assert leaked not in caplog.text


# --- Failures and retries ---------------------------------------------------------


def test_permanent_failure_fails_immediately_without_leaking_details(monkeypatch):
    _raise_from_llm(monkeypatch, llm_module.MissingAPIKeyError(SECRET_DETAIL))

    job_id = _submit()
    response = client.get(f"{JOBS_URL}/{job_id}")

    data = response.json()
    assert data["status"] == "failed"
    assert data["attempts"] == 1  # not retried: a missing key won't fix itself
    assert data["error"] == {"status_code": 503, "message": "LLM provider is not configured."}
    assert data["result"] is None
    assert SECRET_DETAIL not in response.text


def test_temporary_failure_is_retried_and_then_succeeds(monkeypatch):
    _fail_first_llm_call_then_succeed(monkeypatch, _rate_limit_error())

    data = client.get(f"{JOBS_URL}/{_submit()}").json()

    assert data["status"] == "succeeded"
    assert data["attempts"] == 2
    assert data["error"] is None  # the earlier retry reason is cleared on success


def test_temporary_failure_fails_once_retries_are_used_up(monkeypatch):
    _raise_from_llm(monkeypatch, _rate_limit_error())

    response = client.get(f"{JOBS_URL}/{_submit()}")

    data = response.json()
    assert data["status"] == "failed"
    assert data["attempts"] == 2  # first try + JOB_MAX_RETRIES=1
    assert data["error"]["status_code"] == 429
    assert SECRET_DETAIL not in response.text


def test_no_retry_when_job_max_retries_is_zero(monkeypatch):
    monkeypatch.setenv("JOB_MAX_RETRIES", "0")
    _raise_from_llm(monkeypatch, _rate_limit_error())

    data = client.get(f"{JOBS_URL}/{_submit()}").json()

    assert data["status"] == "failed"
    assert data["attempts"] == 1


def test_job_over_time_limit_fails_with_504(monkeypatch):
    _raise_from_llm(monkeypatch, SoftTimeLimitExceeded())

    data = client.get(f"{JOBS_URL}/{_submit()}").json()

    assert data["status"] == "failed"
    assert data["attempts"] == 1  # not retried: it would likely run too long again
    assert data["error"] == {"status_code": 504, "message": "Job timed out."}


# --- Crash recovery (runner-level: simulates a redelivery after a worker died) -----


def test_redelivered_job_after_worker_crash_runs_again(monkeypatch):
    _patch_llm(monkeypatch, critic_verdicts=[True])
    job_id = repository.create_job(VALID_BODY["user_request"])
    repository.mark_running(job_id)  # the attempt whose worker then crashed

    execute_job(job_id, redelivered=True)

    job = repository.get_job(job_id)
    assert job.status is JobStatus.SUCCEEDED
    assert job.attempts == 2


def test_job_that_keeps_crashing_its_worker_eventually_fails(monkeypatch):
    _patch_llm(monkeypatch, critic_verdicts=[True])
    job_id = repository.create_job(VALID_BODY["user_request"])
    repository.mark_running(job_id)  # attempt 1, crashed
    repository.mark_resumed(job_id)  # attempt 2, crashed too

    execute_job(job_id, redelivered=True)

    job = repository.get_job(job_id)
    assert job.status is JobStatus.FAILED
    assert job.error_status_code == 500
    assert job.attempts == 2


def test_duplicate_delivery_of_a_running_job_is_skipped(monkeypatch):
    def must_not_run(user_request):
        raise AssertionError("a job that is already running must not run twice")

    monkeypatch.setattr("jobs.runner.run_workflow", must_not_run)
    job_id = repository.create_job(VALID_BODY["user_request"])
    repository.mark_running(job_id)

    execute_job(job_id)  # an ordinary (not crash-redelivered) duplicate

    job = repository.get_job(job_id)
    assert job.status is JobStatus.RUNNING
    assert job.attempts == 1


# --- Infrastructure unavailable ---------------------------------------------------


def test_queue_unavailable_returns_503_and_marks_job_failed(monkeypatch):
    def broker_down(*args, **kwargs):
        raise OperationalError("Error 61 connecting to localhost:6379. Connection refused.")

    monkeypatch.setattr(run_architecture_job, "apply_async", broker_down)

    response = client.post(JOBS_URL, json=VALID_BODY)

    assert response.status_code == 503
    assert response.json() == {"detail": "Job queue is unavailable. Please retry later."}
    with db.session_scope() as session:
        from jobs.models import ArchitectureJob

        (job,) = session.query(ArchitectureJob).all()
    assert job.status is JobStatus.FAILED
    assert job.error_status_code == 503


def test_job_store_unavailable_returns_503_but_health_still_works(monkeypatch):
    # Nothing listens on this port, so every database call fails to connect.
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://archon:archon@127.0.0.1:3999/archonai")
    db.reset_engine()

    assert client.post(JOBS_URL, json=VALID_BODY).status_code == 503
    assert client.get(f"{JOBS_URL}/any-id").status_code == 503
    assert client.get("/health").status_code == 200


# --- Guarded status transitions ---------------------------------------------------


def test_finished_job_cannot_change_status_again():
    job_id = repository.create_job(VALID_BODY["user_request"])
    assert repository.mark_running(job_id)
    assert repository.mark_succeeded(job_id, {"approved": True})

    assert not repository.mark_running(job_id)
    assert not repository.mark_resumed(job_id)
    assert not repository.mark_failed(job_id, 500, "x")
    assert not repository.mark_requeued(job_id, 429, "x")
    assert repository.get_job(job_id).status is JobStatus.SUCCEEDED


def test_job_must_start_before_it_can_succeed():
    job_id = repository.create_job(VALID_BODY["user_request"])

    assert not repository.mark_succeeded(job_id, {"approved": True})
    assert repository.get_job(job_id).status is JobStatus.QUEUED

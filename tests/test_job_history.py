"""GET /api/v1/architectures/jobs: the signed-in user's own job history.

In-memory SQLite and a test-only secret; jobs are written straight to the store,
so nothing is queued and no LLM is called.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.exc import OperationalError

from api.main import app
from auth import passwords
from jobs import db, repository
from jobs.models import ArchitectureJob, JobStatus

JOBS_URL = "/api/v1/architectures/jobs"
TEST_SECRET = "test-secret-" + "x" * 40
BASE_TIME = datetime(2026, 11, 1, 9, 0, 0)

REAL_LIKE_RESULT: dict[str, Any] = {
    "approved": False,
    "max_revisions_reached": True,
    "architecture": {"version": 2, "services": [{"name": "A"}, {"name": "B"}, {"name": "C"}]},
    "critic_review": {"score": 68},
    "cost_analysis": {"estimated_monthly_range": "$4,120 - $34,800 per month (educational estimate)"},
}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr(passwords, "SCRYPT_N", 2**10)
    monkeypatch.setattr(passwords, "SCRYPT_P", 1)
    db.reset_engine()
    yield
    db.reset_engine()


def _user(email: str) -> tuple[TestClient, str]:
    client = TestClient(app)
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "test password"})
    assert response.status_code == 201, response.text
    return client, response.json()["id"]


def _job(
    owner_id: Optional[str],
    request: str = "Design a blog for 10k users",
    *,
    minutes: int = 0,
    status: JobStatus = JobStatus.QUEUED,
    result: Optional[dict] = None,
    error: Optional[tuple[int, str]] = None,
    attempts: int = 0,
) -> str:
    """A stored job, created `minutes` after BASE_TIME."""
    job_id = repository.create_job(request, owner_id=owner_id)
    created = BASE_TIME + timedelta(minutes=minutes)
    values: dict[str, Any] = {"status": status, "created_at": created, "updated_at": created, "attempts": attempts, "result": result}
    if status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
        values["finished_at"] = created + timedelta(minutes=5)
    if error:
        values["error_status_code"], values["error_message"] = error
    with db.session_scope() as session:
        session.execute(update(ArchitectureJob).where(ArchitectureJob.id == job_id).values(**values))
    return job_id


def _list(client: TestClient, **params) -> dict:
    response = client.get(JOBS_URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


# --- Access ------------------------------------------------------------------------------


def test_signed_out_gets_401():
    response = TestClient(app).get(JOBS_URL)
    assert response.status_code == 401


def test_empty_history():
    client, _ = _user("ada@example.com")
    assert _list(client) == {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
        "counts": {"queued": 0, "running": 0, "succeeded": 0, "failed": 0},
    }


def test_only_the_callers_jobs_are_listed():
    ada, ada_id = _user("ada@example.com")
    grace, grace_id = _user("grace@example.com")
    mine = _job(ada_id, "Ada's design")
    _job(grace_id, "Grace's design")
    _job(None, "Old job from before accounts")  # unowned legacy job

    body = _list(ada)
    assert [item["job_id"] for item in body["items"]] == [mine]
    assert body["total"] == 1 and sum(body["counts"].values()) == 1
    assert [item["user_request"] for item in _list(grace)["items"]] == ["Grace's design"]
    # Searching can't reach other people's jobs either.
    assert _list(ada, q="Grace")["items"] == []
    assert _list(ada, q="Old job")["items"] == []


def test_a_user_id_parameter_is_ignored_identity_comes_from_the_session():
    ada, ada_id = _user("ada@example.com")
    grace, grace_id = _user("grace@example.com")
    _job(ada_id, "Ada's design")
    assert _list(grace, owner_id=ada_id, user_id=ada_id)["items"] == []


# --- Order and pagination ----------------------------------------------------------------


def test_newest_first_and_pages_cover_every_job_once():
    client, uid = _user("ada@example.com")
    ids = [_job(uid, f"Design number {n}", minutes=n) for n in range(25)]
    newest_first = list(reversed(ids))

    pages = [_list(client, limit=10, offset=offset) for offset in (0, 10, 20)]
    assert [len(p["items"]) for p in pages] == [10, 10, 5]
    assert [item["job_id"] for p in pages for item in p["items"]] == newest_first
    assert {p["total"] for p in pages} == {25}
    assert pages[1]["offset"] == 10 and pages[1]["limit"] == 10


def test_jobs_created_in_the_same_second_never_repeat_across_pages():
    client, uid = _user("ada@example.com")
    ids = {_job(uid, f"Same time {n}", minutes=0) for n in range(7)}
    seen = [item["job_id"] for offset in range(0, 7, 3) for item in _list(client, limit=3, offset=offset)["items"]]
    assert len(seen) == 7 and set(seen) == ids


def test_offset_past_the_end_returns_no_items_but_the_total():
    client, uid = _user("ada@example.com")
    _job(uid)
    body = _list(client, offset=40)
    assert body["items"] == [] and body["total"] == 1


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 51}, {"offset": -1}, {"status": "done"}, {"q": "x" * 201}])
def test_invalid_parameters_are_422(params):
    client, _ = _user("ada@example.com")
    assert client.get(JOBS_URL, params=params).status_code == 422


# --- Filtering and search -----------------------------------------------------------------


def test_status_filter_and_counts():
    client, uid = _user("ada@example.com")
    _job(uid, status=JobStatus.QUEUED, minutes=1)
    _job(uid, status=JobStatus.RUNNING, minutes=2, attempts=1)
    _job(uid, status=JobStatus.SUCCEEDED, minutes=3, result=REAL_LIKE_RESULT, attempts=1)
    _job(uid, status=JobStatus.SUCCEEDED, minutes=4, result=REAL_LIKE_RESULT, attempts=1)
    _job(uid, status=JobStatus.FAILED, minutes=5, error=(429, "Rate limit reached."), attempts=2)

    everything = _list(client)
    assert everything["counts"] == {"queued": 1, "running": 1, "succeeded": 2, "failed": 1}
    assert everything["total"] == 5
    succeeded = _list(client, status="succeeded")
    assert succeeded["total"] == 2 and {i["status"] for i in succeeded["items"]} == {"succeeded"}
    assert succeeded["counts"] == everything["counts"]  # counts ignore the status filter
    assert _list(client, status="running")["total"] == 1


def test_search_by_request_text_case_insensitive():
    client, uid = _user("ada@example.com")
    _job(uid, "Design a VIDEO streaming platform", minutes=1)
    _job(uid, "Design a blog", minutes=2)
    body = _list(client, q="  video Streaming ")
    assert [i["user_request"] for i in body["items"]] == ["Design a VIDEO streaming platform"]
    assert body["counts"]["queued"] == 1  # counts follow the search


def test_search_by_job_id_prefix():
    client, uid = _user("ada@example.com")
    target = _job(uid, "First", minutes=1)
    _job(uid, "Second", minutes=2)
    assert [i["job_id"] for i in _list(client, q=target[:8])["items"]] == [target]
    assert _list(client, q=target[4:12])["items"] == []  # prefix only, not anywhere in the id


def test_search_treats_wildcards_literally():
    client, uid = _user("ada@example.com")
    _job(uid, "Cut costs by 50% with spot", minutes=1)
    _job(uid, "Design a snake_case service", minutes=2)
    _job(uid, "Plain request", minutes=3)
    assert [i["user_request"] for i in _list(client, q="50%")["items"]] == ["Cut costs by 50% with spot"]
    assert [i["user_request"] for i in _list(client, q="_")["items"]] == ["Design a snake_case service"]
    assert _list(client, q="%")["total"] == 1
    assert _list(client, q="/")["total"] == 0


def test_blank_search_is_ignored():
    client, uid = _user("ada@example.com")
    _job(uid)
    assert _list(client, q="   ")["total"] == 1


# --- Row contents --------------------------------------------------------------------------


def test_succeeded_row_has_a_small_summary_not_the_full_result():
    client, uid = _user("ada@example.com")
    job_id = _job(uid, "Design an e-commerce platform", status=JobStatus.SUCCEEDED, result=REAL_LIKE_RESULT, attempts=1)
    (item,) = _list(client)["items"]
    assert item["job_id"] == job_id
    assert item["summary"] == {
        "approved": False,
        "critic_score": 68,
        "architecture_version": 2,
        "aws_service_count": 3,
        "estimated_monthly_range": "$4,120 - $34,800 per month (educational estimate)",
        "max_revisions_reached": True,
    }
    assert "result" not in item and "owner_id" not in item
    assert item["created_at"].endswith("Z") or item["created_at"].endswith("+00:00")
    assert item["finished_at"] is not None and item["error"] is None and item["attempts"] == 1


def test_failed_row_has_its_client_safe_error_and_no_summary():
    client, uid = _user("ada@example.com")
    _job(uid, status=JobStatus.FAILED, error=(502, "The LLM provider returned an invalid response."), attempts=1)
    (item,) = _list(client)["items"]
    assert item["error"] == {"status_code": 502, "message": "The LLM provider returned an invalid response."}
    assert item["summary"] is None


def test_queued_and_running_rows_have_no_summary_or_finish_time():
    client, uid = _user("ada@example.com")
    _job(uid, status=JobStatus.RUNNING, attempts=1)
    (item,) = _list(client)["items"]
    assert (item["status"], item["summary"], item["finished_at"]) == ("running", None, None)


@pytest.mark.parametrize(
    "result, expected",
    [
        ({}, {}),
        ({"approved": "yes", "critic_review": {"score": "high"}, "architecture": {"version": True, "services": "many"}}, {}),
        ({"critic_review": None, "architecture": [], "cost_analysis": "cheap"}, {}),
        ({"approved": True, "critic_review": {"score": 90}}, {"approved": True, "critic_score": 90}),
    ],
)
def test_summary_tolerates_partial_or_odd_stored_results(result, expected):
    client, uid = _user("ada@example.com")
    _job(uid, status=JobStatus.SUCCEEDED, result=result)
    (item,) = _list(client)["items"]
    nulls = dict.fromkeys(
        ["approved", "critic_score", "architecture_version", "aws_service_count", "estimated_monthly_range", "max_revisions_reached"]
    )
    assert item["summary"] == {**nulls, **expected}


def test_succeeded_without_a_stored_result_has_an_all_null_summary_omitted():
    client, uid = _user("ada@example.com")
    _job(uid, status=JobStatus.SUCCEEDED, result=None)
    assert _list(client)["items"][0]["summary"] is None


def test_empty_request_text_is_returned_as_is():
    client, uid = _user("ada@example.com")
    _job(uid, "")
    assert _list(client)["items"][0]["user_request"] == ""


def test_job_status_endpoint_now_includes_the_request_text():
    client, uid = _user("ada@example.com")
    job_id = _job(uid, "  kept exactly  ")
    assert client.get(f"{JOBS_URL}/{job_id}").json()["user_request"] == "  kept exactly  "


def test_store_errors_are_503_and_the_search_text_is_not_logged(monkeypatch, caplog):
    client, _ = _user("ada@example.com")

    def broken(*args, **kwargs):
        raise OperationalError("SELECT ... secret search words", {"q": "secret search words"}, Exception("db down"))

    monkeypatch.setattr(repository, "list_jobs", broken)
    with caplog.at_level(logging.INFO):
        response = client.get(JOBS_URL, params={"q": "secret search words"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Job store is unavailable. Please retry later."}
    assert "secret search words" not in caplog.text

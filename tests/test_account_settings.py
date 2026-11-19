"""Account settings: display name, password change (and ending other sessions), and statistics.

In-memory SQLite and test-only secrets. Jobs are written straight to the store, so nothing
is queued and no LLM is called.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, update
from sqlalchemy.exc import OperationalError

from api.main import app
from auth import passwords, repository as auth_repository
from jobs import db, repository
from jobs.models import ArchitectureJob, JobStatus, utcnow

ME = "/api/v1/auth/me"
PASSWORD_URL = "/api/v1/auth/password"
STATS = "/api/v1/stats"
TEST_SECRET = "test-secret-" + "x" * 40
OLD = "old password 1"
NEW = "brand new password 2"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr(passwords, "SCRYPT_N", 2**10)
    monkeypatch.setattr(passwords, "SCRYPT_P", 1)
    db.reset_engine()
    yield
    db.reset_engine()


def _user(email: str = "ada@example.com", password: str = OLD) -> tuple[TestClient, str]:
    client = TestClient(app)
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return client, response.json()["id"]


def _login(email: str = "ada@example.com", password: str = OLD) -> tuple[TestClient, int]:
    client = TestClient(app)
    return client, client.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code


# --- Display name ------------------------------------------------------------------------


def test_the_display_name_starts_empty_and_can_be_set():
    client, _ = _user()
    assert client.get(ME).json()["display_name"] is None
    response = client.patch(ME, json={"display_name": "Ada Lovelace"})
    assert response.status_code == 200
    assert response.json()["display_name"] == "Ada Lovelace"
    assert client.get(ME).json()["display_name"] == "Ada Lovelace"
    assert _login()[0].get(ME).json()["display_name"] == "Ada Lovelace"  # it is stored, not just cached


@pytest.mark.parametrize("sent, stored", [("  Ada   Lovelace  ", "Ada Lovelace"), ("Åda 🙂", "Åda 🙂"), ("x" * 60, "x" * 60)])
def test_the_display_name_is_trimmed_and_whitespace_collapsed(sent, stored):
    client, _ = _user()
    assert client.patch(ME, json={"display_name": sent}).json()["display_name"] == stored


@pytest.mark.parametrize("clearing", [None, "", "   "])
def test_an_empty_display_name_clears_it(clearing):
    client, _ = _user()
    client.patch(ME, json={"display_name": "Ada"})
    response = client.patch(ME, json={"display_name": clearing})
    assert response.status_code == 200 and response.json()["display_name"] is None


@pytest.mark.parametrize("bad", ["A", "x" * 61, 123, ["list"]])
def test_an_invalid_display_name_is_422_and_nothing_changes(bad):
    client, _ = _user()
    client.patch(ME, json={"display_name": "Ada"})
    response = client.patch(ME, json={"display_name": bad})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "display_name"]
    assert client.get(ME).json()["display_name"] == "Ada"


def test_the_email_cannot_be_changed_through_the_profile_endpoint():
    client, user_id = _user()
    response = client.patch(ME, json={"display_name": "Ada", "email": "evil@example.com", "id": "other", "token_version": 9})
    assert response.status_code == 200
    body = response.json()
    assert (body["email"], body["id"]) == ("ada@example.com", user_id)
    assert auth_repository.get_user(user_id).token_version == 0


def test_signed_out_cannot_use_the_profile_or_password_endpoints():
    client = TestClient(app)
    assert client.patch(ME, json={"display_name": "Ada"}).status_code == 401
    assert client.post(PASSWORD_URL, json={"current_password": OLD, "new_password": NEW}).status_code == 401
    assert client.get(STATS).status_code == 401


def test_a_users_display_name_only_changes_their_own_account():
    ada, _ = _user("ada@example.com")
    grace, _ = _user("grace@example.com")
    ada.patch(ME, json={"display_name": "Ada"})
    assert grace.get(ME).json()["display_name"] is None


# --- Password change ---------------------------------------------------------------------


def test_changing_the_password_works_and_the_old_one_stops_working():
    client, _ = _user()
    response = client.post(PASSWORD_URL, json={"current_password": OLD, "new_password": NEW})
    assert response.status_code == 204 and response.content == b""
    assert _login(password=NEW)[1] == 200
    assert _login(password=OLD)[1] == 401


def test_the_session_that_changed_the_password_stays_signed_in():
    client, _ = _user()
    client.post(PASSWORD_URL, json={"current_password": OLD, "new_password": NEW})
    assert client.get(ME).status_code == 200  # got a fresh cookie for the new version


def test_every_other_session_is_signed_out():
    first, _ = _user()
    second, _ = _login()  # the same account, signed in somewhere else
    assert second.get(ME).status_code == 200
    first.post(PASSWORD_URL, json={"current_password": OLD, "new_password": NEW})
    assert second.get(ME).status_code == 401
    assert first.get(ME).status_code == 200


def test_the_cookie_is_reissued_with_the_same_safe_flags():
    client, _ = _user()
    cookie = client.post(PASSWORD_URL, json={"current_password": OLD, "new_password": NEW}).headers["set-cookie"].lower()
    assert "archonai_session=" in cookie and "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie


def test_each_password_change_adds_one_to_the_token_version():
    client, user_id = _user()
    client.post(PASSWORD_URL, json={"current_password": OLD, "new_password": NEW})
    client.post(PASSWORD_URL, json={"current_password": NEW, "new_password": "third password 3"})
    assert auth_repository.get_user(user_id).token_version == 2
    assert client.get(ME).status_code == 200


def test_a_wrong_current_password_is_a_400_and_changes_nothing():
    client, _ = _user()
    response = client.post(PASSWORD_URL, json={"current_password": "wrong password", "new_password": NEW})
    # 400, not 401: the browser signs the user out on any 401.
    assert response.status_code == 400
    assert response.json() == {"detail": "The current password is incorrect."}
    assert _login(password=OLD)[1] == 200 and _login(password=NEW)[1] == 401
    assert client.get(ME).status_code == 200


def test_the_new_password_must_differ_and_follow_the_registration_rule():
    client, _ = _user()
    same = client.post(PASSWORD_URL, json={"current_password": OLD, "new_password": OLD})
    assert same.status_code == 422 and same.json()["detail"][0]["loc"] == ["body", "new_password"]
    for bad in ["short1", "x" * 129]:
        response = client.post(PASSWORD_URL, json={"current_password": OLD, "new_password": bad})
        assert response.status_code == 422 and response.json()["detail"][0]["loc"] == ["body", "new_password"]
    assert _login(password=OLD)[1] == 200


def test_passwords_are_not_echoed_or_logged(caplog):
    client, _ = _user()
    with caplog.at_level(logging.DEBUG):
        rejected = client.post(PASSWORD_URL, json={"current_password": "wrong password", "new_password": "tiny"})
        client.post(PASSWORD_URL, json={"current_password": OLD, "new_password": NEW})
    assert "tiny" not in rejected.text and "wrong password" not in rejected.text
    for secret in (OLD, NEW, "wrong password", "tiny"):
        assert secret not in caplog.text
    assert "Password changed" in caplog.text


def test_a_store_outage_while_changing_the_password_is_503_without_details(monkeypatch, caplog):
    client, _ = _user()

    def broken(*args, **kwargs):
        raise OperationalError("UPDATE secret-statement", {"p": NEW}, Exception("driver-detail"))

    monkeypatch.setattr(auth_repository, "change_password", broken)
    with caplog.at_level(logging.DEBUG):
        response = client.post(PASSWORD_URL, json={"current_password": OLD, "new_password": NEW})
    assert response.status_code == 503
    assert "secret-statement" not in caplog.text and NEW not in caplog.text and "driver-detail" not in caplog.text


# --- In-place upgrade of an existing users table -----------------------------------------


def test_an_existing_users_table_gets_the_new_columns_and_keeps_its_rows(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.reset_engine()
    engine = db.get_engine()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, email VARCHAR(254) NOT NULL, password_hash VARCHAR(255) NOT NULL, created_at DATETIME NOT NULL)"))
        connection.execute(text("INSERT INTO users VALUES ('u-1', 'old@example.com', 'x', '2026-01-01 00:00:00')"))
    db.init_db()
    user = auth_repository.get_user("u-1")
    assert (user.email, user.display_name, user.token_version) == ("old@example.com", None, 0)
    db.init_db()  # safe to run again


# --- Statistics --------------------------------------------------------------------------


def _result(score: Optional[int] = 80, approved: Optional[bool] = True, services: int = 6) -> dict[str, Any]:
    result: dict[str, Any] = {"architecture": {"version": 1, "services": [{"name": f"S{i}"} for i in range(services)]}}
    if score is not None:
        result["critic_review"] = {"score": score}
    if approved is not None:
        result["approved"] = approved
    return result


def _job(
    owner_id: Optional[str],
    status: JobStatus = JobStatus.SUCCEEDED,
    *,
    days_ago: float = 0.0,
    minutes: float = 5,
    result: Optional[dict] = None,
) -> str:
    """A stored job created `days_ago` days back; finished jobs took `minutes`."""
    job_id = repository.create_job("Design a blog for 10k users", owner_id=owner_id)
    created = utcnow() - timedelta(days=days_ago)
    values: dict[str, Any] = {"status": status, "created_at": created, "updated_at": created, "result": result}
    if status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
        values["finished_at"] = created + timedelta(minutes=minutes)
    with db.session_scope() as session:
        session.execute(update(ArchitectureJob).where(ArchitectureJob.id == job_id).values(**values))
    return job_id


def _stats(client: TestClient) -> dict:
    response = client.get(STATS)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_new_account_has_zeros_and_nulls_never_made_up_numbers():
    client, _ = _user()
    body = _stats(client)
    assert body["jobs"] == {"total": 0, "queued": 0, "running": 0, "succeeded": 0, "failed": 0}
    for field in ("success_rate", "average_total_seconds", "average_critic_score", "approval_rate", "average_aws_services", "first_job_at", "last_job_at"):
        assert body[field] is None, field
    assert (body["jobs_last_7_days"], body["jobs_last_30_days"], body["sample_size"], body["sample_capped"]) == (0, 0, 0, False)
    assert len(body["daily"]) == 14 and all(day["jobs"] == 0 for day in body["daily"])


def test_counts_rates_and_averages_are_worked_out_from_the_users_jobs():
    client, user_id = _user()
    _job(user_id, minutes=4, result=_result(score=90, approved=True, services=8))
    _job(user_id, minutes=6, result=_result(score=70, approved=False, services=6))
    _job(user_id, minutes=8, result=_result(score=80, approved=True, services=10))
    _job(user_id, JobStatus.FAILED)
    _job(user_id, JobStatus.QUEUED)
    _job(user_id, JobStatus.RUNNING)

    body = _stats(client)
    assert body["jobs"] == {"total": 6, "queued": 1, "running": 1, "succeeded": 3, "failed": 1}
    assert body["success_rate"] == 0.75  # 3 of the 4 that finished
    assert body["average_total_seconds"] == 360.0  # (4 + 6 + 8) / 3 minutes
    assert body["average_critic_score"] == 80.0
    assert body["approval_rate"] == 0.667  # 2 of 3
    assert body["average_aws_services"] == 8.0
    assert body["sample_size"] == 3 and body["sample_capped"] is False


def test_success_rate_is_null_while_nothing_has_finished():
    client, user_id = _user()
    _job(user_id, JobStatus.QUEUED)
    _job(user_id, JobStatus.RUNNING)
    body = _stats(client)
    assert body["jobs"]["total"] == 2 and body["success_rate"] is None


def test_only_the_callers_jobs_are_counted():
    ada, ada_id = _user("ada@example.com")
    grace, grace_id = _user("grace@example.com")
    _job(ada_id, result=_result(score=100, services=20))
    _job(grace_id, result=_result(score=10, services=2))
    _job(grace_id, JobStatus.FAILED)
    _job(None, result=_result(score=1, services=1))  # an old job with no owner

    mine, theirs = _stats(ada), _stats(grace)
    assert mine["jobs"]["total"] == 1 and mine["average_critic_score"] == 100.0 and mine["average_aws_services"] == 20.0
    assert theirs["jobs"]["total"] == 2 and theirs["average_critic_score"] == 10.0


def test_a_user_id_parameter_is_ignored():
    ada, ada_id = _user("ada@example.com")
    grace, grace_id = _user("grace@example.com")
    _job(ada_id)
    response = grace.get(STATS, params={"user_id": ada_id, "owner_id": ada_id})
    assert response.json()["jobs"]["total"] == 0


def test_recent_activity_windows_and_the_daily_series():
    client, user_id = _user()
    _job(user_id, days_ago=0)
    _job(user_id, days_ago=0)
    _job(user_id, days_ago=2)
    _job(user_id, days_ago=20)
    _job(user_id, days_ago=45)

    body = _stats(client)
    assert (body["jobs_last_7_days"], body["jobs_last_30_days"], body["jobs"]["total"]) == (3, 4, 5)
    daily = body["daily"]
    assert len(daily) == 14
    assert [d["date"] for d in daily] == sorted(d["date"] for d in daily)  # oldest first
    assert daily[-1]["date"] == utcnow().date().isoformat()
    assert daily[-1]["jobs"] == 2 and daily[-3]["jobs"] == 1 and sum(d["jobs"] for d in daily) == 3
    assert body["first_job_at"] < body["last_job_at"]
    assert body["first_job_at"].endswith("Z") or "+00:00" in body["first_job_at"]  # a real UTC timestamp


def test_averages_use_only_the_newest_jobs_when_there_are_many(monkeypatch):
    client, user_id = _user()
    monkeypatch.setattr(repository, "STATS_SAMPLE_LIMIT", 3)
    for days_ago, score in [(10, 10), (9, 20), (3, 60), (2, 70), (1, 80)]:
        _job(user_id, days_ago=days_ago, result=_result(score=score))
    body = _stats(client)
    assert body["jobs"]["succeeded"] == 5  # the count still covers every job
    assert (body["sample_size"], body["sample_capped"]) == (3, True)
    assert body["average_critic_score"] == 70.0  # (60 + 70 + 80) / 3, the three newest


@pytest.mark.parametrize(
    "result",
    [None, {}, "not a dict", [], {"critic_review": "oops", "architecture": 5, "approved": "yes"}, {"critic_review": {"score": True}, "architecture": {"services": "x"}}],
)
def test_odd_or_missing_results_never_break_the_statistics(result):
    client, user_id = _user()
    _job(user_id, result=result)
    _job(user_id, result=_result(score=50, services=4))
    body = _stats(client)
    assert body["jobs"]["succeeded"] == 2
    assert body["average_critic_score"] == 50.0 and body["average_aws_services"] == 4.0


def test_a_store_outage_is_503_without_leaking_details(monkeypatch, caplog):
    client, _ = _user()

    def broken(*args, **kwargs):
        raise OperationalError("SELECT secret-statement", {"id": "x"}, Exception("driver-detail"))

    monkeypatch.setattr(repository, "owner_stats", broken)
    with caplog.at_level(logging.DEBUG):
        response = client.get(STATS)
    assert response.status_code == 503
    assert response.json() == {"detail": "Job store is unavailable. Please retry later."}
    assert "secret-statement" not in caplog.text and "driver-detail" not in caplog.text


def test_the_statistics_reply_contains_no_request_text_or_results():
    client, user_id = _user()
    _job(user_id, result={**_result(), "final_report": {"summary": "TOP-SECRET-REPORT"}})
    assert "TOP-SECRET-REPORT" not in client.get(STATS).text and "Design a blog" not in client.get(STATS).text


def test_the_stats_time_is_utc_now_not_local(monkeypatch):
    # The daily buckets are UTC days: a job created just before UTC midnight counts for that day.
    client, user_id = _user()
    day = datetime(2026, 11, 18, 23, 30)
    job_id = _job(user_id, days_ago=0)
    with db.session_scope() as session:
        session.execute(update(ArchitectureJob).where(ArchitectureJob.id == job_id).values(created_at=day))
    data = repository.owner_stats(user_id, now=datetime(2026, 11, 19, 0, 15))
    assert dict(data.daily)[day.date()] == 1 and data.daily[-1][0] == datetime(2026, 11, 19).date()

"""Job ownership: only the signed-in submitter can read a job; old unowned jobs stay
untouched but unreadable; and the in-place owner_id migration keeps existing rows.

In-memory / temporary SQLite, eager Celery, mocked LLM: no MySQL, Redis or Groq.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from api.main import app
from auth import passwords
from jobs import db, repository
from jobs.celery_app import celery_app
from jobs.models import JobStatus

from .test_graph import _patch_llm

JOBS_URL = "/api/v1/architectures/jobs"
BODY = {"user_request": "Design a blogging platform for 10,000 users."}
TEST_SECRET = "test-secret-" + "x" * 40


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr(passwords, "SCRYPT_N", 2**10)
    monkeypatch.setattr(passwords, "SCRYPT_P", 1)
    db.reset_engine()
    previous = (celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates)
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    yield
    celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates = previous
    db.reset_engine()


def _signed_in(email: str) -> TestClient:
    client = TestClient(app)
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "test password"})
    assert response.status_code == 201, response.text
    return client


def _no_enqueue(monkeypatch):
    """Store jobs without running them (these tests are about who can see them)."""
    from jobs.tasks import run_architecture_job

    monkeypatch.setattr(run_architecture_job, "apply_async", lambda *a, **k: None)


# --- Signed out ----------------------------------------------------------------------


def test_signed_out_cannot_submit_and_nothing_is_stored(monkeypatch):
    _no_enqueue(monkeypatch)
    response = TestClient(app).post(JOBS_URL, json=BODY)
    assert response.status_code == 401
    assert response.json() == {"detail": "Not signed in, or the session has expired."}
    with db.session_scope() as session:
        from jobs.models import ArchitectureJob

        assert session.query(ArchitectureJob).count() == 0


def test_signed_out_cannot_read_a_job(monkeypatch):
    _no_enqueue(monkeypatch)
    job_id = _signed_in("ada@example.com").post(JOBS_URL, json=BODY).json()["job_id"]
    assert TestClient(app).get(f"{JOBS_URL}/{job_id}").status_code == 401


def test_sign_in_is_checked_before_the_body(monkeypatch):
    # An anonymous caller learns nothing about validation rules either.
    assert TestClient(app).post(JOBS_URL, json={"user_request": ""}).status_code == 401


# --- Owner only ----------------------------------------------------------------------


def test_job_is_stored_with_its_owner_and_the_owner_can_read_it(monkeypatch):
    _no_enqueue(monkeypatch)
    ada = _signed_in("ada@example.com")
    ada_id = ada.get("/api/v1/auth/me").json()["id"]
    job_id = ada.post(JOBS_URL, json=BODY).json()["job_id"]

    assert repository.get_job(job_id).owner_id == ada_id
    response = ada.get(f"{JOBS_URL}/{job_id}")
    assert response.status_code == 200
    assert response.json()["job_id"] == job_id
    assert "owner_id" not in response.json()  # ownership is never echoed to clients


def test_another_user_gets_the_same_404_as_for_a_missing_job(monkeypatch):
    _no_enqueue(monkeypatch)
    job_id = _signed_in("ada@example.com").post(JOBS_URL, json=BODY).json()["job_id"]
    grace = _signed_in("grace@example.com")

    someone_elses = grace.get(f"{JOBS_URL}/{job_id}")
    missing = grace.get(f"{JOBS_URL}/00000000-0000-0000-0000-000000000000")
    assert someone_elses.status_code == missing.status_code == 404
    assert someone_elses.json() == missing.json() == {"detail": "Job not found."}


def test_old_unowned_jobs_are_kept_but_nobody_can_read_them():
    legacy_id = repository.create_job(BODY["user_request"])  # as before accounts existed
    ada = _signed_in("ada@example.com")
    assert ada.get(f"{JOBS_URL}/{legacy_id}").status_code == 404
    assert repository.get_job(legacy_id) is not None  # still in the database


def test_owner_sees_the_finished_result_and_others_never_do(monkeypatch):
    _patch_llm(monkeypatch, critic_verdicts=[True])
    ada = _signed_in("ada@example.com")
    job_id = ada.post(JOBS_URL, json=BODY).json()["job_id"]  # runs eagerly with the mocked LLM

    mine = ada.get(f"{JOBS_URL}/{job_id}").json()
    assert mine["status"] == JobStatus.SUCCEEDED.value
    assert mine["result"] is not None
    assert _signed_in("grace@example.com").get(f"{JOBS_URL}/{job_id}").status_code == 404


def test_without_a_jwt_secret_job_endpoints_answer_503(monkeypatch):
    monkeypatch.delenv("JWT_SECRET")
    client = TestClient(app)
    assert client.post(JOBS_URL, json=BODY).status_code == 503
    assert client.get(f"{JOBS_URL}/any").status_code == 503


def test_public_endpoints_stay_public():
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/architectures/examples").status_code == 200


# --- In-place migration ----------------------------------------------------------------

_OLD_SCHEMA = """
CREATE TABLE architecture_jobs (
    id VARCHAR(36) PRIMARY KEY,
    status VARCHAR(16) NOT NULL,
    user_request TEXT NOT NULL,
    result JSON,
    error_status_code INTEGER,
    error_message VARCHAR(255),
    attempts INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    started_at DATETIME,
    finished_at DATETIME,
    updated_at DATETIME NOT NULL
)
"""


def _old_database(path) -> str:
    """A job table as it was before accounts, holding one finished job."""
    connection = sqlite3.connect(path)
    connection.execute(_OLD_SCHEMA)
    connection.execute(
        "INSERT INTO architecture_jobs VALUES ('old-1', 'succeeded', 'Old request', '{\"approved\": true}', NULL, NULL, 1,"
        " '2026-11-01 10:00:00', '2026-11-01 10:00:01', '2026-11-01 10:05:00', '2026-11-01 10:05:00')"
    )
    connection.commit()
    connection.close()
    return f"sqlite:///{path}"


def test_migration_adds_owner_id_and_keeps_existing_rows(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", _old_database(tmp_path / "old.db"))
    db.reset_engine()

    job = repository.get_job("old-1")  # first use runs init_db

    assert job is not None
    assert (job.status, job.user_request, job.result, job.owner_id) == (JobStatus.SUCCEEDED, "Old request", {"approved": True}, None)
    inspector = inspect(db.get_engine())
    assert "owner_id" in {c["name"] for c in inspector.get_columns("architecture_jobs")}
    assert "ix_architecture_jobs_owner_id" in {i["name"] for i in inspector.get_indexes("architecture_jobs")}
    assert "users" in inspector.get_table_names()


def test_migration_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", _old_database(tmp_path / "old.db"))
    for _ in range(3):
        db.reset_engine()
        db.init_db()
    assert repository.get_job("old-1").user_request == "Old request"


def test_migration_tolerates_another_process_adding_the_column_first(monkeypatch, tmp_path):
    url = _old_database(tmp_path / "old.db")
    monkeypatch.setenv("DATABASE_URL", url)
    db.reset_engine()
    engine = db.get_engine()

    # Simulate the worker winning the race: the column appears right after our check.
    real_inspect = db.inspect
    calls = {"n": 0}

    def racing_inspect(target):
        calls["n"] += 1
        if calls["n"] == 1:
            stale = real_inspect(target)
            columns = stale.get_columns("architecture_jobs")
            with engine.begin() as connection:
                connection.exec_driver_sql("ALTER TABLE architecture_jobs ADD COLUMN owner_id VARCHAR(36) NULL")

            class Stale:
                def get_columns(self, table):
                    return columns

            return Stale()
        return real_inspect(target)

    monkeypatch.setattr(db, "inspect", racing_inspect)
    db.init_db()  # must not raise "duplicate column"
    assert "owner_id" in {c["name"] for c in real_inspect(engine).get_columns("architecture_jobs")}


def test_schema_setup_retries_while_another_process_is_creating_tables(monkeypatch):
    # MySQL answers "table already exists" / "being modified by concurrent DDL" while the
    # API and the worker set up the schema at the same moment; setup waits and tries again.
    from sqlalchemy.exc import OperationalError

    real_create_all = db.Base.metadata.create_all
    failures = {"left": 2}

    def busy_then_ok(*args, **kwargs):
        if failures["left"]:
            failures["left"] -= 1
            raise OperationalError("CREATE TABLE users", {}, Exception(1684, "Table 'users' was skipped since its definition is being modified by concurrent DDL statement"))
        return real_create_all(*args, **kwargs)

    monkeypatch.setattr(db.Base.metadata, "create_all", busy_then_ok)
    monkeypatch.setattr(db.time, "sleep", lambda seconds: None)
    db.reset_engine()
    db.init_db()
    assert failures["left"] == 0
    assert {"users", "architecture_jobs"} <= set(inspect(db.get_engine()).get_table_names())


def test_schema_setup_gives_up_after_repeated_failures(monkeypatch):
    from sqlalchemy.exc import OperationalError

    def always_busy(*args, **kwargs):
        raise OperationalError("CREATE TABLE users", {}, Exception(1050, "Table 'users' already exists"))

    monkeypatch.setattr(db.Base.metadata, "create_all", always_busy)
    monkeypatch.setattr(db.time, "sleep", lambda seconds: None)
    db.reset_engine()
    with pytest.raises(OperationalError):
        db.init_db()


def test_a_database_that_is_down_fails_at_once_without_retrying(monkeypatch):
    from sqlalchemy.exc import OperationalError

    calls = {"n": 0}

    def unreachable(*args, **kwargs):
        calls["n"] += 1
        raise OperationalError("SELECT 1", {}, Exception(2003, "Can't connect to MySQL server"))

    monkeypatch.setattr(db.Base.metadata, "create_all", unreachable)
    slept = []
    monkeypatch.setattr(db.time, "sleep", slept.append)
    db.reset_engine()
    with pytest.raises(OperationalError):
        db.init_db()
    assert (calls["n"], slept) == (1, [])

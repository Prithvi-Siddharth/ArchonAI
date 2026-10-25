"""Settings for ArchonAI's background job system.

Shared by the API (which submits jobs) and the worker (which runs them), so
both always agree on where MySQL and Redis are. Every setting has a default
that matches the local docker-compose setup, so an existing .env keeps
working without edits -- set the variable only to override it.

Read at call time (get_settings) rather than at import time, so tests can
point DATABASE_URL at SQLite by setting the environment before use.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(override=True)

DEFAULT_DATABASE_URL = "mysql+pymysql://archon:archon@localhost:3306/archonai"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def _int_env(name: str, default: int, minimum: int) -> int:
    """Read an integer setting, failing loudly on a typo instead of silently
    falling back -- a mistyped WORKER_CONCURRENCY should not quietly run with
    a different value than the one the operator intended."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}.") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}.")
    return value


@dataclass(frozen=True)
class JobSettings:
    database_url: str
    redis_url: str
    # Start at 1: Groq's free tier rate-limits per minute, and each design
    # run already makes several LLM calls in parallel internally.
    worker_concurrency: int
    # Job-level retries are for transient failures only (rate limits,
    # timeouts). Individual LLM calls already retry inside agents/llm.py,
    # so this stays low by default.
    job_max_retries: int
    job_retry_delay_seconds: int
    job_timeout_seconds: int


def get_settings() -> JobSettings:
    """Return the current job settings from the environment."""
    return JobSettings(
        database_url=os.getenv("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL,
        redis_url=os.getenv("REDIS_URL", "").strip() or DEFAULT_REDIS_URL,
        worker_concurrency=_int_env("WORKER_CONCURRENCY", default=1, minimum=1),
        job_max_retries=_int_env("JOB_MAX_RETRIES", default=1, minimum=0),
        job_retry_delay_seconds=_int_env("JOB_RETRY_DELAY_SECONDS", default=60, minimum=0),
        job_timeout_seconds=_int_env("JOB_TIMEOUT_SECONDS", default=900, minimum=60),
    )

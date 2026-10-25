"""Celery application for ArchonAI's background jobs.

Redis is only the queue (the "broker"): it carries job ids from the API to
the worker. Job status and results live in MySQL (jobs/repository.py), so
Celery's own result storage is switched off.

Start a worker with:

    celery -A jobs.celery_app worker --loglevel=info

Worker concurrency comes from WORKER_CONCURRENCY (default 1); the
--concurrency command-line flag overrides it.
"""

from __future__ import annotations

from celery import Celery

from jobs.config import get_settings

_settings = get_settings()

# include: load the task module when a worker starts, so it knows the task exists.
celery_app = Celery("archonai", broker=_settings.redis_url, include=["jobs.tasks"])

celery_app.conf.update(
    # MySQL is the source of truth for job state; don't also store results in Redis.
    task_ignore_result=True,
    task_serializer="json",
    accept_content=["json"],
    # Start conservatively: each design run already makes several LLM calls
    # in parallel, and Groq's free tier rate-limits per minute.
    worker_concurrency=_settings.worker_concurrency,
    # Take one job at a time from Redis. Jobs run for minutes, so letting a
    # worker reserve several ahead would leave them stuck behind a long run
    # while another worker sits idle.
    worker_prefetch_multiplier=1,
    # Keep retrying the Redis connection if Redis is still starting up
    # (e.g. right after `docker compose up`) instead of exiting.
    broker_connection_retry_on_startup=True,
)

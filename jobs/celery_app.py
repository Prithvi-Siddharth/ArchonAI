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

import os

from celery import Celery
from celery.signals import after_setup_logger, worker_process_init

from graph.cloudwatch_logs import configure_cloudwatch_logging
from jobs.config import get_settings

# On macOS the prefork pool starts its child processes with "spawn" rather
# than "fork", and Celery's fast task-tracing path is never initialised in a
# spawned child -- every task then fails with "ValueError: not enough values
# to unpack (expected 3, got 0)". This flag makes the children use the
# standard tracing path instead. Harmless on Linux, where children fork.
# Set before the pool starts so spawned children inherit it.
os.environ.setdefault("FORKED_BY_MULTIPROCESSING", "1")

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
    # Crash safety: acknowledge a job to Redis only after it finishes, and
    # hand it back if the worker process dies mid-run, so a crash doesn't
    # silently lose the job (jobs/runner.py decides whether to re-run it).
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Time limits: the soft limit raises inside the job so it can be marked
    # failed (504) cleanly; the hard limit kills it if that doesn't work.
    task_soft_time_limit=_settings.job_timeout_seconds,
    task_time_limit=_settings.job_timeout_seconds + 60,
    # Redis re-queues an unacknowledged job after this long. With acks_late
    # it must exceed the longest possible run, or a slow but healthy job
    # would be handed to a second worker while the first is still running.
    broker_transport_options={"visibility_timeout": max(3600, (_settings.job_timeout_seconds + 60) * 2)},
)


# Ship worker logs to CloudWatch (/archonai/worker) when CLOUDWATCH_ENABLED=true.
# after_setup_logger covers the main worker process, once Celery has set up
# its own console logging; worker_process_init covers each pool child, where
# the jobs actually run. (A forked child inherits the handler -- watchtower
# restarts its sender thread after fork -- and the call is then a no-op; a
# spawned child starts fresh and gets its own.)
@after_setup_logger.connect
def _ship_worker_logs(logger, **kwargs) -> None:
    configure_cloudwatch_logging("worker", logger)


@worker_process_init.connect
def _ship_worker_child_logs(**kwargs) -> None:
    configure_cloudwatch_logging("worker")

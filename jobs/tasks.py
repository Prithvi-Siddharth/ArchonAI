"""Celery tasks for ArchonAI.

A thin doorway: the worker calls this task, and the task calls
jobs.runner.execute_job. All job logic (status transitions, running the
workflow, storing the result or a client-safe error) lives there. The only
thing decided here is Celery-specific: whether a retry is still available,
whether this delivery is a crash redelivery, and scheduling the retry.
"""

from __future__ import annotations

from jobs.celery_app import celery_app
from jobs.config import get_settings
from jobs.runner import execute_job


# An explicit name keeps queued messages valid even if this module moves.
@celery_app.task(bind=True, name="archonai.run_architecture_job")
def run_architecture_job(self, job_id: str) -> None:
    """Run one architecture job by id (status and result are stored in MySQL)."""
    settings = get_settings()
    can_retry = self.request.retries < settings.job_max_retries
    redelivered = bool((self.request.delivery_info or {}).get("redelivered"))

    failure = execute_job(job_id, allow_retry=can_retry, redelivered=redelivered)

    if failure is not None and failure.retryable and can_retry:
        # execute_job has already put the job back to `queued`; send it
        # through Redis again after a pause so a rate-limit window can reset.
        raise self.retry(countdown=settings.job_retry_delay_seconds, max_retries=settings.job_max_retries)

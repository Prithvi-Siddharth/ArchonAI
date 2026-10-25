"""Run one architecture job: load it, run the workflow, store the outcome.

Deliberately independent of *how* it gets called -- the Celery task in
jobs/tasks.py today -- so the queue never shapes this logic. The workflow
itself is the existing run_workflow(), unchanged. The caller only supplies
two decisions it alone can make: whether a retry is still available, and
whether this delivery is a redelivery after a worker crash.
"""

from __future__ import annotations

import logging
from typing import Optional

from api.errors import WorkflowFailure, classify_workflow_error
from api.schemas import ArchitectureResponse
from graph.workflow import run_workflow
from jobs import repository
from jobs.config import get_settings
from jobs.models import JobStatus

logger = logging.getLogger(__name__)

_INTERRUPTED_TOO_OFTEN = WorkflowFailure(500, "Job was interrupted too many times. Please resubmit.", False)


def _claim(job_id: str, status: JobStatus, attempts: int, redelivered: bool) -> bool:
    """Take ownership of the job for this run. False means: don't run it."""
    # The guarded queued -> running transition is what makes running the
    # same job twice impossible: a duplicate delivery finds it already
    # running (or finished) and stops here.
    if repository.mark_running(job_id):
        return True

    # A redelivered message for a job still marked `running` means the worker
    # that owned it died mid-run (acks_late hands the message back to Redis).
    # Run it again -- but crash restarts share the retry budget, so a job
    # that keeps killing its worker eventually fails instead of looping.
    if redelivered and status is JobStatus.RUNNING:
        if attempts > get_settings().job_max_retries:
            repository.mark_failed(job_id, _INTERRUPTED_TOO_OFTEN.status_code, _INTERRUPTED_TOO_OFTEN.message)
            logger.warning("Job %s was interrupted %d times; marked failed.", job_id, attempts)
            return False
        if repository.mark_resumed(job_id):
            logger.warning("Job %s was interrupted by a worker crash; running it again.", job_id)
            return True

    logger.info("Job %s is not queued (status=%s); skipping.", job_id, status.value)
    return False


def execute_job(job_id: str, *, allow_retry: bool = False, redelivered: bool = False) -> Optional[WorkflowFailure]:
    """Run the job with this id and record the outcome in the database.

    allow_retry: if True and the failure is temporary (rate limit, timeout,
        network), the job is put back to `queued` instead of `failed`, and
        the caller is expected to schedule the retry.
    redelivered: True when the queue is handing this job out again after a
        worker crash.

    Returns None on success (or when the job was skipped), or the classified
    failure so the caller can decide whether to retry.
    """
    job = repository.get_job(job_id)
    if job is None:
        logger.warning("Job %s not found; nothing to run.", job_id)
        return None

    if not _claim(job_id, job.status, job.attempts, redelivered):
        return None

    try:
        final_state = run_workflow(job.user_request)
        result = ArchitectureResponse.from_state(final_state).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - every failure must end in a stored job status
        failure = classify_workflow_error(exc)
        if failure.retryable and allow_retry:
            logger.warning("Job %s hit a temporary failure (%s); will retry.", job_id, failure.status_code)
            repository.mark_requeued(job_id, failure.status_code, failure.message)
        else:
            logger.exception("Job %s failed", job_id)
            repository.mark_failed(job_id, failure.status_code, failure.message)
        return failure

    repository.mark_succeeded(job_id, result)
    logger.info("Job %s succeeded.", job_id)
    return None

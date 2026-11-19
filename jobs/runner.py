"""Run one architecture job: load it, run the workflow, store the outcome.

Deliberately independent of *how* it gets called -- the Celery task in
jobs/tasks.py today -- so the queue never shapes this logic. The workflow
itself is the existing run_workflow(), unchanged. The caller only supplies
two decisions it alone can make: whether a retry is still available, and
whether this delivery is a redelivery after a worker crash.

Logging: every event is structured (graph/observability.py) and runs inside
job_context(job_id), so the workflow and per-node timing events logged
during the run carry this job's id too.
"""

from __future__ import annotations

import logging
from typing import Optional

from api.errors import WorkflowFailure, classify_workflow_error
from agents.llm import use_llm_credentials
from api.schemas import ArchitectureResponse
from graph.observability import elapsed_ms, job_context, log_event, now
from graph.workflow import run_workflow
from jobs import repository
from jobs.config import get_settings
from jobs.models import JobStatus
from llm_keys.service import credentials_for

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
            log_event(
                logger,
                "job_failed",
                logging.WARNING,
                reason="interrupted_too_often",
                attempt=attempts,
                status_code=_INTERRUPTED_TOO_OFTEN.status_code,
            )
            return False
        if repository.mark_resumed(job_id):
            log_event(logger, "job_resumed_after_crash", logging.WARNING, previous_attempts=attempts)
            return True

    log_event(logger, "job_skipped", reason="not_queued", status=status.value)
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
    with job_context(job_id):
        job = repository.get_job(job_id)
        if job is None:
            log_event(logger, "job_skipped", logging.WARNING, reason="not_found")
            return None

        if not _claim(job_id, job.status, job.attempts, redelivered):
            return None

        attempt = job.attempts + 1
        log_event(logger, "job_started", attempt=attempt, redelivered=redelivered)
        start = now()

        try:
            # The owner's own provider key, if they saved one; read here in the worker
            # (never carried by the queue or the job row) and used for this run only.
            with use_llm_credentials(credentials_for(job.owner_id)):
                final_state = run_workflow(job.user_request)
            result = ArchitectureResponse.from_state(final_state).model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 - every failure must end in a stored job status
            failure = classify_workflow_error(exc)
            will_retry = failure.retryable and allow_retry
            if will_retry:
                stored = repository.mark_requeued(job_id, failure.status_code, failure.message)
            else:
                stored = repository.mark_failed(job_id, failure.status_code, failure.message)
            if not stored:
                _log_already_finished(attempt)
                return None
            log_event(
                logger,
                "job_failed",
                logging.WARNING if will_retry else logging.ERROR,
                attempt=attempt,
                status_code=failure.status_code,
                error_type=type(exc.__cause__ or exc).__name__,
                will_retry=will_retry,
                duration_ms=elapsed_ms(start),
            )
            # The traceback can contain provider error text that echoes request
            # details, so it's kept out of the default (INFO) log output.
            logger.debug("Traceback for failed job %s", job_id, exc_info=True)
            return failure

        if not repository.mark_succeeded(job_id, result):
            _log_already_finished(attempt)
            return None
        log_event(logger, "job_succeeded", attempt=attempt, duration_ms=elapsed_ms(start))
        return None


def _log_already_finished(attempt: int) -> None:
    # The guarded update found the job no longer `running`: another delivery
    # already recorded its outcome. Reporting this run as job_succeeded or
    # job_failed too would count the job twice in logs and metrics.
    log_event(logger, "job_skipped", logging.WARNING, reason="already_finished", attempt=attempt)

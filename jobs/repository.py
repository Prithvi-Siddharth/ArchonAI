"""Read and update architecture jobs.

The API and the worker only ever touch the database through these
functions. Every status change is a guarded UPDATE -- "set status to X, but
only if it is currently one of Y" -- executed as one statement, so the check
and the change can't be separated by another process. A function returns
False when the job wasn't in an allowed status (or doesn't exist), and
nothing is changed. This is what stops a job delivered twice from running
twice, or a late retry from overwriting a finished result.

Allowed transitions:
    queued  -> running            (mark_running)
    running -> succeeded          (mark_succeeded)
    queued | running -> failed    (mark_failed)
    running -> queued             (mark_requeued, for a retry)
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import update

from jobs.db import session_scope
from jobs.models import ArchitectureJob, JobStatus, utcnow


def create_job(user_request: str) -> str:
    """Store a new queued job and return its id."""
    with session_scope() as session:
        job = ArchitectureJob(user_request=user_request)
        session.add(job)
        session.flush()  # assigns the default id before the session closes
        return job.id


def get_job(job_id: str) -> Optional[ArchitectureJob]:
    """Return the job, or None if no job has this id. Allowed in any status."""
    with session_scope() as session:
        return session.get(ArchitectureJob, job_id)


def _transition(job_id: str, allowed_from: tuple[JobStatus, ...], **values: Any) -> bool:
    """Apply `values` only if the job is currently in one of `allowed_from`."""
    with session_scope() as session:
        result = session.execute(
            update(ArchitectureJob)
            .where(ArchitectureJob.id == job_id, ArchitectureJob.status.in_(allowed_from))
            .values(updated_at=utcnow(), **values)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1


def mark_running(job_id: str) -> bool:
    """queued -> running. Records the start time and counts the attempt."""
    return _transition(
        job_id,
        (JobStatus.QUEUED,),
        status=JobStatus.RUNNING,
        started_at=utcnow(),
        attempts=ArchitectureJob.attempts + 1,
    )


def mark_succeeded(job_id: str, result: dict[str, Any]) -> bool:
    """running -> succeeded. Stores the result and clears any earlier retry error."""
    return _transition(
        job_id,
        (JobStatus.RUNNING,),
        status=JobStatus.SUCCEEDED,
        result=result,
        error_status_code=None,
        error_message=None,
        finished_at=utcnow(),
    )


def mark_failed(job_id: str, status_code: int, message: str) -> bool:
    """queued | running -> failed. `message` must be client-safe (see api/errors.py)."""
    return _transition(
        job_id,
        (JobStatus.QUEUED, JobStatus.RUNNING),
        status=JobStatus.FAILED,
        error_status_code=status_code,
        error_message=message,
        finished_at=utcnow(),
    )


def mark_requeued(job_id: str, status_code: int, message: str) -> bool:
    """running -> queued, ahead of a retry. Keeps the error that caused the retry visible."""
    return _transition(
        job_id,
        (JobStatus.RUNNING,),
        status=JobStatus.QUEUED,
        error_status_code=status_code,
        error_message=message,
    )

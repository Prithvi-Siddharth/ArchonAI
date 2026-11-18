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
    running -> running            (mark_resumed, only when a worker crashed mid-job
                                   and Redis redelivered it)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import func, or_, select, update

from jobs.db import session_scope
from jobs.models import ArchitectureJob, JobStatus, utcnow


def create_job(user_request: str, owner_id: Optional[str] = None) -> str:
    """Store a new queued job and return its id.

    The API always passes the signed-in user's id; `owner_id` is optional only so
    worker-level code and tests can create jobs directly.
    """
    with session_scope() as session:
        job = ArchitectureJob(user_request=user_request, owner_id=owner_id)
        session.add(job)
        session.flush()  # assigns the default id before the session closes
        return job.id


def get_job(job_id: str) -> Optional[ArchitectureJob]:
    """Return the job, or None if no job has this id. Allowed in any status."""
    with session_scope() as session:
        return session.get(ArchitectureJob, job_id)


def get_owned_job(job_id: str, owner_id: str) -> Optional[ArchitectureJob]:
    """Return the job only if `owner_id` owns it; None if it doesn't exist OR belongs to
    someone else (or to nobody), so callers can't tell those cases apart."""
    with session_scope() as session:
        return session.execute(
            select(ArchitectureJob).where(ArchitectureJob.id == job_id, ArchitectureJob.owner_id == owner_id)
        ).scalar_one_or_none()


@dataclass(frozen=True)
class JobPage:
    """One page of a user's jobs, newest first, plus counts for the whole (searched) history."""

    jobs: list[ArchitectureJob]
    total: int
    counts: dict[JobStatus, int]


# "/" rather than backslash as the LIKE escape: it needs no extra quoting on MySQL or SQLite.
_LIKE_ESCAPE = "/"


def _escape_like(text: str) -> str:
    return text.replace("/", "//").replace("%", "/%").replace("_", "/_")


def list_jobs(
    owner_id: str,
    *,
    status: Optional[JobStatus] = None,
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> JobPage:
    """A page of `owner_id`'s jobs, newest first. Never returns anyone else's jobs.

    `search` matches the request text anywhere (case-insensitive) or the start of the
    job id. `counts` covers every status for the same owner and search, so a UI can
    show how many jobs each status filter would return.
    """
    filters = [ArchitectureJob.owner_id == owner_id]
    if search:
        pattern = _escape_like(search)
        filters.append(
            or_(
                ArchitectureJob.user_request.ilike(f"%{pattern}%", escape=_LIKE_ESCAPE),
                ArchitectureJob.id.ilike(f"{pattern}%", escape=_LIKE_ESCAPE),
            )
        )
    with session_scope() as session:
        counts = {state: 0 for state in JobStatus}
        for state, count in session.execute(
            select(ArchitectureJob.status, func.count()).where(*filters).group_by(ArchitectureJob.status)
        ):
            counts[JobStatus(state)] = count
        if status is not None:
            filters.append(ArchitectureJob.status == status)
        jobs = (
            session.execute(
                select(ArchitectureJob)
                .where(*filters)
                # id breaks ties between jobs created in the same second, so pages never overlap.
                .order_by(ArchitectureJob.created_at.desc(), ArchitectureJob.id.desc())
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
    total = counts[status] if status is not None else sum(counts.values())
    return JobPage(jobs=list(jobs), total=total, counts=counts)


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


def mark_resumed(job_id: str) -> bool:
    """running -> running, for a job whose worker died mid-run.

    Only called for a redelivered message (see jobs/runner.py): the earlier
    attempt can no longer finish, so this one takes over and is counted.
    """
    return _transition(
        job_id,
        (JobStatus.RUNNING,),
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

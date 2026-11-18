"""Architecture endpoints.

Deliberately thin: validate the request (via api/schemas.py), store the job,
and hand it to the Celery worker, which runs the existing LangGraph workflow
(jobs/runner.py). The API never runs the workflow itself. All design,
analysis, and critique logic stays in agents/ and graph/.
"""

from __future__ import annotations

import logging

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import SQLAlchemyError

from api.examples import load_example_prompts
from api.schemas import (
    ArchitectureRequest,
    ErrorResponse,
    ExamplePrompt,
    JobHistoryItem,
    JobHistoryResponse,
    JobStatusCounts,
    JobStatusResponse,
    JobSubmittedResponse,
)
from auth.dependencies import get_current_user
from auth.models import User
from jobs import repository
from jobs.models import JobStatus
from jobs.tasks import run_architecture_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/architectures", tags=["architectures"])


_JOB_STORE_UNAVAILABLE = HTTPException(
    status.HTTP_503_SERVICE_UNAVAILABLE, "Job store is unavailable. Please retry later."
)
_JOB_QUEUE_UNAVAILABLE_MESSAGE = "Job queue is unavailable. Please retry later."

# Fail fast when Redis is unreachable: Celery's default publish retry keeps
# trying for a long time, which would leave the client hanging. A couple of
# quick attempts still rides out a momentary blip.
_ENQUEUE_RETRY_POLICY = {"max_retries": 2, "interval_start": 0, "interval_step": 0.5, "interval_max": 1}


@router.get("/examples", response_model=list[ExamplePrompt])
def list_examples() -> list[dict[str, str]]:
    """Example prompts that can be sent to POST /api/v1/architectures/jobs."""
    return load_example_prompts()


_JOB_ERROR_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}


@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobSubmittedResponse,
    responses=_JOB_ERROR_RESPONSES,
)
def submit_architecture_job(
    body: ArchitectureRequest, request: Request, user: User = Depends(get_current_user)
) -> JobSubmittedResponse:
    """Queue a design request and return a job id immediately.

    The job is stored in MySQL, then its id is sent through Redis to a Celery
    worker, which runs the workflow. Poll the returned status_url for
    progress and the result. A worker must be running for jobs to progress;
    until one is, jobs simply wait as `queued`.

    Requires a signed-in user (session cookie); the job is stored as theirs.
    """
    try:
        job_id = repository.create_job(body.user_request, owner_id=user.id)
    except SQLAlchemyError:
        logger.exception("Could not store new job")
        raise _JOB_STORE_UNAVAILABLE from None

    try:
        run_architecture_job.apply_async(args=[job_id], retry=True, retry_policy=_ENQUEUE_RETRY_POLICY)
    except Exception:  # noqa: BLE001 - any broker failure means the job can never run
        logger.exception("Could not enqueue job %s", job_id)
        # Don't leave a job that no worker will ever see sitting at `queued`.
        try:
            repository.mark_failed(job_id, status.HTTP_503_SERVICE_UNAVAILABLE, _JOB_QUEUE_UNAVAILABLE_MESSAGE)
        except SQLAlchemyError:
            logger.exception("Could not mark job %s as failed", job_id)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _JOB_QUEUE_UNAVAILABLE_MESSAGE) from None

    return JobSubmittedResponse(
        job_id=job_id,
        status="queued",
        status_url=request.app.url_path_for("get_architecture_job", job_id=job_id),
    )


HISTORY_PAGE_MAX = 50


@router.get("/jobs", response_model=JobHistoryResponse, responses=_JOB_ERROR_RESPONSES)
def list_architecture_jobs(
    user: User = Depends(get_current_user),
    limit: Annotated[int, Query(ge=1, le=HISTORY_PAGE_MAX, description="Page size.")] = 20,
    offset: Annotated[int, Query(ge=0, le=1_000_000, description="Jobs to skip (page start).")] = 0,
    status_filter: Annotated[Optional[JobStatus], Query(alias="status", description="Only jobs in this status.")] = None,
    q: Annotated[
        Optional[str], Query(max_length=200, description="Search the request text, or the start of a job id.")
    ] = None,
) -> JobHistoryResponse:
    """The signed-in user's jobs, newest first, with a small summary of each result.

    Only the caller's own jobs are ever listed (jobs created before accounts existed
    have no owner and never appear). Use GET /jobs/{job_id} for a job's full result.
    """
    search = q.strip() if q else None
    try:
        page = repository.list_jobs(user.id, status=status_filter, search=search or None, limit=limit, offset=offset)
    except SQLAlchemyError as exc:
        # Class name only: the statement parameters include the user's search text.
        logger.error("Could not list jobs (%s).", type(exc).__name__)
        raise _JOB_STORE_UNAVAILABLE from None
    return JobHistoryResponse(
        items=[JobHistoryItem.from_job(job) for job in page.jobs],
        total=page.total,
        limit=limit,
        offset=offset,
        counts=JobStatusCounts(**{state.value: count for state, count in page.counts.items()}),
    )


@router.get(
    "/jobs/{job_id}",
    name="get_architecture_job",
    response_model=JobStatusResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}, **_JOB_ERROR_RESPONSES},
)
def get_architecture_job(job_id: str, user: User = Depends(get_current_user)) -> JobStatusResponse:
    """Current status of a job, including the full result once it has succeeded.

    Only the job's owner can read it. Anyone else -- including for jobs created
    before accounts existed, which have no owner -- gets the same 404 as for an
    id that doesn't exist, so job ids can't be probed.
    """
    try:
        job = repository.get_owned_job(job_id, user.id)
    except SQLAlchemyError:
        logger.exception("Could not read job %s", job_id)
        raise _JOB_STORE_UNAVAILABLE from None
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    return JobStatusResponse.from_job(job)

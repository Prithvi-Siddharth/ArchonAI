"""Architecture endpoints.

Deliberately thin: validate the request (via api/schemas.py), store the job,
and hand it to the Celery worker, which runs the existing LangGraph workflow
(jobs/runner.py). The API never runs the workflow itself. All design,
analysis, and critique logic stays in agents/ and graph/.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError

from api.examples import load_example_prompts
from api.schemas import (
    ArchitectureRequest,
    ErrorResponse,
    ExamplePrompt,
    JobStatusResponse,
    JobSubmittedResponse,
)
from jobs import repository
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


_JOB_ERROR_RESPONSES = {status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse}}


@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobSubmittedResponse,
    responses=_JOB_ERROR_RESPONSES,
)
def submit_architecture_job(body: ArchitectureRequest, request: Request) -> JobSubmittedResponse:
    """Queue a design request and return a job id immediately.

    The job is stored in MySQL, then its id is sent through Redis to a Celery
    worker, which runs the workflow. Poll the returned status_url for
    progress and the result. A worker must be running for jobs to progress;
    until one is, jobs simply wait as `queued`.
    """
    try:
        job_id = repository.create_job(body.user_request)
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


@router.get(
    "/jobs/{job_id}",
    name="get_architecture_job",
    response_model=JobStatusResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}, **_JOB_ERROR_RESPONSES},
)
def get_architecture_job(job_id: str) -> JobStatusResponse:
    """Current status of a job, including the full result once it has succeeded."""
    try:
        job = repository.get_job(job_id)
    except SQLAlchemyError:
        logger.exception("Could not read job %s", job_id)
        raise _JOB_STORE_UNAVAILABLE from None
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    return JobStatusResponse.from_job(job)

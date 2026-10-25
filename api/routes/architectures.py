"""Architecture endpoints.

Deliberately thin: validate the request (via api/schemas.py), run the
existing LangGraph workflow unchanged, and serialize the result. All design,
analysis, and critique logic stays in agents/ and graph/.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError

from api.errors import classify_workflow_error
from api.examples import load_example_prompts
from api.schemas import (
    ArchitectureRequest,
    ArchitectureResponse,
    ErrorResponse,
    ExamplePrompt,
    JobStatusResponse,
    JobSubmittedResponse,
)
from graph.workflow import WorkflowError, run_workflow
from jobs import repository
from jobs.tasks import run_architecture_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/architectures", tags=["architectures"])


def _to_http_error(exc: WorkflowError) -> HTTPException:
    """Map a workflow failure to an HTTP error (rules live in api/errors.py)."""
    failure = classify_workflow_error(exc)
    return HTTPException(failure.status_code, failure.message)


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
    """Example prompts that can be sent to POST /api/v1/architectures."""
    return load_example_prompts()


_ERROR_RESPONSES = {
    code: {"model": ErrorResponse}
    for code in (
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        status.HTTP_502_BAD_GATEWAY,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        status.HTTP_504_GATEWAY_TIMEOUT,
    )
}


# A plain `def` (not `async def`): run_workflow blocks for minutes on LLM
# calls, so FastAPI runs it in its threadpool instead of on the event loop,
# keeping other requests (e.g. /health) responsive during a run.
@router.post("", response_model=ArchitectureResponse, responses=_ERROR_RESPONSES)
def create_architecture(request: ArchitectureRequest) -> ArchitectureResponse:
    """Run the full multi-agent workflow and return the architecture and final report.

    Synchronous: the request stays open until the run finishes, which
    typically takes a few minutes.
    """
    try:
        final_state = run_workflow(request.user_request)
    except WorkflowError as exc:
        logger.exception("ArchonAI workflow failed")
        raise _to_http_error(exc) from exc
    return ArchitectureResponse.from_state(final_state)


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

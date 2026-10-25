"""Run one architecture job: load it, run the workflow, store the outcome.

Deliberately independent of *how* it gets called -- FastAPI's BackgroundTasks
today, a Celery worker later -- so swapping the queue never touches this
logic. The workflow itself is the existing run_workflow(), unchanged.
"""

from __future__ import annotations

import logging
from typing import Optional

from api.errors import WorkflowFailure, classify_workflow_error
from api.schemas import ArchitectureResponse
from graph.workflow import run_workflow
from jobs import repository

logger = logging.getLogger(__name__)


def execute_job(job_id: str) -> Optional[WorkflowFailure]:
    """Run the job with this id and record the result in the database.

    Returns None on success (or when the job was skipped), or the classified
    failure so a caller can decide whether to retry.
    """
    job = repository.get_job(job_id)
    if job is None:
        logger.warning("Job %s not found; nothing to run.", job_id)
        return None

    # The guarded queued -> running transition is what makes running the
    # same job twice impossible: a duplicate delivery finds it already
    # running (or finished) and stops here.
    if not repository.mark_running(job_id):
        logger.info("Job %s is not queued (status=%s); skipping.", job_id, job.status.value)
        return None

    try:
        final_state = run_workflow(job.user_request)
        result = ArchitectureResponse.from_state(final_state).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - every failure must end in a stored job status
        logger.exception("Job %s failed", job_id)
        failure = classify_workflow_error(exc)
        repository.mark_failed(job_id, failure.status_code, failure.message)
        return failure

    repository.mark_succeeded(job_id, result)
    logger.info("Job %s succeeded.", job_id)
    return None

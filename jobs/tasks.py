"""Celery tasks for ArchonAI.

A thin doorway: the worker calls this task, and the task calls
jobs.runner.execute_job -- the same function the API's in-process background
runner uses. All job logic (status transitions, running the workflow,
storing the result or a client-safe error) lives there, not here.
"""

from __future__ import annotations

from jobs.celery_app import celery_app
from jobs.runner import execute_job


# An explicit name keeps queued messages valid even if this module moves.
@celery_app.task(name="archonai.run_architecture_job")
def run_architecture_job(job_id: str) -> None:
    """Run one architecture job by id (status and result are stored in MySQL)."""
    execute_job(job_id)

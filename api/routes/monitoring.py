"""GET /api/v1/architectures/jobs/{job_id}/monitoring: one job's metrics and log events, read from CloudWatch.

Read-only, and only for the job's owner (anyone else gets the same 404 as for a job that does not
exist). Each answer is cached for a few seconds while the job is live, and longer once it is over,
so reloading the page does not query CloudWatch every time. Failed reads are never cached.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from api.schemas import (
    ErrorResponse,
    MonitoringAgent,
    MonitoringEvent,
    MonitoringLLMCall,
    MonitoringResponse,
    MonitoringSummary,
    _as_utc,
)
from auth.dependencies import get_current_user
from auth.models import User
from graph import cloudwatch_reader
from graph.cloudwatch_reader import MonitoringUnavailable
from jobs import repository
from jobs.models import ArchitectureJob, JobStatus, utcnow
from jobs.monitoring import build_report, parse_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/architectures/jobs", tags=["monitoring"])

_ERRORS = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}

# Logs reach CloudWatch a few seconds after they are written, and the worker's stream can lag a little more.
WINDOW_BEFORE = timedelta(minutes=2)
WINDOW_AFTER = timedelta(minutes=10)
RECENT = timedelta(minutes=2)
LIVE_TTL_SECONDS = 8
SETTLED_TTL_SECONDS = 300
CACHE_ENTRIES = 256

_MESSAGES = {
    "disabled": "CloudWatch logging is switched off on this server, so there is nothing to show.",
    "no_credentials": "This server has no AWS credentials, so it can't read CloudWatch.",
    "forbidden": "This server isn't allowed to read CloudWatch Logs. Attach the logs-read policy in monitoring/iam/ to its AWS identity.",
    "throttled": "CloudWatch is busy right now. Please try again in a moment.",
    "unreachable": "CloudWatch couldn't be reached. Please try again later.",
    "empty": "No log lines were found for this job. Logs arrive a few seconds late, and jobs from before CloudWatch logging was switched on (or older than its retention period) have none.",
}

_cache: "OrderedDict[str, tuple[float, MonitoringResponse]]" = OrderedDict()
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _ms(moment: datetime) -> int:
    return int(moment.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _from_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def _base(job: ArchitectureJob, state: str, may_still_arrive: bool, **extra) -> MonitoringResponse:
    return MonitoringResponse(
        job_id=job.id,
        job_status=job.status,
        attempts=job.attempts,
        created_at=_as_utc(job.created_at),
        finished_at=_as_utc(job.finished_at) if job.finished_at else None,
        state=state,
        message=_MESSAGES.get(state),
        may_still_arrive=may_still_arrive,
        fetched_at=datetime.now(timezone.utc),
        **extra,
    )


@router.get("/{job_id}/monitoring", response_model=MonitoringResponse, responses=_ERRORS)
def get_job_monitoring(job_id: str, user: User = Depends(get_current_user)) -> MonitoringResponse:
    """The job's agent timings, LLM calls and log events. Only the owner can read it."""
    try:
        job = repository.get_owned_job(job_id, user.id)
    except SQLAlchemyError as exc:
        logger.error("Monitoring job lookup failed (%s).", type(exc).__name__)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Job store is unavailable. Please retry later.") from None
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")

    now = utcnow()
    unfinished = job.status in (JobStatus.QUEUED, JobStatus.RUNNING)
    live = unfinished or (job.finished_at is not None and now - job.finished_at < RECENT)

    with _cache_lock:
        hit = _cache.get(job.id)
        if hit is not None and hit[0] > time.monotonic():
            return hit[1]

    start = _ms(job.created_at - WINDOW_BEFORE)
    end = _ms((job.finished_at or now) + WINDOW_AFTER)
    try:
        raw = cloudwatch_reader.read_job_events(job.id, start, end)
    except MonitoringUnavailable as exc:
        return _base(job, exc.reason, live)  # never cached: the cause may be fixed any moment

    events = [e for e in (parse_event(r, job.id) for r in raw) if e is not None]
    if not events:
        response = _base(job, "empty", live)
    else:
        report = build_report(events)
        response = _base(
            job,
            "ok",
            live,
            summary=MonitoringSummary(**report.summary),
            agents=[MonitoringAgent(**a) for a in report.agents],
            llm_calls=[MonitoringLLMCall(time=_from_ms(c.pop("timestamp_ms")), **c) for c in report.llm_calls],
            timeline=[MonitoringEvent(time=_from_ms(e.timestamp_ms), service=e.service, level=e.level, event=e.event, fields=e.fields) for e in report.timeline],
            truncated=report.truncated,
        )
    with _cache_lock:
        _cache[job.id] = (time.monotonic() + (LIVE_TTL_SECONDS if live else SETTLED_TTL_SECONDS), response)
        _cache.move_to_end(job.id)
        while len(_cache) > CACHE_ENTRIES:
            _cache.popitem(last=False)
    return response

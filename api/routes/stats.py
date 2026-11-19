"""GET /api/v1/stats: the signed-in user's own job statistics (shown on the Settings page).

Everything is computed from that user's rows only; the user comes from the session
cookie, never from a parameter. Averages use the newest succeeded jobs (see
jobs.repository.STATS_SAMPLE_LIMIT) and are null until there is something to average.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from api.schemas import ErrorResponse, JobResultSummary, StatsDay, StatsJobs, StatsResponse, _as_utc
from auth.dependencies import get_current_user
from auth.models import User
from jobs import repository
from jobs.models import JobStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])

_ERRORS = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}


def _mean(values: list[float], digits: int = 1) -> Optional[float]:
    return round(sum(values) / len(values), digits) if values else None


@router.get("", response_model=StatsResponse, responses=_ERRORS)
def get_stats(user: User = Depends(get_current_user)) -> StatsResponse:
    """Counts, rates, averages and a 14-day activity series for the signed-in user."""
    try:
        data = repository.owner_stats(user.id)
    except SQLAlchemyError as exc:
        # Class name only: SQLAlchemy messages can include statement parameters.
        logger.error("Statistics query failed (%s).", type(exc).__name__)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Job store is unavailable. Please retry later.") from None

    succeeded, failed = data.counts[JobStatus.SUCCEEDED], data.counts[JobStatus.FAILED]
    durations: list[float] = []
    scores: list[float] = []
    services: list[float] = []
    verdicts: list[bool] = []
    for created_at, finished_at, result in data.sample:
        if finished_at is not None:
            durations.append(max(0.0, (finished_at - created_at).total_seconds()))
        summary = JobResultSummary.from_result(result)
        if summary is None:
            continue
        if summary.critic_score is not None:
            scores.append(summary.critic_score)
        if summary.aws_service_count is not None:
            services.append(summary.aws_service_count)
        if summary.approved is not None:
            verdicts.append(summary.approved)

    return StatsResponse(
        jobs=StatsJobs(
            total=sum(data.counts.values()),
            queued=data.counts[JobStatus.QUEUED],
            running=data.counts[JobStatus.RUNNING],
            succeeded=succeeded,
            failed=failed,
        ),
        success_rate=round(succeeded / (succeeded + failed), 3) if succeeded + failed else None,
        average_total_seconds=_mean(durations),
        average_critic_score=_mean(scores),
        approval_rate=round(sum(verdicts) / len(verdicts), 3) if verdicts else None,
        average_aws_services=_mean(services),
        jobs_last_7_days=data.last_7_days,
        jobs_last_30_days=data.last_30_days,
        first_job_at=_as_utc(data.first_job_at) if data.first_job_at else None,
        last_job_at=_as_utc(data.last_job_at) if data.last_job_at else None,
        daily=[StatsDay(date=day.isoformat(), jobs=count) for day, count in data.daily],
        sample_size=len(data.sample),
        sample_capped=data.sample_capped,
    )

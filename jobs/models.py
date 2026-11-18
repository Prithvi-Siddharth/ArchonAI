"""Database models for ArchonAI's background jobs.

One table, architecture_jobs: one row per submitted design request, holding
its status, the stored result (or a client-safe error), and timestamps.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from jobs.db import Base


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def utcnow() -> datetime:
    """Current UTC time as a naive datetime.

    MySQL DATETIME columns don't store a timezone, so every timestamp is
    stored as naive UTC by convention -- mixing aware and naive values would
    otherwise make comparisons fail depending on which database is in use.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_job_id() -> str:
    return str(uuid.uuid4())


class ArchitectureJob(Base):
    """One background architecture-design job."""

    __tablename__ = "architecture_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_job_id)
    # native_enum=False stores the status as a short string (plus a CHECK
    # constraint) so the column behaves identically on MySQL and SQLite.
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]),
        default=JobStatus.QUEUED,
        nullable=False,
        index=True,
    )
    user_request: Mapped[str] = mapped_column(Text, nullable=False)
    # The account that submitted the job (users.id). NULL for jobs created before
    # accounts existed: those belong to nobody and no one can open them via the API.
    # Kept as a plain indexed column (no foreign key) so the in-place migration in
    # jobs/db.py produces exactly the same schema as a fresh create_all.
    owner_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    # The serialized ArchitectureResponse (api/schemas.py) once the job succeeds.
    result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    # Only the generic, client-safe message is ever stored -- never raw
    # provider error text, which can contain request details.
    error_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

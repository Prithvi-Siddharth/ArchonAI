"""Request/response models for the ArchonAI REST API.

These are thin API contracts layered over the existing structured-output
models in models/schemas.py -- the agents' own schemas are reused directly
rather than redefined, so the API can never drift from what the workflow
actually produces.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator

from auth.models import User
from graph.state import MAX_REVISIONS, ArchonState
from jobs.models import ArchitectureJob, JobStatus
from models.schemas import (
    AnalysisResult,
    Architecture,
    ArchitecturePlan,
    CostAnalysis,
    CriticReview,
    FinalReport,
    Requirements,
    ValidationResult,
)


class ArchitectureRequest(BaseModel):
    """A user's natural-language description of the system to design."""

    # Whitespace is stripped before the length check, so a blank or
    # whitespace-only request is rejected here (422) before any LLM call.
    user_request: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=4000)] = Field(
        description="Plain-English description of the system to design.",
        examples=[
            "Design an e-commerce platform that supports 500,000 concurrent users, requires "
            "high availability, low latency, secure payment processing, and must scale during "
            "traffic spikes."
        ],
    )


class TraceEntryModel(BaseModel):
    """One recorded workflow step (mirrors graph.state.TraceEntry)."""

    node: str
    action: str
    output_summary: str
    iteration: int


class ArchitectureResponse(BaseModel):
    """The full result of one ArchonAI workflow run."""

    approved: bool = Field(description="Whether the critic approved the final architecture.")
    max_revisions_reached: bool = Field(
        description="True if the revision limit was hit before the critic approved the design."
    )
    revision_count: int = Field(description="Number of critic-driven revisions performed.")

    requirements: Requirements
    architecture_plan: ArchitecturePlan
    architecture: Architecture

    compute_analysis: AnalysisResult
    database_analysis: AnalysisResult
    networking_analysis: AnalysisResult
    security_analysis: AnalysisResult
    reliability_analysis: AnalysisResult
    cost_analysis: CostAnalysis

    validation_results: ValidationResult
    critic_review: CriticReview
    final_report: FinalReport

    execution_trace: list[TraceEntryModel]

    @classmethod
    def from_state(cls, state: ArchonState) -> ArchitectureResponse:
        """Build the response from a completed workflow's final state."""
        review: CriticReview = state["critic_review"]
        revision_count = state.get("revision_count", 0)
        return cls(
            approved=review.approved,
            max_revisions_reached=not review.approved and revision_count >= MAX_REVISIONS,
            revision_count=revision_count,
            requirements=state["requirements"],
            architecture_plan=state["architecture_plan"],
            architecture=state["architecture"],
            compute_analysis=state["compute_analysis"],
            database_analysis=state["database_analysis"],
            networking_analysis=state["networking_analysis"],
            security_analysis=state["security_analysis"],
            reliability_analysis=state["reliability_analysis"],
            cost_analysis=state["cost_analysis"],
            validation_results=state["validation_results"],
            critic_review=review,
            final_report=state["final_report"],
            execution_trace=state.get("execution_trace", []),
        )


class ExamplePrompt(BaseModel):
    """One example prompt, as stored in data/example_prompts.json."""

    label: str
    prompt: str


class HealthResponse(BaseModel):
    status: str = "ok"


class ErrorResponse(BaseModel):
    """Shape of every error reply (documented in /docs)."""

    detail: str


class JobSubmittedResponse(BaseModel):
    """Reply to a job submission: where to check on it."""

    job_id: str
    status: JobStatus
    status_url: str = Field(description="Path to poll for this job's status and result.")


class JobError(BaseModel):
    """Client-safe description of why a job failed (or is being retried)."""

    status_code: int
    message: str


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    # Stored as naive UTC (see jobs/models.py utcnow); mark it as UTC so
    # clients receive an unambiguous timestamp.
    return value.replace(tzinfo=timezone.utc) if value is not None else None


def _job_error(job: ArchitectureJob) -> Optional[JobError]:
    if job.error_status_code is None:
        return None
    return JobError(status_code=job.error_status_code, message=job.error_message or "")


class JobStatusResponse(BaseModel):
    """A job's current state, plus its result once it has succeeded."""

    job_id: str
    user_request: str = Field(description="The design request as submitted (trimmed).")
    status: JobStatus
    attempts: int
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[JobError] = Field(
        default=None, description="Set when the job failed, or while it is queued for a retry."
    )
    result: Optional[ArchitectureResponse] = Field(default=None, description="Set once status is 'succeeded'.")

    @classmethod
    def from_job(cls, job: ArchitectureJob) -> JobStatusResponse:
        return cls(
            job_id=job.id,
            user_request=job.user_request,
            status=job.status,
            attempts=job.attempts,
            created_at=_as_utc(job.created_at),
            started_at=_as_utc(job.started_at),
            finished_at=_as_utc(job.finished_at),
            error=_job_error(job),
            result=ArchitectureResponse.model_validate(job.result) if job.result is not None else None,
        )


# --- Job history (GET /api/v1/architectures/jobs) ---


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


class JobResultSummary(BaseModel):
    """A few headline facts from a succeeded job's stored result -- not the result itself.

    Every field is read defensively and is null when the stored result lacks it, so an
    older or partial result never breaks the list. GET /jobs/{job_id} returns the full result.
    """

    approved: Optional[bool] = None
    critic_score: Optional[int] = None
    architecture_version: Optional[int] = None
    aws_service_count: Optional[int] = None
    estimated_monthly_range: Optional[str] = None
    max_revisions_reached: Optional[bool] = None

    @classmethod
    def from_result(cls, result: object) -> Optional[JobResultSummary]:
        if not isinstance(result, dict):
            return None
        architecture = _dict(result.get("architecture"))
        services = architecture.get("services")

        def typed(value: object, kind: type):
            # bool is a subclass of int; never let True pass as a score or a version.
            if kind is int and isinstance(value, bool):
                return None
            return value if isinstance(value, kind) else None

        return cls(
            approved=typed(result.get("approved"), bool),
            critic_score=typed(_dict(result.get("critic_review")).get("score"), int),
            architecture_version=typed(architecture.get("version"), int),
            aws_service_count=len(services) if isinstance(services, list) else None,
            estimated_monthly_range=typed(_dict(result.get("cost_analysis")).get("estimated_monthly_range"), str),
            max_revisions_reached=typed(result.get("max_revisions_reached"), bool),
        )


class JobHistoryItem(BaseModel):
    """One row of the history list: the job's metadata plus a small result summary."""

    job_id: str
    user_request: str
    status: JobStatus
    attempts: int
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    updated_at: datetime
    error: Optional[JobError] = None
    summary: Optional[JobResultSummary] = Field(default=None, description="Set only for succeeded jobs with a stored result.")

    @classmethod
    def from_job(cls, job: ArchitectureJob) -> JobHistoryItem:
        return cls(
            job_id=job.id,
            user_request=job.user_request,
            status=job.status,
            attempts=job.attempts,
            created_at=_as_utc(job.created_at),
            started_at=_as_utc(job.started_at),
            finished_at=_as_utc(job.finished_at),
            updated_at=_as_utc(job.updated_at),
            error=_job_error(job),
            summary=JobResultSummary.from_result(job.result) if job.status == JobStatus.SUCCEEDED else None,
        )


class JobStatusCounts(BaseModel):
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0


class JobHistoryResponse(BaseModel):
    """A page of the signed-in user's jobs, newest first."""

    items: list[JobHistoryItem]
    total: int = Field(description="Jobs matching the search and status filter (across all pages).")
    limit: int
    offset: int
    counts: JobStatusCounts = Field(description="Jobs per status for the same search, ignoring the status filter.")


# --- Accounts (only needed for the /api/v1/auth endpoints) ---

# A deliberately simple shape check (something@something.tld, no spaces); deliverability
# is not verified. 254 is the longest address SMTP allows.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalise_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not _EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    return email


class RegisterRequest(BaseModel):
    """A new account. The email is stored trimmed and lowercase."""

    email: str = Field(examples=["you@example.com"])
    # Not trimmed: spaces are allowed and count. 128 caps the hashing work per request.
    password: str = Field(min_length=8, max_length=128, description="8 to 128 characters.")

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return _normalise_email(value)


class LoginRequest(BaseModel):
    """Credentials for an existing account."""

    email: str = Field(examples=["you@example.com"])
    # No minimum here, so a policy change never locks out an existing account.
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return _normalise_email(value)


class UserResponse(BaseModel):
    """The signed-in account. Never includes the password hash."""

    id: str
    email: str
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> UserResponse:
        return cls(id=user.id, email=user.email, created_at=_as_utc(user.created_at))

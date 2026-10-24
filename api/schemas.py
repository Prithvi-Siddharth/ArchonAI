"""Request/response models for the ArchonAI REST API.

These are thin API contracts layered over the existing structured-output
models in models/schemas.py -- the agents' own schemas are reused directly
rather than redefined, so the API can never drift from what the workflow
actually produces.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from graph.state import MAX_REVISIONS, ArchonState
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

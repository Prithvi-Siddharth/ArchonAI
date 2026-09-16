"""Shared LangGraph state for the ArchonAI workflow.

Every node reads from and writes to this single typed state. LangGraph merges
each node's returned partial dict into the running state, which is how
independent branches (compute/database/networking, then security/reliability/
cost) can fan out and later fan back in without stepping on each other.
"""

from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict

from models.schemas import (
    Architecture,
    ArchitecturePlan,
    CostAnalysis,
    CriticReview,
    FinalReport,
    Requirements,
    ValidationResult,
)
from models.schemas import AnalysisResult

MAX_REVISIONS = 2


class TraceEntry(TypedDict):
    """One recorded step of the workflow, shown in the UI's execution trace."""

    node: str
    action: str
    output_summary: str
    iteration: int


class ArchonState(TypedDict, total=False):
    """The full shared state threaded through the LangGraph workflow."""

    user_request: str

    requirements: Optional[Requirements]
    architecture_plan: Optional[ArchitecturePlan]
    architecture: Optional[Architecture]

    compute_analysis: Optional[AnalysisResult]
    database_analysis: Optional[AnalysisResult]
    networking_analysis: Optional[AnalysisResult]
    security_analysis: Optional[AnalysisResult]
    reliability_analysis: Optional[AnalysisResult]
    cost_analysis: Optional[CostAnalysis]

    validation_results: Optional[ValidationResult]
    critic_review: Optional[CriticReview]

    revision_count: int
    # Multiple parallel branches (compute/database/networking, then
    # security/reliability/cost) each append to this list in the same
    # superstep. LangGraph requires a reducer to merge concurrent writes to
    # one key, so each node returns a single-item list and operator.add
    # concatenates them (and folds in the running total across supersteps).
    execution_trace: Annotated[list[TraceEntry], operator.add]

    final_report: Optional[FinalReport]

    error: Optional[str]


def make_trace_entry(node: str, action: str, output_summary: str, iteration: int = 0) -> TraceEntry:
    """Build one execution-trace entry recording what a node did."""
    return TraceEntry(node=node, action=action, output_summary=output_summary, iteration=iteration)


def create_initial_state(user_request: str) -> ArchonState:
    """Build a fresh state for a new architecture design run."""
    return ArchonState(
        user_request=user_request,
        requirements=None,
        architecture_plan=None,
        architecture=None,
        compute_analysis=None,
        database_analysis=None,
        networking_analysis=None,
        security_analysis=None,
        reliability_analysis=None,
        cost_analysis=None,
        validation_results=None,
        critic_review=None,
        revision_count=0,
        execution_trace=[],
        final_report=None,
        error=None,
    )

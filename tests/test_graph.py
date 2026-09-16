"""Tests for the LangGraph state and workflow.

The full-workflow tests mock the LLM layer (agents.llm.get_llm and
agents.llm.invoke_structured) so the entire graph -- including the fan-out/
fan-in analysis stages and the critic/revision loop -- can be exercised
without a real GROQ_API_KEY or network access.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from agents import llm as llm_module
from graph.state import MAX_REVISIONS, create_initial_state
from graph.workflow import WorkflowError, _route_after_critic, run_workflow
from models.schemas import (
    AnalysisResult,
    Architecture,
    ArchitecturePlan,
    CostAnalysis,
    CriticReview,
    FinalReport,
    Requirements,
)

from .conftest import (
    make_architecture,
    make_architecture_plan,
    make_analysis,
    make_cost_analysis,
    make_critic_review,
    make_final_report,
    make_requirements,
)


# --- State creation ------------------------------------------------------------


def test_create_initial_state_has_expected_defaults():
    state = create_initial_state("Design a blogging platform for 10,000 users.")
    assert state["user_request"] == "Design a blogging platform for 10,000 users."
    assert state["revision_count"] == 0
    assert state["execution_trace"] == []
    assert state["requirements"] is None
    assert state["architecture"] is None
    assert state["final_report"] is None
    assert state["error"] is None


def test_create_initial_state_strips_nothing_by_itself():
    # create_initial_state stores the request as given; trimming happens in run_workflow.
    state = create_initial_state("  padded request  ")
    assert state["user_request"] == "  padded request  "


# --- Conditional routing --------------------------------------------------------


def test_route_after_critic_approved_goes_to_final_report():
    state = {"critic_review": make_critic_review(approved=True), "revision_count": 0}
    assert _route_after_critic(state) == "approved"


def test_route_after_critic_rejected_under_max_goes_to_revision():
    state = {"critic_review": make_critic_review(approved=False), "revision_count": 1}
    assert _route_after_critic(state) == "rejected"


def test_route_after_critic_rejected_at_max_forces_final_report():
    state = {"critic_review": make_critic_review(approved=False), "revision_count": MAX_REVISIONS}
    assert _route_after_critic(state) == "max_revisions_reached"


# --- Mocked LLM layer for full-graph tests --------------------------------------


class _FakeToolCallingLLM:
    """Stands in for a ChatGroq model bound with tools; never emits tool calls,
    so the Architecture Designer's research loop exits after one round."""

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return AIMessage(content="", tool_calls=[])


def _dummy_for_schema(schema, critic_verdicts, call_counter):
    if schema is Requirements:
        return make_requirements()
    if schema is ArchitecturePlan:
        return make_architecture_plan()
    if schema is Architecture:
        return make_architecture()
    if schema is AnalysisResult:
        return make_analysis()
    if schema is CostAnalysis:
        return make_cost_analysis()
    if schema is CriticReview:
        idx = min(call_counter["critic_calls"], len(critic_verdicts) - 1)
        approved = critic_verdicts[idx]
        call_counter["critic_calls"] += 1
        return make_critic_review(approved=approved)
    if schema is FinalReport:
        return make_final_report()
    raise AssertionError(f"No dummy factory registered for schema {schema}")


def _patch_llm(monkeypatch, critic_verdicts: list[bool]) -> dict:
    """Patch the LLM layer so every agent gets a deterministic structured
    response, with CriticReview verdicts following `critic_verdicts` in
    order (the last value repeats if the critic is called more times)."""
    call_counter = {"critic_calls": 0}

    def fake_get_llm(temperature: float = 0.2, max_tokens: int = 2048):
        return _FakeToolCallingLLM()

    def fake_invoke_structured(llm, schema, prompt):
        return _dummy_for_schema(schema, critic_verdicts, call_counter)

    monkeypatch.setattr(llm_module, "get_llm", fake_get_llm)
    monkeypatch.setattr(llm_module, "invoke_structured", fake_invoke_structured)
    return call_counter


# --- Full workflow: happy path ---------------------------------------------------


def test_full_workflow_approves_immediately_and_populates_all_state(monkeypatch):
    _patch_llm(monkeypatch, critic_verdicts=[True])

    final_state = run_workflow("Design an e-commerce platform for 500,000 concurrent users.")

    assert final_state["revision_count"] == 0
    assert final_state["critic_review"].approved is True
    assert final_state["final_report"] is not None

    for key in (
        "requirements",
        "architecture_plan",
        "architecture",
        "compute_analysis",
        "database_analysis",
        "networking_analysis",
        "security_analysis",
        "reliability_analysis",
        "cost_analysis",
        "validation_results",
    ):
        assert final_state[key] is not None, f"{key} was not populated"

    node_names = [entry["node"] for entry in final_state["execution_trace"]]
    for expected_node in (
        "Requirements Analyzer",
        "Architecture Planner",
        "Architecture Designer",
        "Compute Agent",
        "Database Agent",
        "Networking Agent",
        "Security Agent",
        "Reliability Agent",
        "Cost Agent",
        "Architecture Validator",
        "Architecture Critic",
        "Final Report",
    ):
        assert expected_node in node_names


# --- Full workflow: critic rejection and revision loop ---------------------------


def test_critic_rejection_triggers_revision_then_approval(monkeypatch):
    call_counter = _patch_llm(monkeypatch, critic_verdicts=[False, True])

    final_state = run_workflow("Design a ride-sharing platform with real-time matching.")

    assert call_counter["critic_calls"] == 2
    assert final_state["revision_count"] == 1
    assert final_state["critic_review"].approved is True
    assert final_state["architecture"].version == 2
    assert final_state["final_report"] is not None

    node_names = [entry["node"] for entry in final_state["execution_trace"]]
    assert node_names.count("Architecture Critic") == 2
    assert node_names.count("Architecture Revision") == 1


# --- Maximum revision protection -------------------------------------------------


def test_max_revision_protection_terminates_instead_of_looping_forever(monkeypatch):
    call_counter = _patch_llm(monkeypatch, critic_verdicts=[False])  # always rejects

    final_state = run_workflow("Design a banking transaction system that never satisfies the critic.")

    assert final_state["revision_count"] == MAX_REVISIONS
    assert call_counter["critic_calls"] == MAX_REVISIONS + 1
    assert final_state["critic_review"].approved is False
    # Even though never approved, the graph must still terminate with a report.
    assert final_state["final_report"] is not None

    node_names = [entry["node"] for entry in final_state["execution_trace"]]
    assert node_names.count("Architecture Revision") == MAX_REVISIONS


# --- Error handling ---------------------------------------------------------------


def test_run_workflow_rejects_empty_request():
    with pytest.raises(WorkflowError):
        run_workflow("")


def test_run_workflow_rejects_whitespace_only_request():
    with pytest.raises(WorkflowError):
        run_workflow("   ")


def test_run_workflow_wraps_llm_failures_as_workflow_error(monkeypatch):
    def failing_get_llm(temperature: float = 0.2, max_tokens: int = 2048):
        raise RuntimeError("Groq API unreachable")

    monkeypatch.setattr(llm_module, "get_llm", failing_get_llm)

    with pytest.raises(WorkflowError):
        run_workflow("Design a social media platform.")

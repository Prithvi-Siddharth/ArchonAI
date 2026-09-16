"""ArchonAI's LangGraph workflow.

This is the central orchestration graph. It is intentionally not a linear
chain: after the architecture is first designed, the graph fans out into
three two-agent analysis stages -- infrastructure (compute, database), then
connectivity/protection (networking, security), then operations/economics
(reliability, cost) -- joins them into a deterministic validator, and then
enters a critic/revision loop bounded by MAX_REVISIONS so the graph is
guaranteed to terminate.

Two agents per stage (rather than all six at once) keeps peak concurrent LLM
calls low, which matters on rate-limited API keys: a run's total token usage
is the same either way, but spreading it over three smaller bursts instead
of two larger ones lowers the odds any single burst trips a provider's
per-minute ceiling.

    requirements -> planner -> designer
        -> [compute, database]                        (parallel)
        -> [networking, security]                      (parallel)
        -> [reliability, cost]                          (parallel)
        -> validator (deterministic tool)
        -> critic (LLM judge)
             -> approved         -> final_report -> END
             -> rejected         -> revision -> critic (loop)
             -> max_revisions    -> final_report -> END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agents import (
    architecture as architecture_agent,
    compute as compute_agent,
    cost as cost_agent,
    critic as critic_agent,
    database as database_agent,
    networking as networking_agent,
    planner as planner_agent,
    reliability as reliability_agent,
    report as report_agent,
    requirements as requirements_agent,
    revision as revision_agent,
    security as security_agent,
)
from graph.state import MAX_REVISIONS, ArchonState, create_initial_state, make_trace_entry
from tools.architecture_validator import validate_architecture

# Node name constants, reused for both graph wiring and trace/UI display.
REQUIREMENTS_ANALYZER = "requirements_analyzer"
ARCHITECTURE_PLANNER = "architecture_planner"
ARCHITECTURE_DESIGNER = "architecture_designer"
COMPUTE_AGENT = "compute_agent"
DATABASE_AGENT = "database_agent"
NETWORKING_AGENT = "networking_agent"
SECURITY_AGENT = "security_agent"
RELIABILITY_AGENT = "reliability_agent"
COST_AGENT = "cost_agent"
ARCHITECTURE_VALIDATOR = "architecture_validator"
ARCHITECTURE_CRITIC = "architecture_critic"
ARCHITECTURE_REVISION = "architecture_revision"
FINAL_REPORT = "final_report"

ALL_NODES_IN_ORDER = [
    REQUIREMENTS_ANALYZER,
    ARCHITECTURE_PLANNER,
    ARCHITECTURE_DESIGNER,
    COMPUTE_AGENT,
    DATABASE_AGENT,
    NETWORKING_AGENT,
    SECURITY_AGENT,
    RELIABILITY_AGENT,
    COST_AGENT,
    ARCHITECTURE_VALIDATOR,
    ARCHITECTURE_CRITIC,
    ARCHITECTURE_REVISION,
    FINAL_REPORT,
]

NODE_DISPLAY_NAMES = {
    REQUIREMENTS_ANALYZER: "Requirements Analyzer",
    ARCHITECTURE_PLANNER: "Architecture Planner",
    ARCHITECTURE_DESIGNER: "Architecture Designer",
    COMPUTE_AGENT: "Compute Agent",
    DATABASE_AGENT: "Database Agent",
    NETWORKING_AGENT: "Networking Agent",
    SECURITY_AGENT: "Security Agent",
    RELIABILITY_AGENT: "Reliability Agent",
    COST_AGENT: "Cost Agent",
    ARCHITECTURE_VALIDATOR: "Architecture Validator",
    ARCHITECTURE_CRITIC: "Architecture Critic",
    ARCHITECTURE_REVISION: "Architecture Revision",
    FINAL_REPORT: "Final Report",
}


def _run_validator(state: ArchonState) -> dict:
    """Deterministic Architecture Validator node.

    Runs rule-based checks (tools/architecture_validator.py) and stores the
    result so the critic can weigh confirmed, non-LLM findings alongside its
    own judgment.
    """
    architecture = state["architecture"]
    requirements = state["requirements"]
    result = validate_architecture(architecture, requirements)

    entry = make_trace_entry(
        node="Architecture Validator",
        action=f"Ran deterministic rule-based checks; found {len(result.issues)} issue(s).",
        output_summary=(
            "; ".join(issue.rule for issue in result.issues)
            if result.issues
            else "No deterministic issues found."
        ),
        iteration=state.get("revision_count", 0),
    )
    return {"validation_results": result, "execution_trace": [entry]}


def _route_after_critic(state: ArchonState) -> str:
    """Conditional edge: decide whether to finalize, revise, or stop revising.

    This is the decision point that makes this graph a real workflow rather
    than a linear chain -- the critic can send the design back for rework,
    bounded by MAX_REVISIONS to guarantee the graph terminates.
    """
    review = state["critic_review"]
    revision_count = state.get("revision_count", 0)

    if review.approved:
        return "approved"
    if revision_count >= MAX_REVISIONS:
        return "max_revisions_reached"
    return "rejected"


def build_graph():
    """Construct and compile the ArchonAI LangGraph StateGraph."""
    graph = StateGraph(ArchonState)

    graph.add_node(REQUIREMENTS_ANALYZER, requirements_agent.run)
    graph.add_node(ARCHITECTURE_PLANNER, planner_agent.run)
    graph.add_node(ARCHITECTURE_DESIGNER, architecture_agent.run)
    graph.add_node(COMPUTE_AGENT, compute_agent.run)
    graph.add_node(DATABASE_AGENT, database_agent.run)
    graph.add_node(NETWORKING_AGENT, networking_agent.run)
    graph.add_node(SECURITY_AGENT, security_agent.run)
    graph.add_node(RELIABILITY_AGENT, reliability_agent.run)
    graph.add_node(COST_AGENT, cost_agent.run)
    graph.add_node(ARCHITECTURE_VALIDATOR, _run_validator)
    graph.add_node(ARCHITECTURE_CRITIC, critic_agent.run)
    graph.add_node(ARCHITECTURE_REVISION, revision_agent.run)
    graph.add_node(FINAL_REPORT, report_agent.run)

    graph.add_edge(START, REQUIREMENTS_ANALYZER)
    graph.add_edge(REQUIREMENTS_ANALYZER, ARCHITECTURE_PLANNER)
    graph.add_edge(ARCHITECTURE_PLANNER, ARCHITECTURE_DESIGNER)

    # Three two-agent stages instead of two three-agent stages: same total
    # work, but each parallel burst is smaller, which is kinder to
    # rate-limited API keys (see module docstring).
    graph.add_edge(ARCHITECTURE_DESIGNER, COMPUTE_AGENT)
    graph.add_edge(ARCHITECTURE_DESIGNER, DATABASE_AGENT)

    for source in (COMPUTE_AGENT, DATABASE_AGENT):
        for target in (NETWORKING_AGENT, SECURITY_AGENT):
            graph.add_edge(source, target)

    for source in (NETWORKING_AGENT, SECURITY_AGENT):
        for target in (RELIABILITY_AGENT, COST_AGENT):
            graph.add_edge(source, target)

    # Fan-in: the validator waits for the final stage's two analyses.
    graph.add_edge(RELIABILITY_AGENT, ARCHITECTURE_VALIDATOR)
    graph.add_edge(COST_AGENT, ARCHITECTURE_VALIDATOR)

    graph.add_edge(ARCHITECTURE_VALIDATOR, ARCHITECTURE_CRITIC)

    graph.add_conditional_edges(
        ARCHITECTURE_CRITIC,
        _route_after_critic,
        {
            "approved": FINAL_REPORT,
            "max_revisions_reached": FINAL_REPORT,
            "rejected": ARCHITECTURE_REVISION,
        },
    )
    graph.add_edge(ARCHITECTURE_REVISION, ARCHITECTURE_CRITIC)
    graph.add_edge(FINAL_REPORT, END)

    return graph.compile()


_compiled_graph = None


def get_compiled_graph():
    """Lazily build and cache the compiled graph (LLM client construction is deferred)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


class WorkflowError(RuntimeError):
    """Raised when the ArchonAI workflow fails to complete."""


def run_workflow(user_request: str) -> ArchonState:
    """Run the full ArchonAI graph end-to-end for a user request.

    Wraps graph execution so missing configuration, LLM failures, or
    unexpected errors surface as a single clear WorkflowError instead of a
    raw traceback, while still returning any partial state gathered so far
    where possible.
    """
    if not user_request or not user_request.strip():
        raise WorkflowError("Please describe the system you want to build before running ArchonAI.")

    graph = get_compiled_graph()
    initial_state = create_initial_state(user_request.strip())

    try:
        final_state = graph.invoke(initial_state, config={"recursion_limit": 60})
    except Exception as exc:  # noqa: BLE001 - normalize all graph failures for the UI
        raise WorkflowError(f"ArchonAI workflow failed: {exc}") from exc

    return final_state


def stream_workflow_updates(user_request: str):
    """Run the graph while yielding (node_name, partial_state) as each node
    completes, so a caller (the Streamlit UI) can render live progress
    instead of blocking silently until the whole run finishes.

    Each yielded partial_state is exactly what that node returned -- the
    caller is responsible for merging it into a running accumulated state
    (see app.py), mirroring how LangGraph's own reducers merge state.
    """
    if not user_request or not user_request.strip():
        raise WorkflowError("Please describe the system you want to build before running ArchonAI.")

    graph = get_compiled_graph()
    initial_state = create_initial_state(user_request.strip())

    try:
        for update in graph.stream(initial_state, config={"recursion_limit": 60}, stream_mode="updates"):
            for node_name, partial_state in update.items():
                yield node_name, partial_state
    except Exception as exc:  # noqa: BLE001 - normalize all graph failures for the UI
        raise WorkflowError(f"ArchonAI workflow failed: {exc}") from exc

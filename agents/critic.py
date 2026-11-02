"""Architecture Critic agent.

The decision point of the graph. Compares the proposed architecture against
the original requirements and every specialist analysis, incorporating the
deterministic Architecture Validator's findings as ground-truth signal, and
renders a structured verdict that can approve the architecture or reject it
for revision.
"""

from __future__ import annotations

from agents import llm as llm_module
from agents.formatting import compact_analysis, compact_architecture, compact_cost_analysis
from graph.state import ArchonState, make_trace_entry
from models.schemas import (
    AnalysisResult,
    Architecture,
    CostAnalysis,
    CriticReview,
    Requirements,
    Severity,
    ValidationResult,
)

PROMPT_TEMPLATE = """You are a principal cloud architect acting as a critical reviewer.
Your job is to find real problems, not to rubber-stamp the design. Compare the proposed
architecture against the original requirements and the specialist analyses below.

Original Requirements:
{requirements}

Proposed Architecture (version {version}):
{architecture}

Compute Analysis: {compute}
Database Analysis: {database}
Networking Analysis: {networking}
Security Analysis: {security}
Reliability Analysis: {reliability}
Cost Analysis: {cost}

Deterministic validator findings (treat these as confirmed, real issues -- they were
found by rule-based checks, not opinion):
{validation_issues}

Look specifically for: single points of failure, scalability problems, database
bottlenecks, security weaknesses, networking problems, inappropriate service
selection, unnecessary complexity, cost problems, missing components, and any
violation of the stated requirements.

Requirement provenance: in the requirements, explicit_requirements are what the user
actually asked for; inferred_assumptions are the analyst's assumptions, not user
requirements. Severity rules:
- critical: violates an explicit user requirement, is a confirmed validator finding, or is
  a concrete, named risk of data loss, a security breach or an outage at the stated load.
- An unmet inferred assumption or an optional best practice (e.g. multi-region deployment
  when the user did not ask for it) is at most medium, and on its own must not block approval.

Any unresolved CRITICAL deterministic validator finding must result in approved=false.
Score the architecture from 0-100. Only approve (approved=true) if the score is 80 or
higher AND there are no critical issues. List concrete required_changes for anything
that must be fixed before approval.

Hard size limits (the whole response must fit in a small output budget):
- issues: at most 4, the most important first.
- required_changes: at most 4, the most important first.
- strengths: at most 3.
- Every issue, required_change and strength: one sentence, at most 15 words.
- Name the specific service or component in each item; no generic advice.
"""

# The hard limits above exist for the same reason as in agents/architecture.py:
# a CriticReview that overruns its max_tokens budget is cut off mid-tool-call
# and rejected as tool_use_failed -- and a failed critic call is treated as a
# rejection, which forces a needless revision round.


def _format_validation_issues(validation_results: ValidationResult | None) -> str:
    if validation_results is None or not validation_results.issues:
        return "None found by the deterministic validator."
    lines = [
        f"- [{issue.severity.value.upper()}] ({issue.rule}) {issue.message}"
        for issue in validation_results.issues
    ]
    return "\n".join(lines)


def run(state: ArchonState) -> dict:
    """Produce a CriticReview for the current architecture."""
    requirements: Requirements = state["requirements"]
    architecture: Architecture = state["architecture"]
    compute: AnalysisResult = state["compute_analysis"]
    database: AnalysisResult = state["database_analysis"]
    networking: AnalysisResult = state["networking_analysis"]
    security: AnalysisResult = state["security_analysis"]
    reliability: AnalysisResult = state["reliability_analysis"]
    cost: CostAnalysis = state["cost_analysis"]
    validation_results: ValidationResult | None = state.get("validation_results")

    llm = llm_module.get_llm(temperature=0.1)
    prompt = PROMPT_TEMPLATE.format(
        requirements=requirements.model_dump_json(),
        version=architecture.version,
        architecture=compact_architecture(architecture),
        compute=compact_analysis(compute),
        database=compact_analysis(database),
        networking=compact_analysis(networking),
        security=compact_analysis(security),
        reliability=compact_analysis(reliability),
        cost=compact_cost_analysis(cost),
        validation_issues=_format_validation_issues(validation_results),
    )

    try:
        review = llm_module.invoke_structured(llm, CriticReview, prompt)
        verdict = "APPROVED" if review.approved else "REJECTED"
        action = f"Reviewed architecture v{architecture.version} against requirements and validator findings."
        output_summary = f"{verdict} | score={review.score} | issues={len(review.issues)}"
    except llm_module.LLMInvocationError as exc:
        # The critic LLM call itself failed (e.g. an outlasted rate limit).
        # Fail toward "needs more work" rather than crashing the run -- the
        # normal routing (reject -> revise, or finalize at MAX_REVISIONS)
        # still applies on top of this stand-in verdict.
        # Only the safe, classified message: this text is stored, returned by
        # the API and pasted into the revision prompt, and the raw error can
        # carry the model's whole failed generation.
        reason = llm_module.safe_failure_message(exc)
        review = CriticReview(
            approved=False,
            score=0,
            issues=[{"issue": f"Critic review failed: {reason}.", "severity": Severity.HIGH, "category": "system"}],
            required_changes=["Re-run the critic review; it could not be completed this round."],
            strengths=[],
        )
        action = f"Critic review call failed ({reason}); treated as rejected for this round."
        output_summary = "Critic call failed -- treated as rejected."

    entry = make_trace_entry(
        node="Architecture Critic",
        action=action,
        output_summary=output_summary,
        iteration=state.get("revision_count", 0),
    )
    # critic_history accumulates every round (the revision agent reads it all).
    return {"critic_review": review, "critic_history": [review], "execution_trace": [entry]}

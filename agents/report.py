"""Final Report agent.

Terminal node in the graph, reached once the architecture is approved (or the
maximum revision count is hit). Synthesizes every prior agent's output into a
single structured, human-readable final report.
"""

from __future__ import annotations

from graph.state import MAX_REVISIONS, ArchonState, make_trace_entry
from agents import llm as llm_module
from agents.formatting import compact_analysis, compact_architecture, compact_cost_analysis, compact_critic_review
from models.schemas import (
    AnalysisResult,
    Architecture,
    CostAnalysis,
    CriticReview,
    FinalReport,
    Requirements,
)

PROMPT_TEMPLATE = """You are a principal cloud architect writing the final architecture
recommendation report for a stakeholder audience. Synthesize the material below into a
clear, professional report. Be specific and reference actual numbers/services from the
material -- do not write generic filler.

Requirements:
{requirements}

Final Architecture (version {version}):
{architecture}

Compute Analysis: {compute}
Database Analysis: {database}
Networking Analysis: {networking}
Security Analysis: {security}
Reliability Analysis: {reliability}
Cost Analysis: {cost}

Critic Review:
{critic_review}

{revision_note}

Write the final report with these fields:
- executive_summary: 3-5 sentences, for a non-technical stakeholder
- requirements_summary: what was asked for, distilled
- architecture_overview: how the pieces fit together
- aws_services_summary: the services chosen and why, in prose
- data_flow_summary: how a request flows through the system, in prose
- scalability_strategy: how this scales under load
- high_availability_strategy: how this stays up during failures
- security_summary: how this protects data and access
- reliability_summary: fault tolerance and disaster recovery approach
- observability_summary: how the system is monitored and debugged
- cost_summary: cost posture, referencing the estimate given
- bottlenecks: list of realistic potential bottlenecks
- trade_offs: list of trade-offs made in this design
- critic_findings_summary: what the critic found and how it was resolved
- final_recommendations: concrete next steps for a team implementing this

Be concise: 2-4 sentences per prose field, short bullet phrases for lists. This report
needs to be complete, not exhaustive.
"""


def run(state: ArchonState) -> dict:
    """Synthesize all prior agent output into a FinalReport."""
    requirements: Requirements = state["requirements"]
    architecture: Architecture = state["architecture"]
    compute: AnalysisResult = state["compute_analysis"]
    database: AnalysisResult = state["database_analysis"]
    networking: AnalysisResult = state["networking_analysis"]
    security: AnalysisResult = state["security_analysis"]
    reliability: AnalysisResult = state["reliability_analysis"]
    cost: CostAnalysis = state["cost_analysis"]
    review: CriticReview = state["critic_review"]
    revision_count = state.get("revision_count", 0)

    revision_note = ""
    if not review.approved and revision_count >= MAX_REVISIONS:
        revision_note = (
            f"Note: the maximum of {MAX_REVISIONS} revision cycles was reached before the "
            "critic fully approved this design. Treat the critic's remaining required_changes "
            "as open follow-up items and say so plainly in critic_findings_summary and "
            "final_recommendations."
        )

    llm = llm_module.get_llm(temperature=0.2)
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
        critic_review=compact_critic_review(review),
        revision_note=revision_note,
    )

    try:
        report = llm_module.invoke_structured(llm, FinalReport, prompt)
        action = "Synthesized all agent outputs into the final architecture recommendation report."
    except llm_module.LLMInvocationError as exc:
        # This is the terminal node -- there's nowhere left to route to on
        # failure, so fall back to a plain report assembled directly from
        # the structured data already gathered, instead of losing the whole
        # run's work over one failed synthesis call.
        report = _fallback_report(requirements, architecture, cost, review, revision_note)
        action = f"LLM synthesis failed ({exc}); assembled a fallback report directly from agent outputs."

    entry = make_trace_entry(
        node="Final Report",
        action=action,
        output_summary=report.executive_summary[:150],
        iteration=revision_count,
    )
    return {"final_report": report, "execution_trace": [entry]}


def _fallback_report(
    requirements: Requirements,
    architecture: Architecture,
    cost: CostAnalysis,
    review: CriticReview,
    revision_note: str,
) -> FinalReport:
    """Assemble a FinalReport with no LLM call, from data already on hand.

    Used only if the LLM synthesis call itself fails -- less polished than a
    real synthesis, but guarantees the run still produces a usable report
    instead of nothing.
    """
    service_names = ", ".join(s.name for s in architecture.services) or "no services selected"
    return FinalReport(
        executive_summary=(
            f"Architecture for {requirements.application_type}, v{architecture.version}. "
            f"{architecture.summary}"
        ),
        requirements_summary=(
            f"{requirements.application_type} for {requirements.expected_users}, "
            f"{requirements.concurrent_users} concurrent. {requirements.availability_requirements}"
        ),
        architecture_overview=architecture.summary,
        aws_services_summary=f"Services: {service_names}.",
        data_flow_summary="; ".join(
            f"{step.source} -> {step.destination}" for step in sorted(architecture.data_flow, key=lambda s: s.step)
        )
        or "No data flow was specified.",
        scalability_strategy=requirements.scalability_requirements,
        high_availability_strategy=requirements.availability_requirements,
        security_summary=requirements.security_requirements,
        reliability_summary="See the reliability analysis in the execution trace for details.",
        observability_summary="See the execution trace for observability recommendations.",
        cost_summary=cost.estimated_monthly_range,
        bottlenecks=["Report synthesis failed -- review the execution trace for full analysis detail."],
        trade_offs=["Report synthesis failed -- see individual agent analyses in the execution trace."],
        critic_findings_summary=(
            f"Critic score: {review.score}/100, approved={review.approved}. {revision_note}"
        ).strip(),
        final_recommendations=list(review.required_changes) or ["Re-run ArchonAI to get a fully synthesized report."],
    )

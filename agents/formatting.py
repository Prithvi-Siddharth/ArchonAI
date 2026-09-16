"""Compact prompt formatting for the high-fan-in nodes.

The Architecture Critic, Revision, and Final Report agents each aggregate
the full architecture plus every specialist analysis into one prompt. Raw
`model_dump_json()` repeats field names and JSON punctuation for every
object, and Groq's OSS models tend to write long, discursive `reasoning`
text -- together these can push a single request past a small (e.g.
free-tier) tokens-per-minute ceiling even though the underlying content is
modest. These helpers produce compact, bounded-length plain-text summaries
instead, so prompt size stays predictable regardless of how verbose an
upstream agent's output happens to be.
"""

from __future__ import annotations

from models.schemas import AnalysisResult, Architecture, CostAnalysis, CriticReview


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    return text if len(text) <= max_chars else text[: max_chars - 3].rstrip() + "..."


def compact_analysis(analysis: AnalysisResult, max_reasoning_chars: int = 300) -> str:
    """Render an AnalysisResult as a short, bounded-length text block."""
    recommendations = "; ".join(analysis.recommendations[:4]) or "none"
    risks = "; ".join(analysis.risks[:3]) if analysis.risks else "none noted"
    reasoning = _truncate(analysis.reasoning, max_reasoning_chars)
    return f"{analysis.domain} -- Recommendations: {recommendations}. Risks: {risks}. Reasoning: {reasoning}"


def compact_architecture(architecture: Architecture, max_field_chars: int = 150) -> str:
    """Render an Architecture as a short, bounded-length text block."""
    lines = [
        f"Summary (v{architecture.version}): {_truncate(architecture.summary, 300)}",
        "Services:",
    ]
    for service in architecture.services:
        lines.append(
            f"- {service.name} ({service.category}): {_truncate(service.purpose, max_field_chars)} "
            f"| Why: {_truncate(service.justification, max_field_chars)}"
        )
    if architecture.data_flow:
        lines.append("Data flow:")
        for step in sorted(architecture.data_flow, key=lambda s: s.step):
            lines.append(
                f"{step.step}. {step.source} -> {step.destination}: {_truncate(step.description, max_field_chars)}"
            )
    if architecture.change_log:
        lines.append("Change log: " + "; ".join(architecture.change_log[:5]))
    return "\n".join(lines)


def compact_cost_analysis(cost: CostAnalysis) -> str:
    """Render a CostAnalysis as a short, bounded-length text block."""
    drivers = ", ".join(cost.major_cost_drivers) or "none identified"
    optimizations = "; ".join(cost.optimizations[:3]) or "none"
    trade_offs = "; ".join(cost.trade_offs[:3]) or "none"
    return (
        f"Estimated range: {cost.estimated_monthly_range}. Major drivers: {drivers}. "
        f"Optimizations: {optimizations}. Trade-offs: {trade_offs}"
    )


def compact_critic_review(review: CriticReview) -> str:
    """Render a CriticReview as a short, bounded-length text block."""
    verdict = "APPROVED" if review.approved else "REJECTED"
    issues = "; ".join(f"[{i.severity.value}] {i.issue}" for i in review.issues[:5]) or "none"
    required_changes = "; ".join(review.required_changes[:5]) or "none"
    strengths = "; ".join(review.strengths[:3]) or "none noted"
    return (
        f"{verdict} (score {review.score}/100). Issues: {issues}. "
        f"Required changes: {required_changes}. Strengths: {strengths}"
    )

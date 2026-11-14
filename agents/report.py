"""Final Report agent.

Terminal node in the graph, reached once the architecture is approved (or the
maximum revision count is hit). Synthesizes every prior agent's output into a
single structured, human-readable final report.
"""

from __future__ import annotations

import logging
import re

from graph.observability import log_event
from graph.state import MAX_REVISIONS, ArchonState, make_trace_entry
from agents import llm as llm_module
from agents.formatting import (
    _truncate,
    compact_analysis,
    compact_architecture,
    compact_cost_analysis,
    compact_critic_review,
)
from models.schemas import (
    AnalysisResult,
    Architecture,
    CostAnalysis,
    CriticReview,
    FinalReport,
    ReportSynthesis,
    Requirements,
)
from tools.architecture_facts import (
    FEATURES_BY_NAME,
    NOT_IMPLEMENTED_PREFIX,
    PROPOSED,
    SERVICE,
    absent_features,
    features_in,
    pending_requests,
    present_features,
    verify_changes,
)

logger = logging.getLogger(__name__)

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

Verified facts about the final architecture (a deterministic check of its actual design):
- Services in the final architecture: {services}
- Capabilities verified in the design: {capabilities}
- Mentioned by the analyses or the critic but NOT in the final architecture: {absent}
- Verified changes made during revision: {implemented}
- Open recommendations (requested or proposed, not implemented): {open_recommendations}

Describe only what the final architecture contains. The specialist analyses and the critic's
required changes are suggestions, not features -- never describe them as part of the design,
and do not claim a capability listed as NOT in the final architecture. Anything not in the
final architecture may appear only in final_recommendations.

Write the final report with these fields (the requirements, services, data flow, cost and
critic summaries are added separately from the data above -- do not write them):
- executive_summary: for a non-technical stakeholder
- architecture_overview: how the pieces fit together
- scalability_strategy: how this scales under load
- high_availability_strategy: how this stays up during failures
- security_summary: how this protects data and access
- reliability_summary: fault tolerance and disaster recovery approach
- observability_summary: how the system is monitored and debugged
- bottlenecks: realistic potential bottlenecks
- trade_offs: trade-offs made in this design
- final_recommendations: concrete next steps for a team implementing this

Hard size limits (the whole report must fit in a small output budget):
- Every prose field: 1-2 sentences, at most 35 words in total.
- bottlenecks, trade_offs, final_recommendations: at most 3 items each, at most 12 words per item.
- Spend the words on specifics: name the actual AWS services, numbers (users, latency,
  availability target, cost range) and mechanisms (e.g. multi-AZ, auto scaling, read
  replicas, encryption) from the material. Leave out filler and restated headings.
"""

# The hard limits above keep the report inside its max_tokens budget. Without
# them, 12 prose fields at 2-4 sentences each need more tokens than the cap
# allows, so the answer is cut off mid-tool-call and rejected as
# tool_use_failed -- which then drops the run to _fallback_report.


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
            "as open follow-up items and say so plainly in final_recommendations."
        )

    history: list[CriticReview] = list(state.get("critic_history") or []) or [review]
    open_recommendations = _open_recommendations(architecture, review, history)
    present = present_features(architecture)
    analyses = [compute, database, networking, security, reliability]
    mentioned = (
        [r for a in analyses for r in a.recommendations]
        + list(review.required_changes)
        + [i.issue for i in review.issues]
        + list(architecture.change_log)
    )

    llm = llm_module.get_llm(temperature=0.2)
    prompt = PROMPT_TEMPLATE.format(
        requirements=requirements.model_dump_json(),
        version=architecture.version,
        # The change_log can describe claims, not the design; the verified
        # changes are listed separately below.
        architecture=compact_architecture(architecture, include_change_log=False),
        compute=compact_analysis(compute),
        database=compact_analysis(database),
        networking=compact_analysis(networking),
        security=compact_analysis(security),
        reliability=compact_analysis(reliability),
        cost=compact_cost_analysis(cost),
        critic_review=compact_critic_review(review),
        revision_note=revision_note,
        services=", ".join(s.name for s in architecture.services) or "none",
        capabilities=", ".join(n for n in FEATURES_BY_NAME if n in present and FEATURES_BY_NAME[n].kind == "capability")
        or "none",
        absent=", ".join(absent_features(mentioned, architecture)[:12]) or "none",
        implemented="; ".join(list(state.get("implemented_changes") or [])[-6:]) or "none",
        open_recommendations="; ".join(open_recommendations[:6]) or "none",
    )

    built = _deterministic_fields(
        requirements, architecture, cost, review, revision_count, len(state.get("implemented_changes") or [])
    )
    try:
        synthesis = llm_module.invoke_structured(llm, ReportSynthesis, prompt)
        report = FinalReport(**{name: getattr(synthesis, name) for name in ReportSynthesis.model_fields}, **built)
        action = "Synthesized all agent outputs into the final architecture recommendation report."
    except llm_module.LLMInvocationError as exc:
        # This is the terminal node -- there's nowhere left to route to on
        # failure, so fall back to a plain report assembled directly from
        # the structured data already gathered, instead of losing the whole
        # run's work over one failed synthesis call.
        report = _fallback_report(requirements, architecture, cost, review, revision_note, built)
        action = (
            f"LLM synthesis failed ({llm_module.safe_failure_message(exc)}); "
            "assembled a fallback report directly from agent outputs."
        )

    removed_fields = _enforce_verified_claims(report, architecture, cost, review)
    report.open_recommendations = open_recommendations
    if removed_fields:
        action += (
            f" Removed claims about features not in the final architecture from {len(removed_fields)} field(s)."
        )

    entry = make_trace_entry(
        node="Final Report",
        action=action,
        output_summary=report.executive_summary[:150],
        iteration=revision_count,
    )
    return {"final_report": report, "execution_trace": [entry]}


# ---------------------------------------------------------------------------
# Report fields built from workflow data (no LLM): they restate facts the
# workflow already holds, so generating them only spent output tokens.
# ---------------------------------------------------------------------------

_SERVICE_PURPOSE_CHARS = 70


def _requirements_summary(requirements: Requirements) -> str:
    """What the user asked for: the explicitly stated requirements, else the key figures."""
    stated = [r.strip().rstrip(".") for r in requirements.explicit_requirements if r.strip()]
    if stated:
        return f"{requirements.application_type}: " + "; ".join(stated) + "."
    return (
        f"{requirements.application_type} for {requirements.expected_users}, "
        f"{requirements.concurrent_users} concurrent. {requirements.availability_requirements}"
    )


def _aws_services_summary(architecture: Architecture) -> str:
    """Every service in the final design, with its role (from the design itself)."""
    if not architecture.services:
        return "Services: no services selected."
    parts = [
        f"{s.name} ({_truncate(s.purpose.rstrip('.'), _SERVICE_PURPOSE_CHARS)})" if s.purpose.strip() else s.name
        for s in architecture.services
    ]
    return "Services: " + "; ".join(parts) + "."


def _data_flow_summary(architecture: Architecture) -> str:
    steps = sorted(architecture.data_flow, key=lambda s: s.step)
    return "; ".join(f"{step.source} -> {step.destination}" for step in steps) or "No data flow was specified."


def _cost_summary(cost: CostAnalysis) -> str:
    """The estimator's range and drivers, plus the Cost Agent's first optimization."""
    text = cost.estimated_monthly_range
    if cost.major_cost_drivers:
        text += f"; major cost drivers: {', '.join(cost.major_cost_drivers)}"
    text += "."
    if cost.optimizations:
        # "Recommended" marks it as advice, not a claim about the design.
        text += f" Recommended first optimization: {cost.optimizations[0].rstrip('.')}."
    return text


def _critic_findings_summary(review: CriticReview, revision_count: int, implemented_count: int) -> str:
    """Score, verdict, revision status and issue counts -- names no features, so it can't overclaim."""
    verdict = "approved" if review.approved else "not approved"
    text = f"Critic score {review.score}/100 ({verdict})"
    if revision_count:
        text += f" after {revision_count} revision cycle{'s' if revision_count != 1 else ''}"
        if not review.approved and revision_count >= MAX_REVISIONS:
            text += f"; the maximum of {MAX_REVISIONS} was reached"
    text += "."
    if implemented_count:
        text += f" {implemented_count} verified change{'s were' if implemented_count != 1 else ' was'} made during revision."
    if review.issues:
        counts = {}
        for issue in review.issues:
            counts[issue.severity.value] = counts.get(issue.severity.value, 0) + 1
        order = ("critical", "high", "medium", "low")
        by_severity = ", ".join(f"{counts[s]} {s}" for s in order if s in counts)
        categories = ", ".join(dict.fromkeys(i.category.strip().lower() for i in review.issues if i.category.strip()))
        text += f" It raised {len(review.issues)} issue{'s' if len(review.issues) != 1 else ''} ({by_severity})"
        text += f" in {categories}." if categories else "."
    if review.required_changes and not review.approved:
        text += " Its required changes remain open; see open_recommendations."
    return text


def _deterministic_fields(
    requirements: Requirements,
    architecture: Architecture,
    cost: CostAnalysis,
    review: CriticReview,
    revision_count: int,
    implemented_count: int,
) -> dict[str, str]:
    """The FinalReport fields built from workflow data (the LLM writes the rest)."""
    return {
        "requirements_summary": _requirements_summary(requirements),
        "aws_services_summary": _aws_services_summary(architecture),
        "data_flow_summary": _data_flow_summary(architecture),
        "cost_summary": _cost_summary(cost),
        "critic_findings_summary": _critic_findings_summary(review, revision_count, implemented_count),
    }


def _fallback_report(
    requirements: Requirements,
    architecture: Architecture,
    cost: CostAnalysis,
    review: CriticReview,
    revision_note: str,
    built: dict[str, str],
) -> FinalReport:
    """Assemble a FinalReport with no LLM call, from data already on hand.

    Used only if the LLM synthesis call itself fails -- less polished than a
    real synthesis, but guarantees the run still produces a usable report
    instead of nothing. The data-derived fields (`built`) are the same as in
    a synthesized report.
    """
    return FinalReport(
        executive_summary=(
            f"Architecture for {requirements.application_type}, v{architecture.version}. "
            f"{architecture.summary}"
        ),
        architecture_overview=architecture.summary,
        scalability_strategy=requirements.scalability_requirements,
        high_availability_strategy=requirements.availability_requirements,
        security_summary=requirements.security_requirements,
        reliability_summary="See the reliability analysis in the execution trace for details.",
        observability_summary="See the execution trace for observability recommendations.",
        bottlenecks=["Report synthesis failed -- review the execution trace for full analysis detail."],
        trade_offs=["Report synthesis failed -- see individual agent analyses in the execution trace."],
        final_recommendations=list(review.required_changes) or ["Re-run ArchonAI to get a fully synthesized report."],
        **built,
    )


# ---------------------------------------------------------------------------
# Keeping the report to what the final architecture actually contains
# ---------------------------------------------------------------------------

_MAX_OPEN_RECOMMENDATIONS = 8

# A sentence or clause with one of these words is about what's missing or
# recommended, not a claim that the design has it.
_HEDGE = re.compile(
    r"\b(no|not|without|lacks?|lacking|missing|absent|recommend\w*|should|could|would|consider\w*|"
    r"future|pending|open|follow[- ]?ups?|remains?|remaining|planned|proposed|next steps?|add|introduce)\b",
    re.IGNORECASE,
)
_CHECKED_PROSE = (
    "executive_summary",
    "architecture_overview",
    "aws_services_summary",
    "data_flow_summary",
    "scalability_strategy",
    "high_availability_strategy",
    "security_summary",
    "reliability_summary",
    "observability_summary",
    "cost_summary",
    "critic_findings_summary",
)
_CHECKED_LISTS = ("bottlenecks", "trade_offs")
_FIELD_GROUPS = {
    "scalability_strategy": ["auto scaling", "Elastic Load Balancing", "Amazon ElastiCache", "read replicas",
                             "Amazon SQS", "Amazon CloudFront", "Amazon DynamoDB"],
    "high_availability_strategy": ["multi-AZ deployment", "Elastic Load Balancing", "read replicas",
                                   "cross-region disaster recovery", "warm standby / pilot light", "database backups"],
    "security_summary": ["AWS WAF", "AWS Shield", "encryption", "AWS KMS", "AWS Secrets Manager",
                         "SSM Parameter Store", "Amazon Cognito", "MFA", "private subnets", "VPC endpoints",
                         "AWS CloudTrail", "Amazon GuardDuty"],
    "reliability_summary": ["database backups", "point-in-time recovery", "multi-AZ deployment", "read replicas",
                            "cross-region disaster recovery", "RTO/RPO targets", "retries with backoff",
                            "circuit breakers"],
}


def _open_recommendations(architecture: Architecture, review: CriticReview, history: list[CriticReview]) -> list[str]:
    """Everything requested or proposed that the final architecture does not contain.

    The final review's required changes are open by definition (the critic
    just reviewed this exact architecture) -- also when it approved the
    design, since an approval can still list non-blocking changes (e.g. for
    a MEDIUM finding); earlier rounds' requests are open if they name a
    service/capability the design still lacks; and change_log entries that
    only proposed something stay proposals.
    """
    items: list[str] = list(review.required_changes)
    earlier = [c for past in history if past is not review for c in past.required_changes]
    items += pending_requests(earlier, architecture)
    items += [
        c.entry.removeprefix(NOT_IMPLEMENTED_PREFIX)
        for c in verify_changes(architecture.change_log, architecture)
        if c.status == PROPOSED
    ]
    unique: list[str] = []
    for item in items:
        if item not in unique:
            unique.append(item)
    return unique[:_MAX_OPEN_RECOMMENDATIONS]


# "X over Y", "X instead of Y", ... : Y is the alternative that was NOT chosen.
# The alternative runs to the next colon, semicolon, comma or sentence end.
_COMPARISON = re.compile(
    r"\b(?:over|instead\s+of|rather\s+than|vs\.?|versus|compared\s+(?:to|with))\s+(?P<alternative>[^:;,.]*)",
    re.IGNORECASE,
)


def _unsupported(fragment: str, present: set[str]) -> list[str]:
    """Catalog features a fragment asserts that the design doesn't contain.

    A *service* named only as the alternative in a comparison ("Fargate over
    EC2") is not a claim that the design has it, so it is exempt. Everything
    else is still checked: the subject ("Fargate"), any service also named
    outside the comparison, and every capability -- even inside the
    alternative ("spread over a secondary region" still claims cross-region).
    """
    if _HEDGE.search(fragment):
        return []
    alternatives = " ".join(m.group("alternative") for m in _COMPARISON.finditer(fragment))
    claimed_outside = {f.name for f in features_in(_COMPARISON.sub(" ", fragment))}
    exempt = {
        f.name for f in features_in(alternatives) if f.kind == SERVICE and f.name not in claimed_outside
    }
    return [f.name for f in features_in(fragment) if f.name not in present and f.name not in exempt]


def _fragments(text: str) -> list[str]:
    # Not after "vs.": "Fargate vs. EC2" is one comparison, not two sentences.
    return [part for part in re.split(r"(?<=[.;!?])(?<!\bvs\.)\s+", text.strip()) if part]


def _replacement_text(
    name: str, architecture: Architecture, cost: CostAnalysis, review: CriticReview, present: set[str]
) -> str:
    """What a field says when every sentence in it claimed something the design lacks."""
    if name in ("executive_summary", "architecture_overview"):
        return architecture.summary
    if name == "aws_services_summary":
        return "Services: " + (", ".join(s.name for s in architecture.services) or "none") + "."
    if name == "data_flow_summary":
        steps = sorted(architecture.data_flow, key=lambda s: s.step)
        return "; ".join(f"{s.source} -> {s.destination}" for s in steps) or "No data flow was specified."
    if name == "cost_summary":
        return cost.estimated_monthly_range
    if name == "critic_findings_summary":
        verdict = "approved" if review.approved else "not approved"
        return f"Critic score {review.score}/100 ({verdict}); see open_recommendations for unimplemented requests."
    group = [n for n in _FIELD_GROUPS.get(name, []) if n in present]
    if group:
        return "In the final architecture: " + ", ".join(group) + "."
    return "Not covered by the final architecture; see open_recommendations."


def _enforce_verified_claims(
    report: FinalReport, architecture: Architecture, cost: CostAnalysis, review: CriticReview
) -> list[str]:
    """Remove sentences/items that assert a feature the final architecture lacks.

    Deterministic backstop for the prompt rules: e.g. "DynamoDB added for
    catalog reads" is dropped when DynamoDB is not in the design, while
    "Add DynamoDB for catalog reads" (a recommendation) is kept. A field
    left empty gets a plain description built from the architecture itself.
    Edits the report in place; returns the names of the fields changed.
    """
    present = present_features(architecture)
    changed: list[str] = []
    absent: list[str] = []

    for name in _CHECKED_PROSE:
        kept: list[str] = []
        dropped = False
        for fragment in _fragments(getattr(report, name)):
            unsupported = _unsupported(fragment, present)
            if unsupported:
                dropped = True
                absent.extend(u for u in unsupported if u not in absent)
            else:
                kept.append(fragment)
        if dropped:
            text = re.sub(r"[;,]\s*$", ".", " ".join(kept).strip())
            setattr(report, name, text or _replacement_text(name, architecture, cost, review, present))
            changed.append(name)

    for name in _CHECKED_LISTS:
        items = getattr(report, name)
        kept_items = []
        for item in items:
            unsupported = _unsupported(item, present)
            absent.extend(u for u in unsupported if u not in absent)
            if not unsupported:
                kept_items.append(item)
        if len(kept_items) != len(items):
            setattr(report, name, kept_items)
            changed.append(name)

    # Only field names and catalog feature names -- never report text.
    log_event(
        logger,
        "report_claims_checked",
        fields_changed=len(changed),
        fields=",".join(changed) or None,
        absent_features=",".join(absent) or None,
    )
    return changed

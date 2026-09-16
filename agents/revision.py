"""Architecture Revision agent.

Runs when the Architecture Critic rejects a design. Takes the original
requirements, the current architecture, and the critic's findings, and
produces an improved architecture that explicitly addresses each required
change. The graph routes the result back to the critic for re-review, bounded
by MAX_REVISIONS to guarantee termination.
"""

from __future__ import annotations

from agents import llm as llm_module
from agents.formatting import compact_architecture
from graph.state import ArchonState, make_trace_entry
from models.schemas import Architecture, CriticReview, Requirements

# On a Groq free-tier key, a revision call can occasionally still fail (e.g.
# a transient rate-limit rejection that outlasts our retries). Losing the
# whole run -- including every prior successful node -- over one failed
# revision would be a bad trade: fall back to the unrevised architecture and
# let the critic evaluate it again instead, so the run still terminates with
# a report rather than crashing outright.

PROMPT_TEMPLATE = """You are an AWS solutions architect revising a rejected architecture.

Original Requirements:
{requirements}

Current Architecture (version {version}):
{architecture}

Critic's Review (why it was rejected):
- Score: {score}/100
- Required changes: {required_changes}
- Issues: {issues}

Produce a revised architecture that concretely addresses every required change above.
Keep everything that already worked well -- do not change parts of the design that
were not flagged as problems. In change_log, list exactly what changed and why, tied
directly to the critic's required changes. Increment nothing yourself; the version
number will be set by the caller.

Be concise: keep at most 8-10 services total (fewer for a small/simple system), keep
each summary/purpose/justification/description/change_log entry to one short sentence
(under 20 words), and limit change_log to the changes that were actually needed. This
is a working design document, not a narrative report.
"""


def _format_issues(review: CriticReview) -> str:
    if not review.issues:
        return "None listed."
    return "; ".join(f"[{issue.severity.value}] {issue.issue}" for issue in review.issues)


def run(state: ArchonState) -> dict:
    """Produce a revised Architecture addressing the critic's required changes."""
    requirements: Requirements = state["requirements"]
    architecture: Architecture = state["architecture"]
    review: CriticReview = state["critic_review"]

    llm = llm_module.get_llm(temperature=0.3, max_tokens=llm_module.ARCHITECTURE_MAX_TOKENS)
    prompt = PROMPT_TEMPLATE.format(
        requirements=requirements.model_dump_json(),
        version=architecture.version,
        architecture=compact_architecture(architecture),
        score=review.score,
        required_changes="; ".join(review.required_changes) or "None explicitly listed.",
        issues=_format_issues(review),
    )
    new_revision_count = state.get("revision_count", 0) + 1

    try:
        revised = llm_module.invoke_structured(llm, Architecture, prompt)
        revised.version = architecture.version + 1
        if not revised.change_log:
            revised.change_log = list(review.required_changes)
        action = f"Revised architecture to v{revised.version}, addressing {len(review.required_changes)} required changes."
        output_summary = "; ".join(revised.change_log[:3])
    except llm_module.LLMInvocationError as exc:
        revised = architecture
        action = f"Revision call failed ({exc}); kept the previous architecture and re-submitted it to the critic."
        output_summary = "Revision failed -- architecture unchanged this round."

    entry = make_trace_entry(
        node="Architecture Revision",
        action=action,
        output_summary=output_summary,
        iteration=new_revision_count,
    )
    return {
        "architecture": revised,
        "revision_count": new_revision_count,
        "execution_trace": [entry],
    }

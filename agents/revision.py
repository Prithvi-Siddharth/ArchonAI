"""Architecture Revision agent.

Runs when the Architecture Critic rejects a design. Takes the original
requirements, the current architecture, and the critic's findings, and
produces an improved architecture that explicitly addresses each required
change. The graph routes the result back to the critic for re-review, bounded
by MAX_REVISIONS to guarantee termination.
"""

from __future__ import annotations

import logging

from agents import llm as llm_module
from agents.formatting import _truncate, compact_architecture
from graph.observability import log_event
from graph.state import ArchonState, make_trace_entry
from models.schemas import Architecture, CriticReview, Requirements, ValidationResult
from tools.revision_guard import Regression, blocking, check_revision

logger = logging.getLogger(__name__)

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

Critic review history, oldest first (earlier rounds' required changes still apply):
{review_history}

Previously implemented changes (already in the current architecture -- preserve them):
{implemented_changes}

Outstanding issues to fix now (latest review of version {version}):
- Score: {score}/100
- Required changes: {required_changes}
- Issues: {issues}
- Deterministic validator findings: {validator_findings}

Produce a revised architecture that concretely addresses every outstanding required change
above. Keep everything that already worked well -- do not change parts of the design that
were not flagged as problems. In change_log, list exactly what changed and why, tied
directly to the critic's required changes. Increment nothing yourself; the version
number will be set by the caller.

Preserve earlier fixes -- no regressions:
- Keep every previously implemented change and every existing security, availability,
  disaster-recovery, backup and networking control (e.g. Secrets Manager, KMS, WAF,
  multi-AZ, cross-region replicas, backups, per-AZ NAT gateways, private subnets).
- Remove or replace an existing service or control only for an explicit technical reason,
  and then say so in change_log: "Removed <X> because <reason>" or
  "Replaced <X> with <Y> because <reason>".
- If the latest required changes seem to conflict with an earlier fix, keep the earlier
  fix unless the conflict is real, and explain the choice in change_log.

Hard size limits (the whole response must fit in a small output budget):
- At most 7 services total. Combine closely related services into one entry
  (e.g. "Amazon CloudFront + AWS WAF").
- At most 6 data_flow steps, covering only the main request path.
- Summary: one sentence, at most 30 words.
- Each purpose/justification/description/change_log entry: one sentence, at most 12 words.
- change_log: only the changes that were actually needed, at most 5 entries.

Keep key properties explicit in the text where they apply, using these exact terms:
multi-AZ, auto scaling, load balancer, backups, encryption, private subnet.

This is a working design document, not a narrative report.
"""

# The hard limits above exist for the same reason as in agents/architecture.py:
# a revised Architecture shares the same ARCHITECTURE_MAX_TOKENS budget, and
# output that overruns it is cut off mid-JSON and rejected as tool_use_failed.

# Appended (once) when the first revised architecture regresses: the model is
# told exactly what it removed and asked to restore or justify each item.
CORRECTION_TEMPLATE = """

IMPORTANT: your previous attempt was not accepted because it removed things the current
architecture (version {version}) already had, without an explicit justification:
{regressions}
Produce the revision again. Restore each of these, or -- only if removing it is technically
necessary -- add a change_log entry "Removed <X> because <reason>" (or "Replaced <X> with
<Y> because <reason>"). A new deterministic validator failure (e.g. a missing backup
strategy) must be fixed, not justified.
"""

# Bounds on the history added to the prompt (MAX_REVISIONS keeps it small anyway).
_MAX_HISTORY_REVIEWS = 4
_MAX_IMPLEMENTED_CHANGES = 10
_MAX_ITEM_CHARS = 160


def _format_issues(review: CriticReview) -> str:
    if not review.issues:
        return "None listed."
    return "; ".join(f"[{issue.severity.value}] {issue.issue}" for issue in review.issues)


def _format_review_history(history: list[CriticReview]) -> str:
    if not history:
        return "None."
    lines = []
    for round_number, review in list(enumerate(history))[-_MAX_HISTORY_REVIEWS:]:
        verdict = "APPROVED" if review.approved else "REJECTED"
        changes = "; ".join(_truncate(c, _MAX_ITEM_CHARS) for c in review.required_changes[:4]) or "none"
        lines.append(f"- Round {round_number}: {verdict}, score {review.score}/100. Required changes: {changes}")
    return "\n".join(lines)


def _format_implemented_changes(changes: list[str]) -> str:
    if not changes:
        return "None yet (this is the first revision)."
    return "\n".join(f"- {_truncate(c, _MAX_ITEM_CHARS)}" for c in changes[-_MAX_IMPLEMENTED_CHANGES:])


def _format_validator_findings(validation: ValidationResult | None) -> str:
    if validation is None or not validation.issues:
        return "none."
    return "; ".join(f"[{i.severity.value.upper()}] ({i.rule}) {i.message}" for i in validation.issues)


def _format_regressions(regressions: list[Regression]) -> str:
    return "\n".join(f"- {r.describe()}" for r in regressions)


def _log_check(regressions: list[Regression], corrected: bool, accepted: bool) -> None:
    unjustified = blocking(regressions)
    log_event(
        logger,
        "revision_checked",
        regressions=len(regressions),
        unjustified=len(unjustified),
        justified=len(regressions) - len(unjustified),
        categories=",".join(sorted({r.category for r in unjustified})) or None,
        corrected=corrected,
        accepted=accepted,
    )


def run(state: ArchonState) -> dict:
    """Produce a revised Architecture addressing the critic's required changes.

    The prompt carries the whole critic history and every change earlier
    revisions made, so a later round can't silently undo an earlier fix.
    The result is then checked against the current architecture
    (tools/revision_guard.py): if it removes a service or a security,
    availability, DR, backup or networking capability without saying why in
    its change_log -- or fails a validator rule the current version passes --
    the model gets one corrective attempt. If that still regresses, the
    revision is not accepted and the current architecture is kept.
    """
    requirements: Requirements = state["requirements"]
    architecture: Architecture = state["architecture"]
    review: CriticReview = state["critic_review"]
    history: list[CriticReview] = list(state.get("critic_history") or []) or [review]
    implemented: list[str] = list(state.get("implemented_changes") or [])
    prior_required_changes = [change for past in history for change in past.required_changes]

    llm = llm_module.get_llm(temperature=0.3, max_tokens=llm_module.ARCHITECTURE_MAX_TOKENS)
    prompt = PROMPT_TEMPLATE.format(
        requirements=requirements.model_dump_json(),
        version=architecture.version,
        architecture=compact_architecture(architecture),
        review_history=_format_review_history(history),
        implemented_changes=_format_implemented_changes(implemented),
        score=review.score,
        required_changes="; ".join(review.required_changes) or "None explicitly listed.",
        issues=_format_issues(review),
        validator_findings=_format_validator_findings(state.get("validation_results")),
    )
    new_revision_count = state.get("revision_count", 0) + 1

    def attempt(prompt_text: str) -> tuple[Architecture, list[Regression]]:
        candidate = llm_module.invoke_structured(llm, Architecture, prompt_text)
        return candidate, check_revision(architecture, candidate, requirements, prior_required_changes)

    newly_implemented: list[str] = []
    try:
        revised, regressions = attempt(prompt)
        corrected = False
        if blocking(regressions):
            corrected = True
            revised, regressions = attempt(
                prompt
                + CORRECTION_TEMPLATE.format(
                    version=architecture.version, regressions=_format_regressions(blocking(regressions))
                )
            )
        unjustified = blocking(regressions)
        _log_check(regressions, corrected, accepted=not unjustified)

        if unjustified:
            # Accepting it would undo earlier work; keep the current version and
            # let the critic review it again (same fallback as a failed call).
            listed = "; ".join(r.describe() for r in unjustified[:3])
            more = f"; +{len(unjustified) - 3} more" if len(unjustified) > 3 else ""
            action = (
                f"Rejected the revised architecture as a regression ({listed}{more}); "
                f"kept v{architecture.version} and re-submitted it to the critic."
            )
            revised = architecture
            output_summary = "Revision regressed earlier fixes -- architecture unchanged this round."
        else:
            revised.version = architecture.version + 1
            if not revised.change_log:
                revised.change_log = list(review.required_changes)
            newly_implemented = [f"v{revised.version}: {entry}" for entry in revised.change_log]
            justified = [r for r in regressions if r.justified]
            action = f"Revised architecture to v{revised.version}, addressing {len(review.required_changes)} required changes."
            if corrected:
                action += " A first attempt removed earlier fixes and was corrected."
            if justified:
                action += " Justified removals: " + "; ".join(r.item for r in justified[:4]) + "."
            output_summary = "; ".join(revised.change_log[:3])
    except llm_module.LLMInvocationError as exc:
        revised = architecture
        action = (
            f"Revision call failed ({llm_module.safe_failure_message(exc)}); "
            "kept the previous architecture and re-submitted it to the critic."
        )
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
        "implemented_changes": newly_implemented,
        "execution_trace": [entry],
    }

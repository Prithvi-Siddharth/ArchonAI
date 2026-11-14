"""Architecture Revision agent.

Runs when the Architecture Critic rejects a design. Takes the original
requirements, the current architecture, and the critic's findings, and
produces an improved architecture that explicitly addresses each required
change. The graph routes the result back to the critic for re-review, bounded
by MAX_REVISIONS to guarantee termination.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from agents import llm as llm_module
from agents.formatting import _truncate, compact_architecture
from graph.observability import log_event
from graph.state import ArchonState, make_trace_entry
from models.schemas import (
    Architecture,
    CriticReview,
    Requirements,
    ValidationIssue,
    ValidationResult,
)
from tools.architecture_facts import (
    IMPLEMENTED,
    NOT_IMPLEMENTED_PREFIX,
    PROPOSED,
    REMOVED,
    ChangeCheck,
    pending_requests,
    verify_changes,
)
from tools.revision_guard import (
    Regression,
    blocking,
    check_revision,
    unimplemented_claims,
    unresolved_findings,
)

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

Previously implemented changes (verified present in the current architecture -- preserve them):
{implemented_changes}

Still pending -- requested or proposed earlier but NOT in the current architecture. Do not
assume these exist; implement them now if they are still required:
{pending_changes}

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
- At most 7 services. Combine closely related services into one entry
  (e.g. "Amazon CloudFront + AWS WAF", "Amazon ElastiCache (Redis) + Amazon DynamoDB").
- If a required change needs a new service that cannot share an entry, an 8th service is
  allowed: add it, say why in change_log ("Added <X> as an 8th service because <reason>"),
  and keep data_flow to at most 5 steps. Never remove an essential service just to stay
  under the count.
- At most 6 data_flow steps, covering only the main request path.
- Summary: one sentence, at most 30 words.
- Each purpose/justification/description/change_log entry: one sentence, at most 12 words.
- change_log: only the changes that were actually needed, at most 5 entries. Every service
  or capability a change_log entry names must appear in the services or data_flow above --
  a change that is only described in change_log does not count as implemented.

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

# Appended (once) when a revision did not actually fix the design -- with or
# without regressions: a blocking validator finding is still there, or a
# requested change is claimed only in change_log. The
# rejected attempt is included so the model fixes that attempt instead of
# starting over.
UNRESOLVED_CORRECTION_TEMPLATE = """

IMPORTANT: your previous attempt was not accepted because it did not change the actual
architecture where it had to:
{problems}
Your previous attempt (not accepted):
{attempt}
Produce the revision again, starting from that attempt and keeping its other improvements.
Make every fix in the services (purpose or justification) or data_flow themselves, using the
exact terms given above. Do not claim implementation only in change_log -- a change that is
not in the services or data_flow is not implemented and will be rejected again.
"""

# How to resolve each validator rule, in the exact terms the validator looks for.
_FINDING_FIXES = {
    "database_without_backups": (
        "Add automated backups and point-in-time recovery explicitly to the {database} service's "
        "purpose or justification (use the words 'automated backups' and 'point-in-time recovery')."
    ),
    "high_availability_single_az": (
        "State 'multi-AZ' explicitly in the purpose or justification of the compute and {database} services."
    ),
    "high_traffic_without_scaling": "State 'auto scaling' explicitly in the compute service's purpose or justification.",
    "compute_without_load_balancer": "Add an Application Load Balancer as a service in front of the compute tier.",
    "sensitive_workload_missing_controls": (
        "Describe concrete controls in the services: 'encryption' at rest with KMS, IAM least privilege, WAF."
    ),
    "public_database_exposure": (
        "Place the {database} service in a 'private subnet' and state it is 'not publicly accessible'."
    ),
}

# Bounds on the history added to the prompt (MAX_REVISIONS keeps it small anyway).
_MAX_HISTORY_REVIEWS = 4
_MAX_IMPLEMENTED_CHANGES = 10
_MAX_ITEM_CHARS = 160
_MAX_PENDING = 6


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


def _format_pending(items: list[str]) -> str:
    if not items:
        return "None."
    return "\n".join(f"- {_truncate(i, _MAX_ITEM_CHARS)}" for i in items[:_MAX_PENDING])


def _still_pending(history: list[CriticReview], architecture: Architecture) -> list[str]:
    """Earlier critic requests and claimed-but-absent changes the current design still lacks.

    The latest review's required changes are already listed as outstanding,
    so only earlier rounds are checked here.
    """
    earlier = [change for past in history[:-1] for change in past.required_changes]
    pending = pending_requests(earlier, architecture)
    for check in verify_changes(architecture.change_log, architecture):
        if check.status == PROPOSED:
            item = check.entry.removeprefix(NOT_IMPLEMENTED_PREFIX)
            if item not in pending:
                pending.append(item)
    return pending


def _record_verified_changes(revised: Architecture) -> tuple[list[str], list[ChangeCheck]]:
    """Check every change_log entry against the revised design itself.

    Only verified entries become implemented_changes; an entry naming a
    service or capability the design doesn't contain is marked as proposed
    in the change_log (so neither the critic, the report nor the next
    revision mistakes it for part of the design).
    """
    checks = verify_changes(revised.change_log, revised)
    version = revised.version
    implemented: list[str] = []
    change_log: list[str] = []
    for check in checks:
        entry = check.entry
        if check.status == IMPLEMENTED:
            implemented.append(f"v{version}: {entry}")
        elif check.status == REMOVED:
            implemented.append(f"v{version} (intentional removal): {entry}")
        elif check.status == PROPOSED and not entry.startswith(NOT_IMPLEMENTED_PREFIX):
            entry = NOT_IMPLEMENTED_PREFIX + entry
        change_log.append(entry)
    revised.change_log = change_log
    return implemented, checks


def _format_validator_findings(validation: ValidationResult | None) -> str:
    if validation is None or not validation.issues:
        return "none."
    return "; ".join(f"[{i.severity.value.upper()}] ({i.rule}) {i.message}" for i in validation.issues)


def _format_regressions(regressions: list[Regression]) -> str:
    return "\n".join(f"- {r.describe()}" for r in regressions)


@dataclass
class _Verdict:
    """Why a candidate revision can or cannot be accepted.

    Zero regressions is not enough: the revision must also resolve the
    blocking validator findings and actually contain the requested changes it
    claims. (Approval of the whole architecture is still the critic's call.)
    """

    regressions: list[Regression]
    unresolved: list[ValidationIssue]
    unimplemented: list[ChangeCheck]

    @property
    def regressed(self) -> bool:
        return bool(blocking(self.regressions))

    @property
    def incomplete(self) -> bool:
        return bool(self.unresolved or self.unimplemented)

    @property
    def acceptable(self) -> bool:
        return not self.regressed and not self.incomplete


def _database_name(architecture: Architecture) -> str:
    for service in architecture.services:
        if "database" in service.category.lower():
            return f"'{service.name}'"
    return "database"


def _format_unresolved(verdict: _Verdict, candidate: Architecture) -> str:
    database = _database_name(candidate)
    lines = []
    for issue in verdict.unresolved:
        fix = _FINDING_FIXES.get(issue.rule, "Fix it in the services or data_flow.").format(database=database)
        lines.append(f"- The {issue.rule} validator finding remains unresolved ({issue.message}) {fix}")
    for check in verdict.unimplemented:
        lines.append(
            f"- Claimed in change_log but not in the design: '{_truncate(check.entry, _MAX_ITEM_CHARS)}' "
            f"(missing from services/data_flow: {', '.join(check.missing)}). Add it to the actual architecture."
        )
    return "\n".join(lines)


def _correction(verdict: _Verdict, candidate: Architecture, version: int) -> str:
    """The single corrective addition: regressions to restore, fixes still missing, or both."""
    text = ""
    if verdict.regressed:
        text += CORRECTION_TEMPLATE.format(version=version, regressions=_format_regressions(blocking(verdict.regressions)))
    if verdict.incomplete:
        text += UNRESOLVED_CORRECTION_TEMPLATE.format(
            problems=_format_unresolved(verdict, candidate), attempt=compact_architecture(candidate)
        )
    return text


def _log_check(
    verdict: _Verdict, corrected: bool, accepted: bool, checks: list[ChangeCheck] | None = None
) -> None:
    regressions = verdict.regressions
    unjustified = blocking(regressions)
    counts = {}
    if checks is not None:
        counts = {
            f"changes_{status}": sum(1 for c in checks if c.status == status)
            for status in ("implemented", "proposed", "removed", "unverified")
        }
    log_event(
        logger,
        "revision_checked",
        regressions=len(regressions),
        unjustified=len(unjustified),
        justified=len(regressions) - len(unjustified),
        categories=",".join(sorted({r.category for r in unjustified})) or None,
        unresolved_findings=len(verdict.unresolved),
        findings=",".join(issue.rule for issue in verdict.unresolved) or None,
        unimplemented_claims=len(verdict.unimplemented),
        corrected=corrected,
        accepted=accepted,
        **counts,
    )


def run(state: ArchonState) -> dict:
    """Produce a revised Architecture addressing the critic's required changes.

    The prompt carries the whole critic history and every change earlier
    revisions made, so a later round can't silently undo an earlier fix.
    The result is then checked against the current architecture
    (tools/revision_guard.py): if it removes a service or a security,
    availability, DR, backup or networking capability without saying why in
    its change_log -- or fails a validator rule the current version passes --
    the model gets one corrective attempt. The same single attempt is used
    when the revision leaves a high/critical validator finding unresolved or
    claims a requested change only in its change_log. If the corrected
    attempt still regresses or still leaves the problem unresolved, the
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
        pending_changes=_format_pending(_still_pending(history, architecture)),
        score=review.score,
        required_changes="; ".join(review.required_changes) or "None explicitly listed.",
        issues=_format_issues(review),
        validator_findings=_format_validator_findings(state.get("validation_results")),
    )
    new_revision_count = state.get("revision_count", 0) + 1

    def attempt(prompt_text: str) -> tuple[Architecture, _Verdict]:
        candidate = llm_module.invoke_structured(llm, Architecture, prompt_text)
        return candidate, _Verdict(
            regressions=check_revision(architecture, candidate, requirements, prior_required_changes),
            unresolved=unresolved_findings(architecture, candidate, requirements),
            unimplemented=unimplemented_claims(candidate, prior_required_changes),
        )

    newly_implemented: list[str] = []
    try:
        revised, verdict = attempt(prompt)
        first_verdict = verdict
        corrected = False
        if not verdict.acceptable:
            # At most one corrective attempt per revision, whatever the reason.
            corrected = True
            revised, verdict = attempt(prompt + _correction(verdict, revised, architecture.version))
        regressions = verdict.regressions
        unjustified = blocking(regressions)

        if unjustified:
            _log_check(verdict, corrected, accepted=False)
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
        elif verdict.incomplete:
            _log_check(verdict, corrected, accepted=False)
            # No regressions, but the blocking problem is still there (or only
            # claimed in change_log). Accepting it would record fixes that don't
            # exist; keep the current version, whose validator findings stay
            # visible to the critic, and let the revision budget decide.
            problems = [issue.rule for issue in verdict.unresolved] + [
                f"claimed only in change_log: {_truncate(c.entry, 80)}" for c in verdict.unimplemented
            ]
            listed = "; ".join(problems[:3]) + (f"; +{len(problems) - 3} more" if len(problems) > 3 else "")
            action = (
                f"Rejected the revised architecture: blocking findings still unresolved after a corrective "
                f"attempt ({listed}); kept v{architecture.version} and re-submitted it to the critic."
            )
            revised = architecture
            output_summary = "Revision did not resolve blocking findings -- architecture unchanged this round."
        else:
            revised.version = architecture.version + 1
            if not revised.change_log:
                revised.change_log = list(review.required_changes)
            newly_implemented, checks = _record_verified_changes(revised)
            _log_check(verdict, corrected, accepted=True, checks=checks)
            justified = [r for r in regressions if r.justified]
            action = f"Revised architecture to v{revised.version}, addressing {len(review.required_changes)} required changes."
            if corrected and first_verdict.regressed:
                action += " A first attempt removed earlier fixes and was corrected."
            elif corrected:
                action += " A first attempt left blocking findings unresolved and was corrected."
            if justified:
                action += " Justified removals: " + "; ".join(r.item for r in justified[:4]) + "."
            proposed = sum(1 for c in checks if c.status == PROPOSED)
            unverified = sum(1 for c in checks if c.status not in (IMPLEMENTED, REMOVED, PROPOSED))
            action += (
                f" Change log verified against the design: {len(newly_implemented)} implemented or removed, "
                f"{proposed} proposed only (not in the design)"
                + (f", {unverified} could not be checked." if unverified else ".")
            )
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

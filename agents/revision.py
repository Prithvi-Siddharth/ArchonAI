"""Architecture Revision agent.

Runs when the Architecture Critic rejects a design. Takes the original
requirements, the current architecture, and the critic's findings, and
produces an improved architecture that explicitly addresses each required
change. The graph routes the result back to the critic for re-review, bounded
by MAX_REVISIONS to guarantee termination.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from agents import llm as llm_module
from agents.formatting import _truncate, compact_architecture
from graph.observability import log_event
from graph.state import ArchonState, make_trace_entry
from models.schemas import (
    Architecture,
    ArchitectureDelta,
    CriticReview,
    Requirements,
    ValidationIssue,
    ValidationResult,
)
from tools.architecture_delta import InvalidDeltaError, apply_delta, service_id
from tools.architecture_facts import (
    IMPLEMENTED,
    NOT_IMPLEMENTED_PREFIX,
    PROPOSED,
    REMOVED,
    ChangeCheck,
    pending_requests,
    verify_changes,
)
from tools.architecture_validator import (
    databases_without_backups,
    validate_architecture,
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

# How the revision returns its result. "delta" (default): only what changes
# (ArchitectureDelta), merged into the current design in code
# (tools/architecture_delta.py) -- in live runs ~40% fewer revision output
# tokens, no output cut off at the token cap, and an unchanged entry can't be
# dropped by accident. "full": a complete Architecture, as before -- kept as
# the rollback option. Both go through exactly the same checks. Read at call time.
OUTPUT_MODE_ENV = "REVISION_OUTPUT_MODE"
OUTPUT_FULL = "full"
OUTPUT_DELTA = "delta"


def output_mode() -> str:
    """The configured output mode: "full" only when set explicitly; unset or anything else means "delta"."""
    return OUTPUT_FULL if os.getenv(OUTPUT_MODE_ENV, "").strip().lower() == OUTPUT_FULL else OUTPUT_DELTA


_CONTEXT = """You are an AWS solutions architect revising a rejected architecture.

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
"""

_FULL_INSTRUCTIONS = """
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

PROMPT_TEMPLATE = _CONTEXT + _FULL_INSTRUCTIONS

# Delta mode: the same context (the architecture is shown with IDs S1, S2, ...),
# but the model returns only its changes. The rules are the full mode's,
# restated for a change set.
_DELTA_INSTRUCTIONS = """
Return ONLY what changes, as a change set against the current architecture above. Every
service entry you do not mention is kept exactly as it is -- do not restate unchanged entries.
- updated_services: {{id, service}} for each existing entry you change, using its ID exactly
  as shown (S1, S2, ...), with the complete new entry (name, category, purpose, justification).
  Update an entry only if its text must change -- never restate an unchanged entry, and never
  send the whole design.
- added_services: complete new entries.
- removed_services: {{id, reason}}, only for an explicit technical reason. A removed service
  must not be named anywhere else afterwards: update the summary, data_flow or any entry that
  mentions it.
- data_flow: the complete new data flow, only if it changes; otherwise omit it.
- summary: a new one-sentence summary (at most 30 words), only if it changes; otherwise omit it.
- change_log: exactly what changed and why, tied directly to the critic's required changes,
  at most 5 entries. Every service or capability a change_log entry names must appear in the
  services or data_flow after your changes -- a change that is only described in change_log
  does not count as implemented. Increment nothing yourself; the version is set by the caller.

Address every outstanding required change above. Do not change parts of the design that were
not flagged as problems.

Preserve earlier fixes -- no regressions:
- Keep every previously implemented change and every existing security, availability,
  disaster-recovery, backup and networking control (e.g. Secrets Manager, KMS, WAF,
  multi-AZ, cross-region replicas, backups, per-AZ NAT gateways, private subnets). When you
  update an entry, keep every control it already describes unless a change requires otherwise.
- If the latest required changes seem to conflict with an earlier fix, keep the earlier
  fix unless the conflict is real, and explain the choice in change_log.

Size limits (after your changes):
- At most 7 service entries. Combine closely related services into one entry
  (e.g. "Amazon CloudFront + AWS WAF"). An 8th is allowed only if a required change needs a
  new service that cannot share an entry -- say why in change_log, and keep data_flow to at
  most 5 steps.
- At most 6 data_flow steps, covering only the main request path.
- Each purpose/justification/description/change_log entry: one sentence, at most 12 words.

Keep key properties explicit in the text where they apply, using these exact terms:
multi-AZ, auto scaling, load balancer, backups, encryption, private subnet.
"""

DELTA_PROMPT_TEMPLATE = _CONTEXT + _DELTA_INSTRUCTIONS

# The single correction in delta mode is a change set applied on top of the
# rejected attempt, so it only has to carry the fix. (An attempt that could
# not be applied at all is redone against the current architecture.)
DELTA_CORRECTION_TEMPLATE = """

IMPORTANT: your previous change set was applied, but the result was not accepted:
{problems}
The result of your previous change set (its IDs are the ones to use now):
{attempt}
{added_note}Return a change set against THIS result that fixes every problem above. Make each fix in the
services (purpose or justification) or data_flow themselves, using the exact terms given -- a
change only described in change_log does not count. Restore anything lost, or -- only if
removing it is technically necessary -- remove it explicitly with a reason. A new
deterministic validator failure (e.g. a missing backup strategy) must be fixed, not justified.
Its change_log needs only the new changes.
"""

INVALID_DELTA_CORRECTION_TEMPLATE = """

IMPORTANT: your previous change set could not be applied:
{problems}
Return the change set again, against the current architecture above (version {version},
IDs S1, S2, ... as shown there), fixing these problems.
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
        "Add automated backups and point-in-time recovery explicitly to the purpose or justification of "
        "{uncovered} (use the words 'automated backups' and 'point-in-time recovery'). Each database "
        "needs its own backup strategy; backup wording on any other service does not count."
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
    # Delta mode only: why the change set could not be applied at all.
    invalid: list[str] = field(default_factory=list)

    @property
    def regressed(self) -> bool:
        return bool(blocking(self.regressions))

    @property
    def incomplete(self) -> bool:
        return bool(self.unresolved or self.unimplemented)

    @property
    def acceptable(self) -> bool:
        return not self.invalid and not self.regressed and not self.incomplete

    @property
    def reasons(self) -> list[str]:
        """Why this attempt can't be accepted, in a fixed order (empty if it can)."""
        reasons = []
        if self.invalid:
            reasons.append(REASON_INVALID_DELTA)
        if self.regressed:
            reasons.append(REASON_REGRESSION)
        if self.unresolved:
            reasons.append(REASON_UNRESOLVED_FINDING)
        if self.unimplemented:
            reasons.append(REASON_UNIMPLEMENTED_CLAIM)
        return reasons


# Why a first attempt was rejected and corrected (logged as first_reasons).
REASON_REGRESSION = "regression"
REASON_UNRESOLVED_FINDING = "unresolved_finding"
REASON_UNIMPLEMENTED_CLAIM = "unimplemented_claim"
REASON_INVALID_DELTA = "invalid_delta"


def _correction_note(first: _Verdict) -> str:
    """Trace sentence saying why the first attempt was rejected before it was corrected."""
    phrases = []
    if first.invalid:
        phrases.append(f"returned a change set that could not be applied ({_truncate(first.invalid[0], 100)})")
    if first.regressed:
        phrases.append("introduced an unjustified regression")
    if first.unresolved:
        rules = ", ".join(issue.rule for issue in first.unresolved)
        phrases.append(f"left a blocking validator finding unresolved ({rules})")
    if first.unimplemented:
        phrases.append("claimed a requested change in the change log that was not implemented in the architecture")
    return " A first attempt " + "; it also ".join(phrases) + " -- it was corrected."


def _database_name(architecture: Architecture) -> str:
    for service in architecture.services:
        if "database" in service.category.lower():
            return f"'{service.name}'"
    return "database"


def _fix_hint(rule: str, candidate: Architecture) -> str:
    """How to resolve a validator rule in `candidate`, naming its own services where it can."""
    # The validator's own list of databases lacking backups, by name (never
    # "the first Database-category service", which may be the wrong one).
    uncovered = ", ".join(f"'{name}'" for name in databases_without_backups(candidate)) or "the database service"
    return _FINDING_FIXES.get(rule, "Fix it in the services or data_flow.").format(
        database=_database_name(candidate), uncovered=uncovered
    )


def _format_unresolved(verdict: _Verdict, candidate: Architecture) -> str:
    lines = []
    for issue in verdict.unresolved:
        fix = _fix_hint(issue.rule, candidate)
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


def _delta_correction(
    verdict: _Verdict,
    attempt: Architecture | None,
    current: Architecture,
    requirements: Requirements,
) -> str:
    """The single corrective addition in delta mode."""
    if verdict.invalid or attempt is None:
        return INVALID_DELTA_CORRECTION_TEMPLATE.format(
            problems="\n".join(f"- {_truncate(p, _MAX_ITEM_CHARS)}" for p in verdict.invalid), version=current.version
        )
    problems = []
    if verdict.regressed:
        unjustified = blocking(verdict.regressions)
        problems.append(
            f"- Lost without an explicit justification (compared with version {current.version}):\n"
            + _format_regressions(unjustified)
        )
        # A new validator failure: say exactly what failed and how to fix it in
        # this attempt (e.g. which database still needs its own backups).
        new_rules = {r.item for r in unjustified if r.kind == "new_validator_issue"}
        for issue in validate_architecture(attempt, requirements).issues:
            if issue.rule in new_rules:
                problems.append(f"- To fix {issue.rule}: {issue.message} {_fix_hint(issue.rule, attempt)}")
    if verdict.incomplete:
        problems.append(_format_unresolved(verdict, attempt))
    # Entries the attempt added are already in it: repeating them as additions
    # would duplicate them. Name their IDs so a fix updates them instead.
    current_names = {s.name for s in current.services}
    added_ids = [service_id(i) for i, s in enumerate(attempt.services) if s.name not in current_names]
    added_note = (
        f"Entries {', '.join(added_ids)} were added by your previous change set and are already in it -- "
        "do not add them again; to change one, update it by its ID.\n"
        if added_ids
        else ""
    )
    return DELTA_CORRECTION_TEMPLATE.format(
        problems="\n".join(problems), attempt=compact_architecture(attempt, with_ids=True), added_note=added_note
    )


def _combined_change_log(first: list[str], second: list[str]) -> list[str]:
    """The attempt's change_log followed by its correction's, without duplicates."""
    combined: list[str] = []
    for entry in [*first, *second]:
        if entry not in combined:
            combined.append(entry)
    return combined


def _log_check(
    verdict: _Verdict,
    corrected: bool,
    accepted: bool,
    checks: list[ChangeCheck] | None = None,
    first: _Verdict | None = None,
) -> None:
    """Log the final verdict; when a correction was made, also why the first attempt failed.

    Only counts, categories and validator rule names -- never model text.
    """
    regressions = verdict.regressions
    unjustified = blocking(regressions)
    counts = {}
    if checks is not None:
        counts = {
            f"changes_{status}": sum(1 for c in checks if c.status == status)
            for status in ("implemented", "proposed", "removed", "unverified")
        }
    first_fields = {}
    if corrected and first is not None:
        first_unjustified = blocking(first.regressions)
        first_fields = {
            "first_reasons": ",".join(first.reasons),
            "first_unjustified": len(first_unjustified),
            "first_categories": ",".join(sorted({r.category for r in first_unjustified})) or None,
            "first_findings": ",".join(issue.rule for issue in first.unresolved) or None,
            "first_unimplemented_claims": len(first.unimplemented),
            "first_invalid_delta": len(first.invalid) or None,
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
        invalid_delta=len(verdict.invalid) or None,
        output_mode=output_mode(),
        corrected=corrected,
        accepted=accepted,
        **first_fields,
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

    mode = output_mode()
    llm = llm_module.get_llm(temperature=0.3, max_tokens=llm_module.ARCHITECTURE_MAX_TOKENS)
    template = DELTA_PROMPT_TEMPLATE if mode == OUTPUT_DELTA else PROMPT_TEMPLATE
    prompt = template.format(
        requirements=requirements.model_dump_json(),
        version=architecture.version,
        architecture=compact_architecture(architecture, with_ids=mode == OUTPUT_DELTA),
        review_history=_format_review_history(history),
        implemented_changes=_format_implemented_changes(implemented),
        pending_changes=_format_pending(_still_pending(history, architecture)),
        score=review.score,
        required_changes="; ".join(review.required_changes) or "None explicitly listed.",
        issues=_format_issues(review),
        validator_findings=_format_validator_findings(state.get("validation_results")),
    )
    new_revision_count = state.get("revision_count", 0) + 1

    def attempt(prompt_text: str, base: Architecture) -> tuple[Architecture | None, _Verdict]:
        if mode == OUTPUT_DELTA:
            # Merged in code, so every check below sees a complete design.
            delta = llm_module.invoke_structured(llm, ArchitectureDelta, prompt_text)
            try:
                candidate = apply_delta(base, delta)
            except InvalidDeltaError as exc:
                return None, _Verdict(regressions=[], unresolved=[], unimplemented=[], invalid=exc.problems)
            if base is not architecture:  # a correction on top of the rejected attempt
                candidate.change_log = _combined_change_log(base.change_log, candidate.change_log)
        else:
            candidate = llm_module.invoke_structured(llm, Architecture, prompt_text)
        # Always judged against the current architecture, never the attempt.
        return candidate, _Verdict(
            regressions=check_revision(architecture, candidate, requirements, prior_required_changes),
            unresolved=unresolved_findings(architecture, candidate, requirements),
            unimplemented=unimplemented_claims(candidate, prior_required_changes),
        )

    newly_implemented: list[str] = []
    try:
        revised, verdict = attempt(prompt, architecture)
        first_verdict = verdict
        corrected = False
        if not verdict.acceptable:
            # At most one corrective attempt per revision, whatever the reason.
            corrected = True
            if mode == OUTPUT_DELTA:
                base = revised if revised is not None else architecture
                correction = _delta_correction(verdict, revised, architecture, requirements)
                revised, verdict = attempt(prompt + correction, base)
            else:
                revised, verdict = attempt(prompt + _correction(verdict, revised, architecture.version), architecture)
        regressions = verdict.regressions
        unjustified = blocking(regressions)

        if verdict.invalid:
            _log_check(verdict, corrected, accepted=False, first=first_verdict)
            listed = "; ".join(_truncate(p, 100) for p in verdict.invalid[:2])
            more = f"; +{len(verdict.invalid) - 2} more" if len(verdict.invalid) > 2 else ""
            action = (
                f"Rejected the revision: its change set could not be applied ({listed}{more}); "
                f"kept v{architecture.version} and re-submitted it to the critic."
            )
            revised = architecture
            output_summary = "Revision change set could not be applied -- architecture unchanged this round."
        elif unjustified:
            _log_check(verdict, corrected, accepted=False, first=first_verdict)
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
            _log_check(verdict, corrected, accepted=False, first=first_verdict)
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
            _log_check(verdict, corrected, accepted=True, checks=checks, first=first_verdict)
            justified = [r for r in regressions if r.justified]
            action = f"Revised architecture to v{revised.version}, addressing {len(review.required_changes)} required changes."
            if corrected:
                action += _correction_note(first_verdict)
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

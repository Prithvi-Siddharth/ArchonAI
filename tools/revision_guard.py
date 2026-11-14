"""Revision regression guard.

Deterministic checks run before a revised architecture is accepted: does
the revision remove a service, or lose a security, availability, disaster
recovery, backup or networking capability, that the previous version had?
Like tools/architecture_validator.py this uses no LLM, so the same pair of
architectures always gets the same verdict.

Not every removal is a regression -- replacing a service can be the right
call. A removal counts as *justified* when the revision's change_log says so
explicitly: an entry that removes/replaces/consolidates the thing, names
it, and gives a reason ("Replaced X with Y to cut cost"). Only unjustified
removals, and newly failing validator rules, block.

Capabilities are found in the architecture's descriptive text (summary,
services, data flow) -- never in its change_log, which describes changes
rather than the design ("Replaced per-AZ NAT with ..." must not count as
having per-AZ NAT).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from models.schemas import Architecture, Requirements, ValidationIssue
from tools.architecture_facts import (
    NOT_IMPLEMENTED_PREFIX,
    PROPOSED,
    ChangeCheck,
    features_in,
    mentions,
    service_aliases,
    verify_changes,
)
from tools.architecture_validator import (
    _AUTOSCALING_TERMS,
    _BACKUP_TERMS,
    _LOAD_BALANCER_TERMS,
    _MULTI_AZ_TERMS,
    _full_text,
    blocking_findings,
    validate_architecture,
)

SECURITY = "security"
AVAILABILITY = "availability"
DISASTER_RECOVERY = "disaster_recovery"
BACKUPS = "backups"
NETWORKING = "networking"
SERVICES = "services"

# capability -> (category, terms that indicate it in the architecture text)
CAPABILITIES: dict[str, tuple[str, list[str]]] = {
    "secrets management": (SECURITY, ["secrets manager", "secret rotation", "parameter store"]),
    "encryption (KMS)": (SECURITY, ["kms", "encryption", "encrypted"]),
    "web application firewall": (SECURITY, ["waf", "web application firewall"]),
    "authentication / MFA": (SECURITY, ["cognito", "mfa", "multi-factor"]),
    "audit logging": (SECURITY, ["cloudtrail", "audit log", "audit logging"]),
    "threat detection": (SECURITY, ["guardduty"]),
    "multi-AZ deployment": (AVAILABILITY, [t.strip() for t in _MULTI_AZ_TERMS]),
    "load balancing": (AVAILABILITY, [t.strip() for t in _LOAD_BALANCER_TERMS]),
    "auto scaling": (AVAILABILITY, _AUTOSCALING_TERMS),
    "read replicas": (AVAILABILITY, ["read replica", "read replicas"]),
    "cross-region disaster recovery": (
        DISASTER_RECOVERY,
        [
            "cross-region",
            "cross region",
            "multi-region",
            "multi region",
            "second region",
            "secondary region",
            "aurora global database",
            "global database",
        ],
    ),
    "RTO/RPO targets": (DISASTER_RECOVERY, ["rto", "rpo"]),
    "database backups": (BACKUPS, _BACKUP_TERMS),  # plural-tolerant: "backups" counts
    "private subnets": (NETWORKING, ["private subnet", "private subnets"]),
    "per-AZ NAT gateways": (
        NETWORKING,
        [
            "nat per az",
            "per-az nat",
            "per az nat",
            "nat gateway per az",
            "nat gateways per az",
            "one nat gateway per az",
            "nat gateway in each az",
            "nat gateways in each az",
        ],
    ),
    "VPC endpoints": (NETWORKING, ["vpc endpoint", "vpc endpoints", "privatelink"]),
}

# Newly failing validator rules, by category.
_RULE_CATEGORIES = {
    "database_without_backups": BACKUPS,
    "high_availability_single_az": AVAILABILITY,
    "compute_without_load_balancer": AVAILABILITY,
    "high_traffic_without_scaling": AVAILABILITY,
    "sensitive_workload_missing_controls": SECURITY,
    "public_database_exposure": SECURITY,
    "missing_caching_layer": AVAILABILITY,
}

_REMOVAL_VERBS = re.compile(
    r"\b(remov\w*|replac\w*|drop\w*|retir\w*|consolidat\w*|merg\w*|swap\w*|downgrad\w*|eliminat\w*|deprecat\w*)\b"
)
# A justification must give a reason, not just announce the removal.
_REASON_WORDS = re.compile(r"\b(because|since|due to|so that|in favou?r of|to|as)\b")
_SERVICE_PREFIX = re.compile(r"^(amazon|aws)\s+")


@dataclass
class Regression:
    """Something the previous architecture had that the revision lost."""

    kind: str  # "removed_service" | "lost_capability" | "new_validator_issue"
    category: str
    item: str
    related_requirements: list[str] = field(default_factory=list)
    justification: str | None = None

    @property
    def justified(self) -> bool:
        return self.justification is not None

    def describe(self) -> str:
        what = {
            "removed_service": f"removed service '{self.item}'",
            "lost_capability": f"lost {self.category.replace('_', ' ')} capability '{self.item}'",
            "new_validator_issue": f"new validator failure '{self.item}'",
        }[self.kind]
        if self.related_requirements:
            what += f" (previously requested: {'; '.join(self.related_requirements[:2])})"
        return what


def _mentions(text: str, term: str) -> bool:
    """Whole word/phrase, ignoring hyphens and plurals: 'rto' doesn't match
    'protocol', 'backup' matches 'backups' (tools/architecture_facts.py)."""
    return mentions(text, term)


def _has_capability(text: str, terms: list[str]) -> bool:
    return any(_mentions(text, term) for term in terms)


_QUALIFIERS = re.compile(r"^(multi-?\s?az|single-?\s?az|serverless|provisioned|on-demand|global)$")


def _service_components(architecture: Architecture) -> list[tuple[str, list[str]]]:
    """Individual services with every name they may appear under.

    Splits combined entries ('Amazon CloudFront + AWS WAF'). A bracketed
    engine/variant is an alias, not a separate service: 'Amazon ElastiCache
    (Redis)' -> ('elasticache', [elasticache, redis, memcached, valkey]),
    'Amazon RDS (Aurora)' -> ('rds', [rds, aurora, ...]). Deployment
    qualifiers like '(Multi-AZ)' are dropped (they're checked as capabilities).
    """
    components: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for service in architecture.services:
        lowered = service.name.lower()
        brackets = [b.strip() for b in re.findall(r"\(([^)]*)\)", lowered)]
        bracket_aliases = [b for b in brackets if b and not _QUALIFIERS.match(b)]
        name_text = re.sub(r"\([^)]*\)|\bmulti-az\b|\bmulti az\b", " ", lowered)
        for part in re.split(r"\s*(?:\+|,|&|/|\band\b)\s*", name_text):
            name = _SERVICE_PREFIX.sub("", " ".join(part.split()))
            if not name or name in seen:
                continue
            seen.add(name)
            aliases = service_aliases(name)
            for alias in bracket_aliases:
                aliases.extend(a for a in service_aliases(alias) if a not in aliases)
            components.append((name, aliases))
    return components


def _justification(change_log: list[str], terms: list[str]) -> str | None:
    """The change_log entry that explicitly removes/replaces something named by `terms`."""
    for entry in change_log:
        lowered = entry.lower()
        if (
            _REMOVAL_VERBS.search(lowered)
            and _REASON_WORDS.search(lowered)
            and any(_mentions(lowered, term) for term in terms)
        ):
            return entry
    return None


def check_revision(
    previous: Architecture,
    revised: Architecture,
    requirements: Requirements,
    prior_required_changes: list[str] | None = None,
) -> list[Regression]:
    """Everything the revision lost relative to `previous`, each marked justified or not.

    `prior_required_changes` are the critic's earlier required changes; a
    lost capability that one of them asked for is reported against it (a
    previously satisfied critic requirement that is now unsatisfied).
    """
    before, after = _full_text(previous), _full_text(revised)
    change_log = list(revised.change_log)
    prior_required_changes = prior_required_changes or []
    regressions: list[Regression] = []

    for service, aliases in _service_components(previous):
        # Present under any of its names (ElastiCache as "Redis", RDS as
        # "Aurora") means renamed, not removed.
        if not any(_mentions(after, alias) for alias in aliases):
            regressions.append(
                Regression(
                    kind="removed_service",
                    category=SERVICES,
                    item=service,
                    justification=_justification(change_log, aliases),
                )
            )

    for capability, (category, terms) in CAPABILITIES.items():
        if _has_capability(before, terms) and not _has_capability(after, terms):
            related = [rc for rc in prior_required_changes if _has_capability(rc.lower(), terms)]
            regressions.append(
                Regression(
                    kind="lost_capability",
                    category=category,
                    item=capability,
                    related_requirements=related,
                    justification=_justification(change_log, terms + [capability.lower()]),
                )
            )

    # A rule the previous version passed and the revision fails is a
    # confirmed, deterministic regression; a change_log can't excuse it.
    previous_rules = {issue.rule for issue in validate_architecture(previous, requirements).issues}
    for issue in validate_architecture(revised, requirements).issues:
        if issue.rule not in previous_rules:
            regressions.append(
                Regression(
                    kind="new_validator_issue",
                    category=_RULE_CATEGORIES.get(issue.rule, "other"),
                    item=issue.rule,
                )
            )
    return regressions


def blocking(regressions: list[Regression]) -> list[Regression]:
    """The regressions a revision may not be accepted with: everything not explicitly justified."""
    return [r for r in regressions if not r.justified]


# ---------------------------------------------------------------------------
# Did the revision actually fix what it had to? (separate from regressions)
# ---------------------------------------------------------------------------

def unresolved_findings(previous: Architecture, revised: Architecture, requirements: Requirements) -> list[ValidationIssue]:
    """High/critical validator findings the previous version had and the revision still fails.

    Findings the revision newly introduces are regressions (check_revision),
    not listed here.
    """
    # Blocking severities (HIGH/CRITICAL) are defined once, in the validator;
    # the critic may not approve a design that still has one of these.
    flagged = {issue.rule for issue in blocking_findings(validate_architecture(previous, requirements))}
    return [issue for issue in validate_architecture(revised, requirements).issues if issue.rule in flagged]


def unimplemented_claims(revised: Architecture, required_changes: list[str]) -> list[ChangeCheck]:
    """change_log entries claiming a critic-requested feature the revised design doesn't contain.

    A claim only counts as implemented when the feature appears in the design
    text (summary, services, data flow) -- never because the change_log says
    so. Claims about things nobody requested are left to the usual
    "proposed only" marking and don't block.
    """
    requested = {feature.name for change in required_changes for feature in features_in(change)}
    return [
        check
        for check in verify_changes(revised.change_log, revised)
        if check.status == PROPOSED
        and not check.entry.startswith(NOT_IMPLEMENTED_PREFIX)
        and requested.intersection(check.missing)
    ]

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

from models.schemas import Architecture, Requirements
from tools.architecture_validator import (
    _AUTOSCALING_TERMS,
    _BACKUP_TERMS,
    _LOAD_BALANCER_TERMS,
    _MULTI_AZ_TERMS,
    _full_text,
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
    "database backups": (BACKUPS, _BACKUP_TERMS),
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
    """`term` appears in `text` as a whole word/phrase (so 'rto' doesn't match 'proto')."""
    return re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text) is not None


def _has_capability(text: str, terms: list[str]) -> bool:
    return any(_mentions(text, term) for term in terms)


def _service_components(architecture: Architecture) -> list[str]:
    """Individual services, splitting combined entries like 'Amazon CloudFront + AWS WAF'."""
    components: list[str] = []
    for service in architecture.services:
        # "Amazon RDS (Multi-AZ)" -> "rds"; deployment qualifiers aren't services
        # (they're checked as capabilities instead).
        name_text = re.sub(r"\([^)]*\)|\bmulti-az\b|\bmulti az\b", " ", service.name.lower())
        for part in re.split(r"\s*(?:\+|,|&|/|\band\b)\s*", name_text):
            name = _SERVICE_PREFIX.sub("", " ".join(part.split()))
            if name and name not in components:
                components.append(name)
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

    for service in _service_components(previous):
        if not _mentions(after, service):
            regressions.append(
                Regression(
                    kind="removed_service",
                    category=SERVICES,
                    item=service,
                    justification=_justification(change_log, [service]),
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

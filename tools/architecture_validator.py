"""Architecture Validator tool.

Deterministic, rule-based checks that complement the LLM-based Architecture
Critic. These rules pattern-match the proposed architecture's selected
services and descriptive text against known cloud anti-patterns. They use no
LLM and always produce the same verdict for the same input, which is the
point: the critic can be wrong or inconsistent, this cannot.
"""

from __future__ import annotations

import re

from models.schemas import Architecture, Requirements, Severity, ValidationIssue, ValidationResult

_LOAD_BALANCER_TERMS = ["load balancer", "alb", "elastic load balancing", " elb"]
_COMPUTE_TERMS = ["ec2", "ecs", "eks", "fargate", "lambda"]
_MULTI_AZ_TERMS = [
    "multi-az",
    "multi az",
    "multiple availability zones",
    "across availability zones",
    "across multiple azs",
]
_AUTOSCALING_TERMS = [
    "auto scaling",
    "autoscaling",
    "auto-scaling",
    "scale out",
    "horizontal scaling",
    "scales horizontally",
]
_SECURITY_TERMS = [
    "encryption",
    "encrypted",
    "iam",
    "waf",
    "security group",
    "kms",
    "secrets manager",
    "least privilege",
]
_BACKUP_TERMS = ["backup", "snapshot", "point-in-time recovery", "point in time recovery", "pitr", "aws backup"]
_PRIVATE_DB_TERMS = [
    "private subnet",
    "private networking",
    "not publicly accessible",
    "no public access",
    "isolated in a private",
]
_PUBLIC_DB_TERMS = [
    "publicly accessible",
    "public subnet database",
    "public database",
    "open to the internet",
    "exposed to the internet",
]
_CACHE_TERMS = ["elasticache", "redis", "memcached", "cache", "cdn", "cloudfront"]
_DATABASE_TERMS = ["rds", "aurora", "dynamodb", "database"]
_HIGH_VOLUME_HINTS = ["000", "million", "spike", "high", "large"]


# Severities that block: a revision that leaves one of these unresolved is not
# accepted (tools/revision_guard.py), and the critic may not approve a design
# that still has one (agents/critic.py). MEDIUM findings lower the score and
# LOW findings are informational; neither blocks on its own.
BLOCKING_SEVERITIES = (Severity.HIGH, Severity.CRITICAL)


def blocking_findings(result: ValidationResult | None) -> list[ValidationIssue]:
    """The findings in `result` whose severity blocks acceptance and approval."""
    if result is None:
        return []
    return [issue for issue in result.issues if issue.severity in BLOCKING_SEVERITIES]


# ---------------------------------------------------------------------------
# Backups, per database service
# ---------------------------------------------------------------------------

# Database engines this rule checks, by the whole words that name them in a
# service name. ElastiCache is a cache, not a database, for this rule.
_DATABASE_ENGINES: dict[str, tuple[str, ...]] = {
    "rds": ("rds", "relational database service"),
    "aurora": ("aurora",),
    "dynamodb": ("dynamodb",),
    "documentdb": ("documentdb", "document db"),
    "neptune": ("neptune",),
}
# Generic wording that means a database exists even when no engine is named
# (used only by the whole-text fallback).
_GENERIC_DATABASE_TERMS = ("database", "databases", *(t for terms in _DATABASE_ENGINES.values() for t in terms))
_ALL_DATABASES = re.compile(r"\b(all|every|each)\s+(\w+\s+)?(databases?|data\s+stores?)\b")
_NAME_PARTS = re.compile(r"\s*(?:\+|,|&|/|\band\b)\s*")


def _normalize(text: str) -> str:
    """Lowercase; hyphens and underscores become spaces ('point-in-time' == 'point in time')."""
    return " ".join(re.sub(r"[-_]", " ", text.lower()).split())


def _has_word(text: str, term: str) -> bool:
    """`term` as a whole word or phrase (plural allowed): 'rds' is not in 'records'."""
    pattern = rf"(?<![a-z0-9]){re.escape(_normalize(term))}s?(?![a-z0-9])"
    return re.search(pattern, _normalize(text)) is not None


def _names_any(text: str, terms: set[str]) -> bool:
    return any(_has_word(text, term) for term in terms)


def _has_backup_term(text: str) -> bool:
    return any(_has_word(text, term) for term in _BACKUP_TERMS)


def _split_service_name(name: str) -> list[str]:
    """Split a combined service name on + , & / and -- but never inside brackets.

    'Amazon DynamoDB + Amazon ElastiCache (Redis)' -> ['Amazon DynamoDB', 'Amazon ElastiCache (Redis)'];
    'Amazon RDS (MySQL, PostgreSQL)' stays whole. Each bracketed part is set
    aside before splitting and restored verbatim afterwards.
    """
    brackets: list[str] = []

    def set_aside(match: re.Match) -> str:
        brackets.append(match.group(0))
        return f"\x00{len(brackets) - 1}\x00"

    masked = re.sub(r"\([^)]*\)", set_aside, name)
    restore = re.compile(r"\x00(\d+)\x00")
    return [restore.sub(lambda m: brackets[int(m.group(1))], part).strip() for part in _NAME_PARTS.split(masked)]


def _database_components(architecture: Architecture) -> list[tuple[str, str, set[str]]]:
    """(component name, its service entry's own text, engine terms) for each database named in a service.

    Combined entries are split: 'Amazon DynamoDB + Amazon ElastiCache (Redis)'
    yields only 'Amazon DynamoDB'. A bracketed engine stays with its service:
    'Amazon RDS (Aurora)' is one database.
    """
    components = []
    for service in architecture.services:
        own_text = f"{service.name} {service.purpose} {service.justification}"
        for part in _split_service_name(service.name):
            terms = {t for engine in _DATABASE_ENGINES.values() for t in engine if _has_word(part, t)}
            if terms:
                components.append((part, own_text, terms))
    return components


def _backup_service_texts(architecture: Architecture) -> list[str]:
    """The text of every dedicated AWS Backup service entry."""
    return [
        f"{s.name} {s.purpose} {s.justification}"
        for s in architecture.services
        if _has_word(s.name, "aws backup")
    ]


def databases_without_backups(architecture: Architecture) -> list[str]:
    """Database services (by name) with no backup/recovery strategy of their own.

    A database is covered only by (A) a backup term in its own service entry,
    (B) a data-flow step that names it and a backup term, or (C) an AWS Backup
    service entry that names it or covers all databases. Backup wording that
    belongs to another service (e.g. S3 "with backups") never counts.
    """
    flow_texts = [f"{step.source} {step.destination} {step.description}" for step in architecture.data_flow]
    backup_services = _backup_service_texts(architecture)
    uncovered: list[str] = []
    for name, own_text, terms in _database_components(architecture):
        covered = (
            _has_backup_term(own_text)
            or any(_names_any(text, terms) and _has_backup_term(text) for text in flow_texts)
            or any(_names_any(text, terms) or _ALL_DATABASES.search(_normalize(text)) for text in backup_services)
        )
        if not covered and name not in uncovered:
            uncovered.append(name)
    return uncovered


def _backup_issue(architecture: Architecture) -> ValidationIssue | None:
    """The database_without_backups finding, if any (rule name and HIGH severity unchanged)."""
    if _database_components(architecture):
        uncovered = databases_without_backups(architecture)
        if not uncovered:
            return None
        message = "No backup strategy described for: " + ", ".join(uncovered) + "."
    else:
        # No supported database is named, but the design may still describe
        # one generically ("a relational database"): keep the whole-text check.
        text = _full_text(architecture)
        if not any(_has_word(text, term) for term in _GENERIC_DATABASE_TERMS) or _has_backup_term(text):
            return None
        message = "A database is part of the architecture, but no backup strategy was described."
    return ValidationIssue(rule="database_without_backups", message=message, severity=Severity.HIGH)


def _full_text(architecture: Architecture) -> str:
    parts = [architecture.summary]
    for service in architecture.services:
        parts.extend([service.name, service.purpose, service.justification])
    for step in architecture.data_flow:
        parts.append(step.description)
    return " ".join(parts).lower()


def validate_architecture(architecture: Architecture, requirements: Requirements) -> ValidationResult:
    """Run deterministic rule checks against a proposed architecture.

    Returns every rule violation found, each tagged with a severity. This
    complements, but never replaces, the LLM Architecture Critic node.
    """
    text = _full_text(architecture)
    issues: list[ValidationIssue] = []

    has_compute = any(term in text for term in _COMPUTE_TERMS)
    has_load_balancer = any(term in text for term in _LOAD_BALANCER_TERMS)
    implies_multi_instance = any(
        term in text for term in _AUTOSCALING_TERMS + ["multiple instances", "multiple tasks"]
    )
    if has_compute and implies_multi_instance and not has_load_balancer:
        issues.append(
            ValidationIssue(
                rule="compute_without_load_balancer",
                message=(
                    "Compute is described as scaling across multiple instances/tasks, "
                    "but no load balancer was found in the architecture."
                ),
                severity=Severity.HIGH,
            )
        )

    availability_text = (requirements.availability_requirements + " " + requirements.scalability_requirements).lower()
    wants_high_availability = "99.9" in availability_text or "high availability" in availability_text
    if wants_high_availability and not any(term in text for term in _MULTI_AZ_TERMS):
        issues.append(
            ValidationIssue(
                rule="high_availability_single_az",
                message=(
                    "High availability is required, but the architecture does not "
                    "explicitly describe a multi-AZ deployment."
                ),
                severity=Severity.CRITICAL,
            )
        )

    traffic_text = (requirements.concurrent_users + " " + requirements.traffic_characteristics).lower()
    high_traffic = any(hint in traffic_text for hint in _HIGH_VOLUME_HINTS)
    if high_traffic and not any(term in text for term in _AUTOSCALING_TERMS):
        issues.append(
            ValidationIssue(
                rule="high_traffic_without_scaling",
                message="High or spiky traffic is expected, but no auto-scaling strategy was found.",
                severity=Severity.HIGH,
            )
        )

    sensitive_text = (
        requirements.security_requirements
        + " "
        + requirements.compliance_requirements
        + " "
        + requirements.application_type
    ).lower()
    sensitive_workload = any(
        keyword in sensitive_text
        for keyword in ["payment", "pci", "hipaa", "bank", "financial", "health", "personal data", "pii"]
    )
    if sensitive_workload and not any(term in text for term in _SECURITY_TERMS):
        issues.append(
            ValidationIssue(
                rule="sensitive_workload_missing_controls",
                message=(
                    "Sensitive or regulated data is involved, but the architecture does not "
                    "describe concrete security controls (encryption, IAM, WAF, etc.)."
                ),
                severity=Severity.CRITICAL,
            )
        )

    has_database = any(term in text for term in _DATABASE_TERMS)  # used by public_database_exposure below
    backup_issue = _backup_issue(architecture)
    if backup_issue is not None:
        issues.append(backup_issue)

    if (
        has_database
        and any(term in text for term in _PUBLIC_DB_TERMS)
        and not any(term in text for term in _PRIVATE_DB_TERMS)
    ):
        issues.append(
            ValidationIssue(
                rule="public_database_exposure",
                message="The database appears to be publicly accessible instead of isolated in a private subnet.",
                severity=Severity.CRITICAL,
            )
        )

    extreme_read_traffic = high_traffic and "read" in requirements.database_requirements.lower()
    if extreme_read_traffic and not any(term in text for term in _CACHE_TERMS):
        issues.append(
            ValidationIssue(
                rule="missing_caching_layer",
                message="Very high read traffic is expected, but no caching layer was found in the architecture.",
                severity=Severity.MEDIUM,
            )
        )

    return ValidationResult(passed=len(issues) == 0, issues=issues)

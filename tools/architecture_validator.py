"""Architecture Validator tool.

Deterministic, rule-based checks that complement the LLM-based Architecture
Critic. These rules pattern-match the proposed architecture's selected
services and descriptive text against known cloud anti-patterns. They use no
LLM and always produce the same verdict for the same input, which is the
point: the critic can be wrong or inconsistent, this cannot.
"""

from __future__ import annotations

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
_BACKUP_TERMS = ["backup", "snapshot", "point-in-time recovery", "aws backup"]
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

    has_database = any(term in text for term in _DATABASE_TERMS)
    if has_database and not any(term in text for term in _BACKUP_TERMS):
        issues.append(
            ValidationIssue(
                rule="database_without_backups",
                message="A database is part of the architecture, but no backup strategy was described.",
                severity=Severity.HIGH,
            )
        )

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

"""What an architecture actually contains -- deterministic, no LLM.

A fixed catalog of AWS services and architecture capabilities, each with the
terms (and aliases) that indicate it. Used to:

- verify a revision's change_log against its real design (so "Added
  Secrets Manager" only counts if Secrets Manager is actually in the design);
- tell whether a critic request is satisfied or still pending;
- recognise the same service under another name (ElastiCache <-> Redis);
- keep the final report from claiming features the design doesn't have.

The *design text* is the summary, services and data flow -- never the
change_log, which describes claims rather than the design.

Matching is case-insensitive, whole-word, and ignores hyphens/slashes and
plurals: "warm-standby" == "warm standby", "backup" matches "backups".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from models.schemas import Architecture
from tools.architecture_validator import _full_text

SERVICE = "service"
CAPABILITY = "capability"


@dataclass(frozen=True)
class Feature:
    name: str
    kind: str
    terms: tuple[str, ...]


def _s(name: str, *terms: str) -> Feature:
    return Feature(name, SERVICE, terms)


def _c(name: str, *terms: str) -> Feature:
    return Feature(name, CAPABILITY, terms)


# Aliases are only ones that denote the same service (Aurora is an RDS engine,
# Redis/Memcached/Valkey are ElastiCache engines). Observability tooling
# (CloudWatch, X-Ray) is deliberately not listed: it is ambient on AWS and
# not something a design "adds".
FEATURES: tuple[Feature, ...] = (
    _s("Amazon DynamoDB", "dynamodb"),
    _s("DynamoDB Accelerator (DAX)", "dax", "dynamodb accelerator"),
    _s("Amazon ElastiCache", "elasticache", "redis", "memcached", "valkey"),
    _s("Amazon RDS / Aurora", "rds", "aurora", "relational database service"),
    _s("Amazon Cognito", "cognito"),
    _s("AWS Secrets Manager", "secrets manager"),
    _s("SSM Parameter Store", "parameter store"),
    _s("AWS KMS", "kms", "key management service", "customer managed key", "cmk"),
    _s("AWS WAF", "waf", "web application firewall"),
    _s("AWS Shield", "shield"),
    _s("AWS CloudTrail", "cloudtrail"),
    _s("Amazon GuardDuty", "guardduty"),
    _s("Amazon CloudFront", "cloudfront"),
    _s("Elastic Load Balancing", "application load balancer", "network load balancer", "load balancer",
       "elastic load balancing", "alb", "nlb", "elb"),
    _s("Amazon ECS", "ecs", "elastic container service", "fargate"),
    _s("Amazon EKS", "eks", "elastic kubernetes service", "kubernetes"),
    _s("AWS Lambda", "lambda"),
    _s("Amazon EC2", "ec2"),
    _s("Amazon S3", "s3", "simple storage service"),
    _s("Amazon SQS", "sqs", "simple queue service"),
    _s("Amazon SNS", "sns", "simple notification service"),
    _s("Amazon Kinesis", "kinesis"),
    _s("Amazon API Gateway", "api gateway"),
    _s("Amazon Route 53", "route 53", "route53"),
    _s("AWS Backup", "aws backup"),
    _s("Amazon OpenSearch", "opensearch", "elasticsearch"),
    _s("NAT gateway", "nat gateway", "nat"),
    _c("cross-region disaster recovery", "cross region", "multi region", "second region", "secondary region",
       "global database", "global table"),
    _c("warm standby / pilot light", "warm standby", "pilot light"),
    _c("RTO/RPO targets", "rto", "rpo"),
    _c("read replicas", "read replica"),
    _c("point-in-time recovery", "point in time recovery", "pitr"),
    _c("database backups", "backup", "snapshot"),
    _c("multi-AZ deployment", "multi az", "multiple availability zones", "across availability zones"),
    _c("auto scaling", "auto scaling", "autoscaling", "scale out"),
    _c("private subnets", "private subnet"),
    _c("per-AZ NAT gateways", "nat per az", "per az nat", "nat gateway per az", "nat gateway in each az"),
    _c("VPC endpoints", "vpc endpoint", "privatelink"),
    _c("MFA", "mfa", "multi factor"),
    _c("encryption", "encryption", "encrypted", "tls"),
    _c("circuit breakers", "circuit breaker"),
    _c("retries with backoff", "retry", "retries", "backoff"),
)

FEATURES_BY_NAME = {f.name: f for f in FEATURES}


def normalize(text: str) -> str:
    """Lowercase; hyphens, underscores and slashes become spaces."""
    return " ".join(re.sub(r"[-_/]", " ", text.lower()).split())


def mentions(text: str, term: str) -> bool:
    """`term` appears in `text` as a whole word/phrase, singular or plural.

    'rto' doesn't match 'protocol'; 'backup' matches 'backups';
    'warm-standby' matches 'warm standby'.
    """
    pattern = rf"(?<![a-z0-9]){re.escape(normalize(term))}(?:s|es)?(?![a-z0-9])"
    return re.search(pattern, normalize(text)) is not None


def mentions_any(text: str, terms) -> bool:
    return any(mentions(text, t) for t in terms)


def features_in(text: str) -> list[Feature]:
    """Catalog features the text mentions, in catalog order."""
    return [f for f in FEATURES if mentions_any(text, f.terms)]


def design_text(architecture: Architecture) -> str:
    """Summary, services and data flow -- what the design *is*, not its change_log."""
    return _full_text(architecture)


def present_features(architecture: Architecture) -> set[str]:
    return {f.name for f in features_in(design_text(architecture))}


def service_aliases(component: str) -> list[str]:
    """Every name the same service may appear under ('elasticache' -> redis, ...)."""
    aliases = [component]
    for feature in FEATURES:
        if feature.kind == SERVICE and mentions_any(component, feature.terms):
            aliases.extend(t for t in feature.terms if t not in aliases)
    return aliases


# ---------------------------------------------------------------------------
# Verifying claimed changes and critic requests
# ---------------------------------------------------------------------------

IMPLEMENTED = "implemented"  # every feature it claims is in the design
PROPOSED = "proposed"  # claims a feature the design doesn't contain
REMOVED = "removed"  # an intentional removal, and the thing is gone
UNVERIFIED = "unverified"  # names nothing the catalog knows -- can't be checked

NOT_IMPLEMENTED_PREFIX = "Not implemented (proposed only): "

_REMOVAL = re.compile(r"^\s*(removed?|dropped|drop|retired?|eliminated?|deprecated?|decommissioned?)\b")
_REPLACEMENT = re.compile(
    r"^\s*(replaced?|swapped|swap|migrated?|consolidated?|merged?|moved?)\b(?P<old>.*?)\b(with|by|into|to)\b(?P<new>.*)$"
)
# The reason part of an entry ("... to offload reads", "... for PCI-DSS")
# names things it doesn't claim to add.
_REASON = re.compile(r"\s+(because|since|so that|due to|in order to|to|for)\s+")


@dataclass
class ChangeCheck:
    entry: str
    status: str
    claimed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def _head(text: str) -> str:
    return _REASON.split(text, maxsplit=1)[0]


def _claims(text: str) -> list[Feature]:
    """Features a phrase claims: those in its head clause, else in the whole phrase."""
    return features_in(_head(text)) or features_in(text)


def verify_change(entry: str, architecture: Architecture) -> ChangeCheck:
    """Classify one change_log entry (or critic request) against the design."""
    if entry.startswith(NOT_IMPLEMENTED_PREFIX):
        return ChangeCheck(entry, PROPOSED)
    present = present_features(architecture)
    lowered = normalize(entry)

    if _REMOVAL.match(lowered):
        removed = _claims(entry)
        still_there = [f.name for f in removed if f.name in present]
        if not removed:
            return ChangeCheck(entry, UNVERIFIED)
        return ChangeCheck(entry, PROPOSED if still_there else REMOVED, [f.name for f in removed], still_there)

    replacement = _REPLACEMENT.match(lowered)
    claimed = _claims(replacement.group("new")) if replacement else []
    if not claimed:
        claimed = _claims(entry)
    if not claimed:
        return ChangeCheck(entry, UNVERIFIED)
    missing = [f.name for f in claimed if f.name not in present]
    return ChangeCheck(entry, PROPOSED if missing else IMPLEMENTED, [f.name for f in claimed], missing)


def verify_changes(entries: list[str], architecture: Architecture) -> list[ChangeCheck]:
    return [verify_change(entry, architecture) for entry in entries]


def pending_requests(requests: list[str], architecture: Architecture) -> list[str]:
    """Critic requests whose named services/capabilities are not in the design.

    Requests that name nothing the catalog knows can't be checked and are
    left out (the review history still shows them).
    """
    seen: set[str] = set()
    pending = []
    for request in requests:
        if request in seen:
            continue
        seen.add(request)
        if verify_change(request, architecture).status == PROPOSED:
            pending.append(request)
    return pending


def absent_features(texts: list[str], architecture: Architecture) -> list[str]:
    """Catalog features mentioned in `texts` (analyses, critic, change_log) but not in the design."""
    present = present_features(architecture)
    names: list[str] = []
    for text in texts:
        for feature in features_in(text):
            if feature.name not in present and feature.name not in names:
                names.append(feature.name)
    return names

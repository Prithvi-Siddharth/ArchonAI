"""database_without_backups is checked per database service.

Backup wording belonging to another service (S3 "with backups") must not
satisfy a database's requirement. A database is covered by its own service
entry, by a data-flow step that names it, or by an AWS Backup entry that
names it or covers all databases. Rule name and HIGH severity are unchanged.
Deterministic -- no LLM.
"""

from __future__ import annotations

from agents import revision as revision_agent
from graph.state import create_initial_state
from models.schemas import AWSService, CriticReview, DataFlowStep, Severity
from tools.architecture_validator import (
    databases_without_backups,
    validate_architecture,
)
from tools.revision_guard import blocking, check_revision

from .conftest import make_architecture, make_requirements
from .test_revision_guard import _script_revisions

RULE = "database_without_backups"


def _svc(name: str, purpose: str = "Stores data", justification: str = "Managed service", category="Database"):
    return AWSService(name=name, category=category, purpose=purpose, justification=justification)


AURORA_NO_BACKUPS = _svc("Amazon Aurora (PostgreSQL)", "Orders and payments", "Multi-AZ, encrypted, private subnet")
AURORA_BACKUPS = _svc("Amazon Aurora (PostgreSQL)", "Orders and payments", "Multi-AZ with automated backups")
DYNAMODB_NO_BACKUPS = _svc("Amazon DynamoDB", "Catalog reads", "Single-digit ms at scale")
S3_WITH_BACKUPS = _svc("Amazon S3", "Product images/media with encryption and backups.", "Durable storage", "Storage")
ALB = _svc("Application Load Balancer", "Routes traffic", "Multi-AZ health checks", "Networking")


def _design(*services: AWSService, data_flow=None, summary="A multi-AZ, auto scaling platform behind a load balancer."):
    return make_architecture(
        summary=summary,
        services=[ALB, *services],
        data_flow=data_flow if data_flow is not None else [],
    )


def _backup_issues(architecture):
    return [i for i in validate_architecture(architecture, make_requirements()).issues if i.rule == RULE]


# ---------------------------------------------------------------------------
# Coverage per database
# ---------------------------------------------------------------------------


def test_s3_backups_do_not_cover_aurora():  # 1
    design = _design(AURORA_NO_BACKUPS, S3_WITH_BACKUPS)

    (issue,) = _backup_issues(design)
    assert issue.message == "No backup strategy described for: Amazon Aurora (PostgreSQL)."
    assert databases_without_backups(design) == ["Amazon Aurora (PostgreSQL)"]


def test_aurora_with_its_own_automated_backups_passes():  # 2
    assert _backup_issues(_design(AURORA_BACKUPS, S3_WITH_BACKUPS)) == []


def test_aurora_with_pitr_passes():  # 3
    assert _backup_issues(_design(_svc("Amazon Aurora", "Orders", "PITR enabled, multi-AZ"))) == []


def test_dynamodb_with_point_in_time_recovery_passes():  # 4
    for wording in ("point-in-time recovery enabled", "Point in time recovery enabled"):
        assert _backup_issues(_design(_svc("Amazon DynamoDB", "Catalog reads", wording))) == []


def test_dynamodb_without_backups_is_flagged():  # 5
    (issue,) = _backup_issues(_design(AURORA_BACKUPS, DYNAMODB_NO_BACKUPS))
    assert issue.message == "No backup strategy described for: Amazon DynamoDB."


def test_aws_backup_covering_all_databases_covers_every_database():  # 6
    backup = _svc("AWS Backup", "Centralized backup plans for all databases", "Daily, 35-day retention", "Storage")
    assert _backup_issues(_design(AURORA_NO_BACKUPS, DYNAMODB_NO_BACKUPS, backup)) == []


def test_aws_backup_naming_only_aurora_leaves_dynamodb_flagged():  # 7
    backup = _svc("AWS Backup", "Backup plans for Aurora", "Daily, 35-day retention", "Storage")
    design = _design(AURORA_NO_BACKUPS, DYNAMODB_NO_BACKUPS, backup)

    assert databases_without_backups(design) == ["Amazon DynamoDB"]


def test_data_flow_step_naming_the_database_and_its_backups_covers_it():
    flow = [DataFlowStep(step=1, source="Aurora", destination="AWS Backup vault", description="Nightly snapshots")]
    assert _backup_issues(_design(AURORA_NO_BACKUPS, data_flow=flow)) == []
    # A step about another service's backups does not count.
    s3_flow = [DataFlowStep(step=1, source="S3", destination="Glacier", description="Media backups")]
    assert len(_backup_issues(_design(AURORA_NO_BACKUPS, data_flow=s3_flow))) == 1


# ---------------------------------------------------------------------------
# Identifying databases
# ---------------------------------------------------------------------------


def test_records_is_not_rds():  # 8
    records = _svc("Order Records Service", "Keeps records of orders", "Stateless API", "Compute")
    design = _design(records, summary="A stateless records API behind a load balancer.")

    assert databases_without_backups(design) == []
    assert _backup_issues(design) == []


def test_elasticache_is_not_a_database_for_this_rule():  # 9
    cache = _svc("Amazon ElastiCache (Redis)", "Session cache", "In-memory, multi-AZ", "Database")
    assert databases_without_backups(_design(AURORA_BACKUPS, cache)) == []


def test_combined_dynamodb_and_elasticache_entry_contains_dynamodb():  # 10
    combined = _svc("Amazon DynamoDB + Amazon ElastiCache (Redis)", "Catalog and sessions", "Fast key-value state")
    assert databases_without_backups(_design(AURORA_BACKUPS, combined)) == ["Amazon DynamoDB"]
    covered = _svc("Amazon DynamoDB + Amazon ElastiCache (Redis)", "Catalog and sessions", "DynamoDB PITR on")
    assert databases_without_backups(_design(AURORA_BACKUPS, covered)) == []


def test_multiple_uncovered_databases_produce_one_finding_naming_all():  # 11
    (issue,) = _backup_issues(_design(AURORA_NO_BACKUPS, DYNAMODB_NO_BACKUPS, S3_WITH_BACKUPS))
    assert issue.message == "No backup strategy described for: Amazon Aurora (PostgreSQL), Amazon DynamoDB."


def test_generic_database_description_keeps_the_whole_text_fallback():  # 12
    generic = _svc("Managed relational store", "A relational database for orders", "Simple", "Database")
    (issue,) = _backup_issues(_design(generic))
    assert issue.message == "A database is part of the architecture, but no backup strategy was described."
    # With backup wording anywhere, the fallback passes as it did before.
    assert _backup_issues(_design(generic, summary="Relational database with nightly snapshots.")) == []


def test_rule_name_and_high_severity_are_unchanged():  # 13, 14
    (issue,) = _backup_issues(_design(AURORA_NO_BACKUPS))
    assert issue.rule == "database_without_backups"
    assert issue.severity == Severity.HIGH


# ---------------------------------------------------------------------------
# Revision guard and revision hint
# ---------------------------------------------------------------------------


def test_guard_treats_a_newly_uncovered_database_as_a_regression():  # 15
    before = _design(AURORA_BACKUPS)
    after = _design(AURORA_BACKUPS, DYNAMODB_NO_BACKUPS)

    (regression,) = blocking(check_revision(before, after, make_requirements()))
    assert (regression.kind, regression.item, regression.category) == ("new_validator_issue", RULE, "backups")


def test_moving_backup_wording_from_aurora_to_s3_is_rejected_as_a_regression(monkeypatch):  # 16
    current = _design(AURORA_BACKUPS, _svc("Amazon S3", "Product images", "Durable storage", "Storage"))
    moved = _design(AURORA_NO_BACKUPS, S3_WITH_BACKUPS)
    assert "new validator failure 'database_without_backups'" in [
        r.describe() for r in blocking(check_revision(current, moved, make_requirements()))
    ]
    _script_revisions(monkeypatch, moved, moved)
    state = create_initial_state("Design an e-commerce platform.")
    review = CriticReview(approved=False, score=60, required_changes=["Add product image storage."])
    state.update(requirements=make_requirements(), architecture=current, critic_review=review,
                 critic_history=[review], revision_count=0)

    result = revision_agent.run(state)

    assert result["architecture"] == current  # rejected; the current version is kept
    assert result["execution_trace"][0]["action"].startswith("Rejected the revised architecture as a regression")


def test_revision_hint_names_the_uncovered_database_not_the_first_one(monkeypatch):
    current = _design(AURORA_BACKUPS, DYNAMODB_NO_BACKUPS)  # Aurora is listed first, but covered
    review = CriticReview(approved=False, score=60, required_changes=["Add DynamoDB backups."])
    prompts = _script_revisions(monkeypatch, current, current)
    state = create_initial_state("Design an e-commerce platform.")
    state.update(requirements=make_requirements(), architecture=current, critic_review=review,
                 critic_history=[review], revision_count=0)

    revision_agent.run(state)

    correction = prompts[1]
    assert "purpose or justification of 'Amazon DynamoDB'" in correction
    assert "of 'Amazon Aurora" not in correction


# ---------------------------------------------------------------------------
# Bracket-aware service names (displayed in the finding and the revision hint)
# ---------------------------------------------------------------------------


def test_commas_and_and_inside_brackets_do_not_split_a_database_name():
    rds = _svc("Amazon RDS (MySQL, PostgreSQL)")
    aurora = _svc("Amazon Aurora (MySQL and PostgreSQL)")

    (issue,) = _backup_issues(_design(rds, aurora))
    assert issue.message == (
        "No backup strategy described for: Amazon RDS (MySQL, PostgreSQL), Amazon Aurora (MySQL and PostgreSQL)."
    )


def test_splitting_outside_brackets_still_works():
    names = databases_without_backups(
        _design(
            _svc("Amazon RDS (MySQL/PostgreSQL) + Amazon DynamoDB"),
            _svc("Amazon Neptune, Amazon DocumentDB"),
            _svc("Amazon ElastiCache (Redis, Valkey) and Amazon Aurora"),
        )
    )
    assert names == [
        "Amazon RDS (MySQL/PostgreSQL)",
        "Amazon DynamoDB",
        "Amazon Neptune",
        "Amazon DocumentDB",
        "Amazon Aurora",
    ]


def test_revision_hint_shows_the_full_bracketed_name(monkeypatch):
    current = _design(_svc("Amazon RDS (MySQL, PostgreSQL)"))
    review = CriticReview(approved=False, score=60, required_changes=["Add RDS backups."])
    prompts = _script_revisions(monkeypatch, current, current)
    state = create_initial_state("Design an e-commerce platform.")
    state.update(requirements=make_requirements(), architecture=current, critic_review=review,
                 critic_history=[review], revision_count=0)

    revision_agent.run(state)

    assert "purpose or justification of 'Amazon RDS (MySQL, PostgreSQL)'" in prompts[1]


# ---------------------------------------------------------------------------
# DocumentDB and Neptune
# ---------------------------------------------------------------------------


def test_documentdb_is_identified_as_a_database():
    assert databases_without_backups(_design(_svc("Amazon DocumentDB"))) == ["Amazon DocumentDB"]


def test_documentdb_without_backups_is_a_high_finding():
    (issue,) = _backup_issues(_design(_svc("Amazon DocumentDB", "Product documents", "MongoDB-compatible")))
    assert issue.severity == Severity.HIGH
    assert issue.message == "No backup strategy described for: Amazon DocumentDB."


def test_documentdb_with_automated_backups_passes():
    assert _backup_issues(_design(_svc("Amazon DocumentDB", "Product documents", "Automated backups, 7-day retention"))) == []


def test_documentdb_with_snapshots_passes():
    assert _backup_issues(_design(_svc("Amazon DocumentDB", "Product documents", "Daily cluster snapshots"))) == []


def test_neptune_is_identified_as_a_database():
    assert databases_without_backups(_design(_svc("Amazon Neptune"))) == ["Amazon Neptune"]


def test_neptune_without_backups_is_a_high_finding():
    (issue,) = _backup_issues(_design(_svc("Amazon Neptune", "Recommendation graph", "Managed graph store")))
    assert issue.severity == Severity.HIGH
    assert issue.message == "No backup strategy described for: Amazon Neptune."


def test_neptune_with_automated_backups_passes():
    assert _backup_issues(_design(_svc("Amazon Neptune", "Recommendation graph", "Automated backups enabled"))) == []


def test_neptune_with_snapshots_passes():
    assert _backup_issues(_design(_svc("Amazon Neptune", "Recommendation graph", "Manual snapshots before releases"))) == []

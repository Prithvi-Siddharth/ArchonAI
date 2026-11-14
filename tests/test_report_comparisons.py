"""The report claim checker keeps comparisons with an alternative that wasn't chosen.

"Fargate over EC2: ..." names EC2 only as the rejected alternative; it is not
a claim that the design contains EC2. Only *services* inside the alternative
phrase are exempt: the sentence's subject and every capability are still
checked. Deterministic -- no LLM.
"""

from __future__ import annotations

import pytest

from agents.report import _enforce_verified_claims, _unsupported
from models.schemas import AWSService, CriticReview
from tools.architecture_facts import present_features

from .conftest import make_architecture, make_cost_analysis, make_final_report

# make_architecture(): ALB, ECS, Aurora (multi-AZ, backups, KMS), ElastiCache -- no EC2, Lambda or DynamoDB.
PRESENT = present_features(make_architecture())
FARGATE_OVER_EC2 = "Fargate over EC2: higher per-unit compute cost for zero server management and faster spike scaling"
DYNAMODB = AWSService(
    name="Amazon DynamoDB", category="Database", purpose="Catalog reads", justification="Point-in-time recovery on"
)


def _check(trade_offs: list[str], architecture=None, **prose):
    report = make_final_report().model_copy(update={"trade_offs": trade_offs, **prose})
    review = CriticReview(approved=False, score=70)
    changed = _enforce_verified_claims(report, architecture or make_architecture(), make_cost_analysis(), review)
    return report, changed


# ---------------------------------------------------------------------------
# Comparison alternatives are not claims
# ---------------------------------------------------------------------------


def test_fargate_over_ec2_is_kept_when_fargate_exists():  # 1
    assert _unsupported(FARGATE_OVER_EC2, PRESENT) == []
    report, changed = _check([FARGATE_OVER_EC2])
    assert report.trade_offs == [FARGATE_OVER_EC2]
    assert "trade_offs" not in changed


def test_dynamodb_instead_of_aurora_is_kept_when_dynamodb_exists():  # 2
    design = make_architecture(services=[*make_architecture().services, DYNAMODB])
    statement = "DynamoDB instead of Aurora for catalog reads, trading joins for scale"

    report, _ = _check([statement], design)
    assert report.trade_offs == [statement]


def test_lambda_over_ec2_is_removed_when_lambda_is_absent():  # 3
    statement = "Lambda over EC2: lower idle cost for bursty jobs"

    assert _unsupported(statement, PRESENT) == ["AWS Lambda"]  # the subject is still checked; EC2 is exempt
    report, changed = _check([statement, FARGATE_OVER_EC2])
    assert report.trade_offs == [FARGATE_OVER_EC2]
    assert "trade_offs" in changed


def test_multi_az_over_single_az_is_still_checked_for_multi_az():  # 4
    statement = "Multi-AZ over single-AZ: higher cost for availability"
    assert _unsupported(statement, PRESENT) == []  # the design is multi-AZ

    single_az = make_architecture(
        summary="A load-balanced, auto-scaling architecture with a caching layer.",
        services=[
            s.model_copy(update={"justification": "Relational, automated backups, encrypted via KMS"})
            if s.name == "Amazon Aurora"
            else s.model_copy(update={"justification": "Managed service"})
            for s in make_architecture().services
        ],
        data_flow=[],
    )
    assert "multi-AZ deployment" not in present_features(single_az)
    assert _unsupported(statement, present_features(single_az)) == ["multi-AZ deployment"]


def test_capabilities_inside_the_alternative_are_still_checked():  # 5
    statement = "Aurora spread over a secondary region for disaster recovery"
    # "over" introduces the phrase, but cross-region DR is a capability, never exempt.
    assert _unsupported(statement, PRESENT) == ["cross-region disaster recovery"]
    report, changed = _check([statement])
    assert report.trade_offs == []
    assert "trade_offs" in changed


@pytest.mark.parametrize(
    "statement",
    [
        "Fargate compared with EC2, lower operational overhead",  # 6
        "Fargate compared to EC2: no instance patching",
        "Fargate vs. EC2: less to manage",  # 7
        "Fargate vs EC2: less to manage",
        "Fargate versus EC2; higher unit cost",
        "Fargate rather than EC2 for spiky load",
        "Fargate instead of EC2 to avoid server management",
    ],
)
def test_every_comparison_expression_exempts_the_alternative(statement):
    assert _unsupported(statement, PRESENT) == []


def test_vs_with_a_period_does_not_split_a_prose_sentence():  # 7, in prose fields
    report, changed = _check([], scalability_strategy="Fargate vs. EC2 keeps operations simple. ECS auto scaling.")
    assert report.scalability_strategy == "Fargate vs. EC2 keeps operations simple. ECS auto scaling."
    assert "scalability_strategy" not in changed


# ---------------------------------------------------------------------------
# The exemption stays narrow
# ---------------------------------------------------------------------------


def test_a_service_named_outside_the_comparison_is_still_checked():
    # EC2 is the subject here, not the alternative.
    assert _unsupported("EC2 over Fargate for steady baseline load", PRESENT) == ["Amazon EC2"]
    # EC2 named again after the alternative phrase ends.
    assert _unsupported("Fargate over EC2; EC2 Spot runs batch jobs", PRESENT) == ["Amazon EC2"]


def test_comparison_words_are_not_hedges():
    # The whole sentence is not exempt: the absent subject is still removed.
    report, _ = _check([], architecture_overview="Lambda over EC2 handles payment bursts.")
    assert "Lambda" not in report.architecture_overview


def test_fargate_over_ec2_replay_from_job_21c17890():
    # The cost agent's trade-off that the checker removed in job 21c17890 (absent_features=Amazon EC2).
    report, changed = _check([FARGATE_OVER_EC2, "Multi-AZ redundancy adds cost for HA."])
    assert report.trade_offs == [FARGATE_OVER_EC2, "Multi-AZ redundancy adds cost for HA."]
    assert changed == []

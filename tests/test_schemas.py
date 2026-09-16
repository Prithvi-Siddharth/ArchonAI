"""Tests for the Pydantic schemas in models/schemas.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.schemas import (
    Architecture,
    AWSService,
    CriticIssue,
    CriticReview,
    Requirements,
    Severity,
    TrafficPattern,
    ValidationResult,
)


def test_requirements_requires_core_fields():
    with pytest.raises(ValidationError):
        Requirements()


def test_requirements_defaults_apply_when_not_specified():
    req = Requirements(
        application_type="internal admin tool",
        expected_users="200 employees",
        concurrent_users="50",
        traffic_characteristics="steady, business-hours only",
        latency_requirements="under 1 second",
        availability_requirements="99% during business hours",
        scalability_requirements="minimal",
        storage_requirements="small amounts of structured data",
        database_requirements="simple CRUD",
        security_requirements="internal-only access",
    )
    assert req.traffic_pattern == TrafficPattern.STEADY
    assert req.compliance_requirements == "None specified"
    assert req.geographic_requirements == "Not specified"
    assert req.budget_constraints == "Not specified"


def test_architecture_defaults_version_and_change_log():
    arch = Architecture(summary="A minimal architecture.", services=[], data_flow=[])
    assert arch.version == 1
    assert arch.change_log == []


def test_aws_service_requires_justification():
    with pytest.raises(ValidationError):
        AWSService(name="Amazon S3", category="Storage", purpose="store static assets")


def test_critic_review_score_must_be_within_bounds():
    with pytest.raises(ValidationError):
        CriticReview(approved=True, score=150)
    with pytest.raises(ValidationError):
        CriticReview(approved=True, score=-1)

    review = CriticReview(approved=True, score=100)
    assert review.score == 100


def test_critic_review_accepts_nested_issue_dicts():
    review = CriticReview(
        approved=False,
        score=40,
        issues=[{"issue": "No backups configured", "severity": "high", "category": "reliability"}],
    )
    assert isinstance(review.issues[0], CriticIssue)
    assert review.issues[0].severity == Severity.HIGH


def test_critic_review_defaults_to_empty_lists():
    review = CriticReview(approved=True, score=95)
    assert review.issues == []
    assert review.required_changes == []
    assert review.strengths == []


def test_validation_result_defaults_to_empty_issue_list():
    result = ValidationResult(passed=True)
    assert result.issues == []


def test_validation_result_requires_passed_field():
    with pytest.raises(ValidationError):
        ValidationResult()

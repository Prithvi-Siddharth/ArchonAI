"""Tests for the three ArchonAI tools: AWS service search, the deterministic
architecture validator, and the rule-based cost estimator. None of these
require an LLM or network access.
"""

from __future__ import annotations

from models.schemas import AWSService, DataFlowStep
from tools.architecture_validator import validate_architecture
from tools.aws_service_search import (
    get_service_by_name,
    list_categories,
    search_aws_services,
    search_aws_services_tool,
)
from tools.cost_estimator import estimate_cost

from .conftest import make_architecture, make_requirements

# --- AWS Service Search -----------------------------------------------------


def test_search_aws_services_finds_database_services():
    results = search_aws_services("database")
    names = {r["name"] for r in results}
    assert names & {"Amazon RDS", "Amazon Aurora", "Amazon DynamoDB"}


def test_search_aws_services_empty_query_returns_everything():
    assert len(search_aws_services("")) == len(search_aws_services(""))
    assert len(search_aws_services("")) > 20


def test_search_aws_services_no_match_returns_empty_list():
    assert search_aws_services("this-service-does-not-exist") == []


def test_search_aws_services_is_case_insensitive():
    assert search_aws_services("DATABASE") == search_aws_services("database")


def test_get_service_by_name_is_case_insensitive():
    service = get_service_by_name("amazon s3")
    assert service is not None
    assert service["name"] == "Amazon S3"


def test_get_service_by_name_returns_none_for_unknown_service():
    assert get_service_by_name("Not A Real AWS Service") is None


def test_list_categories_includes_core_categories():
    categories = list_categories()
    for expected in ("Compute", "Database", "Security", "Networking"):
        assert expected in categories


def test_search_aws_services_tool_returns_matching_services_as_json():
    output = search_aws_services_tool.invoke({"query": "compute"})
    assert any(name in output for name in ("Amazon ECS", "Amazon EC2", "AWS Lambda"))


def test_search_aws_services_tool_reports_no_match_clearly():
    output = search_aws_services_tool.invoke({"query": "this-service-does-not-exist"})
    assert "No AWS services found" in output


# --- Architecture Validator ---------------------------------------------------


def test_validate_architecture_passes_for_well_formed_architecture():
    result = validate_architecture(make_architecture(), make_requirements())
    assert result.passed is True
    assert result.issues == []


def test_validate_architecture_flags_missing_multi_az_when_ha_required():
    # Deliberately override every text-bearing field so no leftover language
    # from the "well-formed" fixture (e.g. its default data_flow) can
    # accidentally satisfy the rule being tested here.
    architecture = make_architecture(
        summary="A single-instance deployment with no redundancy mentioned.",
        services=[AWSService(name="Amazon EC2", category="Compute", purpose="run app", justification="single instance")],
        data_flow=[DataFlowStep(step=1, source="User", destination="EC2", description="direct request to the instance")],
    )
    requirements = make_requirements(availability_requirements="99.99%, high availability required")
    result = validate_architecture(architecture, requirements)
    rules = {issue.rule for issue in result.issues}
    assert "high_availability_single_az" in rules


def test_validate_architecture_flags_database_without_backups():
    architecture = make_architecture(
        summary="A relational data store for orders with no recovery strategy described.",
        services=[AWSService(name="Amazon RDS", category="Database", purpose="store data", justification="simple relational store")],
        data_flow=[DataFlowStep(step=1, source="User", destination="RDS", description="direct access")],
    )
    result = validate_architecture(architecture, make_requirements())
    rules = {issue.rule for issue in result.issues}
    assert "database_without_backups" in rules


def test_validate_architecture_flags_public_database_exposure():
    architecture = make_architecture(
        summary="Database is publicly accessible directly from the internet for simplicity.",
        services=[
            AWSService(
                name="Amazon RDS",
                category="Database",
                purpose="store data",
                justification="simple relational store, publicly accessible",
            )
        ],
    )
    result = validate_architecture(architecture, make_requirements())
    rules = {issue.rule for issue in result.issues}
    assert "public_database_exposure" in rules


def test_validate_architecture_flags_sensitive_workload_without_security_controls():
    architecture = make_architecture(
        summary="Basic architecture with no explicit security controls described.",
        services=[AWSService(name="Amazon EC2", category="Compute", purpose="run app", justification="runs the payment service")],
    )
    requirements = make_requirements(security_requirements="handles credit card payments")
    result = validate_architecture(architecture, requirements)
    rules = {issue.rule for issue in result.issues}
    assert "sensitive_workload_missing_controls" in rules


# --- Cost Estimator ------------------------------------------------------------


def test_estimate_cost_returns_a_sane_positive_range():
    estimate = estimate_cost(make_architecture(), make_requirements())
    assert estimate.monthly_low > 0
    assert estimate.monthly_high >= estimate.monthly_low
    assert len(estimate.major_cost_drivers) > 0
    assert len(estimate.assumptions) > 0


def test_estimate_cost_scales_up_with_higher_concurrency():
    architecture = make_architecture()
    low_traffic = estimate_cost(architecture, make_requirements(concurrent_users="500"))
    high_traffic = estimate_cost(architecture, make_requirements(concurrent_users="500,000"))
    assert high_traffic.monthly_high > low_traffic.monthly_high


def test_estimate_cost_breakdown_only_covers_categories_present():
    architecture = make_architecture()
    estimate = estimate_cost(architecture, make_requirements())
    categories_present = {service.category for service in architecture.services}
    assert set(estimate.category_breakdown.keys()) == categories_present

"""Shared pytest fixtures and factories for ArchonAI tests.

These factories build minimal-but-valid Pydantic model instances so tests
never need a real GROQ_API_KEY or network access. The default architecture
produced by `make_architecture()` is deliberately written to satisfy every
rule in tools/architecture_validator.py -- see test_tools.py for the
negative cases that deliberately violate individual rules.
"""

from __future__ import annotations

import os

import dotenv

# Tests must never ship logs to real CloudWatch, even if a developer's .env
# sets CLOUDWATCH_ENABLED=true. The app calls load_dotenv(override=True) at
# import time, which would overwrite a value set here -- so for the test run,
# make .env loading non-overriding. This conftest is imported before any app
# module, so their `from dotenv import load_dotenv` picks up the wrapper.
os.environ["CLOUDWATCH_ENABLED"] = "false"
os.environ["CLOUDWATCH_METRICS_ENABLED"] = "false"
# Likewise the revision output mode: the existing revision tests script full
# architectures, so the suite pins "full" (the rollback mode) regardless of
# .env; tests/test_revision_delta_mode.py sets or unsets it per test to cover
# the "delta" default.
os.environ["REVISION_OUTPUT_MODE"] = "full"
_real_load_dotenv = dotenv.load_dotenv


def _load_dotenv_without_override(*args, **kwargs):
    kwargs["override"] = False
    return _real_load_dotenv(*args, **kwargs)


dotenv.load_dotenv = _load_dotenv_without_override

from models.schemas import (  # noqa: E402
    AnalysisResult,
    Architecture,
    ArchitecturePlan,
    AWSService,
    CostAnalysis,
    CriticReview,
    DataFlowStep,
    FinalReport,
    Requirements,
    TrafficPattern,
)


def make_requirements(**overrides) -> Requirements:
    defaults = dict(
        application_type="e-commerce platform",
        expected_users="2 million registered users",
        concurrent_users="500,000",
        traffic_pattern=TrafficPattern.SPIKY,
        traffic_characteristics="Large spikes during sales events with heavy read traffic.",
        latency_requirements="Sub-200ms API responses",
        availability_requirements="99.99% uptime, high availability required",
        scalability_requirements="Must scale 10x during traffic spikes",
        storage_requirements="Product images and user-generated content",
        database_requirements="High-throughput reads, strongly consistent writes for orders",
        security_requirements="PCI-DSS-aligned payment processing",
        compliance_requirements="PCI-DSS",
        geographic_requirements="North America and Europe",
        budget_constraints="Not specified",
    )
    defaults.update(overrides)
    return Requirements(**defaults)


def make_architecture_plan(**overrides) -> ArchitecturePlan:
    defaults = dict(
        frontend="CDN-backed web and mobile clients.",
        networking="Multi-AZ VPC with public/private subnet segmentation.",
        compute="Horizontally scalable, stateless containers behind a load balancer.",
        database="Relational store for orders, cache for catalog reads.",
        caching="Redis-based caching in front of read-heavy endpoints.",
        storage="Object storage for media and static assets.",
        messaging="Asynchronous queue for order processing.",
        security="Least-privilege IAM, encryption at rest and in transit.",
        observability="Centralized metrics, logs, and tracing.",
        reliability="Multi-AZ deployment with automated backups.",
        scalability="Auto scaling tied to traffic-driven metrics.",
        cost="Right-sized managed services with reserved capacity for baseline load.",
    )
    defaults.update(overrides)
    return ArchitecturePlan(**defaults)


def make_architecture(**overrides) -> Architecture:
    """A well-formed architecture that satisfies every deterministic
    validator rule: load balancing, multi-AZ, auto scaling, security
    controls, backups, private database isolation, and caching."""
    defaults = dict(
        summary=(
            "A load-balanced, auto-scaling, multi-AZ architecture with a caching "
            "layer and defense-in-depth security controls."
        ),
        services=[
            AWSService(
                name="Application Load Balancer",
                category="Networking",
                purpose="Distribute traffic across compute targets",
                justification="Needed for high availability, protected by AWS WAF",
            ),
            AWSService(
                name="Amazon ECS",
                category="Compute",
                purpose="Run application services",
                justification=(
                    "Container orchestration with auto scaling across multiple AZs, "
                    "using IAM least-privilege roles"
                ),
            ),
            AWSService(
                name="Amazon Aurora",
                category="Database",
                purpose="Store transactional order data",
                justification=(
                    "Relational, multi-AZ, with automated backups, encrypted at rest via "
                    "KMS, isolated in a private subnet, not publicly accessible"
                ),
            ),
            AWSService(
                name="Amazon ElastiCache",
                category="Caching",
                purpose="Cache catalog reads",
                justification="Redis cache to reduce database load for high read traffic",
            ),
        ],
        data_flow=[
            DataFlowStep(step=1, source="User", destination="ALB", description="User request hits the load balancer"),
            DataFlowStep(
                step=2,
                source="ALB",
                destination="ECS",
                description="Load balancer routes to ECS tasks, auto scaling across multiple AZs",
            ),
        ],
        version=1,
        change_log=[],
    )
    defaults.update(overrides)
    return Architecture(**defaults)


def make_analysis(domain: str = "Compute") -> AnalysisResult:
    return AnalysisResult(
        domain=domain,
        recommendations=[f"{domain} recommendation"],
        reasoning=f"{domain} reasoning tied to the stated requirements.",
        risks=[],
    )


def make_cost_analysis() -> CostAnalysis:
    return CostAnalysis(
        estimated_monthly_range="$1,000 - $2,000 per month (educational estimate)",
        major_cost_drivers=["Compute", "Database"],
        relative_cost_breakdown={"Compute": "high", "Database": "medium"},
        optimizations=["Use reserved instances for baseline compute load."],
        trade_offs=["Higher availability increases cost relative to a single-AZ design."],
    )


def make_cost_insights():
    """What the Cost Agent's LLM returns (the qualitative part of make_cost_analysis())."""
    from models.schemas import CostInsights

    cost = make_cost_analysis()
    return CostInsights(
        relative_cost_breakdown=cost.relative_cost_breakdown, optimizations=cost.optimizations, trade_offs=cost.trade_offs
    )


def make_critic_review(approved: bool, score: int | None = None) -> CriticReview:
    if score is None:
        score = 92 if approved else 45
    return CriticReview(
        approved=approved,
        score=score,
        issues=(
            []
            if approved
            else [{"issue": "Missing multi-AZ deployment", "severity": "high", "category": "reliability"}]
        ),
        required_changes=[] if approved else ["Add multi-AZ deployment for the compute and database layers."],
        strengths=["Good use of managed services."],
    )


def make_final_report() -> FinalReport:
    return FinalReport(
        executive_summary="Executive summary of the recommended architecture.",
        requirements_summary="Summary of the stated requirements.",
        architecture_overview="Overview of how the architecture fits together.",
        aws_services_summary="Summary of the AWS services chosen and why.",
        data_flow_summary="Summary of the end-to-end data flow.",
        scalability_strategy="How the system scales under load.",
        high_availability_strategy="How the system stays available during failures.",
        security_summary="How the system protects data and access.",
        reliability_summary="Fault tolerance and disaster recovery approach.",
        observability_summary="How the system is monitored and debugged.",
        cost_summary="Cost posture referencing the estimate provided.",
        bottlenecks=["Potential bottleneck in the primary database under extreme write load."],
        trade_offs=["Higher cost in exchange for multi-AZ availability."],
        critic_findings_summary="Summary of what the critic found and how it was resolved.",
        final_recommendations=["Proceed to a proof-of-concept deployment in a staging account."],
    )


def make_report_synthesis():
    """What the Final Report's LLM returns (the synthesized fields of make_final_report())."""
    from models.schemas import ReportSynthesis

    report = make_final_report()
    return ReportSynthesis(**{name: getattr(report, name) for name in ReportSynthesis.model_fields})

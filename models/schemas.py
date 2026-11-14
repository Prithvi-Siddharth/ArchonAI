"""Pydantic data models shared across all ArchonAI agents.

These models are the structured-output contracts that keep the LangGraph
workflow type-safe: every agent reads and writes these shapes instead of
passing raw strings between nodes.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema


class TrafficPattern(str, Enum):
    STEADY = "steady"
    SPIKY = "spiky"
    SEASONAL = "seasonal"
    UNPREDICTABLE = "unpredictable"


class Requirements(BaseModel):
    """Structured requirements extracted from the user's natural-language request."""

    application_type: str = Field(
        description="The kind of system being built, e.g. 'e-commerce platform', 'video streaming platform'."
    )
    expected_users: str = Field(
        description="Total expected user base, e.g. '2 million registered users'."
    )
    concurrent_users: str = Field(
        description="Peak concurrent users the system must support, e.g. '500,000'."
    )
    traffic_pattern: TrafficPattern = Field(
        default=TrafficPattern.STEADY,
        description="The general shape of expected traffic over time.",
    )
    traffic_characteristics: str = Field(
        description="Narrative description of traffic behavior, spikes, read/write ratio, etc."
    )
    latency_requirements: str = Field(
        description="Latency expectations, e.g. 'sub-200ms API responses globally'."
    )
    availability_requirements: str = Field(
        description="Uptime/availability target, e.g. '99.99% uptime'."
    )
    scalability_requirements: str = Field(
        description="How the system needs to scale, e.g. 'must absorb 10x traffic spikes during sales events'."
    )
    storage_requirements: str = Field(
        description="Storage needs, e.g. 'product images, videos, user-generated content'."
    )
    database_requirements: str = Field(
        description="Data model and access-pattern needs, e.g. 'strong consistency for orders, high-throughput catalog reads'."
    )
    security_requirements: str = Field(
        description="Security needs, e.g. 'PCI-DSS-aligned payment handling, encrypted PII'."
    )
    compliance_requirements: str = Field(
        default="None specified",
        description="Regulatory/compliance needs, e.g. 'PCI-DSS', 'HIPAA', 'GDPR'.",
    )
    geographic_requirements: str = Field(
        default="Not specified",
        description="Geographic distribution of users, e.g. 'North America and Europe'.",
    )
    budget_constraints: str = Field(
        default="Not specified",
        description="Any stated budget constraints or cost sensitivity.",
    )
    # Provenance: what the user actually asked for vs what the analyst
    # assumed. Downstream, only explicit requirements (or concrete technical
    # risk) may justify a critical, approval-blocking issue. Defaults keep
    # older stored results and callers valid.
    explicit_requirements: list[str] = Field(
        default_factory=list,
        description="Requirements the user actually stated, closely paraphrased. At most 6, each at most 12 words.",
    )
    inferred_assumptions: list[str] = Field(
        default_factory=list,
        description=(
            "Assumptions inferred rather than stated by the user (e.g. an uptime target "
            "or multi-region redundancy). At most 5, each at most 12 words."
        ),
    )


class ArchitecturePlan(BaseModel):
    """High-level plan of concerns the architecture must address, before service selection."""

    frontend: str = Field(description="Frontend/delivery considerations.")
    networking: str = Field(description="Networking and traffic-routing considerations.")
    compute: str = Field(description="Compute model considerations.")
    database: str = Field(description="Data storage and access considerations.")
    caching: str = Field(description="Caching strategy considerations.")
    storage: str = Field(description="Object/blob storage considerations.")
    messaging: str = Field(description="Async messaging/eventing considerations.")
    security: str = Field(description="Security posture considerations.")
    observability: str = Field(description="Monitoring, logging, and tracing considerations.")
    reliability: str = Field(description="Fault tolerance and HA considerations.")
    scalability: str = Field(description="Scaling strategy considerations.")
    cost: str = Field(description="Cost-shape considerations.")


class AWSService(BaseModel):
    """A single AWS service selected for the architecture."""

    name: str = Field(description="AWS service name, e.g. 'Amazon ECS'.")
    category: str = Field(description="Category, e.g. 'Compute', 'Database', 'Networking'.")
    purpose: str = Field(description="What this service does in this specific architecture.")
    justification: str = Field(description="Why this service was chosen over alternatives.")


class DataFlowStep(BaseModel):
    """One hop in the end-to-end request/data flow."""

    step: int = Field(description="Sequential order of this step.")
    source: str = Field(description="Origin component of this hop.")
    destination: str = Field(description="Destination component of this hop.")
    description: str = Field(description="What happens on this hop.")


class Architecture(BaseModel):
    """A complete proposed (or revised) cloud architecture."""

    summary: str = Field(description="One-paragraph overview of the architecture.")
    services: list[AWSService] = Field(description="AWS services selected, with justification.")
    data_flow: list[DataFlowStep] = Field(description="Ordered end-to-end data flow.")
    version: int = Field(default=1, description="Revision number, starting at 1.")
    change_log: list[str] = Field(
        default_factory=list,
        description="Human-readable list of what changed in this revision and why.",
    )


class AnalysisResult(BaseModel):
    """Generic structured output for a specialist analysis agent (compute, db, network, etc.)."""

    domain: str = Field(description="The analysis domain, e.g. 'Compute', 'Database'.")
    recommendations: list[str] = Field(description="Concrete recommendations.")
    reasoning: str = Field(description="Narrative reasoning tying recommendations to requirements.")
    risks: list[str] = Field(default_factory=list, description="Risks or open concerns in this domain.")


class CostAnalysis(BaseModel):
    """High-level, explicitly-labeled-as-estimate cost analysis."""

    estimated_monthly_range: str = Field(
        description="Rough estimated monthly cost range, e.g. '$8,000 - $15,000 (educational estimate)'."
    )
    major_cost_drivers: list[str] = Field(description="The components driving the most cost.")
    relative_cost_breakdown: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of component -> relative cost weight, e.g. {'compute': 'high'}.",
    )
    optimizations: list[str] = Field(description="Possible cost optimizations.")
    trade_offs: list[str] = Field(description="Cost-vs-capability trade-offs made.")
    disclaimer: str = Field(
        default=(
            "This is an educational, order-of-magnitude estimate only. It is not an AWS "
            "quote and does not reflect real-time AWS pricing."
        )
    )


class CostInsights(BaseModel):
    """What the Cost Agent's LLM writes: only the qualitative analysis.

    The headline range and cost drivers come from the deterministic cost
    estimator, so the model is never asked to restate them. The agent
    combines both into the public CostAnalysis.
    """

    relative_cost_breakdown: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of component -> relative cost weight, e.g. {'compute': 'high'}.",
    )
    optimizations: list[str] = Field(description="Possible cost optimizations.")
    trade_offs: list[str] = Field(description="Cost-vs-capability trade-offs made.")


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CriticIssue(BaseModel):
    issue: str = Field(description="Description of the problem found.")
    severity: Severity = Field(description="How serious this issue is.")
    category: str = Field(description="Category, e.g. 'security', 'scalability', 'cost'.")


class CriticReview(BaseModel):
    """Structured verdict from the Architecture Critic."""

    approved: bool = Field(description="Whether the architecture is approved as-is.")
    score: int = Field(ge=0, le=100, description="Overall quality score out of 100.")
    issues: list[CriticIssue] = Field(default_factory=list, description="Issues found, if any.")
    required_changes: list[str] = Field(
        default_factory=list, description="Concrete changes required for approval."
    )
    strengths: list[str] = Field(default_factory=list, description="What the architecture does well.")


class ValidationIssue(BaseModel):
    """A deterministic issue found by the rule-based Architecture Validator tool."""

    rule: str = Field(description="Name of the validation rule that triggered.")
    message: str = Field(description="Human-readable description of the issue.")
    severity: Severity = Field(description="How serious this issue is.")


class ValidationResult(BaseModel):
    """Output of the deterministic Architecture Validator tool."""

    passed: bool = Field(description="True if no issues were found.")
    issues: list[ValidationIssue] = Field(default_factory=list)


class ReportSynthesis(BaseModel):
    """What the Final Report's LLM writes: only the fields that need synthesis.

    requirements_summary, aws_services_summary, data_flow_summary,
    cost_summary, critic_findings_summary and open_recommendations restate
    data the workflow already holds, so the report agent builds them in code
    and assembles the public FinalReport.
    """

    executive_summary: str
    architecture_overview: str
    scalability_strategy: str
    high_availability_strategy: str
    security_summary: str
    reliability_summary: str
    observability_summary: str
    bottlenecks: list[str]
    trade_offs: list[str]
    final_recommendations: list[str]


class FinalReport(BaseModel):
    """The final, human-readable architecture recommendation report."""

    executive_summary: str
    requirements_summary: str
    architecture_overview: str
    aws_services_summary: str
    data_flow_summary: str
    scalability_strategy: str
    high_availability_strategy: str
    security_summary: str
    reliability_summary: str
    observability_summary: str
    cost_summary: str
    bottlenecks: list[str]
    trade_offs: list[str]
    critic_findings_summary: str
    final_recommendations: list[str]
    # Filled deterministically by the report agent, never by the LLM (hidden
    # from the structured-output schema): critic requests and proposed
    # changes that are NOT in the final architecture. Defaults to empty so
    # stored results from before this field still load.
    open_recommendations: SkipJsonSchema[list[str]] = Field(
        default_factory=list,
        description="Requested or proposed changes that the final architecture does not contain.",
    )

"""Networking Agent.

Specialist analysis node. Evaluates the network topology of the proposed
architecture: VPC design, subnet segmentation, AZ distribution, load
balancing, CDN/API edge, and ingress/egress isolation.
"""

from __future__ import annotations

from agents import llm as llm_module
from agents.formatting import compact_architecture
from graph.state import ArchonState, make_trace_entry
from models.schemas import AnalysisResult, Architecture, Requirements

PROMPT_TEMPLATE = """You are a cloud networking specialist reviewing a proposed AWS architecture.

Requirements:
{requirements}

Proposed Architecture:
{architecture}

Analyze the networking layer of this architecture. Specifically address:
- VPC design and public/private subnet segmentation
- Distribution across Availability Zones
- Load balancing strategy
- Use of CloudFront and/or API Gateway at the edge, if applicable
- Ingress/egress control and network isolation between tiers

Return concrete recommendations, your reasoning, and any risks. Be concise: keep reasoning to 2-3 sentences, and limit recommendations/risks to short bullet phrases, not paragraphs.
"""


def run(state: ArchonState) -> dict:
    """Analyze networking for the current state['architecture']."""
    requirements: Requirements = state["requirements"]
    architecture: Architecture = state["architecture"]

    llm = llm_module.get_llm(temperature=0.2)
    prompt = PROMPT_TEMPLATE.format(
        requirements=requirements.model_dump_json(),
        architecture=compact_architecture(architecture),
    )
    analysis = llm_module.invoke_structured(llm, AnalysisResult, prompt)
    analysis.domain = "Networking"

    entry = make_trace_entry(
        node="Networking Agent",
        action="Analyzed VPC design, AZ distribution, load balancing, and network isolation.",
        output_summary="; ".join(analysis.recommendations[:2]),
    )
    return {"networking_analysis": analysis, "execution_trace": [entry]}

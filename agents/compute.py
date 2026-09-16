"""Compute Agent.

Specialist analysis node. Evaluates the compute portion of the proposed
architecture against the requirements: service choice (ECS vs EKS vs Lambda
vs EC2), scaling strategy, statelessness, and bottlenecks.
"""

from __future__ import annotations

from agents import llm as llm_module
from agents.formatting import compact_architecture
from graph.state import ArchonState, make_trace_entry
from models.schemas import AnalysisResult, Architecture, Requirements

PROMPT_TEMPLATE = """You are a cloud compute specialist reviewing a proposed AWS architecture.

Requirements:
{requirements}

Proposed Architecture:
{architecture}

Analyze the compute portion of this architecture. Specifically address:
- Whether ECS, EKS, Lambda, or EC2 (or a mix) is the right choice here, and why
- Horizontal scaling and auto-scaling strategy
- Whether the compute layer is stateless and safe to scale out
- Availability of the compute layer (single instance vs. distributed)
- Likely compute bottlenecks under the stated load

Return concrete recommendations, your reasoning, and any risks. Be concise: keep reasoning to 2-3 sentences, and limit recommendations/risks to short bullet phrases, not paragraphs.
"""


def run(state: ArchonState) -> dict:
    """Analyze compute for the current state['architecture']."""
    requirements: Requirements = state["requirements"]
    architecture: Architecture = state["architecture"]

    llm = llm_module.get_llm(temperature=0.2)
    prompt = PROMPT_TEMPLATE.format(
        requirements=requirements.model_dump_json(),
        architecture=compact_architecture(architecture),
    )
    analysis = llm_module.invoke_structured(llm, AnalysisResult, prompt)
    analysis.domain = "Compute"

    entry = make_trace_entry(
        node="Compute Agent",
        action="Analyzed compute service selection, scaling strategy, and bottlenecks.",
        output_summary="; ".join(analysis.recommendations[:2]),
    )
    return {"compute_analysis": analysis, "execution_trace": [entry]}

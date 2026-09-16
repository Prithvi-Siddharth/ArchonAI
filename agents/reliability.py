"""Reliability Agent.

Specialist analysis node. Evaluates fault tolerance and disaster-recovery
posture: multi-AZ deployment, backups, retries/timeouts/circuit breakers,
and how the architecture behaves under common failure scenarios.
"""

from __future__ import annotations

from agents import llm as llm_module
from agents.formatting import compact_architecture
from graph.state import ArchonState, make_trace_entry
from models.schemas import AnalysisResult, Architecture, Requirements

PROMPT_TEMPLATE = """You are a site-reliability specialist reviewing a proposed AWS architecture.

Requirements:
{requirements}

Proposed Architecture:
{architecture}

Analyze the reliability posture of this architecture. Specifically address:
- High availability and multi-AZ deployment
- Fault tolerance for individual component failures
- Disaster recovery approach and backup strategy
- Use of retries, timeouts, and circuit breakers between services
- What happens under 2-3 concrete failure scenarios (e.g. an AZ outage, a
  database failover, a downstream dependency timing out)

Return concrete recommendations, your reasoning, and any risks. Be concise: keep reasoning to 2-3 sentences, and limit recommendations/risks to short bullet phrases, not paragraphs.
"""


def run(state: ArchonState) -> dict:
    """Analyze reliability for the current state['architecture']."""
    requirements: Requirements = state["requirements"]
    architecture: Architecture = state["architecture"]

    llm = llm_module.get_llm(temperature=0.2)
    prompt = PROMPT_TEMPLATE.format(
        requirements=requirements.model_dump_json(),
        architecture=compact_architecture(architecture),
    )
    analysis = llm_module.invoke_structured(llm, AnalysisResult, prompt)
    analysis.domain = "Reliability"

    entry = make_trace_entry(
        node="Reliability Agent",
        action="Analyzed multi-AZ HA, disaster recovery, and failure-scenario resilience.",
        output_summary="; ".join(analysis.recommendations[:2]),
    )
    return {"reliability_analysis": analysis, "execution_trace": [entry]}

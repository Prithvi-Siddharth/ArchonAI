"""Cost Agent.

Specialist analysis node. Grounds its numbers in the deterministic
rule-based Cost Estimator tool, then uses the LLM only for the qualitative
reasoning (trade-offs, optimizations) layered on top of those numbers. This
keeps the headline figures reproducible while still explaining *why*.
"""

from __future__ import annotations

from agents import llm as llm_module
from agents.formatting import compact_architecture
from graph.state import ArchonState, make_trace_entry
from models.schemas import Architecture, CostAnalysis, Requirements
from tools.cost_estimator import estimate_cost

PROMPT_TEMPLATE = """You are a FinOps specialist reviewing a proposed AWS architecture.

Requirements:
{requirements}

Proposed Architecture:
{architecture}

A deterministic rule-based cost estimator produced the following baseline (treat
these numbers as ground truth -- do not recompute or contradict them):
- Estimated monthly range: ${monthly_low:,} - ${monthly_high:,} (educational estimate only)
- Major cost drivers: {major_drivers}
- Assumptions: {assumptions}

Using this baseline, provide:
- estimated_monthly_range: restate the range above, clearly labeled as an estimate
- major_cost_drivers: the drivers above, described in plain language
- relative_cost_breakdown: a mapping of component -> relative weight (e.g. "high", "medium", "low")
- optimizations: concrete ways to reduce cost without violating the requirements
- trade_offs: cost-vs-capability trade-offs made in this design

Be concise: short phrases per list item, not paragraphs.
"""


def run(state: ArchonState) -> dict:
    """Analyze cost for the current state['architecture'], grounded by a deterministic estimate."""
    requirements: Requirements = state["requirements"]
    architecture: Architecture = state["architecture"]

    estimate = estimate_cost(architecture, requirements)

    llm = llm_module.get_llm(temperature=0.2)
    prompt = PROMPT_TEMPLATE.format(
        requirements=requirements.model_dump_json(),
        architecture=compact_architecture(architecture),
        monthly_low=estimate.monthly_low,
        monthly_high=estimate.monthly_high,
        major_drivers=", ".join(estimate.major_cost_drivers) or "none identified",
        assumptions="; ".join(estimate.assumptions),
    )
    analysis = llm_module.invoke_structured(llm, CostAnalysis, prompt)
    # Keep the headline range and drivers tied to the deterministic tool, not the LLM's paraphrase.
    analysis.estimated_monthly_range = f"${estimate.monthly_low:,} - ${estimate.monthly_high:,} per month (educational estimate)"
    analysis.major_cost_drivers = estimate.major_cost_drivers

    entry = make_trace_entry(
        node="Cost Agent",
        action="Ran the rule-based cost estimator tool and layered trade-off analysis on top.",
        output_summary=analysis.estimated_monthly_range,
    )
    return {"cost_analysis": analysis, "execution_trace": [entry]}

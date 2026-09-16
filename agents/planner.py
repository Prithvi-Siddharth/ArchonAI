"""Architecture Planner agent.

Second node in the graph. Bridges structured requirements to a concrete
architecture by deciding, at a conceptual level, what each architectural
concern (frontend, networking, compute, ...) needs to address -- before any
specific AWS service is chosen.
"""

from __future__ import annotations

from agents import llm as llm_module
from graph.state import ArchonState, make_trace_entry
from models.schemas import ArchitecturePlan, Requirements

PROMPT_TEMPLATE = """You are a senior cloud solutions architect. Given the structured
requirements below, produce an architecture plan that states what each concern
must address. Be concrete and reference the actual numbers/constraints given --
do not restate generic cloud best practices without tying them to these requirements.

Requirements:
{requirements}

Be concise: keep each field to 1-2 sentences. This is a working plan, not a report.
"""


def run(state: ArchonState) -> dict:
    """Produce an ArchitecturePlan from state['requirements']."""
    requirements: Requirements = state["requirements"]

    llm = llm_module.get_llm(temperature=0.2)
    prompt = PROMPT_TEMPLATE.format(requirements=requirements.model_dump_json())
    plan = llm_module.invoke_structured(llm, ArchitecturePlan, prompt)

    entry = make_trace_entry(
        node="Architecture Planner",
        action="Determined architectural concerns to address across 12 dimensions.",
        output_summary=f"Compute plan: {plan.compute[:120]}",
    )
    return {"architecture_plan": plan, "execution_trace": [entry]}

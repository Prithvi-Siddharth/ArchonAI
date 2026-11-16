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

# The plan's only consumer is the Architecture Designer (its service research
# and design prompts), so every field must keep the concrete numbers and
# constraints it needs -- but nothing more. Without a hard limit the model
# wrote ~35 words per field (job 21c17890: 387 words, exactly 750/750
# output tokens, at risk of being cut off and rejected as tool_use_failed).
# At <= 20 words per field a full plan is ~240 words, well inside the cap.
# (Stated in PROMPT_TEMPLATE; a test keeps the two in step.)
PLAN_MAX_WORDS_PER_FIELD = 20

# Unchanged from the shared default: the cap doesn't shorten what the model
# writes (the word limits do), so it is kept as headroom against truncation.
PLANNER_MAX_TOKENS = llm_module.DEFAULT_MAX_TOKENS

PROMPT_TEMPLATE = """You are a senior cloud solutions architect. Given the structured
requirements below, produce an architecture plan that states what each concern
must address. Be concrete and reference the actual numbers/constraints given --
do not restate generic cloud best practices without tying them to these requirements.

Requirements:
{requirements}

Output limits -- these are STRICT limits, not suggestions. A longer response may be cut off and rejected.
- Fill every field: frontend, networking, compute, database, caching, storage, messaging,
  security, observability, reliability, scalability, cost.
- Each field: exactly one sentence, at most 20 words.
- Keep the specifics the design needs: user counts, latency and availability targets,
  traffic shape, data consistency, compliance and security constraints.
- Name the capability needed (e.g. in-memory cache, CDN, message queue); no lists of
  alternatives, no explanations of why best practices matter, no repeated field names.
- If a concern does not apply, say so in a few words instead of inventing a need.
This is a working plan, not a report. Return valid structured output matching the
ArchitecturePlan schema exactly and nothing else.
"""


def run(state: ArchonState) -> dict:
    """Produce an ArchitecturePlan from state['requirements']."""
    requirements: Requirements = state["requirements"]

    llm = llm_module.get_llm(temperature=0.2, max_tokens=PLANNER_MAX_TOKENS)
    prompt = PROMPT_TEMPLATE.format(requirements=requirements.model_dump_json())
    plan = llm_module.invoke_structured(llm, ArchitecturePlan, prompt)

    entry = make_trace_entry(
        node="Architecture Planner",
        action="Determined architectural concerns to address across 12 dimensions.",
        output_summary=f"Compute plan: {plan.compute[:120]}",
    )
    return {"architecture_plan": plan, "execution_trace": [entry]}

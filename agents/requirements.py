"""Requirements Analyzer agent.

First node in the ArchonAI graph. Converts the user's free-form natural
language request into structured requirements that every downstream agent
relies on.
"""

from __future__ import annotations

from agents import llm as llm_module
from graph.state import ArchonState, make_trace_entry
from models.schemas import Requirements

PROMPT_TEMPLATE = """You are a senior cloud solutions architect performing requirements analysis.

Read the user's natural-language software requirement below and extract a complete,
structured set of architectural requirements. Be specific, and reasonably infer
details the user didn't state explicitly (e.g. infer a latency expectation from the
application type), but do not invent precise numbers you have no basis for --
describe those qualitatively instead.

For traffic_pattern, you must pick exactly one of these four literal values --
do not paraphrase or combine them: steady, spiky, seasonal, unpredictable.

User request:
\"\"\"
{user_request}
\"\"\"
"""


def run(state: ArchonState) -> dict:
    """Extract structured Requirements from state['user_request']."""
    user_request = (state.get("user_request") or "").strip()
    if not user_request:
        raise ValueError("user_request must be a non-empty string.")

    llm = llm_module.get_llm(temperature=0.1)
    prompt = PROMPT_TEMPLATE.format(user_request=user_request)
    requirements = llm_module.invoke_structured(llm, Requirements, prompt)

    entry = make_trace_entry(
        node="Requirements Analyzer",
        action="Extracted structured requirements from the user's natural-language request.",
        output_summary=(
            f"Type: {requirements.application_type} | "
            f"Concurrent users: {requirements.concurrent_users} | "
            f"Availability: {requirements.availability_requirements}"
        ),
    )
    return {"requirements": requirements, "execution_trace": [entry]}

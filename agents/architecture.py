"""Architecture Designer agent.

Third node in the graph. Designs the initial AWS architecture from the
requirements and plan produced by the previous two nodes. This is the node
that performs a genuine LLM tool-calling loop: the model searches the AWS
service knowledge base for candidate services before committing to a design,
so service selection is grounded in real service data instead of guesswork.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agents import llm as llm_module
from graph.state import ArchonState, make_trace_entry
from models.schemas import Architecture, ArchitecturePlan, Requirements
from tools.aws_service_search import search_aws_services_tool

MAX_TOOL_ROUNDS = 2

# Hard cap on the accumulated research text embedded in the design prompt.
# The AWS search tool already caps how many services one call can return,
# but the model can still make several calls across MAX_TOOL_ROUNDS -- this
# backstop keeps the design prompt's input-token size predictable regardless
# of how many searches actually happen.
MAX_RESEARCH_CHARS = 3000

SYSTEM_PROMPT = """You are an AWS solutions architect designing a cloud architecture.
You have a tool that searches a curated AWS service knowledge base. Use it to look up
candidate services for the concerns in the architecture plan (for example, search
"compute", "database", "caching", "networking", "security") before proposing a final
design. Do not select every AWS service available -- choose only what this workload
actually needs, and be ready to justify each choice against the requirements.
"""

DESIGN_PROMPT_TEMPLATE = """Using the requirements, architecture plan, and AWS service
research below, design an initial AWS architecture.

Requirements:
{requirements}

Architecture Plan:
{plan}

AWS service research gathered:
{research}

Produce a complete architecture: a concise summary, the list of AWS services selected
(each with a clear purpose and a justification tied to the requirements), and an
ordered end-to-end data flow from the user's request through the system. Only include
services that are actually justified by the requirements -- do not add services just
to look thorough.

Be concise: select at most 8-10 services (fewer for a small/simple system), and keep
each summary/purpose/justification/description field to one short sentence (under 20
words). This is a working design document, not a narrative report.
"""


def _run_tool_calling_research(requirements: Requirements, plan: ArchitecturePlan) -> str:
    """Let the LLM search the AWS knowledge base via real tool calls.

    Returns the accumulated research notes as text, to be fed into the final
    structured-output design call.
    """
    llm_with_tools = llm_module.get_llm(temperature=0.2, max_tokens=512).bind_tools([search_aws_services_tool])
    messages: list = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "Requirements:\n"
                f"{requirements.model_dump_json()}\n\n"
                "Architecture Plan:\n"
                f"{plan.model_dump_json()}\n\n"
                "Search the AWS knowledge base for services relevant to each concern above."
            )
        ),
    ]

    research_notes: list[str] = []
    for _ in range(MAX_TOOL_ROUNDS):
        response: AIMessage = llm_module.invoke_with_retry(lambda: llm_with_tools.invoke(messages))
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break
        for call in tool_calls:
            result = search_aws_services_tool.invoke(call["args"])
            research_notes.append(f"Query '{call['args'].get('query', '')}':\n{result}")
            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))

    combined = "\n\n".join(research_notes) if research_notes else "No tool searches were made."
    if len(combined) > MAX_RESEARCH_CHARS:
        combined = combined[:MAX_RESEARCH_CHARS] + "\n...(truncated)"
    return combined


def run(state: ArchonState) -> dict:
    """Design the initial Architecture from requirements and architecture_plan."""
    requirements: Requirements = state["requirements"]
    plan: ArchitecturePlan = state["architecture_plan"]

    research = _run_tool_calling_research(requirements, plan)

    llm = llm_module.get_llm(temperature=0.3, max_tokens=llm_module.ARCHITECTURE_MAX_TOKENS)
    prompt = DESIGN_PROMPT_TEMPLATE.format(
        requirements=requirements.model_dump_json(),
        plan=plan.model_dump_json(),
        research=research,
    )
    architecture = llm_module.invoke_structured(llm, Architecture, prompt)
    architecture.version = 1

    entry = make_trace_entry(
        node="Architecture Designer",
        action=(
            f"Searched the AWS service knowledge base and designed the initial "
            f"architecture with {len(architecture.services)} services."
        ),
        output_summary=", ".join(s.name for s in architecture.services),
    )
    return {"architecture": architecture, "execution_trace": [entry]}

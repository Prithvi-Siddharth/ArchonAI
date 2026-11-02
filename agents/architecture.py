"""Architecture Designer agent.

Third node in the graph. Designs the initial AWS architecture from the
requirements and plan produced by the previous two nodes. This is the node
that performs a genuine LLM tool-calling loop: the model searches the AWS
service knowledge base for candidate services before committing to a design,
so service selection is grounded in real service data instead of guesswork.
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agents import llm as llm_module
from graph.observability import log_event
from graph.state import ArchonState, make_trace_entry
from models.schemas import Architecture, ArchitecturePlan, Requirements
from tools.aws_service_search import search_aws_services_tool

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 2

RESEARCH_TEMPERATURE = 0.2
# One corrective retry after a tool_use_failed, sampled a little hotter (the
# same +0.25 nudge invoke_structured uses) so it doesn't just repeat the
# same malformed tool call.
RESEARCH_RETRY_TEMPERATURE = 0.45
RESEARCH_MAX_TOKENS = 512

RESEARCH_CORRECTION = (
    "Your previous reply was rejected because it was not a valid tool call. "
    "Call search_aws_services_tool with exactly one string argument named 'query' "
    "(one short keyword per call), or reply without any tool call if you have enough information."
)

# What the design prompt gets as its research section when the search step
# failed: the research is optional, so the design goes ahead without it.
NO_RESEARCH_NOTE = (
    "No research is available: the AWS service search step failed. "
    "Choose well-known AWS services from general knowledge."
)
RESEARCH_STOPPED_NOTE = "(Research stopped early: a later AWS service search failed.)"

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

Hard size limits (the whole response must fit in a small output budget):
- At most 7 services (fewer for a small/simple system). Combine closely related
  services into one entry (e.g. "Amazon CloudFront + AWS WAF").
- At most 6 data_flow steps, covering only the main request path.
- Summary: one sentence, at most 30 words.
- Each purpose/justification/description: one sentence, at most 12 words.

Keep key properties explicit in the text where they apply, using these exact terms:
multi-AZ, auto scaling, load balancer, backups, encryption, private subnet.

This is a working design document, not a narrative report.
"""

# Why the hard limits above: the structured Architecture response is capped at
# ARCHITECTURE_MAX_TOKENS (see agents/llm.py). Without an explicit cap on
# data_flow steps, the model kept adding steps until its output was cut off
# mid-JSON, which Groq rejects as tool_use_failed -- and since every retry
# asks for the same size of output, every retry was cut off too. The terms
# list keeps shorter text from dropping the keywords the deterministic
# validator (tools/architecture_validator.py) looks for.


def _log_research_failure(
    exc: BaseException, round_number: int, retry_succeeded: bool, fallback_used: bool, notes_kept: int
) -> None:
    """Only safe facts (type, HTTP status, error code) -- never the provider's
    message or failed_generation, which echo the model's output."""
    log_event(
        logger,
        "research_call_failed",
        logging.WARNING,
        **llm_module._provider_error_fields(exc),
        error_category="tool_use_failed",
        round=round_number,
        corrective_retry_attempted=True,
        corrective_retry_succeeded=retry_succeeded,
        fallback_used=fallback_used,
        research_notes_kept=notes_kept,
    )


def _corrective_research_retry(
    messages: list, first_exc: BaseException, round_number: int, notes_kept: int
) -> Optional[AIMessage]:
    """Retry a research call that failed with tool_use_failed, exactly once.

    Returns the response, or None if the retry also failed with
    tool_use_failed (the caller then stops researching). Any other error is
    raised unchanged -- only a malformed tool call is recoverable here.
    """
    retry_llm = llm_module.get_llm(
        temperature=RESEARCH_RETRY_TEMPERATURE, max_tokens=RESEARCH_MAX_TOKENS
    ).bind_tools([search_aws_services_tool])
    # The correction is sent with this one call only, not kept in the history.
    retry_messages = [*messages, HumanMessage(content=RESEARCH_CORRECTION)]
    try:
        response: AIMessage = llm_module.invoke_with_retry(lambda: retry_llm.invoke(retry_messages))
    except Exception as retry_exc:
        if not llm_module._is_tool_use_failure(retry_exc):
            raise
        _log_research_failure(first_exc, round_number, retry_succeeded=False, fallback_used=True, notes_kept=notes_kept)
        return None
    _log_research_failure(first_exc, round_number, retry_succeeded=True, fallback_used=False, notes_kept=notes_kept)
    return response


def _run_tool_calling_research(requirements: Requirements, plan: ArchitecturePlan) -> tuple[str, bool]:
    """Let the LLM search the AWS knowledge base via real tool calls.

    Returns (research notes as text, fallback_used). The notes feed the final
    structured-output design call. The research is optional: if a search
    call fails with tool_use_failed (a malformed tool call) and its one
    corrective retry fails the same way, researching stops, the notes
    gathered so far are kept, and fallback_used is True. Any other error
    propagates as before.
    """
    llm_with_tools = llm_module.get_llm(
        temperature=RESEARCH_TEMPERATURE, max_tokens=RESEARCH_MAX_TOKENS
    ).bind_tools([search_aws_services_tool])
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
    fallback_used = False
    for round_number in range(1, MAX_TOOL_ROUNDS + 1):
        try:
            response: AIMessage = llm_module.invoke_with_retry(lambda: llm_with_tools.invoke(messages))
        except Exception as exc:
            if not llm_module._is_tool_use_failure(exc):
                raise
            retried = _corrective_research_retry(messages, exc, round_number, len(research_notes))
            if retried is None:
                fallback_used = True
                break
            response = retried
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break
        for call in tool_calls:
            result = search_aws_services_tool.invoke(call["args"])
            research_notes.append(f"Query '{call['args'].get('query', '')}':\n{result}")
            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))

    if fallback_used and not research_notes:
        return NO_RESEARCH_NOTE, True
    combined = "\n\n".join(research_notes) if research_notes else "No tool searches were made."
    if len(combined) > MAX_RESEARCH_CHARS:
        combined = combined[:MAX_RESEARCH_CHARS] + "\n...(truncated)"
    if fallback_used:
        combined += "\n\n" + RESEARCH_STOPPED_NOTE
    return combined, fallback_used


def run(state: ArchonState) -> dict:
    """Design the initial Architecture from requirements and architecture_plan."""
    requirements: Requirements = state["requirements"]
    plan: ArchitecturePlan = state["architecture_plan"]

    research, research_fallback = _run_tool_calling_research(requirements, plan)

    llm = llm_module.get_llm(temperature=0.3, max_tokens=llm_module.ARCHITECTURE_MAX_TOKENS)
    prompt = DESIGN_PROMPT_TEMPLATE.format(
        requirements=requirements.model_dump_json(),
        plan=plan.model_dump_json(),
        research=research,
    )
    architecture = llm_module.invoke_structured(llm, Architecture, prompt)
    architecture.version = 1

    action = (
        f"Searched the AWS service knowledge base and designed the initial "
        f"architecture with {len(architecture.services)} services."
    )
    if research_fallback:
        action += " The AWS service search failed, so the design used only the research gathered before it."
    entry = make_trace_entry(
        node="Architecture Designer",
        action=action,
        output_summary=", ".join(s.name for s in architecture.services),
    )
    return {"architecture": architecture, "execution_trace": [entry]}

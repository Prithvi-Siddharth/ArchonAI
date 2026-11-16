"""Architecture Planner: concise, complete plans inside the output budget.

Every field gets a strict one-sentence, <= 20-word limit (job 21c17890's
plan was 387 words and used exactly 750/750 output tokens). The schema and
the 750-token cap are unchanged, every field still reaches the Designer,
and failures propagate exactly as before. No live LLM calls.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from agents import architecture as designer
from agents import llm as llm_module
from agents import planner
from graph.state import create_initial_state
from models.schemas import ArchitecturePlan

from .conftest import make_architecture, make_architecture_plan, make_requirements

PLAN_FIELDS = [
    "frontend",
    "networking",
    "compute",
    "database",
    "caching",
    "storage",
    "messaging",
    "security",
    "observability",
    "reliability",
    "scalability",
    "cost",
]


def _run_planner(monkeypatch, result=None):
    calls: dict = {}

    def fake_get_llm(temperature=0.2, max_tokens=llm_module.DEFAULT_MAX_TOKENS):
        calls.update(temperature=temperature, max_tokens=max_tokens)
        return object()

    def fake_invoke_structured(llm, schema, prompt):
        calls.update(schema=schema, prompt=prompt)
        if isinstance(result, BaseException):
            raise result
        return result or make_architecture_plan()

    monkeypatch.setattr(llm_module, "get_llm", fake_get_llm)
    monkeypatch.setattr(llm_module, "invoke_structured", fake_invoke_structured)
    state = create_initial_state("Design an e-commerce platform for 500,000 concurrent users.")
    state["requirements"] = make_requirements()
    return planner.run(state), calls


# ---------------------------------------------------------------------------
# Prompt limits and output cap
# ---------------------------------------------------------------------------


def test_prompt_sets_strict_per_field_limits(monkeypatch):
    _, calls = _run_planner(monkeypatch)
    prompt = calls["prompt"]

    assert "STRICT limits, not suggestions" in prompt
    assert f"exactly one sentence, at most {planner.PLAN_MAX_WORDS_PER_FIELD} words" in prompt
    assert planner.PLAN_MAX_WORDS_PER_FIELD == 20
    assert "no lists of\n  alternatives" in prompt  # the main source of padding in long plans
    assert "1-2 sentences" not in prompt  # the old, looser limit
    # Every schema field is named, so none is dropped to save words.
    assert all(field in prompt for field in PLAN_FIELDS)
    # The requirements are still filled in, with their concrete numbers.
    assert "{requirements}" not in prompt and '"concurrent_users":"500,000"' in prompt
    assert "Keep the specifics the design needs" in prompt


def test_output_cap_is_explicit_and_unchanged(monkeypatch):
    _, calls = _run_planner(monkeypatch)

    assert calls["max_tokens"] == planner.PLANNER_MAX_TOKENS == llm_module.DEFAULT_MAX_TOKENS == 750
    assert calls["temperature"] == 0.2
    assert calls["schema"] is ArchitecturePlan


def test_a_plan_at_the_word_limit_fits_the_cap_with_headroom():
    # Heuristic budget check, fitted to the two real plans we have:
    #   job 21c17890: 387 words -> 750 output tokens; job 9d8d40a3: 186 words -> 466.
    # That line is ~1.41 tokens/word plus ~204 tokens of fixed overhead
    # (tool-call wrapper, field names, any hidden tokens the provider counts).
    tokens_per_word = (750 - 466) / (387 - 186)
    overhead = 466 - tokens_per_word * 186

    def estimate(words: int) -> float:
        return tokens_per_word * words + overhead

    assert round(estimate(387)) == 750  # the fit reproduces the job that hit the cap
    max_words = planner.PLAN_MAX_WORDS_PER_FIELD * len(PLAN_FIELDS)  # 240
    assert estimate(max_words) < planner.PLANNER_MAX_TOKENS * 0.8  # ~542 tokens: >= 20% headroom


# ---------------------------------------------------------------------------
# Output validity, schema and downstream use
# ---------------------------------------------------------------------------


def test_planner_output_is_the_valid_plan_and_trace(monkeypatch):
    plan = make_architecture_plan()
    result, _ = _run_planner(monkeypatch, plan)

    assert result["architecture_plan"] is plan
    (entry,) = result["execution_trace"]
    assert entry["node"] == "Architecture Planner"
    assert entry["output_summary"].startswith("Compute plan: ")


def test_plan_schema_is_unchanged():
    assert list(ArchitecturePlan.model_fields) == PLAN_FIELDS
    tool = convert_to_openai_tool(ArchitecturePlan)["function"]["parameters"]
    assert set(tool["properties"]) == set(PLAN_FIELDS)
    assert set(tool["required"]) == set(PLAN_FIELDS)


def test_designer_still_receives_every_plan_field(monkeypatch):
    plan = make_architecture_plan()
    prompts: list[str] = []
    monkeypatch.setattr(designer, "_run_tool_calling_research", lambda requirements, p: ("notes", False))
    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
    monkeypatch.setattr(
        llm_module, "invoke_structured", lambda llm, schema, prompt: prompts.append(prompt) or make_architecture()
    )
    state = create_initial_state("x")
    state.update(requirements=make_requirements(), architecture_plan=plan)

    designer.run(state)

    (prompt,) = prompts
    assert plan.model_dump_json() in prompt  # the whole plan, as JSON
    for field in PLAN_FIELDS:
        assert json.dumps(getattr(plan, field)) in prompt


# ---------------------------------------------------------------------------
# Error handling unchanged
# ---------------------------------------------------------------------------


def test_planner_failures_still_propagate_unchanged(monkeypatch):
    error = llm_module.LLMInvocationError("simulated", reason=llm_module.FAILURE_INVALID_OUTPUT)

    with pytest.raises(llm_module.LLMInvocationError) as raised:
        _run_planner(monkeypatch, error)

    assert raised.value is error  # no fallback plan is invented

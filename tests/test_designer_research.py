"""The Architecture Designer's research loop recovers from tool_use_failed.

The research step (the model calling the AWS search tool) is optional
context for the design. A malformed tool call (Groq HTTP 400
tool_use_failed) gets exactly one corrective retry; if that fails the same
way, research stops, the notes gathered so far are kept, and the design
goes ahead. Every other error still fails the node exactly as before.
"""

from __future__ import annotations

import json

import httpx
import pytest
from groq import APIStatusError
from langchain_core.messages import AIMessage, HumanMessage

from agents import architecture as designer
from agents import llm as llm_module
from graph.state import create_initial_state
from graph.workflow import WorkflowError, run_workflow

from .conftest import make_architecture, make_architecture_plan, make_requirements
from .test_graph import _patch_llm
from .test_resilience import _groq_scripted, _rate_limited, _tool_use_failed, fake_time  # noqa: F401

FAILED_GENERATION = "<tool_call><function=search_aws_services_tool><parameter=qu LEAKED-MODEL-OUTPUT"


def _fake_response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))


def _tool_use_error() -> APIStatusError:
    body = {
        "error": {
            "message": "Failed to call a function. Please adjust your prompt.",
            "type": "invalid_request_error",
            "code": "tool_use_failed",
            "failed_generation": FAILED_GENERATION,
        }
    }
    # Like the real SDK: the exception's text embeds the whole body.
    return APIStatusError(f"Error code: 400 - {body}", response=_fake_response(400), body=body)


def _other_400_error() -> APIStatusError:
    body = {"error": {"message": "invalid model", "type": "invalid_request_error", "code": "model_not_found"}}
    return APIStatusError(f"Error code: 400 - {body}", response=_fake_response(400), body=body)


def _search(query: str, call_id: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": "search_aws_services_tool", "args": {"query": query}, "id": call_id}])


def _done() -> AIMessage:
    return AIMessage(content="Enough research.", tool_calls=[])


class _ScriptedResearchLLM:
    """A tool-bound chat model answering each invoke from a shared script
    (an AIMessage, or an exception to raise). Records every call."""

    def __init__(self, script: list, calls: list, temperature: float):
        self._script, self._calls, self.temperature = script, calls, temperature

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self._calls.append({"temperature": self.temperature, "messages": list(messages)})
        step = self._script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


def _script_llm(monkeypatch, *steps) -> list:
    script, calls = list(steps), []
    monkeypatch.setattr(
        llm_module,
        "get_llm",
        lambda temperature=0.2, max_tokens=750: _ScriptedResearchLLM(script, calls, temperature),
    )
    return calls


def _research():
    return designer._run_tool_calling_research(make_requirements(), make_architecture_plan())


def _events(caplog, name: str) -> list[dict]:
    return [r.event_fields for r in caplog.records if getattr(r, "event_fields", {}).get("event") == name]


def _assert_nothing_leaked(caplog) -> None:
    text = caplog.text + json.dumps([getattr(r, "event_fields", {}) for r in caplog.records], default=str)
    assert "LEAKED-MODEL-OUTPUT" not in text
    assert "Failed to call a function" not in text


class TestResearchRecovery:
    def test_successful_research_unchanged(self, monkeypatch, caplog):
        calls = _script_llm(monkeypatch, _search("compute"), _done())

        with caplog.at_level("INFO"):
            research, fallback = _research()

        assert fallback is False
        assert research.startswith("Query 'compute':")
        assert designer.NO_RESEARCH_NOTE not in research and designer.RESEARCH_STOPPED_NOTE not in research
        assert [c["temperature"] for c in calls] == [designer.RESEARCH_TEMPERATURE] * 2
        assert not any(isinstance(m, HumanMessage) and m.content == designer.RESEARCH_CORRECTION for c in calls for m in c["messages"])
        assert _events(caplog, "research_call_failed") == []

    def test_no_tool_calls_still_reports_no_searches(self, monkeypatch):
        _script_llm(monkeypatch, _done())
        assert _research() == ("No tool searches were made.", False)

    def test_tool_use_failed_then_corrective_retry_succeeds(self, monkeypatch, caplog):
        calls = _script_llm(monkeypatch, _tool_use_error(), _search("database"), _done())

        with caplog.at_level("INFO"):
            research, fallback = _research()

        assert fallback is False
        assert research.startswith("Query 'database':")
        assert designer.RESEARCH_STOPPED_NOTE not in research
        # Exactly one retry, hotter, with the correction added for that call only.
        assert [c["temperature"] for c in calls] == [0.2, designer.RESEARCH_RETRY_TEMPERATURE, 0.2]
        retry_messages = calls[1]["messages"]
        assert isinstance(retry_messages[-1], HumanMessage) and retry_messages[-1].content == designer.RESEARCH_CORRECTION
        assert not any(getattr(m, "content", None) == designer.RESEARCH_CORRECTION for m in calls[2]["messages"])

        (event,) = _events(caplog, "research_call_failed")
        assert event | {"job_id": None} == {
            "event": "research_call_failed",
            "job_id": None,
            "error_type": "APIStatusError",
            "provider_status": 400,
            "provider_error_code": "tool_use_failed",
            "error_category": "tool_use_failed",
            "round": 1,
            "corrective_retry_attempted": True,
            "corrective_retry_succeeded": True,
            "fallback_used": False,
            "research_notes_kept": 0,
        }
        _assert_nothing_leaked(caplog)

    def test_both_attempts_fail_falls_back_to_no_research(self, monkeypatch, caplog):
        calls = _script_llm(monkeypatch, _tool_use_error(), _tool_use_error())

        with caplog.at_level("INFO"):
            research, fallback = _research()

        assert (research, fallback) == (designer.NO_RESEARCH_NOTE, True)
        assert len(calls) == 2  # the original call and exactly one corrective retry
        (event,) = _events(caplog, "research_call_failed")
        assert event["corrective_retry_attempted"] is True
        assert event["corrective_retry_succeeded"] is False
        assert event["fallback_used"] is True
        assert event["research_notes_kept"] == 0
        assert event["provider_error_code"] == "tool_use_failed"
        _assert_nothing_leaked(caplog)

    def test_later_failure_keeps_earlier_notes(self, monkeypatch, caplog):
        calls = _script_llm(monkeypatch, _search("database"), _tool_use_error(), _tool_use_error())

        with caplog.at_level("INFO"):
            research, fallback = _research()

        assert fallback is True
        assert research.startswith("Query 'database':")
        assert research.endswith(designer.RESEARCH_STOPPED_NOTE)
        assert len(calls) == 3
        # The round-2 retry still carries round 1's tool call and its result.
        assert any(getattr(m, "tool_call_id", None) == "c1" for m in calls[2]["messages"])
        (event,) = _events(caplog, "research_call_failed")
        assert (event["round"], event["research_notes_kept"], event["fallback_used"]) == (2, 1, True)

    def test_stopped_note_survives_research_truncation(self, monkeypatch):
        monkeypatch.setattr(designer, "MAX_RESEARCH_CHARS", 50)
        _script_llm(monkeypatch, _search("database"), _tool_use_error(), _tool_use_error())

        research, _ = _research()

        assert "...(truncated)" in research and research.endswith(designer.RESEARCH_STOPPED_NOTE)

    def test_unrelated_provider_error_is_not_swallowed(self, monkeypatch, caplog):
        calls = _script_llm(monkeypatch, _other_400_error())

        with caplog.at_level("INFO"), pytest.raises(APIStatusError):
            _research()

        assert len(calls) == 1  # no corrective retry
        assert _events(caplog, "research_call_failed") == []

    def test_unexpected_exception_is_not_swallowed(self, monkeypatch):
        calls = _script_llm(monkeypatch, ValueError("boom"))

        with pytest.raises(ValueError):
            _research()
        assert len(calls) == 1

    def test_unrelated_error_on_the_corrective_retry_is_raised(self, monkeypatch, caplog):
        _script_llm(monkeypatch, _tool_use_error(), _other_400_error())

        with caplog.at_level("INFO"), pytest.raises(APIStatusError) as raised:
            _research()

        assert raised.value.body["error"]["code"] == "model_not_found"
        assert _events(caplog, "research_call_failed") == []


class TestDesignerNodeContinues:
    def test_design_step_runs_with_fallback_research(self, monkeypatch):
        _script_llm(monkeypatch, _tool_use_error(), _tool_use_error())
        prompts: list[str] = []

        def fake_invoke_structured(llm, schema, prompt):
            prompts.append(prompt)
            return make_architecture()

        monkeypatch.setattr(llm_module, "invoke_structured", fake_invoke_structured)
        state = create_initial_state("Design a blog.")
        state.update(requirements=make_requirements(), architecture_plan=make_architecture_plan())

        result = designer.run(state)

        assert result["architecture"].version == 1
        (prompt,) = prompts
        assert designer.NO_RESEARCH_NOTE in prompt
        assert "LEAKED-MODEL-OUTPUT" not in prompt
        (entry,) = result["execution_trace"]
        assert "search failed" in entry["action"]
        assert "LEAKED-MODEL-OUTPUT" not in json.dumps(result["execution_trace"])

    def test_design_trace_unchanged_on_success(self, monkeypatch):
        _script_llm(monkeypatch, _done())
        monkeypatch.setattr(llm_module, "invoke_structured", lambda llm, schema, prompt: make_architecture())
        state = create_initial_state("Design a blog.")
        state.update(requirements=make_requirements(), architecture_plan=make_architecture_plan())

        (entry,) = designer.run(state)["execution_trace"]

        assert entry["action"].startswith("Searched the AWS service knowledge base")
        assert "search failed" not in entry["action"]

    def test_full_workflow_completes_when_research_fails(self, monkeypatch):
        _patch_llm(monkeypatch, critic_verdicts=[True])
        _script_llm(monkeypatch, _tool_use_error(), _tool_use_error())  # research only; structured calls stay mocked

        final_state = run_workflow("Design a blogging platform for 10,000 users.")

        assert final_state["final_report"] is not None
        designer_entries = [e for e in final_state["execution_trace"] if e["node"] == "Architecture Designer"]
        assert "search failed" in designer_entries[0]["action"]

    def test_full_workflow_still_fails_on_unrelated_research_error(self, monkeypatch):
        _patch_llm(monkeypatch, critic_verdicts=[True])
        _script_llm(monkeypatch, _other_400_error())

        with pytest.raises(WorkflowError):
            run_workflow("Design a blogging platform for 10,000 users.")


# --- Real Groq SDK behind a mock transport (no network) --------------------------


def _plain_completion() -> httpx.Response:
    completion = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Done."}}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 40, "total_tokens": 940},
    }
    return httpx.Response(200, json=completion)


class TestRealSdkPaths:
    def _use(self, monkeypatch, llm):
        monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: llm)

    def test_429_retry_behaviour_unchanged(self, monkeypatch, fake_time, caplog):  # noqa: F811
        # 3 x 429: the SDK retries twice, then our app retry gets the 4th request through.
        llm, seen = _groq_scripted(_rate_limited(), _rate_limited(), _rate_limited(), _plain_completion(), max_tokens=512)
        self._use(monkeypatch, llm)

        with caplog.at_level("INFO"):
            research, fallback = _research()

        assert (research, fallback) == ("No tool searches were made.", False)
        assert len(seen) == 4
        (summary,) = _events(caplog, "llm_call_summary")
        assert (summary["outcome"], summary["sdk_retries"], summary["app_retries"]) == ("success", 2, 1)
        assert _events(caplog, "research_call_failed") == []

    def test_real_tool_use_failed_400_gets_corrective_retry(self, monkeypatch, fake_time, caplog):  # noqa: F811
        llm, seen = _groq_scripted(_tool_use_failed(), _plain_completion(), max_tokens=512)
        self._use(monkeypatch, llm)

        with caplog.at_level("INFO"):
            research, fallback = _research()

        assert (research, fallback) == ("No tool searches were made.", False)
        assert len(seen) == 2  # a 400 is not retried by the SDK; only our one corrective retry
        assert fake_time == []  # no waiting before the corrective retry
        (event,) = _events(caplog, "research_call_failed")
        assert (event["provider_status"], event["provider_error_code"]) == (400, "tool_use_failed")
        assert event["corrective_retry_succeeded"] is True
        assert "SECRET-PROMPT-AND-GENERATION" not in caplog.text

    def test_real_tool_use_failed_twice_falls_back(self, monkeypatch, fake_time, caplog):  # noqa: F811
        llm, seen = _groq_scripted(_tool_use_failed(), _tool_use_failed(), max_tokens=512)
        self._use(monkeypatch, llm)

        with caplog.at_level("INFO"):
            assert _research() == (designer.NO_RESEARCH_NOTE, True)

        assert len(seen) == 2
        assert "SECRET-PROMPT-AND-GENERATION" not in caplog.text

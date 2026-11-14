"""Validator severity and critic approval follow one policy.

CRITICAL and HIGH validator findings block approval (and block revision
acceptance); MEDIUM findings lower the score but do not block on their own;
LOW findings are informational. The critic keeps the validator's severity
instead of treating every finding as critical, and can still reject for
problems it finds itself. The LLM is always mocked.
"""

from __future__ import annotations

import pytest

from agents import critic as critic_agent
from agents import llm as llm_module
from graph.state import create_initial_state
from models.schemas import CriticReview, Severity, ValidationIssue, ValidationResult
from tools import revision_guard
from tools.architecture_validator import BLOCKING_SEVERITIES, blocking_findings

from .conftest import (
    make_analysis,
    make_architecture,
    make_cost_analysis,
    make_critic_review,
    make_requirements,
)

APPROVED = CriticReview(approved=True, score=86, issues=[], required_changes=[], strengths=["Solid design."])


def _finding(severity: Severity, rule: str = "some_rule") -> ValidationIssue:
    return ValidationIssue(rule=rule, message=f"A {severity.value} problem.", severity=severity)


def _run_critic(monkeypatch, review: CriticReview, *findings: ValidationIssue):
    prompts: list[str] = []

    def fake_invoke_structured(llm, schema, prompt):
        prompts.append(prompt)
        return review.model_copy(deep=True)

    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
    monkeypatch.setattr(llm_module, "invoke_structured", fake_invoke_structured)
    state = create_initial_state("Design an e-commerce platform.")
    state.update(
        requirements=make_requirements(),
        architecture=make_architecture(),
        **{f"{d}_analysis": make_analysis(d) for d in ("compute", "database", "networking", "security", "reliability")},
        cost_analysis=make_cost_analysis(),
        validation_results=ValidationResult(passed=not findings, issues=list(findings)),
    )
    result = critic_agent.run(state)
    return result, prompts[0]


# ---------------------------------------------------------------------------
# Blocking findings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("severity", [Severity.CRITICAL, Severity.HIGH])
def test_critical_and_high_findings_block_approval(monkeypatch, caplog, severity):
    finding = _finding(severity, "database_without_backups")

    with caplog.at_level("INFO"):
        result, _ = _run_critic(monkeypatch, APPROVED, finding)

    review = result["critic_review"]
    assert review.approved is False
    assert review.score == 86  # the critic's own score is kept
    (added,) = review.issues
    assert added.severity == severity  # the validator's severity, not raised to critical
    assert "database_without_backups" in added.issue
    assert review.required_changes == ["Resolve the database_without_backups validator finding."]
    assert result["critic_history"] == [review]
    action = result["execution_trace"][0]["action"]
    assert "Approval withheld: unresolved high/critical validator findings (database_without_backups)" in action
    events = [r.event_fields for r in caplog.records if getattr(r, "event_fields", {}).get("event") == "critic_approval_withheld"]
    assert events and events[0]["findings"] == "database_without_backups"


# ---------------------------------------------------------------------------
# Non-blocking findings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("severity", [Severity.MEDIUM, Severity.LOW])
def test_medium_or_low_finding_alone_does_not_block_approval(monkeypatch, severity):
    result, prompt = _run_critic(monkeypatch, APPROVED, _finding(severity, "missing_caching_layer"))

    review = result["critic_review"]
    assert review.approved is True
    assert review == APPROVED  # untouched
    assert f"- [{severity.value.upper()}] (missing_caching_layer)" in prompt  # shown at its own severity
    assert "Approval withheld" not in result["execution_trace"][0]["action"]


def test_prompt_keeps_validator_severity_and_no_longer_makes_every_finding_critical(monkeypatch):
    _, prompt = _run_critic(monkeypatch, APPROVED)

    assert "is a confirmed validator finding" not in prompt  # the old "every finding is critical" rule
    assert "Validator findings keep the validator's severity -- do not raise them to critical." in prompt
    assert "CRITICAL and HIGH findings block approval" in prompt
    assert "A MEDIUM finding lowers the score and belongs\n  in required_changes, but on its own does not block" in prompt
    assert "LOW findings are informational" in prompt
    assert "Any unresolved CRITICAL or HIGH deterministic validator finding must result in approved=false" in prompt


# ---------------------------------------------------------------------------
# The critic's own judgement is not weakened
# ---------------------------------------------------------------------------


def test_critic_can_still_reject_for_an_independent_serious_issue(monkeypatch):
    own_finding = CriticReview(
        approved=False,
        score=55,
        issues=[{"issue": "Single Aurora writer bottlenecks 500k users.", "severity": "critical", "category": "scalability"}],
        required_changes=["Add Aurora read replicas for catalog reads."],
    )

    result, prompt = _run_critic(monkeypatch, own_finding)  # no validator findings at all

    assert result["critic_review"] == own_finding
    assert "Problems you identify yourself are rated on their own merits" in prompt
    assert "concrete, named risk of data\n  loss, a security breach or an outage" in prompt


@pytest.mark.parametrize("severity", list(Severity))
def test_a_rejection_is_never_turned_into_an_approval(monkeypatch, severity):
    result, _ = _run_critic(monkeypatch, make_critic_review(approved=False), _finding(severity))

    assert result["critic_review"] == make_critic_review(approved=False)


# ---------------------------------------------------------------------------
# One policy for critic approval and revision acceptance
# ---------------------------------------------------------------------------


def test_critic_and_revision_guard_share_the_blocking_severities():
    assert BLOCKING_SEVERITIES == (Severity.HIGH, Severity.CRITICAL)
    assert revision_guard.blocking_findings is blocking_findings
    mixed = ValidationResult(passed=False, issues=[_finding(s, s.value) for s in Severity])
    assert [f.rule for f in blocking_findings(mixed)] == ["high", "critical"]
    assert blocking_findings(None) == []

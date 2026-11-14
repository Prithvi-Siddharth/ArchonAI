"""Revision acceptance: zero regressions is not enough.

A revision is accepted only when it (1) introduces no unjustified
regressions, (2) resolves the high/critical validator findings the current
version had, and (3) actually contains every requested change its change_log
claims. A failure gets at most one corrective attempt; if that still fails,
the current architecture is kept.

Modelled on job d6b97780, where every revision claimed "Added Aurora
automated backups and point-in-time recovery" in change_log only, and was
accepted each time because nothing regressed. The LLM is always mocked.
"""

from __future__ import annotations

from agents import revision as revision_agent
from agents.formatting import compact_architecture
from graph.state import MAX_REVISIONS, create_initial_state
from graph.workflow import run_workflow
from models.schemas import AWSService, CriticReview
from tools.architecture_facts import PROPOSED, verify_change
from tools.architecture_validator import validate_architecture
from tools.revision_guard import (
    blocking,
    check_revision,
    unimplemented_claims,
    unresolved_findings,
)

from .conftest import make_architecture, make_critic_review, make_requirements
from .test_revision_guard import _patch_workflow, _script_revisions

CLAIM = "Added Aurora automated backups and point-in-time recovery."

BACKUPS_REVIEW = CriticReview(
    approved=False,
    score=62,
    issues=[{"issue": "Aurora lacks backup/PITR.", "severity": "critical", "category": "reliability"}],
    required_changes=["Add Aurora automated backups and point-in-time recovery for orders."],
)
SECRETS_REVIEW = CriticReview(
    approved=False,
    score=70,
    issues=[{"issue": "Credentials are not managed.", "severity": "high", "category": "security"}],
    required_changes=["Add AWS Secrets Manager for DB credentials."],
)
SECRETS = AWSService(
    name="AWS Secrets Manager",
    category="Security",
    purpose="Stores DB credentials with automatic rotation",
    justification="Keeps credentials out of code",
)


def _aurora(justification: str) -> AWSService:
    return AWSService(name="Amazon Aurora", category="Database", purpose="Store transactional order data",
                      justification=justification)


NO_BACKUPS = _aurora("Relational, multi-AZ, encrypted at rest via KMS, isolated in a private subnet, not publicly accessible")
WITH_BACKUPS = _aurora(
    "Relational, multi-AZ, automated backups and point-in-time recovery, encrypted via KMS, "
    "in a private subnet, not publicly accessible"
)


def _design(aurora: AWSService, *extra: AWSService, drop: str | None = None, **overrides):
    """make_architecture() with the given Aurora entry (and optional extra/dropped services)."""
    services = [aurora if s.name == "Amazon Aurora" else s for s in make_architecture().services if s.name != drop]
    return make_architecture(services=[*services, *extra], **overrides)


def _state(architecture, review: CriticReview, **overrides) -> dict:
    state = create_initial_state("Design an e-commerce platform for 500,000 users.")
    state.update(
        requirements=make_requirements(),
        architecture=architecture,
        critic_review=review,
        critic_history=[review],
        revision_count=0,
        validation_results=validate_architecture(architecture, make_requirements()),
    )
    state.update(overrides)
    return state


def _rules(architecture) -> list[str]:
    return [i.rule for i in validate_architecture(architecture, make_requirements()).issues]


def _revision_checks(caplog) -> list[dict]:
    return [r.event_fields for r in caplog.records if getattr(r, "event_fields", {}).get("event") == "revision_checked"]


def test_the_fixture_reproduces_the_d6b97780_finding():
    assert _rules(_design(NO_BACKUPS)) == ["database_without_backups"]
    assert _rules(_design(WITH_BACKUPS)) == []


# ---------------------------------------------------------------------------
# 1-3. Zero regressions is not acceptance; change_log claims are not implementation
# ---------------------------------------------------------------------------


def test_zero_regressions_but_unresolved_blocking_finding_is_rejected(monkeypatch):
    current = _design(NO_BACKUPS)
    unchanged = _design(NO_BACKUPS, change_log=[])
    assert blocking(check_revision(current, unchanged, make_requirements())) == []  # no regressions...
    prompts = _script_revisions(monkeypatch, unchanged, unchanged)

    result = revision_agent.run(_state(current, BACKUPS_REVIEW))

    assert len(prompts) == 2  # ...one corrective attempt, then rejected
    assert result["architecture"].version == 1
    assert result["implemented_changes"] == []
    action = result["execution_trace"][0]["action"]
    assert action.startswith("Rejected the revised architecture: blocking findings still unresolved")
    assert "database_without_backups" in action


def test_zero_regressions_but_requested_change_only_proposed_is_not_accepted(monkeypatch):
    claimed_only = _design(WITH_BACKUPS, change_log=["Added AWS Secrets Manager for DB credentials."])
    prompts = _script_revisions(monkeypatch, claimed_only, claimed_only)

    result = revision_agent.run(_state(_design(WITH_BACKUPS), SECRETS_REVIEW))

    assert len(prompts) == 2
    assert result["architecture"].version == 1
    assert "AWS Secrets Manager" not in [s.name for s in result["architecture"].services]
    assert "claimed only in change_log" in result["execution_trace"][0]["action"]


def test_a_change_only_in_the_change_log_is_not_implemented():
    claimed_only = _design(NO_BACKUPS, change_log=[CLAIM])

    check = verify_change(CLAIM, claimed_only)
    assert check.status == PROPOSED
    assert {"point-in-time recovery", "database backups"} <= set(check.missing)
    (unimplemented,) = unimplemented_claims(claimed_only, BACKUPS_REVIEW.required_changes)
    assert unimplemented.entry == CLAIM
    (finding,) = unresolved_findings(_design(NO_BACKUPS), claimed_only, make_requirements())
    assert finding.rule == "database_without_backups"


# ---------------------------------------------------------------------------
# 4-6. The corrective attempt, and revalidation after it
# ---------------------------------------------------------------------------


def test_correction_that_adds_the_configuration_is_accepted(monkeypatch):
    claimed_only = _design(NO_BACKUPS, change_log=[CLAIM])
    fixed = _design(WITH_BACKUPS, change_log=[CLAIM])
    prompts = _script_revisions(monkeypatch, claimed_only, fixed)

    result = revision_agent.run(_state(_design(NO_BACKUPS), BACKUPS_REVIEW))

    correction = prompts[1]
    assert "The database_without_backups validator finding remains unresolved" in correction
    assert "'Amazon Aurora' service" in correction
    assert "'automated backups' and 'point-in-time recovery'" in correction
    assert f"Claimed in change_log but not in the design: '{CLAIM}'" in correction
    assert "Do not claim implementation only in change_log" in correction

    revised = result["architecture"]
    assert revised.version == 2
    assert _rules(revised) == []  # revalidated: the validator now passes
    assert result["implemented_changes"] == [f"v2: {CLAIM}"]
    assert revised.change_log == [CLAIM]  # verified, so not marked as proposed
    assert "left blocking findings unresolved and was corrected" in result["execution_trace"][0]["action"]


def test_correction_that_still_does_not_implement_it_stays_rejected(monkeypatch, caplog):
    claimed_only = _design(NO_BACKUPS, change_log=[CLAIM])
    _script_revisions(monkeypatch, claimed_only, claimed_only)
    current = _design(NO_BACKUPS)

    with caplog.at_level("INFO"):
        result = revision_agent.run(_state(current, BACKUPS_REVIEW))

    kept = result["architecture"]
    assert kept == current  # unchanged, and the claim is not recorded anywhere
    assert result["implemented_changes"] == []
    assert _rules(kept) == ["database_without_backups"]  # the finding is preserved for the critic
    (logged,) = _revision_checks(caplog)
    assert logged["accepted"] is False and logged["corrected"] is True
    assert logged["regressions"] == 0
    assert logged["unresolved_findings"] == 1 and logged["findings"] == "database_without_backups"
    assert logged["unimplemented_claims"] == 1
    assert CLAIM not in caplog.text  # rule names only, never the model's text


def test_correction_that_introduces_a_regression_is_rejected_as_a_regression(monkeypatch):
    claimed_only = _design(NO_BACKUPS, change_log=[CLAIM])
    fixed_but_dropped_cache = _design(WITH_BACKUPS, drop="Amazon ElastiCache", change_log=[CLAIM])
    _script_revisions(monkeypatch, claimed_only, fixed_but_dropped_cache)

    result = revision_agent.run(_state(_design(NO_BACKUPS), BACKUPS_REVIEW))

    assert result["architecture"].version == 1
    assert "Amazon ElastiCache" in [s.name for s in result["architecture"].services]
    assert result["execution_trace"][0]["action"].startswith("Rejected the revised architecture as a regression")


# ---------------------------------------------------------------------------
# 7. Existing acceptance unchanged
# ---------------------------------------------------------------------------


def test_clean_revision_is_accepted_first_time(monkeypatch):
    added = _design(WITH_BACKUPS, SECRETS, change_log=["Added AWS Secrets Manager for DB credentials."])
    prompts = _script_revisions(monkeypatch, added)

    result = revision_agent.run(_state(_design(WITH_BACKUPS), SECRETS_REVIEW))

    assert len(prompts) == 1  # no correction
    assert result["architecture"].version == 2
    assert result["implemented_changes"] == ["v2: Added AWS Secrets Manager for DB credentials."]
    assert "corrected" not in result["execution_trace"][0]["action"]


def test_a_medium_finding_does_not_block_acceptance(monkeypatch):
    # missing_caching_layer is MEDIUM: still shown to the critic, but not a blocker.
    no_cache = _design(WITH_BACKUPS, drop="Amazon ElastiCache")
    assert _rules(no_cache) == ["missing_caching_layer"]
    prompts = _script_revisions(monkeypatch, no_cache)

    result = revision_agent.run(_state(no_cache, make_critic_review(approved=False)))

    assert len(prompts) == 1 and result["architecture"].version == 2


# ---------------------------------------------------------------------------
# 8. Bounded: one correction per revision, MAX_REVISIONS per run
# ---------------------------------------------------------------------------


def test_at_most_one_correction_per_revision(monkeypatch):
    claimed_only = _design(NO_BACKUPS, change_log=[CLAIM])
    prompts = _script_revisions(monkeypatch, *[claimed_only] * 5)

    revision_agent.run(_state(_design(NO_BACKUPS), BACKUPS_REVIEW))

    assert len(prompts) == 2


def test_workflow_still_stops_at_max_revisions(monkeypatch):
    calls = _patch_workflow(
        monkeypatch,
        lambda node: _design(NO_BACKUPS, change_log=[CLAIM] if node == "architecture_revision" else []),
        [BACKUPS_REVIEW],  # the critic never approves
    )

    final_state = run_workflow("Design an e-commerce platform for 500,000 concurrent users.")

    assert final_state["revision_count"] == MAX_REVISIONS
    assert len(calls["revision_prompts"]) == 2 * MAX_REVISIONS  # one attempt + one correction per round
    assert final_state["architecture"].version == 1  # never accepted
    assert "database_without_backups" in [i.rule for i in final_state["validation_results"].issues]
    assert final_state["implemented_changes"] == []
    assert final_state["final_report"] is not None


# ---------------------------------------------------------------------------
# 9. The correction works from the latest architecture
# ---------------------------------------------------------------------------


def test_correction_gets_the_current_version_and_the_rejected_attempt(monkeypatch):
    current = _design(NO_BACKUPS, version=2, summary="Current v2 design with read replicas for the catalog.")
    attempt = _design(NO_BACKUPS, version=2, summary="First attempt: v2 with read replicas for the catalog, plus SQS.", change_log=[CLAIM])
    prompts = _script_revisions(monkeypatch, attempt, attempt)

    revision_agent.run(_state(current, BACKUPS_REVIEW, revision_count=1))

    first, correction = prompts
    assert correction.startswith(first)  # the same base prompt, built from the current architecture
    assert "Current Architecture (version 2)" in first
    assert compact_architecture(current) in first
    assert "Your previous attempt (not accepted):\n" + compact_architecture(attempt) in correction
    assert correction.count("IMPORTANT:") == 1  # one correction, not stacked

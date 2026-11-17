"""Revision in delta mode -- the default since Optimization 4d (REVISION_OUTPUT_MODE).

The model returns an ArchitectureDelta; tools/architecture_delta.py merges
it into the current design; and the merged design goes through exactly the
same guard, validator and change-log checks as a full revision, against the
current version. The single correction is a change set applied on top of
the rejected attempt. REVISION_OUTPUT_MODE=full (the rollback option) keeps the
previous behaviour unchanged. No LLM.
"""

from __future__ import annotations

import pytest

from agents import llm as llm_module
from agents import revision as revision_agent
from agents.formatting import compact_architecture
from graph.state import MAX_REVISIONS
from graph.workflow import run_workflow
from models.schemas import (
    Architecture,
    ArchitectureDelta,
    AWSService,
    ServiceRemoval,
    ServiceUpdate,
)
from tools.architecture_delta import service_id

from .conftest import make_architecture
from .test_revision_acceptance import (
    BACKUPS_REVIEW,
    CLAIM,
    NO_BACKUPS,
    SECRETS,
    SECRETS_REVIEW,
    WITH_BACKUPS,
    _design,
    _revision_checks,
    _rules,
    _state,
)
from .test_revision_guard import _patch_workflow

ADD_SECRETS_LOG = "Added AWS Secrets Manager for DB credentials."


@pytest.fixture
def delta_mode(monkeypatch):
    monkeypatch.setenv(revision_agent.OUTPUT_MODE_ENV, "delta")


def _script(monkeypatch, *replies) -> list[tuple[type, str]]:
    """Each LLM call returns the next reply (or raises it); (schema, prompt) pairs are recorded."""
    remaining = list(replies)
    calls: list[tuple[type, str]] = []

    def fake_invoke_structured(llm, schema, prompt):
        calls.append((schema, prompt))
        reply = remaining.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply.model_copy(deep=True)

    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
    monkeypatch.setattr(llm_module, "invoke_structured", fake_invoke_structured)
    return calls


def _run(state, caplog):
    with caplog.at_level("INFO"):
        result = revision_agent.run(state)
    (logged,) = _revision_checks(caplog)
    return result, logged


# ---------------------------------------------------------------------------
# Mode selection and prompts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "delta"),  # unset: the default
        ("", "delta"),
        ("diff", "delta"),  # unknown values fall back to the default
        ("delta", "delta"),
        (" DELTA ", "delta"),
        ("full", "full"),  # the explicit rollback
        (" Full ", "full"),
    ],
)
def test_output_mode_setting(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv(revision_agent.OUTPUT_MODE_ENV, raising=False)
    else:
        monkeypatch.setenv(revision_agent.OUTPUT_MODE_ENV, value)
    assert revision_agent.output_mode() == expected


def test_unset_mode_revises_with_a_delta(monkeypatch, caplog):
    monkeypatch.delenv(revision_agent.OUTPUT_MODE_ENV, raising=False)
    base = _design(WITH_BACKUPS)
    calls = _script(monkeypatch, ArchitectureDelta(added_services=[SECRETS], change_log=[ADD_SECRETS_LOG]))

    result, logged = _run(_state(base, SECRETS_REVIEW), caplog)

    ((schema, prompt),) = calls
    assert schema is ArchitectureDelta and "Return ONLY what changes" in prompt
    assert result["architecture"].services == [*base.services, SECRETS]
    assert logged["output_mode"] == "delta"


def test_explicit_full_mode_is_unchanged(monkeypatch, caplog):
    monkeypatch.setenv(revision_agent.OUTPUT_MODE_ENV, "full")
    calls = _script(monkeypatch, _design(WITH_BACKUPS, SECRETS, change_log=[ADD_SECRETS_LOG]))

    result, logged = _run(_state(_design(WITH_BACKUPS), SECRETS_REVIEW), caplog)

    ((schema, prompt),) = calls
    assert schema is Architecture
    assert prompt.startswith("You are an AWS solutions architect revising a rejected architecture.")
    assert "Hard size limits" in prompt and "Return ONLY what changes" not in prompt
    assert "- Application Load Balancer (Networking)" in prompt and "S1." not in prompt
    assert result["architecture"].version == 2
    assert logged["output_mode"] == "full" and "invalid_delta" not in logged


def test_delta_prompt_shows_ids_and_asks_only_for_changes(monkeypatch, delta_mode):
    calls = _script(monkeypatch, ArchitectureDelta(added_services=[SECRETS], change_log=[ADD_SECRETS_LOG]))

    revision_agent.run(_state(_design(WITH_BACKUPS), SECRETS_REVIEW))

    ((schema, prompt),) = calls
    assert schema is ArchitectureDelta
    assert "S1. Application Load Balancer (Networking)" in prompt and "S4. Amazon ElastiCache" in prompt
    assert "Return ONLY what changes" in prompt
    assert "Hard size limits" not in prompt  # the full-architecture output rules are not shown
    # The same context as in full mode.
    for section in ("Critic review history", "Still pending", "Deterministic validator findings", "multi-AZ, auto"):
        assert section in prompt


def test_compact_architecture_ids_match_the_merge_ids():
    text = compact_architecture(make_architecture(), with_ids=True)
    for index, service in enumerate(make_architecture().services):
        assert f"{service_id(index)}. {service.name} (" in text
    assert compact_architecture(make_architecture()) == compact_architecture(make_architecture(), with_ids=False)


# ---------------------------------------------------------------------------
# Accepted deltas
# ---------------------------------------------------------------------------


def test_a_clean_delta_is_merged_and_accepted(monkeypatch, delta_mode, caplog):
    base = _design(WITH_BACKUPS)
    _script(monkeypatch, ArchitectureDelta(added_services=[SECRETS], change_log=[ADD_SECRETS_LOG]))

    result, logged = _run(_state(base, SECRETS_REVIEW), caplog)

    revised = result["architecture"]
    assert revised.version == 2
    assert revised.services == [*base.services, SECRETS]
    assert result["implemented_changes"] == [f"v2: {ADD_SECRETS_LOG}"]
    assert logged["accepted"] is True and logged["corrected"] is False and logged["output_mode"] == "delta"


def test_entries_the_delta_does_not_mention_are_kept_exactly(monkeypatch, delta_mode):
    base = _design(WITH_BACKUPS)
    new_aurora = base.services[2].model_copy(update={"purpose": "Orders, with read replicas for catalog reads"})
    _script(
        monkeypatch,
        ArchitectureDelta(
            updated_services=[ServiceUpdate(id="S3", service=new_aurora)],
            change_log=["Added Aurora read replicas for catalog reads."],
        ),
    )

    revised = revision_agent.run(_state(base, SECRETS_REVIEW))["architecture"]

    assert revised.version == 2
    assert revised.services[2] == new_aurora
    assert [revised.services[i] for i in (0, 1, 3)] == [base.services[i] for i in (0, 1, 3)]
    assert revised.data_flow == base.data_flow and revised.summary == base.summary


def test_an_explicit_removal_is_justified(monkeypatch, delta_mode):
    base = _design(WITH_BACKUPS, SECRETS)
    _script(monkeypatch, ArchitectureDelta(removed_services=[ServiceRemoval(id="S5", reason="IAM roles replace keys")]))

    result = revision_agent.run(_state(base, SECRETS_REVIEW))

    revised = result["architecture"]
    assert revised.version == 2 and "AWS Secrets Manager" not in [s.name for s in revised.services]
    assert "Removed AWS Secrets Manager because IAM roles replace keys" in revised.change_log[0]
    assert "Justified removals:" in result["execution_trace"][0]["action"]


# ---------------------------------------------------------------------------
# The single correction
# ---------------------------------------------------------------------------


def test_an_invalid_delta_is_corrected_against_the_current_architecture(monkeypatch, delta_mode, caplog):
    base = _design(WITH_BACKUPS)
    calls = _script(
        monkeypatch,
        ArchitectureDelta(updated_services=[ServiceUpdate(id="S9", service=SECRETS)]),  # unknown ID
        ArchitectureDelta(added_services=[SECRETS], change_log=[ADD_SECRETS_LOG]),
    )

    result, logged = _run(_state(base, SECRETS_REVIEW), caplog)

    correction = calls[1][1]
    assert "your previous change set could not be applied" in correction
    assert "updated unknown service ID 'S9'" in correction
    assert "against the current architecture above (version 1" in correction
    assert result["architecture"].services == [*base.services, SECRETS]
    assert logged["first_reasons"] == "invalid_delta" and logged["first_invalid_delta"] == 1
    assert logged["accepted"] is True and "invalid_delta" not in logged
    assert "returned a change set that could not be applied (updated unknown service ID 'S9')" in (
        result["execution_trace"][0]["action"]
    )


def test_an_invalid_delta_twice_is_rejected(monkeypatch, delta_mode, caplog):
    base = _design(WITH_BACKUPS)
    stale = ArchitectureDelta(removed_services=[ServiceRemoval(id="S1", reason="API Gateway replaces it")])
    _script(monkeypatch, stale, stale)  # the data flow still routes through the ALB

    result, logged = _run(_state(base, SECRETS_REVIEW), caplog)

    assert result["architecture"] == base and result["implemented_changes"] == []
    assert result["execution_trace"][0]["action"].startswith(
        "Rejected the revision: its change set could not be applied (removed S1 (Application Load Balancer)"
    )
    assert logged["accepted"] is False and logged["invalid_delta"] == 1 and logged["first_reasons"] == "invalid_delta"


def test_an_update_that_drops_backups_is_a_regression_and_the_fix_applies_to_the_attempt(monkeypatch, delta_mode, caplog):
    base = _design(WITH_BACKUPS)
    attempt = ArchitectureDelta(
        updated_services=[ServiceUpdate(id="S3", service=NO_BACKUPS)],
        added_services=[SECRETS],
        change_log=[ADD_SECRETS_LOG],
    )
    fix = ArchitectureDelta(updated_services=[ServiceUpdate(id="S3", service=WITH_BACKUPS)])
    calls = _script(monkeypatch, attempt, fix)

    result, logged = _run(_state(base, SECRETS_REVIEW), caplog)

    correction = calls[1][1]
    assert "Lost without an explicit justification (compared with version 1)" in correction
    assert "new validator failure 'database_without_backups'" in correction
    assert "The result of your previous change set" in correction and "S5. AWS Secrets Manager" in correction
    revised = result["architecture"]
    # The fix was applied on top of the attempt: its addition and change_log are kept.
    assert revised.services == [*base.services[:2], WITH_BACKUPS, base.services[3], SECRETS]
    assert revised.change_log == [ADD_SECRETS_LOG]
    assert _rules(revised) == []
    assert logged["first_reasons"] == "regression" and logged["accepted"] is True


def test_a_change_log_only_claim_is_fixed_by_a_small_follow_up(monkeypatch, delta_mode, caplog):
    claimed_only = ArchitectureDelta(added_services=[SECRETS], change_log=[CLAIM])  # backups only "claimed"
    fix = ArchitectureDelta(updated_services=[ServiceUpdate(id="S3", service=WITH_BACKUPS)])
    calls = _script(monkeypatch, claimed_only, fix)

    result, logged = _run(_state(_design(NO_BACKUPS), BACKUPS_REVIEW), caplog)

    correction = calls[1][1]
    assert "The database_without_backups validator finding remains unresolved" in correction
    assert f"Claimed in change_log but not in the design: '{CLAIM}'" in correction
    revised = result["architecture"]
    assert revised.version == 2 and "AWS Secrets Manager" in [s.name for s in revised.services]
    assert result["implemented_changes"] == [f"v2: {CLAIM}"]  # the attempt's claim, now verified
    assert logged["first_reasons"] == "unresolved_finding,unimplemented_claim" and logged["accepted"] is True


def test_still_unresolved_after_the_correction_is_rejected(monkeypatch, delta_mode):
    no_op = ArchitectureDelta(change_log=[CLAIM])
    _script(monkeypatch, no_op, ArchitectureDelta())

    result = revision_agent.run(_state(_design(NO_BACKUPS), BACKUPS_REVIEW))

    assert result["architecture"].version == 1
    assert result["execution_trace"][0]["action"].startswith(
        "Rejected the revised architecture: blocking findings still unresolved"
    )


# ---------------------------------------------------------------------------
# Whole workflow
# ---------------------------------------------------------------------------


def test_workflow_in_delta_mode_still_stops_at_max_revisions(monkeypatch, delta_mode):
    # Every revision returns an empty change set, so the backup finding is never fixed.
    _patch_workflow(monkeypatch, lambda node: _design(NO_BACKUPS), [BACKUPS_REVIEW])

    final_state = run_workflow("Design an e-commerce platform for 500,000 concurrent users.")

    assert final_state["revision_count"] == MAX_REVISIONS
    assert final_state["architecture"].version == 1
    assert "database_without_backups" in [i.rule for i in final_state["validation_results"].issues]
    assert final_state["final_report"] is not None


# ---------------------------------------------------------------------------
# Fixes from the live benchmark (job 780a29f0): corrections that re-added
# entries, and a new backup failure the correction didn't know how to fix
# ---------------------------------------------------------------------------

DYNAMODB_NO_BACKUPS = AWSService(
    name="Amazon DynamoDB", category="Database", purpose="Catalog reads", justification="Single-digit ms at scale"
)
DYNAMODB_PITR = DYNAMODB_NO_BACKUPS.model_copy(update={"justification": "Point-in-time recovery enabled"})


def test_delta_prompt_asks_to_update_only_what_must_change(monkeypatch, delta_mode):
    calls = _script(monkeypatch, ArchitectureDelta(added_services=[SECRETS], change_log=[ADD_SECRETS_LOG]))
    revision_agent.run(_state(_design(WITH_BACKUPS), SECRETS_REVIEW))
    assert "Update an entry only if its text must change" in calls[0][1]


def test_a_new_backup_failure_is_explained_and_fixed_on_the_added_entry(monkeypatch, delta_mode, caplog):
    base = _design(WITH_BACKUPS)  # S1-S4; the addition becomes S5
    attempt = ArchitectureDelta(added_services=[DYNAMODB_NO_BACKUPS], change_log=["Added DynamoDB for catalog reads."])
    fix = ArchitectureDelta(updated_services=[ServiceUpdate(id="S5", service=DYNAMODB_PITR)])
    calls = _script(monkeypatch, attempt, fix)

    result, logged = _run(_state(base, SECRETS_REVIEW), caplog)

    correction = calls[1][1]
    assert "new validator failure 'database_without_backups'" in correction
    assert "To fix database_without_backups: No backup strategy described for: Amazon DynamoDB." in correction
    assert "purpose or justification of 'Amazon DynamoDB'" in correction  # the exact entry to fix
    assert "Entries S5 were added by your previous change set and are already in it" in correction
    revised = result["architecture"]
    assert revised.version == 2 and revised.services[-1] == DYNAMODB_PITR
    assert logged["first_reasons"] == "regression" and logged["accepted"] is True


def test_a_correction_that_repeats_its_attempts_addition_still_applies(monkeypatch, delta_mode):
    base = _design(WITH_BACKUPS)
    attempt = ArchitectureDelta(
        added_services=[SECRETS, DYNAMODB_NO_BACKUPS], change_log=[ADD_SECRETS_LOG, "Added DynamoDB for reads."]
    )
    # As in job 780a29f0: the fix re-sends the attempt's additions alongside the actual fix.
    fix = ArchitectureDelta(added_services=[SECRETS], updated_services=[ServiceUpdate(id="S6", service=DYNAMODB_PITR)])
    _script(monkeypatch, attempt, fix)

    result = revision_agent.run(_state(base, SECRETS_REVIEW))

    revised = result["architecture"]
    assert revised.version == 2
    assert revised.services == [*base.services, SECRETS, DYNAMODB_PITR]  # no duplicate Secrets Manager


def test_re_adding_a_changed_copy_of_an_added_entry_is_still_rejected(monkeypatch, delta_mode):
    base = _design(WITH_BACKUPS)
    attempt = ArchitectureDelta(added_services=[DYNAMODB_NO_BACKUPS], change_log=["Added DynamoDB for reads."])
    fix = ArchitectureDelta(added_services=[DYNAMODB_PITR])  # should have updated S5 instead
    _script(monkeypatch, attempt, fix)

    result = revision_agent.run(_state(base, SECRETS_REVIEW))

    assert result["architecture"] == base
    assert "two service entries are named 'Amazon DynamoDB'" in result["execution_trace"][0]["action"]

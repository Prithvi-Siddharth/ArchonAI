"""Merging a revision's ArchitectureDelta into the current Architecture (Optimization 4a).

Pure and deterministic. Entries the delta doesn't mention are kept exactly;
anything ambiguous raises InvalidDeltaError instead of being guessed; and
the merged result goes through the existing guard and validator unchanged.
Nothing here is wired into the revision agent yet. No LLM.
"""

from __future__ import annotations

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from models.schemas import (
    Architecture,
    ArchitectureDelta,
    AWSService,
    DataFlowStep,
    ServiceRemoval,
    ServiceUpdate,
)
from tools.architecture_delta import (
    InvalidDeltaError,
    apply_delta,
    delta_between,
    service_id,
    service_ids,
)
from tools.architecture_validator import validate_architecture
from tools.revision_guard import blocking, check_revision

from .conftest import make_architecture, make_requirements

# make_architecture(): S1 Application Load Balancer, S2 Amazon ECS, S3 Amazon Aurora, S4 Amazon ElastiCache.
SECRETS = AWSService(
    name="AWS Secrets Manager", category="Security", purpose="DB credentials with rotation", justification="PCI-DSS"
)
NEW_FLOW = [DataFlowStep(step=1, source="User", destination="ECS", description="Requests reach ECS tasks")]


def _previous(**overrides) -> Architecture:
    return make_architecture(version=2, change_log=["Earlier change."], **overrides)


def _problems(previous: Architecture, delta: ArchitectureDelta) -> list[str]:
    with pytest.raises(InvalidDeltaError) as raised:
        apply_delta(previous, delta)
    return raised.value.problems


# ---------------------------------------------------------------------------
# IDs and schemas
# ---------------------------------------------------------------------------


def test_service_ids_follow_design_order():
    assert service_id(0) == "S1"
    assert {key: s.name for key, s in service_ids(make_architecture()).items()} == {
        "S1": "Application Load Balancer",
        "S2": "Amazon ECS",
        "S3": "Amazon Aurora",
        "S4": "Amazon ElastiCache",
    }


def test_delta_schema_is_all_optional_and_architecture_is_unchanged():
    assert ArchitectureDelta.model_validate({}) == ArchitectureDelta()
    tool = convert_to_openai_tool(ArchitectureDelta)["function"]["parameters"]
    assert set(tool["properties"]) == {
        "updated_services",
        "added_services",
        "removed_services",
        "data_flow",
        "summary",
        "change_log",
    }
    assert not tool.get("required")
    assert list(Architecture.model_fields) == ["summary", "services", "data_flow", "version", "change_log"]


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------


def test_an_empty_delta_keeps_everything_as_an_independent_copy():
    previous = _previous()
    merged = apply_delta(previous, ArchitectureDelta())

    assert merged.services == previous.services and merged.data_flow == previous.data_flow
    assert merged.summary == previous.summary and merged.version == 2
    assert merged.change_log == []  # the change_log is the revision's own
    merged.services[0].purpose = "mutated"
    assert previous.services[0].purpose != "mutated"


def test_update_replaces_one_entry_in_place_and_keeps_the_rest():
    previous = _previous()
    new_aurora = previous.services[2].model_copy(update={"purpose": "Orders, with read replicas for catalog reads"})

    merged = apply_delta(
        previous,
        ArchitectureDelta(
            updated_services=[ServiceUpdate(id=" s3 ", service=new_aurora)],  # IDs are trimmed and case-insensitive
            change_log=["Added Aurora read replicas for catalog reads."],
        ),
    )

    assert [s.name for s in merged.services] == [s.name for s in previous.services]
    assert merged.services[2] == new_aurora
    assert merged.services[:2] == previous.services[:2] and merged.services[3] == previous.services[3]
    assert merged.change_log == ["Added Aurora read replicas for catalog reads."]


def test_additions_are_appended():
    merged = apply_delta(_previous(), ArchitectureDelta(added_services=[SECRETS]))
    assert merged.services[-1] == SECRETS and len(merged.services) == 5


def test_data_flow_and_summary_are_replaced_only_when_sent():
    previous = _previous()
    assert apply_delta(previous, ArchitectureDelta(data_flow=[], summary="  ")).data_flow == previous.data_flow
    replaced = apply_delta(previous, ArchitectureDelta(data_flow=NEW_FLOW, summary="New multi-AZ summary."))
    assert replaced.data_flow == NEW_FLOW and replaced.summary == "New multi-AZ summary."


def test_a_removal_is_recorded_with_its_reason():
    previous = _previous()
    merged = apply_delta(
        previous, ArchitectureDelta(removed_services=[ServiceRemoval(id="S4", reason="DynamoDB DAX now caches reads.")])
    )

    assert "Amazon ElastiCache" not in [s.name for s in merged.services]
    assert merged.change_log == ["Removed Amazon ElastiCache because DynamoDB DAX now caches reads."]


def test_a_removal_already_justified_in_the_change_log_is_not_repeated():
    entry = "Removed ElastiCache because DAX now caches reads."
    merged = apply_delta(
        _previous(),
        ArchitectureDelta(removed_services=[ServiceRemoval(id="S4", reason="DAX caches reads")], change_log=[entry]),
    )
    assert merged.change_log == [entry]


# ---------------------------------------------------------------------------
# Invalid deltas are rejected, never guessed
# ---------------------------------------------------------------------------


def test_unknown_ids_are_rejected():
    problems = _problems(
        _previous(),
        ArchitectureDelta(
            updated_services=[ServiceUpdate(id="S9", service=SECRETS)],
            removed_services=[ServiceRemoval(id="ECS", reason="x")],
        ),
    )
    assert problems == ["updated unknown service ID 'S9'", "removed unknown service ID 'ECS'"]


def test_the_same_id_cannot_be_changed_twice():
    previous = _previous()
    twice = ArchitectureDelta(
        updated_services=[ServiceUpdate(id="S2", service=previous.services[1]), ServiceUpdate(id="S2", service=SECRETS)]
    )
    assert _problems(previous, twice) == ["service S2 is updated and updated in the same revision"]
    both = ArchitectureDelta(
        updated_services=[ServiceUpdate(id="S2", service=previous.services[1])],
        removed_services=[ServiceRemoval(id="S2", reason="x")],
    )
    assert _problems(previous, both) == ["service S2 is updated and removed in the same revision"]


def test_a_removal_needs_a_reason():
    problems = _problems(_previous(), ArchitectureDelta(removed_services=[ServiceRemoval(id="S4", reason="  ")]))
    assert problems == ["removal of S4 (Amazon ElastiCache) has no reason"]


def test_duplicate_names_are_rejected():
    duplicate = make_architecture().services[1].model_copy(update={"purpose": "Second ECS"})
    problems = _problems(_previous(), ArchitectureDelta(added_services=[duplicate]))
    assert problems == ["two service entries are named 'Amazon ECS'"]


def test_a_removed_service_still_named_in_the_design_is_rejected():
    # The data flow still routes through the "ALB" / "load balancer" that S1 removes.
    problems = _problems(
        _previous(),
        ArchitectureDelta(removed_services=[ServiceRemoval(id="S1", reason="API Gateway replaces it")]),
    )
    assert len(problems) == 1
    assert problems[0].startswith("removed S1 (Application Load Balancer) is still named in the design")

    # Sending a data flow that no longer names it makes the removal valid.
    merged = apply_delta(
        _previous(),
        ArchitectureDelta(removed_services=[ServiceRemoval(id="S1", reason="API Gateway replaces it")], data_flow=NEW_FLOW),
    )
    assert "Application Load Balancer" not in [s.name for s in merged.services]


def test_a_name_shared_with_a_kept_service_is_not_stale():
    replica = AWSService(name="Aurora Global Database", category="Database", purpose="Cross-region replica",
                         justification="DR, snapshots copied cross-region")
    previous = _previous(services=[*make_architecture().services, replica])
    # The kept "Amazon Aurora" entry still says Aurora: that's not a stale reference to the replica.
    merged = apply_delta(previous, ArchitectureDelta(removed_services=[ServiceRemoval(id="S5", reason="single region")]))
    assert [s.name for s in merged.services][-1] == "Amazon ElastiCache"


# ---------------------------------------------------------------------------
# The merged design goes through the existing checks unchanged
# ---------------------------------------------------------------------------


def test_services_the_delta_does_not_mention_can_no_longer_be_dropped():
    previous = _previous(services=[*make_architecture().services, SECRETS])
    merged = apply_delta(previous, ArchitectureDelta(change_log=["Added nothing."]))
    assert check_revision(previous, merged, make_requirements()) == []


def test_an_explicit_removal_is_justified_for_the_guard():
    previous = _previous(services=[*make_architecture().services, SECRETS])
    merged = apply_delta(
        previous, ArchitectureDelta(removed_services=[ServiceRemoval(id="S5", reason="IAM roles replace stored keys")])
    )

    regressions = check_revision(previous, merged, make_requirements())
    assert regressions and blocking(regressions) == []  # reported, and justified by the recorded reason


def test_an_update_that_drops_backups_is_still_a_blocking_regression():
    previous = _previous()
    no_backups = previous.services[2].model_copy(update={"justification": "Relational, multi-AZ, encrypted via KMS"})
    merged = apply_delta(previous, ArchitectureDelta(updated_services=[ServiceUpdate(id="S3", service=no_backups)]))

    assert [i.rule for i in validate_architecture(merged, make_requirements()).issues] == ["database_without_backups"]
    assert "database_without_backups" in [r.item for r in blocking(check_revision(previous, merged, make_requirements()))]


# ---------------------------------------------------------------------------
# delta_between: the inverse, for tests and benchmarks
# ---------------------------------------------------------------------------


def test_delta_between_round_trips_a_full_revision():
    previous = _previous()
    new_aurora = previous.services[2].model_copy(update={"purpose": "Orders with read replicas"})
    target = make_architecture(
        summary="A revised multi-AZ design.",
        services=[previous.services[0], previous.services[1], new_aurora, SECRETS],  # ElastiCache removed
        data_flow=NEW_FLOW,
        change_log=["Removed ElastiCache because DAX caches reads.", "Added Secrets Manager."],
    )

    delta = delta_between(previous, target)

    assert [u.id for u in delta.updated_services] == ["S3"]
    assert [s.name for s in delta.added_services] == ["AWS Secrets Manager"]
    assert [r.id for r in delta.removed_services] == ["S4"]
    merged = apply_delta(previous, delta)
    assert (merged.summary, merged.services, merged.data_flow) == (target.summary, target.services, target.data_flow)
    assert merged.change_log == target.change_log  # the removal was already justified


def test_delta_between_unchanged_design_is_empty():
    previous = _previous()
    delta = delta_between(previous, previous.model_copy(update={"change_log": []}))
    assert delta == ArchitectureDelta()


def test_re_sending_an_identical_entry_is_ignored():
    # A correction that repeats its attempt's addition word for word changes nothing.
    previous = _previous(services=[*make_architecture().services, SECRETS])
    merged = apply_delta(previous, ArchitectureDelta(added_services=[SECRETS, SECRETS]))
    assert merged.services == previous.services
    # A *different* entry under an existing name is still ambiguous.
    changed = SECRETS.model_copy(update={"purpose": "Something else"})
    assert _problems(previous, ArchitectureDelta(added_services=[changed])) == [
        "two service entries are named 'AWS Secrets Manager'"
    ]

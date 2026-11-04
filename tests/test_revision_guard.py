"""Tests for revision regression protection, cumulative critic feedback,
re-validation after each revision, and explicit vs inferred requirements.

The LLM is always mocked; nothing reaches a provider.
"""

from __future__ import annotations


from agents import critic as critic_agent
from agents import llm as llm_module
from agents import requirements as requirements_agent
from agents import revision as revision_agent
from graph.observability import current_node
from graph.state import MAX_REVISIONS, create_initial_state
from graph.workflow import run_workflow
from models.schemas import AWSService, Architecture, CriticReview, Requirements
from tools.architecture_validator import validate_architecture
from tools.revision_guard import blocking, check_revision

from .conftest import (
    make_analysis,
    make_architecture,
    make_cost_analysis,
    make_critic_review,
    make_requirements,
)
from .test_graph import _FakeToolCallingLLM, _dummy_for_schema

SECRETS = AWSService(
    name="AWS Secrets Manager",
    category="Security",
    purpose="Stores DB and payment-gateway credentials with automatic rotation",
    justification="Keeps credentials out of code for PCI-DSS",
)
CROSS_REGION_DR = AWSService(
    name="Aurora Global Database",
    category="Database",
    purpose="Cross-region replica in a secondary region for disaster recovery",
    justification="RTO 15 min, RPO 5 min if the primary region fails",
)

ROUND_0 = CriticReview(
    approved=False,
    score=58,
    issues=[{"issue": "No secrets management for credentials.", "severity": "high", "category": "security"}],
    required_changes=["Add AWS Secrets Manager for DB and payment-gateway credentials."],
)
ROUND_1 = CriticReview(
    approved=False,
    score=68,
    issues=[{"issue": "No cross-region DR plan.", "severity": "high", "category": "reliability"}],
    required_changes=["Add a cross-region Aurora replica with documented RTO/RPO."],
)


def _architecture(*extra: AWSService, **overrides) -> Architecture:
    base = make_architecture()
    return make_architecture(services=[*base.services, *extra], **overrides)


def _v2() -> Architecture:
    """Revision 1's result: added Secrets Manager and cross-region DR."""
    return _architecture(
        SECRETS,
        CROSS_REGION_DR,
        version=2,
        change_log=["Added Secrets Manager for credentials.", "Added cross-region Aurora replica for DR."],
    )


def _revision_state(**overrides) -> dict:
    state = create_initial_state("Design an e-commerce platform.")
    state.update(
        requirements=make_requirements(),
        architecture=_v2(),
        critic_review=ROUND_1,
        critic_history=[ROUND_0, ROUND_1],
        implemented_changes=["v2: Added Secrets Manager for credentials.", "v2: Added cross-region Aurora replica for DR."],
        revision_count=1,
        validation_results=validate_architecture(_v2(), make_requirements()),
    )
    state.update(overrides)
    return state


def _script_revisions(monkeypatch, *architectures: Architecture | BaseException) -> list[str]:
    """Each revision LLM call returns (or raises) the next item; prompts are recorded."""
    remaining = list(architectures)
    prompts: list[str] = []

    def fake_invoke_structured(llm, schema, prompt):
        prompts.append(prompt)
        item = remaining.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item.model_copy(deep=True)

    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
    monkeypatch.setattr(llm_module, "invoke_structured", fake_invoke_structured)
    return prompts


def _names(architecture: Architecture) -> list[str]:
    return [s.name for s in architecture.services]


# ---------------------------------------------------------------------------
# The deterministic guard
# ---------------------------------------------------------------------------


class TestRevisionGuard:
    def test_no_regressions_for_an_unchanged_or_extended_architecture(self):
        v2 = _v2()

        assert check_revision(v2, v2, make_requirements()) == []
        assert check_revision(make_architecture(), v2, make_requirements()) == []

    def test_removed_security_control_is_detected(self):
        regressions = check_revision(_v2(), _architecture(CROSS_REGION_DR), make_requirements())

        assert [(r.kind, r.item) for r in blocking(regressions)] == [
            ("removed_service", "secrets manager"),
            ("lost_capability", "secrets management"),
        ]
        assert regressions[1].category == "security"

    def test_removed_availability_controls_are_detected(self):
        single_az = make_architecture(
            summary="A containerized architecture with a caching layer.",
            services=[
                AWSService(name="Amazon ECS", category="Compute", purpose="Run services", justification="Containers"),
                *make_architecture().services[2:],
            ],
            data_flow=[],
        )

        lost = {r.item for r in blocking(check_revision(make_architecture(), single_az, make_requirements()))
                if r.category == "availability"}

        assert {"load balancing", "auto scaling"} <= lost

    def test_per_az_nat_replaced_by_shared_nat_without_reason_is_a_networking_regression(self):
        per_az = make_architecture(summary="Multi-AZ design with one NAT gateway per AZ and a caching layer.")
        shared = make_architecture(
            summary="Multi-AZ design with a shared NAT gateway and a caching layer.",
            change_log=["Switched to a shared NAT gateway."],
        )

        (regression,) = blocking(check_revision(per_az, shared, make_requirements()))

        assert (regression.category, regression.item) == ("networking", "per-AZ NAT gateways")

    def test_new_missing_database_backups_is_detected_and_cannot_be_justified(self):
        without_backups = make_architecture()
        aurora = without_backups.services[2]
        aurora.justification = "Relational, multi-AZ, encrypted at rest via KMS, isolated in a private subnet"
        without_backups.change_log = ["Removed backups because snapshots are costly."]

        regressions = check_revision(make_architecture(), without_backups, make_requirements())

        new_issue = next(r for r in regressions if r.kind == "new_validator_issue")
        assert (new_issue.item, new_issue.category, new_issue.justified) == ("database_without_backups", "backups", False)
        assert new_issue in blocking(regressions)

    def test_removal_with_an_explicit_reason_is_justified(self):
        parameter_store = AWSService(
            name="AWS Systems Manager Parameter Store",
            category="Security",
            purpose="Encrypted SecureString parameters for credentials",
            justification="Cheaper for this workload",
        )
        revised = _architecture(
            CROSS_REGION_DR,
            parameter_store,
            change_log=["Replaced Secrets Manager with SSM Parameter Store to cut cost for this workload."],
        )

        regressions = check_revision(_v2(), revised, make_requirements())

        removed = next(r for r in regressions if r.kind == "removed_service")
        assert removed.justified and "Parameter Store" in removed.justification
        # "parameter store" itself still counts as secrets management, so no capability was lost.
        assert not any(r.item == "secrets management" for r in regressions)

    def test_announcing_a_removal_without_a_reason_is_not_a_justification(self):
        revised = _architecture(CROSS_REGION_DR, change_log=["Removed Secrets Manager."])

        assert any(r.item == "secrets manager" for r in blocking(check_revision(_v2(), revised, make_requirements())))

    def test_lost_capability_is_reported_against_the_critic_requirement_it_satisfied(self):
        regressions = check_revision(
            _v2(), _architecture(SECRETS), make_requirements(), prior_required_changes=ROUND_1.required_changes
        )

        dr = next(r for r in regressions if r.item == "cross-region disaster recovery")
        assert dr.category == "disaster_recovery"
        assert dr.related_requirements == ROUND_1.required_changes

    def test_merging_services_into_one_entry_is_not_a_removal(self):
        before = make_architecture(
            services=[*make_architecture().services, AWSService(name="Amazon SQS", category="Messaging", purpose="q", justification="j")]
        )
        merged = make_architecture(
            services=[
                *make_architecture().services[:3],
                AWSService(name="Amazon ElastiCache + SQS", category="Storage", purpose="Redis cache and queue", justification="j"),
            ]
        )

        assert check_revision(before, merged, make_requirements()) == []

    def test_short_terms_match_whole_words_only(self):
        with_rto = make_architecture(summary=make_architecture().summary + " RTO 15 min.")
        protocol_only = make_architecture(summary=make_architecture().summary + " Uses a binary protocol.")

        assert [r.item for r in check_revision(with_rto, protocol_only, make_requirements())] == ["RTO/RPO targets"]


# ---------------------------------------------------------------------------
# The revision agent: cumulative feedback and regression protection
# ---------------------------------------------------------------------------


class TestRevisionAgent:
    def test_prompt_carries_all_reviews_implemented_changes_and_outstanding_issues(self, monkeypatch):
        prompts = _script_revisions(monkeypatch, _architecture(SECRETS, CROSS_REGION_DR))

        revision_agent.run(_revision_state())

        (prompt,) = prompts
        assert "Round 0: REJECTED, score 58/100. Required changes: Add AWS Secrets Manager" in prompt
        assert "Round 1: REJECTED, score 68/100. Required changes: Add a cross-region Aurora replica" in prompt
        assert "- v2: Added Secrets Manager for credentials." in prompt
        assert "[high] No cross-region DR plan." in prompt  # outstanding issues from the latest review
        assert "Deterministic validator findings: none." in prompt
        assert "Removed <X> because <reason>" in prompt

    def test_revision_2_keeps_secrets_manager_from_revision_1(self, monkeypatch):
        dropped = _architecture(CROSS_REGION_DR, change_log=["Added Route 53 failover."])
        kept = _architecture(SECRETS, CROSS_REGION_DR, change_log=["Added Route 53 failover."])
        prompts = _script_revisions(monkeypatch, dropped, kept)

        result = revision_agent.run(_revision_state())

        assert "AWS Secrets Manager" in _names(result["architecture"])
        assert result["architecture"].version == 3
        assert len(prompts) == 2  # one corrective attempt
        assert "removed service 'secrets manager'" in prompts[1]
        assert "lost security capability 'secrets management'" in prompts[1]
        assert "was corrected" in result["execution_trace"][0]["action"]
        # Route 53 is only named in the change_log, not in the design: a proposal, not an implemented change.
        assert result["implemented_changes"] == []
        assert result["architecture"].change_log == ["Not implemented (proposed only): Added Route 53 failover."]

    def test_revision_that_keeps_regressing_is_not_accepted(self, monkeypatch):
        dropped = _architecture(CROSS_REGION_DR)
        _script_revisions(monkeypatch, dropped, dropped)

        result = revision_agent.run(_revision_state())

        assert result["architecture"].version == 2  # the current architecture is kept
        assert "AWS Secrets Manager" in _names(result["architecture"])
        assert result["revision_count"] == 2  # max-revision protection still advances
        assert result["implemented_changes"] == []
        assert result["execution_trace"][0]["action"].startswith("Rejected the revised architecture as a regression")

    def test_revision_2_keeps_cross_region_dr_unless_explicitly_justified(self, monkeypatch):
        unjustified = _architecture(SECRETS)
        justified = _architecture(
            SECRETS,
            change_log=[
                "Replaced cross-region replica (Aurora Global Database) with multi-AZ plus backups "
                "because the user did not require multi-region and RTO/RPO is met in-region."
            ],
        )
        prompts = _script_revisions(monkeypatch, unjustified, justified)

        result = revision_agent.run(_revision_state())

        assert "lost disaster recovery capability 'cross-region disaster recovery'" in prompts[1]
        assert result["architecture"].version == 3  # accepted: the removal is now explicit and reasoned
        action = result["execution_trace"][0]["action"]
        assert "Justified removals:" in action and "cross-region disaster recovery" in action

    def test_cross_region_dr_dropped_without_justification_is_kept(self, monkeypatch):
        _script_revisions(monkeypatch, _architecture(SECRETS), _architecture(SECRETS))

        result = revision_agent.run(_revision_state())

        assert "Aurora Global Database" in _names(result["architecture"])

    def test_failed_corrective_call_keeps_the_current_architecture(self, monkeypatch):
        _script_revisions(monkeypatch, _architecture(CROSS_REGION_DR), llm_module.LLMInvocationError("x"))

        result = revision_agent.run(_revision_state())

        assert result["architecture"].version == 2
        assert "Revision call failed" in result["execution_trace"][0]["action"]

    def test_works_without_history_in_state(self, monkeypatch):
        # Older callers/states without critic_history or implemented_changes.
        prompts = _script_revisions(monkeypatch, make_architecture())
        state = _revision_state(architecture=make_architecture(), critic_review=ROUND_0)
        del state["critic_history"], state["implemented_changes"]

        result = revision_agent.run(state)

        assert result["architecture"].version == 2
        assert "Round 0: REJECTED, score 58/100" in prompts[0]  # the latest review is the history
        assert "None yet (this is the first revision)." in prompts[0]


# ---------------------------------------------------------------------------
# Full workflow: history accumulates, every revision is re-validated
# ---------------------------------------------------------------------------


def _patch_workflow(monkeypatch, architecture_for, critic_reviews: list[CriticReview]) -> dict:
    calls = {"critic": 0, "revision_prompts": []}

    def fake_invoke_structured(llm, schema, prompt):
        if schema is Architecture:
            if current_node() == "architecture_revision":
                calls["revision_prompts"].append(prompt)
            return architecture_for(current_node()).model_copy(deep=True)
        if schema is CriticReview:
            review = critic_reviews[min(calls["critic"], len(critic_reviews) - 1)]
            calls["critic"] += 1
            return review
        return _dummy_for_schema(schema, [True], {"critic_calls": 0})

    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: _FakeToolCallingLLM())
    monkeypatch.setattr(llm_module, "invoke_structured", fake_invoke_structured)
    return calls


def test_every_revision_is_revalidated_against_the_latest_architecture(monkeypatch):
    without_cache = make_architecture(services=make_architecture().services[:3])  # fails missing_caching_layer
    assert [i.rule for i in validate_architecture(without_cache, make_requirements()).issues] == ["missing_caching_layer"]
    _patch_workflow(
        monkeypatch,
        lambda node: without_cache if node == "architecture_designer" else make_architecture(),
        [make_critic_review(approved=False), make_critic_review(approved=True)],
    )

    final_state = run_workflow("Design an e-commerce platform for 500,000 concurrent users.")

    assert final_state["architecture"].version == 2
    assert final_state["validation_results"].passed is True  # v2's result, not v1's
    validator_runs = [e for e in final_state["execution_trace"] if e["node"] == "Architecture Validator"]
    assert [(e["iteration"], e["output_summary"]) for e in validator_runs] == [
        (0, "missing_caching_layer"),
        (1, "No deterministic issues found."),
    ]
    order = [e["node"] for e in final_state["execution_trace"]]
    revision_at = order.index("Architecture Revision")
    assert order[revision_at + 1 : revision_at + 3] == ["Architecture Validator", "Architecture Critic"]


def test_second_revision_sees_the_first_rounds_feedback_and_changes(monkeypatch):
    # make_architecture() contains KMS encryption but no read replicas, so the
    # first request is implemented by the revision and the second is not.
    asks = ["Round 0 change: add KMS encryption at rest.", "Round 1 change: add Aurora read replicas.", "Round 2 change."]
    reviews = [
        CriticReview(approved=False, score=50 + n, required_changes=[asks[n]]) for n in range(MAX_REVISIONS + 1)
    ]
    calls = _patch_workflow(monkeypatch, lambda node: make_architecture(), reviews)

    final_state = run_workflow("Design a banking system.")

    assert [r.score for r in final_state["critic_history"]] == [50, 51, 52]
    assert final_state["critic_review"].score == 52
    first, second = calls["revision_prompts"]
    assert "Round 0 change" in first and "Round 1 change" not in first
    assert "Round 0: REJECTED, score 50/100. Required changes: Round 0 change" in second
    assert "- v2: Round 0 change: add KMS encryption at rest." in second  # implemented in revision 1
    # Only the verified change is recorded; the read replicas were never added to the design.
    assert final_state["implemented_changes"] == ["v2: Round 0 change: add KMS encryption at rest."]
    assert final_state["architecture"].change_log == [
        "Not implemented (proposed only): Round 1 change: add Aurora read replicas."
    ]


def test_approved_first_time_workflow_is_unchanged(monkeypatch):
    _patch_workflow(monkeypatch, lambda node: make_architecture(), [make_critic_review(approved=True)])

    final_state = run_workflow("Design a blogging platform.")

    assert final_state["revision_count"] == 0
    nodes = [e["node"] for e in final_state["execution_trace"]]
    assert nodes.count("Architecture Validator") == 1 and "Architecture Revision" not in nodes
    assert len(final_state["critic_history"]) == 1 and final_state["implemented_changes"] == []


# ---------------------------------------------------------------------------
# Explicit vs inferred requirements
# ---------------------------------------------------------------------------


class TestRequirementProvenance:
    def test_requirements_without_provenance_fields_still_load(self):
        stored = make_requirements().model_dump(exclude={"explicit_requirements", "inferred_assumptions"})

        loaded = Requirements(**stored)

        assert loaded.explicit_requirements == [] and loaded.inferred_assumptions == []

    def test_requirements_prompt_separates_stated_from_assumed(self, monkeypatch):
        prompts: list[str] = []
        monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
        monkeypatch.setattr(
            llm_module, "invoke_structured", lambda llm, schema, prompt: prompts.append(prompt) or make_requirements()
        )

        requirements_agent.run({"user_request": "An e-commerce site with high availability."})

        (prompt,) = prompts
        assert "explicit_requirements: only what the user actually stated" in prompt
        assert "inferred_assumptions: everything you inferred instead" in prompt
        assert 'do not\n  turn "high availability" into "multi-region"' in prompt

    def test_critic_gets_provenance_and_inferred_items_cannot_block_alone(self, monkeypatch):
        prompts: list[str] = []
        monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
        monkeypatch.setattr(
            llm_module, "invoke_structured", lambda llm, schema, prompt: prompts.append(prompt) or make_critic_review(True)
        )
        requirements = make_requirements(
            explicit_requirements=["High availability", "500,000 concurrent users"],
            inferred_assumptions=["Multi-region redundancy"],
        )
        state = create_initial_state("x")
        state.update(
            requirements=requirements,
            architecture=make_architecture(),
            **{f"{d}_analysis": make_analysis(d) for d in ("compute", "database", "networking", "security", "reliability")},
            cost_analysis=make_cost_analysis(),
        )

        result = critic_agent.run(state)

        (prompt,) = prompts
        assert '"inferred_assumptions":["Multi-region redundancy"]' in prompt
        assert "explicit_requirements are what the user\nactually asked for" in prompt
        assert "multi-region deployment\n  when the user did not ask for it) is at most medium" in prompt
        assert "must not block approval" in prompt
        assert result["critic_history"] == [result["critic_review"]]

    def test_api_response_includes_provenance_additively(self, monkeypatch):
        from .test_graph import _patch_llm

        _patch_llm(monkeypatch, critic_verdicts=[True])
        from api.schemas import ArchitectureResponse

        response = ArchitectureResponse.from_state(run_workflow("Design a blogging platform.")).model_dump()

        assert response["requirements"]["explicit_requirements"] == []  # new, optional fields
        assert {"approved", "architecture", "critic_review", "validation_results", "execution_trace"} <= set(response)
        assert "critic_history" not in response and "implemented_changes" not in response  # API shape unchanged

"""Architecture correctness: verified changes, alias-aware regression checks,
reports that describe only the real design, no redundant critic calls, and
the 8th-service rule.

The LLM is always mocked; nothing reaches a provider.
"""

from __future__ import annotations

import json

from langchain_core.utils.function_calling import convert_to_openai_tool

from agents import critic as critic_agent
from agents import llm as llm_module
from agents import report as report_agent
from agents import revision as revision_agent
from graph.observability import current_node
from graph.state import MAX_REVISIONS, create_initial_state
from graph.workflow import run_workflow
from models.schemas import AWSService, Architecture, CriticReview, DataFlowStep, FinalReport
from tools.architecture_facts import (
    IMPLEMENTED,
    NOT_IMPLEMENTED_PREFIX,
    PROPOSED,
    REMOVED,
    UNVERIFIED,
    mentions,
    pending_requests,
    verify_change,
)
from tools.architecture_validator import validate_architecture
from tools.revision_guard import blocking, check_revision

from .conftest import (
    make_analysis,
    make_architecture,
    make_cost_analysis,
    make_final_report,
    make_requirements,
)
from .test_graph import _FakeToolCallingLLM, _dummy_for_schema
from .test_revision_guard import SECRETS, _script_revisions

ELASTICACHE_REDIS = AWSService(
    name="Amazon ElastiCache (Redis)",
    category="Caching",
    purpose="In-memory cache for catalog reads and sessions",
    justification="Keeps catalog latency low under read-heavy load",
)
DYNAMODB = AWSService(
    name="Amazon DynamoDB",
    category="Database",
    purpose="Catalog, session and cart data at single-digit ms",
    justification="Offloads high-volume catalog reads from Aurora; point-in-time recovery enabled",
)
ADD_SECRETS = CriticReview(
    approved=False,
    score=60,
    issues=[{"issue": "Credentials are not managed.", "severity": "high", "category": "security"}],
    required_changes=["Add AWS Secrets Manager for DB credentials."],
)
ADD_DYNAMODB = CriticReview(
    approved=False,
    score=70,
    issues=[{"issue": "Catalog reads overload Aurora.", "severity": "high", "category": "scalability"}],
    required_changes=["Add DynamoDB for catalog and session reads."],
)


def _with(*services: AWSService, base: Architecture | None = None, **overrides) -> Architecture:
    base = base or make_architecture()
    return make_architecture(services=[*base.services, *services], **overrides)


def _state(architecture: Architecture, review: CriticReview, **overrides) -> dict:
    state = create_initial_state("Design an e-commerce platform.")
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


def _seven_services() -> Architecture:
    """A design already at the 7-service limit, like job dec849c9's v2."""
    extra = [
        AWSService(name="Amazon CloudFront + AWS WAF", category="Networking", purpose="CDN and WAF", justification="j"),
        AWSService(name="Amazon SQS", category="Messaging", purpose="Queue order writes", justification="j"),
        AWSService(name="Amazon S3", category="Storage", purpose="Encrypted media storage", justification="j"),
    ]
    return _with(*extra, version=2)


# ---------------------------------------------------------------------------
# 1. Verified implemented changes
# ---------------------------------------------------------------------------


class TestChangeVerification:
    def test_claimed_secrets_manager_without_adding_it_is_never_implemented(self, monkeypatch):
        # The model says it added the requested Secrets Manager, but the design
        # doesn't contain it -- not even after the one corrective attempt.
        claimed_only = _with(change_log=["Added AWS Secrets Manager for DB credentials."])
        prompts = _script_revisions(monkeypatch, claimed_only, claimed_only)

        result = revision_agent.run(_state(make_architecture(), ADD_SECRETS))

        assert len(prompts) == 2
        assert result["implemented_changes"] == []
        assert result["architecture"].version == 1  # not accepted
        assert "Secrets Manager" not in json.dumps(result["architecture"].model_dump())
        assert "claimed only in change_log" in result["execution_trace"][0]["action"]

    def test_an_unrequested_claim_is_only_marked_proposed(self, monkeypatch):
        # Nobody asked for Route 53: the claim doesn't block, it is just not counted.
        claimed_only = _with(change_log=["Added Route 53 failover."])
        prompts = _script_revisions(monkeypatch, claimed_only)

        result = revision_agent.run(_state(make_architecture(), ADD_SECRETS))

        assert len(prompts) == 1
        assert result["implemented_changes"] == []
        assert result["architecture"].change_log == [NOT_IMPLEMENTED_PREFIX + "Added Route 53 failover."]
        assert "0 implemented or removed, 1 proposed only" in result["execution_trace"][0]["action"]

    def test_next_revision_is_told_the_proposal_is_still_pending(self, monkeypatch):
        v2 = _with(version=2, change_log=[NOT_IMPLEMENTED_PREFIX + "Added AWS Secrets Manager for DB credentials."])
        prompts = _script_revisions(monkeypatch, _with(SECRETS))

        revision_agent.run(_state(v2, ADD_DYNAMODB, critic_history=[ADD_SECRETS, ADD_DYNAMODB], revision_count=1))

        (prompt,) = prompts
        pending = prompt.split("Still pending")[1].split("Outstanding issues")[0]
        assert "- Add AWS Secrets Manager for DB credentials." in pending  # the earlier critic request
        assert "- Added AWS Secrets Manager for DB credentials." in pending  # the unimplemented claim
        implemented = prompt.split("Previously implemented changes")[1].split("Still pending")[0]
        assert "Secrets Manager" not in implemented  # never presented as already present

    def test_verified_implementation_is_recorded(self, monkeypatch):
        _script_revisions(monkeypatch, _with(SECRETS, change_log=["Added AWS Secrets Manager for DB credentials."]))

        result = revision_agent.run(_state(make_architecture(), ADD_SECRETS))

        assert result["implemented_changes"] == ["v2: Added AWS Secrets Manager for DB credentials."]
        assert result["architecture"].change_log == ["Added AWS Secrets Manager for DB credentials."]

    def test_implemented_proposed_and_removed_are_distinguished(self, monkeypatch):
        v2 = _with(SECRETS, version=2)
        revised = _with(
            DYNAMODB,
            change_log=[
                "Added DynamoDB for catalog reads.",
                "Added Cognito MFA for customer logins.",
                "Removed AWS Secrets Manager because credentials moved to IAM database auth.",
            ],
        )
        _script_revisions(monkeypatch, revised)

        result = revision_agent.run(_state(v2, ADD_DYNAMODB))

        assert result["implemented_changes"] == [
            "v3: Added DynamoDB for catalog reads.",
            "v3 (intentional removal): Removed AWS Secrets Manager because credentials moved to IAM database auth.",
        ]
        assert result["architecture"].change_log[1] == NOT_IMPLEMENTED_PREFIX + "Added Cognito MFA for customer logins."

    def test_unimplemented_critic_request_remains_pending(self):
        assert pending_requests(ADD_DYNAMODB.required_changes, make_architecture()) == ADD_DYNAMODB.required_changes
        assert pending_requests(ADD_DYNAMODB.required_changes, _with(DYNAMODB)) == []

    def test_reason_clause_is_not_a_claim(self):
        # "to offload Aurora and Redis" names services the change doesn't add.
        check = verify_change("Added DynamoDB to offload Aurora and Redis.", make_architecture())
        assert (check.status, check.missing) == (PROPOSED, ["Amazon DynamoDB"])
        assert verify_change("Added DynamoDB to offload Aurora and Redis.", _with(DYNAMODB)).status == IMPLEMENTED

    def test_replacement_checks_the_new_service_and_removals_check_absence(self):
        assert verify_change("Replaced Redis with DynamoDB to cut cost.", _with(DYNAMODB)).status == IMPLEMENTED
        assert verify_change("Removed AWS Secrets Manager because it was unused.", make_architecture()).status == REMOVED
        assert verify_change("Removed AWS Secrets Manager because it was unused.", _with(SECRETS)).status == PROPOSED

    def test_change_naming_nothing_checkable_is_unverified(self):
        assert verify_change("Split the API into two services.", make_architecture()).status == UNVERIFIED


# ---------------------------------------------------------------------------
# 2. Alias-aware, plural-tolerant regression guard
# ---------------------------------------------------------------------------


class TestGuardAliases:
    def test_elasticache_recognised_as_redis(self):
        before = _with(ELASTICACHE_REDIS)
        renamed = _with()  # base already has "Amazon ElastiCache" ...
        renamed.services = [s for s in renamed.services if "ElastiCache" not in s.name] + [
            AWSService(name="Redis cache (multi-AZ)", category="Caching", purpose="Catalog cache", justification="j")
        ]

        assert check_revision(before, renamed, make_requirements()) == []

    def test_merging_redis_with_dynamodb_is_not_a_removal(self):
        merged = make_architecture(
            services=[
                *make_architecture().services[:3],
                AWSService(
                    name="Amazon ElastiCache (Redis) + Amazon DynamoDB",
                    category="Database",
                    purpose="Redis cache plus DynamoDB catalog store",
                    justification="DynamoDB point-in-time recovery enabled",
                ),
            ]
        )

        assert check_revision(make_architecture(), merged, make_requirements()) == []

    def test_rds_renamed_to_aurora_is_not_a_removal(self):
        rds = make_architecture()
        rds.services[2] = rds.services[2].model_copy(update={"name": "Amazon RDS (Aurora)"})
        aurora = make_architecture()  # "Amazon Aurora"

        assert check_revision(rds, aurora, make_requirements()) == []

    def test_redis_swapped_for_dynamodb_with_a_reason_is_justified(self):
        swapped = make_architecture(
            summary="A load-balanced, auto-scaling, multi-AZ architecture with defense-in-depth security controls.",
            services=[*make_architecture().services[:3], DYNAMODB],
            change_log=["Replaced Redis with DynamoDB because it serves catalog and sessions."],
        )

        removed = next(r for r in check_revision(make_architecture(), swapped, make_requirements())
                       if r.kind == "removed_service")
        assert removed.item == "elasticache" and removed.justified  # "Redis" names the same service

    def test_genuinely_removed_cache_is_still_a_regression(self):
        no_cache = make_architecture(
            summary="A load-balanced, auto-scaling, multi-AZ architecture.",
            services=make_architecture().services[:3],
        )

        assert [(r.kind, r.item) for r in blocking(check_revision(make_architecture(), no_cache, make_requirements()))
                ][:1] == [("removed_service", "elasticache")]

    def test_backup_and_backups_are_the_same_capability(self):
        assert mentions("multi-AZ database with backups", "backup")
        assert mentions("one nightly backup", "backup")
        plural = make_architecture()
        plural.services[2].justification = "Relational, multi-AZ, with nightly backups, encrypted via KMS, private subnet"
        singular = make_architecture()
        singular.services[2].justification = "Relational, multi-AZ, with a nightly backup, encrypted via KMS, private subnet"

        assert check_revision(plural, singular, make_requirements()) == []
        assert check_revision(singular, plural, make_requirements()) == []

    def test_losing_backups_written_in_the_plural_is_detected(self):
        plural = make_architecture()
        plural.services[2].justification = "Relational, multi-AZ, with nightly backups, encrypted via KMS, private subnet"
        without = make_architecture()
        without.services[2].justification = "Relational, multi-AZ, encrypted via KMS, private subnet"

        items = {r.item for r in blocking(check_revision(plural, without, make_requirements()))}
        assert {"database backups", "database_without_backups"} <= items  # capability and validator both catch it

    def test_hyphen_and_space_variants_match(self):
        assert mentions("secondary-region warm-standby", "warm standby")
        assert mentions("RTO/RPO defined", "rpo")
        assert not mentions("a binary protocol", "rto")


# ---------------------------------------------------------------------------
# 3. Final report describes only the final architecture
# ---------------------------------------------------------------------------


def _report_state(architecture: Architecture, review: CriticReview, **overrides) -> dict:
    state = _state(architecture, review, revision_count=MAX_REVISIONS)
    state.update(
        compute_analysis=make_analysis("Compute"),
        database_analysis=make_analysis("Database").model_copy(
            update={"recommendations": ["Add DynamoDB for catalog reads.", "Use Aurora Global Database for DR."]}
        ),
        networking_analysis=make_analysis("Networking"),
        security_analysis=make_analysis("Security").model_copy(
            update={"recommendations": ["Use Cognito MFA and AWS Secrets Manager."]}
        ),
        reliability_analysis=make_analysis("Reliability"),
        cost_analysis=make_cost_analysis(),
    )
    state.update(overrides)
    return state


def _report_with(**fields) -> FinalReport:
    return make_final_report().model_copy(update=fields)


def _capture(monkeypatch, report: FinalReport) -> list[str]:
    prompts: list[str] = []
    monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
    monkeypatch.setattr(llm_module, "invoke_structured", lambda llm, schema, prompt: prompts.append(prompt) or report)
    return prompts


class TestFinalReport:
    def test_report_does_not_claim_absent_services(self, monkeypatch):
        llm_report = _report_with(
            aws_services_summary="ALB, ECS, Aurora, ElastiCache, plus DynamoDB for catalog/sessions.",
            security_summary="Cognito MFA, Secrets Manager, KMS encryption and WAF.",
            reliability_summary="Automated backups; Aurora Global Database cross-region replica; defined RTO/RPO.",
            architecture_overview="Multi-AZ ALB, ECS and Aurora with an ElastiCache layer. DynamoDB added for sessions.",
            bottlenecks=["Aurora write throughput at peak", "DynamoDB hot partitions"],
        )
        _capture(monkeypatch, llm_report)

        report = report_agent.run(_report_state(make_architecture(), ADD_DYNAMODB))["final_report"]

        claims = json.dumps(report.model_dump(exclude={"final_recommendations", "open_recommendations"}))
        for absent in ("DynamoDB", "Cognito", "Secrets Manager", "Global Database", "RTO"):
            assert absent not in claims
        assert report.architecture_overview == "Multi-AZ ALB, ECS and Aurora with an ElastiCache layer."
        assert report.reliability_summary == "Automated backups."
        assert report.security_summary.startswith("In the final architecture:")  # rebuilt from the design
        assert "AWS WAF" in report.security_summary and "AWS KMS" in report.security_summary
        assert report.bottlenecks == ["Aurora write throughput at peak"]

    def test_present_services_and_hedged_statements_are_kept(self, monkeypatch):
        llm_report = _report_with(
            aws_services_summary="ALB, ECS on auto scaling, Aurora with backups, ElastiCache (Redis).",
            critic_findings_summary="Rejected 70/100; DynamoDB for catalog reads remains an open follow-up.",
        )
        _capture(monkeypatch, llm_report)

        report = report_agent.run(_report_state(make_architecture(), ADD_DYNAMODB))["final_report"]

        assert report.aws_services_summary == llm_report.aws_services_summary
        assert "DynamoDB for catalog reads remains an open follow-up" in report.critic_findings_summary

    def test_recommendations_stay_separate_from_implemented_features(self, monkeypatch):
        architecture = _with(
            version=3, change_log=[NOT_IMPLEMENTED_PREFIX + "Added Cognito MFA for customer logins."]
        )
        llm_report = _report_with(final_recommendations=["Add DynamoDB for catalog reads."])
        prompts = _capture(monkeypatch, llm_report)
        state = _report_state(architecture, ADD_DYNAMODB, critic_history=[ADD_SECRETS, ADD_DYNAMODB])

        report = report_agent.run(state)["final_report"]

        assert report.open_recommendations == [
            "Add DynamoDB for catalog and session reads.",  # the final review's open request
            "Add AWS Secrets Manager for DB credentials.",  # an earlier request still not in the design
            "Added Cognito MFA for customer logins.",  # proposed in the change_log, never implemented
        ]
        assert report.final_recommendations == ["Add DynamoDB for catalog reads."]  # a recommendation, kept
        (prompt,) = prompts
        assert "Mentioned by the analyses or the critic but NOT in the final architecture: " in prompt
        absent_line = prompt.split("NOT in the final architecture: ")[1].splitlines()[0]
        assert "Amazon DynamoDB" in absent_line and "AWS Secrets Manager" in absent_line
        assert "Change log:" not in prompt  # claims are not shown as part of the design
        assert "never describe them as part of the design" in prompt

    def test_open_recommendations_is_not_generated_by_the_llm(self):
        parameters = convert_to_openai_tool(FinalReport)["function"]["parameters"]
        assert "open_recommendations" not in parameters["properties"]
        # Stored results from before the field existed still load.
        stored = make_final_report().model_dump(exclude={"open_recommendations"})
        assert FinalReport(**stored).open_recommendations == []

    def test_fallback_report_is_checked_too(self, monkeypatch):
        def failing(llm, schema, prompt):
            raise llm_module.LLMInvocationError("x")

        monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
        monkeypatch.setattr(llm_module, "invoke_structured", failing)
        requirements = make_requirements(security_requirements="Secrets Manager and Cognito MFA required")

        report = report_agent.run(_report_state(make_architecture(), ADD_DYNAMODB, requirements=requirements))[
            "final_report"
        ]

        assert "Cognito" not in report.security_summary and "Secrets Manager" not in report.security_summary
        assert report.open_recommendations == ADD_DYNAMODB.required_changes


# ---------------------------------------------------------------------------
# 4. No redundant critic calls on an unchanged architecture
# ---------------------------------------------------------------------------


def _critic_state(architecture: Architecture, **overrides) -> dict:
    state = _state(architecture, None)
    state.update(
        critic_review=None,
        critic_history=[],
        **{f"{d}_analysis": make_analysis(d) for d in ("compute", "database", "networking", "security", "reliability")},
        cost_analysis=make_cost_analysis(),
    )
    state.update(overrides)
    return state


class TestCriticReuse:
    def _count_calls(self, monkeypatch, outcome) -> list[str]:
        prompts: list[str] = []

        def fake(llm, schema, prompt):
            prompts.append(prompt)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: object())
        monkeypatch.setattr(llm_module, "invoke_structured", fake)
        return prompts

    def test_unchanged_architecture_reuses_the_previous_review(self, monkeypatch):
        prompts = self._count_calls(monkeypatch, ADD_DYNAMODB)
        state = _critic_state(make_architecture())
        first = critic_agent.run(state)
        state.update(critic_review=first["critic_review"], critic_input_hash=first["critic_input_hash"], revision_count=1)

        second = critic_agent.run(state)

        assert len(prompts) == 1
        assert second["critic_review"] is first["critic_review"]
        assert "critic_history" not in second  # not a new review
        assert "reused that review" in second["execution_trace"][0]["action"]

    def test_changed_architecture_is_reviewed_again(self, monkeypatch):
        prompts = self._count_calls(monkeypatch, ADD_DYNAMODB)
        state = _critic_state(make_architecture())
        first = critic_agent.run(state)
        state.update(
            architecture=_with(DYNAMODB, version=2),
            critic_review=first["critic_review"],
            critic_input_hash=first["critic_input_hash"],
        )

        critic_agent.run(state)

        assert len(prompts) == 2

    def test_a_failed_review_is_never_reused(self, monkeypatch):
        prompts = self._count_calls(monkeypatch, llm_module.LLMInvocationError("x"))
        state = _critic_state(make_architecture())
        first = critic_agent.run(state)
        assert first["critic_input_hash"] is None
        state.update(critic_review=first["critic_review"], critic_input_hash=first["critic_input_hash"])

        critic_agent.run(state)

        assert len(prompts) == 2

    def test_rejected_unchanged_revisions_do_not_trigger_redundant_critic_calls(self, monkeypatch):
        no_cache = make_architecture(
            summary="A load-balanced, auto-scaling, multi-AZ architecture.", services=make_architecture().services[:3]
        )  # always rejected by the guard: removes ElastiCache with no reason
        calls = {"critic": 0}

        def fake(llm, schema, prompt):
            if schema is Architecture:
                return (make_architecture() if current_node() == "architecture_designer" else no_cache).model_copy(
                    deep=True
                )
            if schema is CriticReview:
                calls["critic"] += 1
                return ADD_DYNAMODB
            return _dummy_for_schema(schema, [True], {"critic_calls": 0})

        monkeypatch.setattr(llm_module, "get_llm", lambda temperature=0.2, max_tokens=750: _FakeToolCallingLLM())
        monkeypatch.setattr(llm_module, "invoke_structured", fake)

        final_state = run_workflow("Design an e-commerce platform for 500,000 concurrent users.")

        assert calls["critic"] == 1  # rounds 1 and 2 reused round 0's review of the same v1
        assert final_state["revision_count"] == MAX_REVISIONS  # the revision limit still ends the loop
        assert final_state["architecture"].version == 1
        assert final_state["critic_review"].approved is False and final_state["final_report"] is not None
        critic_entries = [e for e in final_state["execution_trace"] if e["node"] == "Architecture Critic"]
        assert [("reused" in e["action"]) for e in critic_entries] == [False, True, True]
        assert len(final_state["critic_history"]) == 1


# ---------------------------------------------------------------------------
# 5. The service-count conflict
# ---------------------------------------------------------------------------


class TestServiceBudget:
    def test_prompts_allow_a_justified_eighth_service_or_consolidation(self, monkeypatch):
        prompts = _script_revisions(monkeypatch, make_architecture())
        revision_agent.run(_state(make_architecture(), ADD_DYNAMODB))

        (prompt,) = prompts
        assert "an 8th service is\n  allowed" in prompt
        assert '"Added <X> as an 8th service because <reason>"' in prompt
        assert "Never remove an essential service just to stay\n  under the count." in prompt
        assert '"Amazon ElastiCache (Redis) + Amazon DynamoDB"' in prompt
        assert "at most 8 service entries" in critic_agent.PROMPT_TEMPLATE

    def test_required_eighth_service_is_accepted_and_recorded(self, monkeypatch):
        v2 = _seven_services()
        assert len(v2.services) == 7
        eighth = _with(
            DYNAMODB,
            base=v2,
            data_flow=[
                *v2.data_flow,
                DataFlowStep(step=3, source="ECS", destination="DynamoDB", description="API reads catalog from DynamoDB"),
            ],
            change_log=["Added Amazon DynamoDB as an 8th service because catalog reads need it."],
        )
        _script_revisions(monkeypatch, eighth)

        result = revision_agent.run(_state(v2, ADD_DYNAMODB))

        assert len(result["architecture"].services) == 8
        assert result["architecture"].version == 3
        assert result["implemented_changes"] == [
            "v3: Added Amazon DynamoDB as an 8th service because catalog reads need it."
        ]
        assert "Rejected" not in result["execution_trace"][0]["action"]

    def test_dropping_an_essential_service_to_fit_the_count_is_still_rejected(self, monkeypatch):
        v2 = _seven_services()
        swapped = make_architecture(
            summary="A load-balanced, auto-scaling, multi-AZ architecture with defense-in-depth security controls.",
            services=[s for s in v2.services if "ElastiCache" not in s.name] + [DYNAMODB],
            change_log=["Added DynamoDB for catalog reads."],
        )
        _script_revisions(monkeypatch, swapped, swapped)

        result = revision_agent.run(_state(v2, ADD_DYNAMODB))

        assert result["architecture"].version == 2  # ElastiCache removed without a reason: kept v2
        assert "removed service 'elasticache'" in result["execution_trace"][0]["action"]

"""Tests for CloudWatch custom metrics (graph/cloudwatch_metrics.py) and monitoring/.

No AWS credentials or network access are used: the CloudWatch client is a
real botocore client with dummy keys wrapped in a botocore Stubber (which
also checks every request against the API's schema), or a small fake that
records or fails calls. The sender thread is kept idle with a long flush
interval; tests call flush() themselves.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.stub import ANY, Stubber
from botocore.validate import validate_parameters

from graph import cloudwatch_metrics, observability
from graph.cloudwatch_logs import DEFAULT_REGION
from graph.cloudwatch_metrics import (
    MAX_DATUMS_PER_REQUEST,
    CloudWatchMetricsPublisher,
    configure_cloudwatch_metrics,
    get_metrics_settings,
    metrics_for_event,
    shutdown_cloudwatch_metrics,
)
from jobs import db, repository
from jobs.runner import execute_job

from .test_graph import _patch_llm

MONITORING = Path(__file__).resolve().parent.parent / "monitoring"
METRIC_NAMES = {"AgentDuration", "WorkflowDuration", "WorkflowFailures", "JobsCompleted", "JobRetries"}


class _RecordingClient:
    """Fake CloudWatch client: records put_metric_data calls, or raises `error`."""

    def __init__(self, error: BaseException | None = None):
        self.error = error
        self.calls: list[dict] = []

    def put_metric_data(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error

    @property
    def datapoints(self) -> list[dict]:
        return [datum for call in self.calls for datum in call["MetricData"]]


class _FakeSession:
    def __init__(self, client, has_credentials: bool = True):
        self._client = client
        self._has_credentials = has_credentials

    def get_credentials(self):
        return object() if self._has_credentials else None

    def client(self, service_name, **kwargs):
        assert service_name == "cloudwatch"
        return self._client


@pytest.fixture
def cloudwatch_client():
    client = boto3.session.Session(
        aws_access_key_id="testing", aws_secret_access_key="testing", region_name=DEFAULT_REGION
    ).client("cloudwatch")
    with Stubber(client) as stubber:
        yield client, stubber


@pytest.fixture
def metrics_enabled(monkeypatch):
    monkeypatch.setenv("CLOUDWATCH_METRICS_ENABLED", "true")
    monkeypatch.setenv("CLOUDWATCH_METRICS_FLUSH_INTERVAL_SECONDS", "3600")
    for name in ("AWS_REGION", "CLOUDWATCH_METRICS_NAMESPACE"):
        monkeypatch.delenv(name, raising=False)
    yield
    shutdown_cloudwatch_metrics()


def _publisher(client) -> CloudWatchMetricsPublisher:
    return CloudWatchMetricsPublisher(client, "ArchonAI", flush_interval_seconds=3600)


def _dimensions(datum: dict) -> dict:
    return {d["Name"]: d["Value"] for d in datum.get("Dimensions", [])}


def _summary(datapoints: list[dict]) -> list[tuple]:
    return sorted((d["MetricName"], tuple(sorted(_dimensions(d).items())), d["Value"]) for d in datapoints)


# --- Metric construction -----------------------------------------------------------


def test_node_event_becomes_agent_duration_in_milliseconds():
    (datum,) = metrics_for_event(
        "node_finished", {"job_id": "j1", "node": "compute_agent", "outcome": "success", "duration_ms": 4120}
    )

    assert datum["MetricName"] == "AgentDuration"
    assert datum["Unit"] == "Milliseconds"
    assert datum["Value"] == 4120.0
    assert _dimensions(datum) == {"Agent": "compute_agent"}  # no job id: it stays in the logs


def test_failed_workflow_reports_duration_and_a_failure():
    data = metrics_for_event("workflow_finished", {"outcome": "failure", "error_type": "X", "duration_ms": 900})

    assert [(d["MetricName"], d["Unit"], _dimensions(d)) for d in data] == [
        ("WorkflowDuration", "Milliseconds", {"Outcome": "failure"}),
        ("WorkflowFailures", "Count", {}),
    ]


def test_successful_workflow_reports_only_its_duration():
    (datum,) = metrics_for_event("workflow_finished", {"outcome": "success", "approved": True, "duration_ms": 5})

    assert (datum["MetricName"], _dimensions(datum)) == ("WorkflowDuration", {"Outcome": "success"})


@pytest.mark.parametrize(
    ("event", "fields", "expected"),
    [
        ("job_succeeded", {"attempt": 1, "duration_ms": 10}, ("JobsCompleted", {"Outcome": "succeeded"})),
        ("job_failed", {"attempt": 1, "will_retry": False}, ("JobsCompleted", {"Outcome": "failed"})),
        ("job_failed", {"attempt": 2, "reason": "interrupted_too_often"}, ("JobsCompleted", {"Outcome": "failed"})),
        ("job_failed", {"attempt": 1, "will_retry": True}, ("JobRetries", {})),
        ("job_resumed_after_crash", {"previous_attempts": 1}, ("JobRetries", {})),
    ],
    ids=["succeeded", "failed", "interrupted-too-often", "retrying", "crash-resume"],
)
def test_job_events_become_counts(event, fields, expected):
    (datum,) = metrics_for_event(event, {"job_id": "j1", **fields})

    assert (datum["MetricName"], _dimensions(datum)) == expected
    assert (datum["Unit"], datum["Value"]) == ("Count", 1.0)


@pytest.mark.parametrize("event", ["job_started", "job_skipped", "workflow_started", "cloudwatch_enabled"])
def test_events_without_a_measurement_publish_nothing(event):
    assert metrics_for_event(event, {"job_id": "j1"}) == []


# --- Batching and failure handling --------------------------------------------------


def test_buffered_datapoints_are_sent_in_one_valid_request(cloudwatch_client):
    client, stubber = cloudwatch_client
    publisher = _publisher(client)
    publisher.record_event("node_finished", {"node": "compute_agent", "duration_ms": 10})
    publisher.record_event("node_finished", {"node": "database_agent", "duration_ms": 20})
    publisher.record_event("job_succeeded", {"job_id": "j1", "attempt": 1})
    # The Stubber checks the request against CloudWatch's real API schema.
    stubber.add_response("put_metric_data", {}, {"Namespace": "ArchonAI", "MetricData": ANY})

    assert publisher.flush() == 3
    stubber.assert_no_pending_responses()
    assert publisher.flush() == 0  # nothing left over


def test_large_batches_are_split_at_the_request_limit():
    client = _RecordingClient()
    publisher = _publisher(client)
    for _ in range(MAX_DATUMS_PER_REQUEST + 5):
        publisher.record_event("node_finished", {"node": "cost_agent", "duration_ms": 1})

    publisher.flush()

    assert [len(call["MetricData"]) for call in client.calls] == [MAX_DATUMS_PER_REQUEST, 5]


def test_throttled_batch_is_retried_once_then_dropped(cloudwatch_client, caplog):
    client, stubber = cloudwatch_client
    publisher = _publisher(client)
    publisher.record_event("job_succeeded", {"job_id": "j1", "attempt": 1})
    stubber.add_client_error("put_metric_data", service_error_code="Throttling", http_status_code=400)
    stubber.add_client_error("put_metric_data", service_error_code="Throttling", http_status_code=400)

    with caplog.at_level(logging.WARNING, logger="graph.cloudwatch_metrics"):
        assert publisher.flush() == 0  # kept for one more try
        assert publisher.dropped == 0
        assert publisher.flush() == 0  # failed again: dropped
    assert publisher.dropped == 1
    assert publisher.flush() == 0
    failures = [r.event_fields for r in caplog.records if r.event_fields["event"] == "metrics_publish_failed"]
    assert [f["will_retry"] for f in failures] == [True, False]
    assert failures[0]["error_type"] == "ClientError"


def test_batch_that_fails_once_is_sent_on_the_next_flush():
    client = _RecordingClient(error=EndpointConnectionError(endpoint_url="https://monitoring.example"))
    publisher = _publisher(client)
    publisher.record_event("job_succeeded", {"job_id": "j1", "attempt": 1})

    assert publisher.flush() == 0  # network down: never raises
    client.error = None
    assert publisher.flush() == 1


def test_buffer_is_bounded_while_cloudwatch_is_unreachable():
    publisher = CloudWatchMetricsPublisher(_RecordingClient(), "ArchonAI", flush_interval_seconds=3600, max_buffered=3)
    for index in range(5):
        publisher.record_event("node_finished", {"node": f"agent_{index}", "duration_ms": 1})

    assert publisher.dropped == 2
    client = _RecordingClient()
    publisher._client = client
    publisher.flush()
    assert [_dimensions(d)["Agent"] for d in client.datapoints] == ["agent_2", "agent_3", "agent_4"]  # newest kept


def test_forked_child_does_not_resend_the_parents_buffer():
    client = _RecordingClient()
    publisher = _publisher(client)
    publisher.record_event("node_finished", {"node": "cost_agent", "duration_ms": 1})
    publisher._pid = -1  # as seen from a forked worker child

    assert publisher.flush() == 0
    assert client.calls == []


# --- Duplicate events ---------------------------------------------------------------


def test_duplicate_job_outcome_is_counted_once():
    client = _RecordingClient()
    publisher = _publisher(client)
    publisher.record_event("job_failed", {"job_id": "j1", "attempt": 1, "will_retry": True})
    publisher.record_event("job_failed", {"job_id": "j1", "attempt": 1, "will_retry": True})  # emitted twice
    publisher.record_event("job_succeeded", {"job_id": "j1", "attempt": 2})
    publisher.record_event("job_succeeded", {"job_id": "j1", "attempt": 2})
    publisher.record_event("job_succeeded", {"job_id": "j2", "attempt": 1})  # a different job

    publisher.flush()

    assert _summary(client.datapoints) == [
        ("JobRetries", (), 1.0),
        ("JobsCompleted", (("Outcome", "succeeded"),), 1.0),
        ("JobsCompleted", (("Outcome", "succeeded"),), 1.0),
    ]


def test_runner_does_not_report_an_outcome_another_delivery_already_stored(monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.reset_engine()
    _patch_llm(monkeypatch, critic_verdicts=[True])
    job_id = repository.create_job("Design a blogging platform for 10,000 users.")
    # Simulate a second delivery having finished the job while this run was going.
    monkeypatch.setattr(repository, "mark_succeeded", lambda job_id, result: False)

    with caplog.at_level(logging.INFO):
        execute_job(job_id)

    events = [r.event_fields for r in caplog.records if hasattr(r, "event_fields")]
    assert "job_succeeded" not in [e["event"] for e in events]
    assert {"event": "job_skipped", "reason": "already_finished"}.items() <= events[-1].items()
    db.reset_engine()


# --- Setup, disabled mode, end to end -----------------------------------------------


def test_metrics_are_disabled_by_default_and_in_tests(monkeypatch):
    monkeypatch.delenv("CLOUDWATCH_METRICS_ENABLED", raising=False)

    settings = get_metrics_settings()
    assert settings.enabled is False
    assert (settings.namespace, settings.region) == ("ArchonAI", "ap-south-1")
    assert configure_cloudwatch_metrics("worker", boto3_session=_FakeSession(_RecordingClient())) is None


def test_missing_credentials_disable_metrics_with_a_warning(metrics_enabled, caplog):
    with caplog.at_level(logging.WARNING, logger="graph.cloudwatch_metrics"):
        publisher = configure_cloudwatch_metrics("worker", boto3_session=_FakeSession(None, has_credentials=False))

    assert publisher is None
    assert "event=metrics_disabled service=worker reason=no_aws_credentials" in caplog.text


def test_setup_is_idempotent_and_shutdown_stops_listening(metrics_enabled):
    session = _FakeSession(_RecordingClient())

    first = configure_cloudwatch_metrics("worker", boto3_session=session)
    assert configure_cloudwatch_metrics("worker", boto3_session=session) is first
    assert observability._event_listeners.count(first.record_event) == 1

    shutdown_cloudwatch_metrics()
    assert first.record_event not in observability._event_listeners


def test_real_job_publishes_workflow_agent_and_job_metrics(metrics_enabled, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.reset_engine()
    _patch_llm(monkeypatch, critic_verdicts=[True])
    client = _RecordingClient()
    publisher = configure_cloudwatch_metrics("worker", boto3_session=_FakeSession(client))
    job_id = repository.create_job("Design a blogging platform for 10,000 users.")

    execute_job(job_id)
    publisher.flush()

    names = [d["MetricName"] for d in client.datapoints]
    assert names.count("AgentDuration") == 12  # every node but revision (approved first time)
    assert names.count("WorkflowDuration") == 1
    assert names.count("JobsCompleted") == 1
    assert {call["Namespace"] for call in client.calls} == {"ArchonAI"}
    for datum in client.datapoints:
        assert set(_dimensions(datum)) <= {"Agent", "Outcome"}
        assert job_id not in json.dumps(datum, default=str)
    db.reset_engine()


def test_job_still_succeeds_when_cloudwatch_is_down(metrics_enabled, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.reset_engine()
    _patch_llm(monkeypatch, critic_verdicts=[True])
    client = _RecordingClient(error=EndpointConnectionError(endpoint_url="https://monitoring.example"))
    publisher = configure_cloudwatch_metrics("worker", boto3_session=_FakeSession(client))
    job_id = repository.create_job("Design a blogging platform for 10,000 users.")

    execute_job(job_id)
    publisher.flush()

    assert repository.get_job(job_id).status.value == "succeeded"
    db.reset_engine()


def test_broken_listener_never_breaks_logging():
    def broken(event, fields):
        raise RuntimeError("listener bug")

    observability.add_event_listener(broken)
    try:
        observability.log_event(logging.getLogger("test"), "anything", value=1)  # must not raise
    finally:
        observability.remove_event_listener(broken)


# --- monitoring/ definitions ----------------------------------------------------------


def _dashboard_metric_names(dashboard: dict) -> set[str]:
    names = set()
    for widget in dashboard["widgets"]:
        for row in widget.get("properties", {}).get("metrics", []):
            if isinstance(row[0], dict):  # a SEARCH expression
                names |= {name for name in METRIC_NAMES if f'MetricName=\\"{name}\\"' in json.dumps(row[0])}
            else:
                names.add(row[1])
    return names


def test_dashboard_covers_every_published_metric():
    dashboard = json.loads((MONITORING / "archonai-dashboard.json").read_text())

    assert _dashboard_metric_names(dashboard) == METRIC_NAMES


@pytest.mark.parametrize("path", sorted((MONITORING / "alarms").glob("*.json")), ids=lambda p: p.name)
def test_alarm_definitions_are_valid_put_metric_alarm_input(path):
    alarm = json.loads(path.read_text())
    client = boto3.session.Session(
        aws_access_key_id="testing", aws_secret_access_key="testing", region_name=DEFAULT_REGION
    ).client("cloudwatch")

    # Raises if a field is unknown or has the wrong type -- no AWS call is made.
    validate_parameters(alarm, client.meta.service_model.operation_model("PutMetricAlarm").input_shape)
    assert alarm["Namespace"] == cloudwatch_metrics.DEFAULT_NAMESPACE
    assert alarm["MetricName"] in METRIC_NAMES
    assert alarm["TreatMissingData"] == "notBreaching"  # quiet hours never alarm

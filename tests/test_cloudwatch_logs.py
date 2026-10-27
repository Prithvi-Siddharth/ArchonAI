"""Tests for shipping logs to CloudWatch (graph/cloudwatch_logs.py).

No AWS credentials or network access are used: the boto3 session is a fake
that hands out a real botocore CloudWatch Logs client with dummy keys, and a
botocore Stubber intercepts every API call before it leaves the process.
"""

from __future__ import annotations

import logging
import warnings

import boto3
import pytest
from botocore.stub import ANY, Stubber

from graph.cloudwatch_logs import (
    DEFAULT_REGION,
    configure_cloudwatch_logging,
    get_cloudwatch_settings,
)
from jobs import db, repository
from jobs.models import JobStatus
from jobs.runner import execute_job

from .test_graph import _patch_llm


class _FakeSession:
    """Stands in for boto3.session.Session: credentials present, stubbed client."""

    def __init__(self, client, has_credentials: bool = True):
        self._client = client
        self._has_credentials = has_credentials
        self.client_kwargs: dict = {}

    def get_credentials(self):
        return object() if self._has_credentials else None

    def client(self, service_name, **kwargs):
        assert service_name == "logs"
        self.client_kwargs = kwargs
        return self._client


@pytest.fixture
def cloudwatch_enabled(monkeypatch):
    monkeypatch.setenv("CLOUDWATCH_ENABLED", "true")
    monkeypatch.setenv("CLOUDWATCH_SEND_INTERVAL_SECONDS", "1")
    for name in ("AWS_REGION", "CLOUDWATCH_API_LOG_GROUP", "CLOUDWATCH_WORKER_LOG_GROUP"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def logs_client():
    client = boto3.session.Session(
        aws_access_key_id="testing", aws_secret_access_key="testing", region_name=DEFAULT_REGION
    ).client("logs")
    with Stubber(client) as stubber:
        yield client, stubber


@pytest.fixture
def target_logger():
    """An isolated logger, so tests never touch the real root logger's handlers."""
    logger = logging.getLogger("test.cloudwatch.target")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    yield logger
    for handler in _cloudwatch_handlers(logger) + [h for h in logger.handlers if isinstance(h, _CapturingHandler)]:
        logger.removeHandler(handler)
        handler.close()


def _cloudwatch_handlers(logger: logging.Logger) -> list[logging.Handler]:
    # pytest attaches its own log-capture handlers; count only ours.
    return [h for h in logger.handlers if getattr(h, "_archonai_cloudwatch", False)]


def _expect_put(stubber, log_group: str) -> None:
    stubber.add_response(
        "put_log_events",
        {"nextSequenceToken": "1"},
        {"logGroupName": log_group, "logStreamName": ANY, "logEvents": ANY},
    )


# --- Settings -----------------------------------------------------------------------


def test_disabled_by_default(monkeypatch, target_logger):
    monkeypatch.delenv("CLOUDWATCH_ENABLED", raising=False)

    assert configure_cloudwatch_logging("api", target_logger) is None
    assert _cloudwatch_handlers(target_logger) == []


def test_settings_defaults_and_overrides(monkeypatch, cloudwatch_enabled):
    settings = get_cloudwatch_settings()
    assert settings.region == "ap-south-1"
    assert settings.log_groups == {"api": "/archonai/api", "worker": "/archonai/worker"}

    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("CLOUDWATCH_WORKER_LOG_GROUP", "/custom/worker")
    settings = get_cloudwatch_settings()
    assert settings.region == "us-east-1"
    assert settings.log_groups["worker"] == "/custom/worker"


# --- Shipping logs ------------------------------------------------------------------


@pytest.mark.parametrize(("service", "log_group"), [("api", "/archonai/api"), ("worker", "/archonai/worker")])
def test_logs_are_batched_to_the_service_log_group(cloudwatch_enabled, logs_client, target_logger, service, log_group):
    client, stubber = logs_client
    session = _FakeSession(client)
    _expect_put(stubber, log_group)  # one call for the whole batch

    handler = configure_cloudwatch_logging(service, target_logger, boto3_session=session)
    target_logger.info("event=job_started job_id=abc attempt=1")
    target_logger.info("event=job_succeeded job_id=abc duration_ms=10")
    handler.flush()

    stubber.assert_no_pending_responses()
    assert session.client_kwargs["region_name"] == "ap-south-1"
    # The groups are pre-provisioned: the only AWS call allowed was the stubbed
    # put_log_events -- any create/describe-log-group call would have failed setup.
    assert handler is not None


def test_one_stream_per_process_not_per_event(cloudwatch_enabled, logs_client, target_logger):
    client, stubber = logs_client
    _expect_put(stubber, "/archonai/api")
    handler = configure_cloudwatch_logging("api", target_logger, boto3_session=_FakeSession(client))

    records = [logging.LogRecord("app", logging.INFO, __file__, 1, f"event=e{i}", None, None) for i in range(5)]
    assert len({handler._get_stream_name(r) for r in records}) == 1
    for record in records:
        target_logger.handle(record)
    handler.flush()
    stubber.assert_no_pending_responses()


def test_configuring_twice_reuses_the_handler(cloudwatch_enabled, logs_client, target_logger):
    client, _ = logs_client
    first = configure_cloudwatch_logging("worker", target_logger, boto3_session=_FakeSession(client))
    second = configure_cloudwatch_logging("worker", target_logger, boto3_session=_FakeSession(client))

    assert first is second
    assert len(_cloudwatch_handlers(target_logger)) == 1


def test_aws_library_logs_are_not_shipped(cloudwatch_enabled, logs_client, target_logger):
    client, _ = logs_client
    handler = configure_cloudwatch_logging("api", target_logger, boto3_session=_FakeSession(client))

    assert not handler.filter(logging.LogRecord("botocore.endpoint", logging.INFO, __file__, 1, "x", None, None))
    assert handler.filter(logging.LogRecord("jobs.runner", logging.INFO, __file__, 1, "x", None, None))


# --- Failures never break the app ---------------------------------------------------


def test_missing_credentials_disables_cloudwatch_without_error(cloudwatch_enabled, logs_client, target_logger, caplog):
    client, _ = logs_client
    caplog.set_level(logging.WARNING)

    handler = configure_cloudwatch_logging("api", target_logger, boto3_session=_FakeSession(client, False))

    assert handler is None
    assert _cloudwatch_handlers(target_logger) == []
    assert "event=cloudwatch_disabled service=api reason=no_aws_credentials" in caplog.text


def test_setup_error_disables_cloudwatch_without_error(cloudwatch_enabled, target_logger, caplog):
    class _BrokenSession:
        def get_credentials(self):
            raise RuntimeError("profile archonai-dev not found")

    caplog.set_level(logging.WARNING)

    assert configure_cloudwatch_logging("worker", target_logger, boto3_session=_BrokenSession()) is None
    assert "reason=setup_failed error_type=RuntimeError" in caplog.text
    assert "archonai-dev" not in caplog.text  # only the error type is logged


def test_aws_delivery_errors_become_warnings_and_console_logging_continues(
    cloudwatch_enabled, logs_client, target_logger
):
    client, stubber = logs_client
    for _ in range(5):  # watchtower retries a failed batch, then gives up on it
        stubber.add_client_error("put_log_events", "ServiceUnavailableException", http_status_code=503)
    handler = configure_cloudwatch_logging("api", target_logger, boto3_session=_FakeSession(client))
    console = _CapturingHandler()
    target_logger.addHandler(console)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        target_logger.info("event=job_started job_id=abc")  # must not raise
        handler.flush()

    assert any("Failed to deliver logs" in str(w.message) for w in caught)
    assert [r.getMessage() for r in console.records] == ["event=job_started job_id=abc"]


def test_architecture_job_still_succeeds_when_cloudwatch_is_failing(cloudwatch_enabled, logs_client, monkeypatch):
    client, stubber = logs_client
    for _ in range(50):
        stubber.add_client_error("put_log_events", "ServiceUnavailableException", http_status_code=503)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.reset_engine()
    _patch_llm(monkeypatch, critic_verdicts=[True])
    root = logging.getLogger()
    handler = configure_cloudwatch_logging("worker", root, boto3_session=_FakeSession(client))
    try:
        job_id = repository.create_job("Design a blog for 10k users")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            execute_job(job_id)
            handler.flush()
        assert repository.get_job(job_id).status is JobStatus.SUCCEEDED
    finally:
        root.removeHandler(handler)
        handler.close()
        db.reset_engine()


class _CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)

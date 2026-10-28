"""Publish ArchonAI's custom metrics to AWS CloudWatch (namespace `ArchonAI`).

Nothing new is instrumented: the structured events from
graph/observability.py are the source. log_event() hands every event to its
listeners, and the listener registered here turns the few events that carry
a measurement into CloudWatch datapoints:

    event                     metric              dimensions           unit
    node_finished          -> AgentDuration       Agent                Milliseconds
    workflow_finished      -> WorkflowDuration    Outcome              Milliseconds
                              WorkflowFailures    (failed runs only)   Count
    job_succeeded          -> JobsCompleted       Outcome=succeeded    Count
    job_failed             -> JobRetries          (will_retry=true)    Count
                              JobsCompleted       Outcome=failed       Count (otherwise)
    job_resumed_after_crash-> JobRetries                               Count

Dimensions stay low-cardinality (agent name, outcome): every distinct
dimension combination is a separate, billed metric. Job ids stay in the logs.

Datapoints are buffered and sent in batches from a background thread every
CLOUDWATCH_METRICS_FLUSH_INTERVAL_SECONDS, so a slow, throttling or
unreachable CloudWatch never delays a job. botocore retries throttling and
network errors with backoff; a batch that still fails is kept for one more
flush, then dropped with a warning. The buffer is bounded, so an outage
can't grow memory without limit.

Job outcomes are de-duplicated by (event, job id, attempt), so an event
emitted twice in a process is counted once; jobs/runner.py only emits an
outcome when its guarded status update succeeded, which covers duplicates
across workers.

Credentials come from the AWS SDK's default chain, exactly as for logs
(graph/cloudwatch_logs.py). Off unless CLOUDWATCH_METRICS_ENABLED is true.
"""

from __future__ import annotations

import atexit
import logging
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from graph.cloudwatch_logs import DEFAULT_REGION, Service, _bool_env
from graph.observability import add_event_listener, log_event, remove_event_listener

DEFAULT_NAMESPACE = "ArchonAI"
DEFAULT_FLUSH_INTERVAL_SECONDS = 10

# PutMetricData accepts up to 1000 datapoints per request.
MAX_DATUMS_PER_REQUEST = 1000
# Upper bound on datapoints held while CloudWatch is unreachable; oldest go first.
MAX_BUFFERED_DATUMS = 10_000
# How many recent job outcomes are remembered for de-duplication.
_DEDUPE_MEMORY = 4096

MILLISECONDS = "Milliseconds"
COUNT = "Count"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MetricsSettings:
    enabled: bool
    region: str
    namespace: str
    flush_interval_seconds: int


def get_metrics_settings() -> MetricsSettings:
    """Current settings from the environment (read at call time, so tests can override)."""
    try:
        interval = max(
            1, int(os.getenv("CLOUDWATCH_METRICS_FLUSH_INTERVAL_SECONDS", "").strip() or DEFAULT_FLUSH_INTERVAL_SECONDS)
        )
    except ValueError:
        interval = DEFAULT_FLUSH_INTERVAL_SECONDS
    return MetricsSettings(
        enabled=_bool_env("CLOUDWATCH_METRICS_ENABLED"),
        region=os.getenv("AWS_REGION", "").strip() or DEFAULT_REGION,
        namespace=os.getenv("CLOUDWATCH_METRICS_NAMESPACE", "").strip() or DEFAULT_NAMESPACE,
        flush_interval_seconds=interval,
    )


def _datum(name: str, value: float, unit: str, timestamp: datetime, **dimensions: Any) -> dict:
    datum: dict[str, Any] = {"MetricName": name, "Value": float(value), "Unit": unit, "Timestamp": timestamp}
    if dimensions:
        datum["Dimensions"] = [{"Name": key, "Value": str(dim)} for key, dim in dimensions.items()]
    return datum


def metrics_for_event(event: str, fields: dict[str, Any], timestamp: Optional[datetime] = None) -> list[dict]:
    """The CloudWatch datapoints (PutMetricData format) for one event; [] if it carries none."""
    timestamp = timestamp or datetime.now(timezone.utc)
    duration = fields.get("duration_ms")

    if event == "node_finished":
        if duration is None or not fields.get("node"):
            return []
        return [_datum("AgentDuration", duration, MILLISECONDS, timestamp, Agent=fields["node"])]

    if event == "workflow_finished":
        outcome = fields.get("outcome", "unknown")
        data = []
        if duration is not None:
            data.append(_datum("WorkflowDuration", duration, MILLISECONDS, timestamp, Outcome=outcome))
        if outcome == "failure":
            data.append(_datum("WorkflowFailures", 1, COUNT, timestamp))
        return data

    if event == "job_succeeded":
        return [_datum("JobsCompleted", 1, COUNT, timestamp, Outcome="succeeded")]

    if event == "job_failed":
        # A failure that will be retried isn't the job's outcome yet.
        if fields.get("will_retry"):
            return [_datum("JobRetries", 1, COUNT, timestamp)]
        return [_datum("JobsCompleted", 1, COUNT, timestamp, Outcome="failed")]

    if event == "job_resumed_after_crash":
        return [_datum("JobRetries", 1, COUNT, timestamp)]

    return []


def _dedupe_key(event: str, fields: dict[str, Any]) -> Optional[tuple]:
    """Identity of a job-level event: each attempt of a job has exactly one outcome."""
    job_id = fields.get("job_id")
    if job_id is None:
        return None
    if event in ("job_succeeded", "job_failed"):
        return (event, job_id, fields.get("attempt"))
    if event == "job_resumed_after_crash":
        return (event, job_id, fields.get("previous_attempts"))
    return None


class CloudWatchMetricsPublisher:
    """Buffers datapoints from events and sends them to CloudWatch in batches."""

    def __init__(
        self,
        client,
        namespace: str = DEFAULT_NAMESPACE,
        flush_interval_seconds: int = DEFAULT_FLUSH_INTERVAL_SECONDS,
        max_buffered: int = MAX_BUFFERED_DATUMS,
    ):
        self._client = client
        self._namespace = namespace
        self._interval = flush_interval_seconds
        self._max_buffered = max_buffered
        self._reset_for_process()

    def _reset_for_process(self) -> None:
        # Runs at creation and again in a forked worker child: the parent's
        # lock state, sender thread and buffer don't carry over (the parent
        # sends its own buffer -- copying it would double-count).
        self._pid = os.getpid()
        self._lock = threading.Lock()
        self._buffer: list[tuple[dict, bool]] = []  # (datapoint, already retried once)
        self._seen: OrderedDict[tuple, None] = OrderedDict()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.dropped = 0

    def _check_process(self) -> None:
        if os.getpid() != self._pid:
            self._reset_for_process()

    def record_event(self, event: str, fields: dict[str, Any]) -> None:
        """Event listener: buffer this event's datapoints (if any) for the next flush."""
        self._check_process()
        data = metrics_for_event(event, fields)
        if not data:
            return
        key = _dedupe_key(event, fields)
        with self._lock:
            if key is not None:
                if key in self._seen:
                    return
                self._seen[key] = None
                if len(self._seen) > _DEDUPE_MEMORY:
                    self._seen.popitem(last=False)
            self._store([(datum, False) for datum in data])
            self._ensure_sender()

    def _store(self, items: list[tuple[dict, bool]], *, first: bool = False) -> None:
        # Lock held by the caller.
        self._buffer = items + self._buffer if first else self._buffer + items
        overflow = len(self._buffer) - self._max_buffered
        if overflow > 0:
            del self._buffer[:overflow]
            self.dropped += overflow

    def _ensure_sender(self) -> None:
        # Lock held by the caller.
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="archonai-metrics", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self.flush()

    def flush(self) -> int:
        """Send everything buffered now. Returns the number of datapoints sent; never raises."""
        self._check_process()
        with self._lock:
            pending, self._buffer = self._buffer, []
        sent = 0
        for start in range(0, len(pending), MAX_DATUMS_PER_REQUEST):
            chunk = pending[start : start + MAX_DATUMS_PER_REQUEST]
            try:
                self._client.put_metric_data(Namespace=self._namespace, MetricData=[datum for datum, _ in chunk])
            except Exception as exc:  # noqa: BLE001 - CloudWatch trouble must never reach a job
                retry = [(datum, True) for datum, retried in chunk if not retried]
                with self._lock:
                    self._store(retry, first=True)
                    self.dropped += len(chunk) - len(retry)
                log_event(
                    logger,
                    "metrics_publish_failed",
                    logging.WARNING,
                    error_type=type(exc).__name__,
                    datapoints=len(chunk),
                    will_retry=bool(retry),
                )
                continue
            sent += len(chunk)
        return sent

    def close(self) -> None:
        """Stop the sender thread and send what's left."""
        self._stop.set()
        self.flush()


_active: Optional[CloudWatchMetricsPublisher] = None


def configure_cloudwatch_metrics(service: Service, boto3_session=None) -> Optional[CloudWatchMetricsPublisher]:
    """Start publishing metrics from this process's events.

    Returns the publisher, or None when metrics are disabled or couldn't be
    set up -- the app keeps running either way. Safe to call more than once.
    `boto3_session` is for tests; normally a session is created here.
    """
    global _active
    settings = get_metrics_settings()
    if not settings.enabled:
        return None
    if _active is not None:
        return _active

    try:
        import boto3
        from botocore.config import Config

        session = boto3_session or boto3.session.Session(region_name=settings.region)
        if session.get_credentials() is None:
            log_event(logger, "metrics_disabled", logging.WARNING, service=service, reason="no_aws_credentials")
            return None
        client = session.client(
            "cloudwatch",
            region_name=settings.region,
            config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 3, "mode": "standard"}),
        )
        publisher = CloudWatchMetricsPublisher(client, settings.namespace, settings.flush_interval_seconds)
    except Exception as exc:  # noqa: BLE001 - metrics must never stop the app from starting
        log_event(
            logger, "metrics_disabled", logging.WARNING, service=service, reason="setup_failed", error_type=type(exc).__name__
        )
        return None

    add_event_listener(publisher.record_event)
    _active = publisher
    log_event(logger, "metrics_enabled", service=service, namespace=settings.namespace, region=settings.region)
    return publisher


def shutdown_cloudwatch_metrics() -> None:
    """Send whatever is buffered and stop publishing (process shutdown; tests)."""
    global _active
    publisher, _active = _active, None
    if publisher is not None:
        remove_event_listener(publisher.record_event)
        publisher.close()


atexit.register(shutdown_cloudwatch_metrics)

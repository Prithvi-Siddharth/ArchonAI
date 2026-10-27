"""Ship ArchonAI's logs to AWS CloudWatch Logs.

Adds a CloudWatch handler *alongside* the existing console logging, so every
line already printed -- including the structured `event=...` lines from
graph/observability.py -- is also sent to CloudWatch. Nothing about the log
content changes.

The handler is watchtower's CloudWatchLogHandler, which:
- queues records and sends them in batches from a background thread, so a
  slow or unreachable AWS never blocks a request or an architecture job;
- writes one log stream per process per day (not one per event);
- turns delivery failures into warnings instead of exceptions.

Credentials come from the AWS SDK's default chain: locally that's the
profile named by AWS_PROFILE (e.g. archonai-dev); in production, environment
credentials or an attached IAM role -- no profile required. Nothing here
ever reads or logs a key. Off unless CLOUDWATCH_ENABLED is true.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal, Optional

from graph.observability import log_event

Service = Literal["api", "worker"]

DEFAULT_REGION = "ap-south-1"
DEFAULT_LOG_GROUPS: dict[str, str] = {"api": "/archonai/api", "worker": "/archonai/worker"}

# One stream per process, rolled daily: busy enough to stay well under
# CloudWatch's per-stream limits, few enough to browse.
LOG_STREAM_NAME = "{strftime:%Y-%m-%d}/{machine_name}/{process_id}"

# Logs from the AWS libraries themselves are never shipped: they describe the
# shipping, and sending them would feed the handler its own traffic.
_EXCLUDED_LOGGER_PREFIXES = ("botocore", "boto3", "urllib3", "s3transfer", "watchtower")

_MARKER = "_archonai_cloudwatch"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CloudWatchSettings:
    enabled: bool
    region: str
    log_groups: dict[str, str]
    send_interval_seconds: int


def _bool_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def get_cloudwatch_settings() -> CloudWatchSettings:
    """Current settings from the environment (read at call time, so tests can override)."""
    try:
        interval = max(1, int(os.getenv("CLOUDWATCH_SEND_INTERVAL_SECONDS", "").strip() or 5))
    except ValueError:
        interval = 5
    return CloudWatchSettings(
        enabled=_bool_env("CLOUDWATCH_ENABLED"),
        region=os.getenv("AWS_REGION", "").strip() or DEFAULT_REGION,
        log_groups={
            "api": os.getenv("CLOUDWATCH_API_LOG_GROUP", "").strip() or DEFAULT_LOG_GROUPS["api"],
            "worker": os.getenv("CLOUDWATCH_WORKER_LOG_GROUP", "").strip() or DEFAULT_LOG_GROUPS["worker"],
        },
        send_interval_seconds=interval,
    )


class _ExcludeAwsLibraries(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith(_EXCLUDED_LOGGER_PREFIXES)


def _existing_handler(target: logging.Logger) -> Optional[logging.Handler]:
    return next((h for h in target.handlers if getattr(h, _MARKER, False)), None)


def configure_cloudwatch_logging(
    service: Service, target: Optional[logging.Logger] = None, boto3_session=None
) -> Optional[logging.Handler]:
    """Attach a CloudWatch handler for `service` to `target` (the root logger by default).

    Returns the handler, or None when CloudWatch is disabled or couldn't be
    set up -- in which case console logging carries on exactly as before.
    Safe to call more than once: an existing handler is reused.
    `boto3_session` is for tests; normally a session is created here.
    """
    settings = get_cloudwatch_settings()
    if not settings.enabled:
        return None

    target = target if target is not None else logging.getLogger()
    existing = _existing_handler(target)
    if existing is not None:
        return existing

    log_group = settings.log_groups[service]
    try:
        import boto3
        import watchtower
        from botocore.config import Config

        session = boto3_session or boto3.session.Session(region_name=settings.region)
        if session.get_credentials() is None:
            log_event(logger, "cloudwatch_disabled", logging.WARNING, service=service, reason="no_aws_credentials")
            return None
        client = session.client(
            "logs",
            region_name=settings.region,
            # Bounded network waits and a few retries with backoff: delivery
            # happens on watchtower's background thread, but a hung call
            # would still hold up later batches.
            config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 3, "mode": "standard"}),
        )
        handler = watchtower.CloudWatchLogHandler(
            log_group_name=log_group,
            log_stream_name=LOG_STREAM_NAME,
            boto3_client=client,
            # The groups are provisioned ahead of time (with their retention
            # policy), so the app only needs permission to write streams/events.
            create_log_group=False,
            send_interval=settings.send_interval_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - CloudWatch must never stop the app from starting
        log_event(
            logger,
            "cloudwatch_disabled",
            logging.WARNING,
            service=service,
            reason="setup_failed",
            error_type=type(exc).__name__,
        )
        return None

    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    handler.addFilter(_ExcludeAwsLibraries())
    setattr(handler, _MARKER, True)
    target.addHandler(handler)
    log_event(logger, "cloudwatch_enabled", service=service, log_group=log_group, region=settings.region)
    return handler

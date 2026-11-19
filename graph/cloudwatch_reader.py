"""Read one job's log lines back from AWS CloudWatch Logs. Read-only.

The only AWS call made is `FilterLogEvents`, on the API and worker log groups that
graph/cloudwatch_logs.py writes to. Nothing is created, changed or deleted. It uses the same
credentials and region as log shipping, and needs the policy in
monitoring/iam/archonai-logs-read-policy.json.

Failures are reported as a short reason (MonitoringUnavailable.reason), never as AWS's own
message, which can contain account ids and ARNs. Only exception class names and AWS error
codes are logged.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Literal, Optional

from graph.cloudwatch_logs import get_cloudwatch_settings
from jobs.monitoring import RawEvent

logger = logging.getLogger(__name__)

Reason = Literal["disabled", "no_credentials", "forbidden", "throttled", "unreachable"]

# A job writes a few hundred lines. These bounds keep one request small however big a log group is.
MAX_EVENTS = 1500
MAX_PAGES_PER_GROUP = 5
PAGE_SIZE = 1000

_ACCESS_DENIED = {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation", "UnrecognizedClientException"}
_THROTTLED = {"ThrottlingException", "Throttling", "TooManyRequestsException", "RequestLimitExceeded"}


class MonitoringUnavailable(Exception):
    """Logs couldn't be read. `reason` is safe to show to the user."""

    def __init__(self, reason: Reason):
        super().__init__(reason)
        self.reason = reason


_client: Optional[Any] = None
_client_lock = threading.Lock()


def reset_client() -> None:
    """Forget the cached AWS client (tests, and picking up changed credentials)."""
    global _client
    with _client_lock:
        _client = None


def _logs_client(region: str) -> Any:
    global _client
    with _client_lock:
        if _client is not None:
            return _client
        import boto3
        from botocore.config import Config

        session = boto3.session.Session(region_name=region)
        if session.get_credentials() is None:
            raise MonitoringUnavailable("no_credentials")
        _client = session.client(
            "logs",
            region_name=region,
            config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 3, "mode": "standard"}),
        )
        return _client


def read_job_events(job_id: str, start_ms: int, end_ms: int) -> list[RawEvent]:
    """Every log line mentioning this job in the window, from both log groups, oldest first.

    `job_id` must be a UUID (callers only pass ids of jobs they loaded from the database), so it
    is safe inside the quoted filter pattern.
    """
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, PartialCredentialsError, ProfileNotFound

    settings = get_cloudwatch_settings()
    if not settings.enabled:
        raise MonitoringUnavailable("disabled")
    events: list[RawEvent] = []
    try:
        client = _logs_client(settings.region)
        for service, group in settings.log_groups.items():
            token: Optional[str] = None
            for _ in range(MAX_PAGES_PER_GROUP):
                params: dict[str, Any] = {
                    "logGroupName": group,
                    "startTime": start_ms,
                    "endTime": end_ms,
                    "filterPattern": f'"job_id={job_id}"',
                    "limit": PAGE_SIZE,
                }
                if token:
                    params["nextToken"] = token
                try:
                    page = client.filter_log_events(**params)
                except ClientError as exc:
                    code = exc.response.get("Error", {}).get("Code", "")
                    if code == "ResourceNotFoundException":
                        break  # that log group doesn't exist (yet): nothing to read from it
                    raise
                events += [RawEvent(int(e["timestamp"]), service, str(e.get("message", ""))) for e in page.get("events", [])]
                token = page.get("nextToken")
                if not token or len(events) >= MAX_EVENTS:
                    break
    except MonitoringUnavailable:
        raise
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        logger.warning("CloudWatch Logs read failed (%s).", code or type(exc).__name__)
        if code in _ACCESS_DENIED:
            raise MonitoringUnavailable("forbidden") from None
        if code in _THROTTLED:
            raise MonitoringUnavailable("throttled") from None
        raise MonitoringUnavailable("unreachable") from None
    except (NoCredentialsError, PartialCredentialsError, ProfileNotFound):
        reset_client()
        raise MonitoringUnavailable("no_credentials") from None
    except BotoCoreError as exc:
        logger.warning("CloudWatch Logs read failed (%s).", type(exc).__name__)
        raise MonitoringUnavailable("unreachable") from None
    return sorted(events, key=lambda e: e.timestamp_ms)[:MAX_EVENTS]

"""Tests for the datapoint verifier (monitoring/verify_metrics.py).

The CloudWatch client is a real botocore client with dummy keys inside a
Stubber, so requests are checked against the API schema and nothing reaches AWS.
"""

from __future__ import annotations

import importlib.util
import io
from datetime import datetime, timezone
from pathlib import Path

import boto3
import pytest
from botocore.stub import ANY, Stubber

_PATH = Path(__file__).resolve().parent.parent / "monitoring" / "verify_metrics.py"
_spec = importlib.util.spec_from_file_location("verify_metrics", _PATH)
verify_metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_metrics)

WINDOW = ["--start", "2026-10-28T07:00:00Z", "--end", "2026-10-28T07:15:00Z"]
AT = datetime(2026, 10, 28, 7, 7, tzinfo=timezone.utc)

PUBLISHED = [
    {"Namespace": "ArchonAI", "MetricName": "WorkflowFailures", "Dimensions": []},
    {"Namespace": "ArchonAI", "MetricName": "AgentDuration", "Dimensions": [{"Name": "Agent", "Value": "compute_agent"}]},
]


@pytest.fixture
def stubbed():
    client = boto3.session.Session(
        aws_access_key_id="testing", aws_secret_access_key="testing", region_name="ap-south-1"
    ).client("cloudwatch")
    with Stubber(client) as stubber:
        yield client, stubber


def _run(client, argv=WINDOW) -> tuple[int, str]:
    out = io.StringIO()
    return verify_metrics.main(argv, client=client, out=out), out.getvalue()


def test_parse_utc_accepts_z_and_naive_times():
    assert verify_metrics.parse_utc("2026-10-28T07:00:00Z") == datetime(2026, 10, 28, 7, tzinfo=timezone.utc)
    assert verify_metrics.parse_utc("2026-10-28T07:00:00") == datetime(2026, 10, 28, 7, tzinfo=timezone.utc)
    assert verify_metrics.parse_utc("2026-10-28T12:30:00+05:30") == datetime(2026, 10, 28, 7, tzinfo=timezone.utc)


def test_queries_use_the_published_dimensions_and_a_fitting_statistic():
    queries = verify_metrics.build_queries(PUBLISHED, period=60)

    assert [(q["MetricStat"]["Metric"]["MetricName"], q["MetricStat"]["Stat"]) for q in queries] == [
        ("WorkflowFailures", "Sum"),
        ("AgentDuration", "Maximum"),
        ("AgentDuration", "SampleCount"),
    ]
    assert queries[1]["MetricStat"]["Metric"]["Dimensions"] == [{"Name": "Agent", "Value": "compute_agent"}]
    assert len({q["Id"] for q in queries}) == 3


def test_reports_datapoints_with_utc_timestamps(stubbed):
    client, stubber = stubbed
    stubber.add_response("list_metrics", {"Metrics": PUBLISHED}, {"Namespace": "ArchonAI"})
    stubber.add_response(
        "get_metric_data",
        {
            "MetricDataResults": [
                {"Id": "m0", "Timestamps": [AT], "Values": [1.0], "StatusCode": "Complete"},
                {"Id": "m1", "Timestamps": [AT], "Values": [58187.0], "StatusCode": "Complete"},
                {"Id": "m2", "Timestamps": [AT], "Values": [1.0], "StatusCode": "Complete"},
            ]
        },
        {
            "MetricDataQueries": ANY,
            "StartTime": datetime(2026, 10, 28, 7, tzinfo=timezone.utc),
            "EndTime": datetime(2026, 10, 28, 7, 15, tzinfo=timezone.utc),
            "ScanBy": "TimestampAscending",
        },
    )

    code, output = _run(client)

    assert code == 0
    assert "OK                 AgentDuration {Agent=compute_agent} Maximum" in output
    assert "2026-10-28T07:07:00Z  58187" in output
    assert "NOT PUBLISHED YET  JobRetries" in output
    assert "3 datapoints found." in output


def test_empty_window_exits_1_with_diagnosis(stubbed):
    client, stubber = stubbed
    stubber.add_response("list_metrics", {"Metrics": PUBLISHED[:1]}, {"Namespace": "ArchonAI"})
    stubber.add_response(
        "get_metric_data",
        {"MetricDataResults": [{"Id": "m0", "Timestamps": [], "Values": [], "StatusCode": "Complete"}]},
        None,
    )

    code, output = _run(client)

    assert code == 1
    assert "NO DATA IN WINDOW  WorkflowFailures {(no dimensions)} Sum" in output
    assert "UTC" in output and "metrics_publish_failed" in output


def test_access_denied_points_to_the_read_policy(stubbed):
    client, stubber = stubbed
    stubber.add_client_error("list_metrics", service_error_code="AccessDenied", http_status_code=403)

    code, output = _run(client)

    assert code == 2
    assert "archonai-metrics-read-policy.json" in output


@pytest.mark.parametrize(
    "argv",
    [
        ["--start", "2026-10-28T07:15:00Z", "--end", "2026-10-28T07:00:00Z"],
        [*WINDOW, "--period", "90"],
    ],
    ids=["end-before-start", "bad-period"],
)
def test_invalid_arguments_make_no_aws_calls(stubbed, argv):
    client, _ = stubbed  # the Stubber fails the test on any unexpected call

    assert _run(client, argv)[0] == 2

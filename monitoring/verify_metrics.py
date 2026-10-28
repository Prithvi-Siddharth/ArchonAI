"""Check that ArchonAI's CloudWatch metrics have queryable datapoints.

Discovers every metric and dimension combination actually published in the
namespace (ListMetrics), then queries each one with GetMetricData for a UTC
time window and prints the timestamps and values. Querying the discovered
dimensions -- rather than guessing them -- matters because CloudWatch treats
every dimension combination as a separate metric: AgentDuration with no
dimensions has no data; AgentDuration{Agent=compute_agent} does.

Usage (read-only; needs cloudwatch:ListMetrics and cloudwatch:GetMetricData,
see monitoring/iam/archonai-metrics-read-policy.json):

    python monitoring/verify_metrics.py --start 2026-10-28T07:00:00Z --end 2026-10-28T07:15:00Z \
        --profile archonai-dev

Exit code: 0 if any datapoints were found, 1 if none, 2 on an AWS error.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

DEFAULT_NAMESPACE = "ArchonAI"
DEFAULT_REGION = "ap-south-1"

EXPECTED_METRICS = ("WorkflowDuration", "AgentDuration", "JobsCompleted", "JobRetries", "WorkflowFailures")
# Durations: the slowest run and how many runs; counts: how many events.
_STATISTICS = {"WorkflowDuration": ("Maximum", "SampleCount"), "AgentDuration": ("Maximum", "SampleCount")}
_DEFAULT_STATISTICS = ("Sum",)

# GetMetricData accepts up to 500 queries per request.
_MAX_QUERIES_PER_REQUEST = 500
# CloudWatch keeps 1-minute datapoints for 15 days, then only 5-minute and coarser.
_ONE_MINUTE_RETENTION = timedelta(days=15)


def parse_utc(value: str) -> datetime:
    """An ISO-8601 time; a value without a timezone is taken as UTC."""
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def list_published_metrics(client, namespace: str) -> list[dict]:
    """Every (MetricName, Dimensions) combination in the namespace."""
    metrics: list[dict] = []
    for page in client.get_paginator("list_metrics").paginate(Namespace=namespace):
        metrics.extend(page["Metrics"])
    return sorted(metrics, key=lambda m: (m["MetricName"], _describe_dimensions(m.get("Dimensions", []))))


def build_queries(metrics: list[dict], period: int) -> list[dict]:
    queries = []
    for metric in metrics:
        for stat in _STATISTICS.get(metric["MetricName"], _DEFAULT_STATISTICS):
            queries.append(
                {
                    "Id": f"m{len(queries)}",
                    "MetricStat": {"Metric": metric, "Period": period, "Stat": stat},
                    "ReturnData": True,
                }
            )
    return queries


def fetch_datapoints(client, queries: list[dict], start: datetime, end: datetime) -> dict[str, list[tuple]]:
    """Query id -> [(timestamp, value), ...] in time order."""
    results: dict[str, list[tuple]] = {query["Id"]: [] for query in queries}
    for offset in range(0, len(queries), _MAX_QUERIES_PER_REQUEST):
        batch = queries[offset : offset + _MAX_QUERIES_PER_REQUEST]
        kwargs = {"MetricDataQueries": batch, "StartTime": start, "EndTime": end, "ScanBy": "TimestampAscending"}
        while True:
            response = client.get_metric_data(**kwargs)
            for result in response["MetricDataResults"]:
                results[result["Id"]].extend(zip(result["Timestamps"], result["Values"]))
            if not response.get("NextToken"):
                break
            kwargs["NextToken"] = response["NextToken"]
    return {query_id: sorted(points) for query_id, points in results.items()}


def _describe_dimensions(dimensions: list[dict]) -> str:
    return ",".join(f"{d['Name']}={d['Value']}" for d in dimensions) or "(no dimensions)"


def report(metrics: list[dict], queries: list[dict], datapoints: dict[str, list[tuple]], out) -> int:
    """Print what was found; returns the number of datapoints."""
    published = {metric["MetricName"] for metric in metrics}
    for name in EXPECTED_METRICS:
        if name not in published:
            print(f"NOT PUBLISHED YET  {name}  (no event has produced it -- e.g. no retries so far)", file=out)

    total = 0
    for query in queries:
        stat = query["MetricStat"]
        label = f"{stat['Metric']['MetricName']} {{{_describe_dimensions(stat['Metric'].get('Dimensions', []))}}} {stat['Stat']}"
        points = datapoints.get(query["Id"], [])
        total += len(points)
        if not points:
            print(f"NO DATA IN WINDOW  {label}", file=out)
            continue
        print(f"OK                 {label}", file=out)
        for timestamp, value in points:
            print(f"                     {timestamp.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ}  {value:g}", file=out)
    return total


def _parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--start", required=True, type=parse_utc, help="UTC start, e.g. 2026-10-28T07:00:00Z")
    parser.add_argument("--end", required=True, type=parse_utc, help="UTC end, e.g. 2026-10-28T07:15:00Z")
    parser.add_argument("--period", type=int, default=60, help="Seconds per datapoint (multiple of 60; default 60)")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--profile", default=None, help="AWS CLI profile (omit to use the default credential chain)")
    return parser.parse_args(argv)


def main(argv=None, client=None, out=sys.stdout) -> int:
    args = _parse_args(argv)
    if args.end <= args.start:
        print("--end must be after --start", file=out)
        return 2
    if args.period < 60 or args.period % 60:
        print("--period must be a multiple of 60", file=out)
        return 2
    if args.period < 300 and datetime.now(timezone.utc) - args.start > _ONE_MINUTE_RETENTION:
        print("Note: 1-minute data is only kept 15 days; use --period 300 or more for this window.", file=out)

    from botocore.exceptions import BotoCoreError, ClientError

    try:
        if client is None:
            import boto3

            client = boto3.session.Session(profile_name=args.profile, region_name=args.region).client("cloudwatch")
        print(
            f"Namespace {args.namespace}, region {args.region}, "
            f"{args.start:%Y-%m-%dT%H:%M:%SZ} to {args.end:%Y-%m-%dT%H:%M:%SZ} UTC, period {args.period}s",
            file=out,
        )
        metrics = list_published_metrics(client, args.namespace)
        queries = build_queries(metrics, args.period)
        datapoints = fetch_datapoints(client, queries, args.start, args.end) if queries else {}
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        print(f"AWS error: {code or type(exc).__name__}", file=out)
        if code in ("AccessDenied", "AccessDeniedException"):
            print("Attach monitoring/iam/archonai-metrics-read-policy.json to this identity.", file=out)
        return 2
    except BotoCoreError as exc:
        print(f"AWS error: {type(exc).__name__} (check the profile, region and network)", file=out)
        return 2

    total = report(metrics, queries, datapoints, out)
    if total == 0:
        print(
            "\nNo datapoints. Check: the window is in UTC and covers the job; new data can take a few "
            "minutes to appear; the worker logged event=metrics_enabled and no event=metrics_publish_failed.",
            file=out,
        )
        return 1
    print(f"\n{total} datapoints found.", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

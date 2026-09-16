"""AWS Service Search tool.

Loads a local knowledge base of AWS services (data/aws_services.json) and
exposes keyword search over it, both as a plain function and as a LangChain
`@tool` that agents can bind and call directly. Grounding service selection
in a fixed, inspectable knowledge base keeps the Architecture Designer from
hallucinating service names or capabilities.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "aws_services.json"
_SERVICES_CACHE: list[dict[str, Any]] | None = None


def _load_services() -> list[dict[str, Any]]:
    global _SERVICES_CACHE
    if _SERVICES_CACHE is None:
        with _DATA_PATH.open("r", encoding="utf-8") as f:
            _SERVICES_CACHE = json.load(f)
    return _SERVICES_CACHE


def search_aws_services(query: str) -> list[dict[str, Any]]:
    """Search the AWS service knowledge base by keyword.

    Matches (case-insensitively) against service name, category,
    description, and use cases. An empty query returns every service.
    """
    if not query or not query.strip():
        return _load_services()

    q = query.lower().strip()
    matches = []
    for service in _load_services():
        haystack = " ".join(
            [
                service.get("name", ""),
                service.get("category", ""),
                service.get("description", ""),
                " ".join(service.get("common_use_cases", [])),
            ]
        ).lower()
        if q in haystack:
            matches.append(service)
    return matches


def get_service_by_name(name: str) -> dict[str, Any] | None:
    """Exact (case-insensitive) lookup of a single service by name."""
    for service in _load_services():
        if service["name"].lower() == name.lower():
            return service
    return None


def list_categories() -> list[str]:
    """Return the distinct set of service categories in the knowledge base."""
    return sorted({service["category"] for service in _load_services()})


MAX_TOOL_RESULTS = 6


@tool
def search_aws_services_tool(query: str) -> str:
    """Search the AWS services knowledge base for services matching a keyword
    such as a category (e.g. 'database', 'compute') or capability (e.g.
    'caching', 'DDoS'). Returns matching services with their description,
    strengths, and limitations so you can justify a service choice."""
    results = search_aws_services(query)
    if not results:
        return f"No AWS services found matching '{query}'."
    # Cap what's echoed back: a broad query (e.g. "compute") can match many
    # entries in the knowledge base, and all of them get embedded straight
    # into the eventual design prompt -- an unbounded result set can itself
    # become the largest single contributor to that prompt's input-token
    # size. Compact (non-indented) JSON for the same reason.
    return json.dumps(results[:MAX_TOOL_RESULTS], separators=(",", ":"))

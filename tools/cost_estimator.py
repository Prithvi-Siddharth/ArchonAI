"""Cost Estimator tool.

A simple, rule-based, order-of-magnitude cost estimator. This is explicitly
NOT a substitute for the AWS Pricing Calculator or a real AWS bill -- it
gives the Cost Agent (and the reader of the final report) a directional
sense of which parts of the architecture will likely dominate spend.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from models.schemas import Architecture, Requirements

# Educational, order-of-magnitude baseline monthly USD range per service
# category for a moderate-traffic deployment. Deliberately rough, and scaled
# by a coarse traffic multiplier below. These are NOT AWS list prices.
CATEGORY_BASE_MONTHLY_USD: dict[str, tuple[int, int]] = {
    "Compute": (400, 3000),
    "Database": (300, 2500),
    "Caching": (100, 600),
    "Storage": (50, 400),
    "Messaging": (30, 300),
    "Networking": (100, 1500),
    "Security": (20, 200),
    "Observability": (50, 400),
    "Reliability": (50, 500),
}

DEFAULT_CATEGORY_RANGE = (50, 400)


def _scale_multiplier(requirements: Requirements) -> float:
    """Derive a rough scale multiplier from stated concurrency.

    Used only to widen or narrow the baseline ranges -- never to produce a
    precise figure.
    """
    text = requirements.concurrent_users.lower()
    digits = re.findall(r"[\d,]+", text)
    number = 0
    if digits:
        try:
            number = int(digits[0].replace(",", ""))
        except ValueError:
            number = 0
    if "million" in text:
        number *= 1_000_000

    if number >= 500_000:
        return 4.0
    if number >= 100_000:
        return 2.5
    if number >= 10_000:
        return 1.5
    if number >= 1_000:
        return 1.0
    return 0.6


@dataclass
class CostEstimate:
    """Result of the rule-based cost estimator."""

    monthly_low: int
    monthly_high: int
    major_cost_drivers: list[str]
    category_breakdown: dict[str, tuple[int, int]]
    assumptions: list[str]


def estimate_cost(architecture: Architecture, requirements: Requirements) -> CostEstimate:
    """Produce a rough, rule-based monthly cost range for the given architecture.

    Sums a configurable per-category baseline range across the categories
    present in the architecture, scaled by a coarse traffic multiplier
    derived from expected concurrency. The math is intentionally simple and
    transparent so the derivation is easy to explain and audit.
    """
    categories_present = sorted({service.category for service in architecture.services})
    multiplier = _scale_multiplier(requirements)

    category_breakdown: dict[str, tuple[int, int]] = {}
    for category in categories_present:
        base_low, base_high = CATEGORY_BASE_MONTHLY_USD.get(category, DEFAULT_CATEGORY_RANGE)
        category_breakdown[category] = (int(base_low * multiplier), int(base_high * multiplier))

    low_total = sum(low for low, _ in category_breakdown.values())
    high_total = sum(high for _, high in category_breakdown.values())

    major_drivers = [
        category
        for category, _ in sorted(category_breakdown.items(), key=lambda kv: kv[1][1], reverse=True)[:3]
    ]

    assumptions = [
        f"Traffic scale multiplier applied: {multiplier}x, derived from concurrent users "
        f"('{requirements.concurrent_users}').",
        "Baseline per-category ranges are educational order-of-magnitude figures, not AWS list prices.",
        "Estimate excludes data-transfer egress specifics, support plans, and reserved/savings-plan discounts.",
        f"Categories priced: {', '.join(categories_present) if categories_present else 'none identified'}.",
    ]

    return CostEstimate(
        monthly_low=low_total,
        monthly_high=high_total,
        major_cost_drivers=major_drivers,
        category_breakdown=category_breakdown,
        assumptions=assumptions,
    )

"""Merging a revision's ArchitectureDelta into the current Architecture.

Deterministic, no LLM. A revision that returns only what it changes is
merged here into a complete Architecture, so the revision guard, the
validator, change-log verification, the critic and the report all keep
working on a full design exactly as before.

Services are referenced by position-based IDs (S1, S2, ...) shown to the
model, because names are unreliable keys (combined entries get renamed).
Anything ambiguous makes the whole delta invalid -- it is never guessed:

- an unknown ID, or the same ID updated/removed more than once;
- a removal without a reason;
- two different entries ending up with the same name (re-sending an
  identical entry is simply ignored);
- a removed service that is still named in the merged design (a stale
  summary, data flow or other entry would make the guard and report
  believe it is still there).

Entries the delta doesn't mention are copied unchanged, so a revision can
no longer drop a service by forgetting to restate it. An explicit removal
always carries a reason and is recorded in the change_log as
"Removed <name> because <reason>" -- the same form the revision guard
already accepts as a justification.
"""

from __future__ import annotations

from models.schemas import (
    Architecture,
    ArchitectureDelta,
    AWSService,
    ServiceRemoval,
    ServiceUpdate,
)
from tools.architecture_facts import mentions
from tools.revision_guard import _justification, _service_components

ID_PREFIX = "S"


class InvalidDeltaError(ValueError):
    """The delta can't be merged unambiguously. `problems` are short, safe descriptions."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def service_id(index: int) -> str:
    """The ID shown to the model for the service at `index` (0-based): S1, S2, ..."""
    return f"{ID_PREFIX}{index + 1}"


def service_ids(architecture: Architecture) -> dict[str, AWSService]:
    """ID -> service entry, in design order."""
    return {service_id(i): service for i, service in enumerate(architecture.services)}


def _normalized_id(value: str) -> str:
    return value.strip().upper()


def _name_key(name: str) -> str:
    return " ".join(name.lower().split())


def _aliases(service: AWSService) -> set[str]:
    """Every name a single entry's services can appear under ('Amazon ElastiCache (Redis)' -> redis, ...)."""
    probe = Architecture(summary="", services=[service], data_flow=[])
    return {alias for _, aliases in _service_components(probe) for alias in aliases}


def _design_text(architecture: Architecture) -> str:
    parts = [architecture.summary]
    for service in architecture.services:
        parts.extend([service.name, service.purpose, service.justification])
    for step in architecture.data_flow:
        parts.extend([step.source, step.destination, step.description])
    return " ".join(parts)


def apply_delta(previous: Architecture, delta: ArchitectureDelta) -> Architecture:
    """Merge `delta` into a copy of `previous`; raise InvalidDeltaError if it is ambiguous.

    The result keeps previous.version (the revision agent sets the new
    version on acceptance, as today) and takes the delta's change_log, plus
    one "Removed <name> because <reason>" entry per removal that the
    change_log doesn't already justify.
    """
    by_id = service_ids(previous)
    problems: list[str] = []
    touched: dict[str, str] = {}  # id -> "updated" | "removed"

    def claim(raw_id: str, action: str) -> str | None:
        key = _normalized_id(raw_id)
        if key not in by_id:
            problems.append(f"{action} unknown service ID '{raw_id.strip()[:12]}'")
            return None
        if key in touched:
            problems.append(f"service {key} is {touched[key]} and {action} in the same revision")
            return None
        touched[key] = action
        return key

    updates: dict[str, AWSService] = {}
    for update in delta.updated_services:
        key = claim(update.id, "updated")
        if key is not None:
            updates[key] = update.service

    removals: dict[str, str] = {}
    for removal in delta.removed_services:
        key = claim(removal.id, "removed")
        if key is None:
            continue
        if not removal.reason.strip():
            problems.append(f"removal of {key} ({by_id[key].name}) has no reason")
        removals[key] = removal.reason.strip()

    services: list[AWSService] = []
    for key, service in by_id.items():
        if key in removals:
            continue
        services.append((updates.get(key) or service).model_copy(deep=True))
    for added in delta.added_services:
        # Re-sending an entry that is already in the design, word for word
        # (e.g. a correction repeating its attempt's addition), changes
        # nothing, so it is ignored. A *different* entry under an existing
        # name is still ambiguous and rejected below.
        if added not in services:
            services.append(added.model_copy(deep=True))

    seen: set[str] = set()
    for service in services:
        name = _name_key(service.name)
        if name in seen:
            problems.append(f"two service entries are named '{service.name[:60]}'")
        seen.add(name)

    # A removal only counts if the merged design no longer names the service;
    # otherwise the guard and the report would still see it as present.
    summary = delta.summary if delta.summary and delta.summary.strip() else previous.summary
    data_flow = delta.data_flow if delta.data_flow else previous.data_flow
    merged = Architecture(
        summary=summary,
        services=services,
        data_flow=[step.model_copy(deep=True) for step in data_flow],
        version=previous.version,
        change_log=list(delta.change_log),
    )
    kept_aliases = {alias for service in services for alias in _aliases(service)}
    text = _design_text(merged)
    for key in removals:
        removed = by_id[key]
        stale = [a for a in _aliases(removed) if a not in kept_aliases and mentions(text, a)]
        if stale:
            problems.append(
                f"removed {key} ({removed.name}) is still named in the design ('{stale[0]}'); "
                "update the summary, data_flow or entries that mention it"
            )

    if problems:
        raise InvalidDeltaError(problems)

    for key, reason in removals.items():
        removed = by_id[key]
        if _justification(merged.change_log, sorted(_aliases(removed))) is None:
            merged.change_log.append(f"Removed {removed.name} because {reason.rstrip('.')}.")
    return merged


def delta_between(previous: Architecture, target: Architecture, removal_reason: str = "it is no longer needed") -> ArchitectureDelta:
    """The delta that turns `previous` into `target` (matched by exact service name).

    The inverse of apply_delta, for tests and benchmarks: an entry whose name
    changed becomes a removal plus an addition. Applying the result to
    `previous` gives `target`'s services, data flow and summary.
    """
    target_by_name = {s.name: s for s in target.services}
    updated, removed = [], []
    for key, service in service_ids(previous).items():
        match = target_by_name.get(service.name)
        if match is None:
            removed.append(ServiceRemoval(id=key, reason=removal_reason))
        elif match != service:
            updated.append(ServiceUpdate(id=key, service=match.model_copy(deep=True)))
    previous_names = {s.name for s in previous.services}
    return ArchitectureDelta(
        updated_services=updated,
        added_services=[s.model_copy(deep=True) for s in target.services if s.name not in previous_names],
        removed_services=removed,
        data_flow=[s.model_copy(deep=True) for s in target.data_flow] if target.data_flow != previous.data_flow else None,
        summary=target.summary if target.summary != previous.summary else None,
        change_log=list(target.change_log),
    )

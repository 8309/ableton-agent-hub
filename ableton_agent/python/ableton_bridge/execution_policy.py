from __future__ import annotations

from dataclasses import dataclass


class ExecutionPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class ExecutionDecision:
    requested: str
    effective: str
    wire_mode: str
    risk: str
    requires_inspection: bool


LOW_RISK_ACTIONS = frozenset({"set_mix", "set_parameters", "set_parameter", "set_tempo"})
EPHEMERAL_ACTIONS = frozenset({"transport"})
INSPECT_REQUIRED_ACTIONS = frozenset({
    "clear_region",
    "delete_empty_track",
    "delete_return_track",
    "delete_scene",
    "delete_locator",
    "delete_notes_in_range",
})


def action_risk(action: str) -> str:
    normalized = str(action or "").strip().lower()
    if normalized in LOW_RISK_ACTIONS:
        return "low"
    if normalized in EPHEMERAL_ACTIONS:
        return "ephemeral"
    if normalized in INSPECT_REQUIRED_ACTIONS or normalized.startswith(("delete_", "clear_", "replace_")):
        return "high"
    return "medium"


def resolve_execution(
    action: str,
    *,
    execution: str = "auto",
    commit: bool | None = None,
) -> ExecutionDecision:
    """Resolve user intent while preserving the legacy commit flag."""
    risk = action_risk(action)
    if commit is not None:
        requested = "apply" if commit else "inspect"
    else:
        requested = str(execution or "auto").strip().lower()
    requested = {"dry_run": "inspect", "preview": "inspect", "commit": "apply"}.get(requested, requested)
    if requested not in {"auto", "inspect", "apply"}:
        raise ExecutionPolicyError("execution must be auto, inspect, or apply")
    # Risk is legacy reply metadata only; it no longer selects execution behavior.
    requires_inspection = False
    effective = "apply" if requested == "auto" else requested
    return ExecutionDecision(
        requested=requested,
        effective=effective,
        wire_mode="commit" if effective == "apply" else "dry_run",
        risk=risk,
        requires_inspection=requires_inspection,
    )

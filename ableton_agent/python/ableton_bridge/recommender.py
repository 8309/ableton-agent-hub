from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from .inserter import insert_devices, insert_effects, resolve_device, resolve_effect
from .mixer_control import set_mix
from .multi_parameter_control import set_parameters
from .parameter_summary import ParameterSummaryError, read_parameter_summary
from .style_profiles import StyleProfileError, load_style_profile


class RecommenderError(RuntimeError):
    pass


ACTION_TYPES = {"insert_device", "insert_effect", "set_mix", "set_parameter"}
BATCH_LIMITS = {
    "insert_devices": 8,
    "insert_effects": 8,
    "set_mix": 8,
    "set_parameters": 8,
}


def infer_role(track: dict[str, Any], profile: dict[str, Any] | None = None) -> str | None:
    profile = profile or load_style_profile("uk_garage")
    text = " ".join(
        [
            str(track.get("name", "")),
            str(track.get("target_device", "")),
            " ".join(str(device.get("name", "")) for device in track.get("devices", [])),
        ]
    ).lower()
    for item in profile.get("role_keywords", []):
        role = str(item.get("role", ""))
        keywords = item.get("keywords", [])
        if any(keyword in text for keyword in keywords):
            return role
    return None


def recommend(
    parameter_summary: dict[str, Any] | None = None,
    *,
    style: str = "uk_garage",
) -> dict[str, Any]:
    if not parameter_summary:
        raise RecommenderError("parameter_summary is required")
    try:
        profile = load_style_profile(style)
    except StyleProfileError as error:
        raise RecommenderError(str(error)) from error

    tracks = parameter_summary.get("tracks", [])
    actions: list[dict[str, Any]] = []
    track_summaries: list[dict[str, Any]] = []

    for track in tracks:
        name = str(track.get("name", ""))
        if not name:
            continue
        role = infer_role(track, profile)
        role_profile = profile.get("roles", {}).get(role or "", {})
        devices = _device_names(track)
        target_device = str(track.get("target_device") or "")
        track_summary = {
            "track": name,
            "role": role,
            "target_device": target_device,
            "device_count": len(devices),
        }
        track_summaries.append(track_summary)
        if role is None:
            actions.append(_note_action(name, f"No clear {profile.get('name', style)} role inferred from track/device names."))
            continue

        instrument = role_profile.get("instrument")
        if instrument and not target_device and not devices:
            actions.append(
                {
                    "type": "insert_device",
                    "track": name,
                    "role": role,
                    "device": resolve_device(instrument),
                    "reason": f"{role} track has no matching target instrument",
                }
            )

        for effect in role_profile.get("effects", []):
            resolved = resolve_effect(effect)
            if not _has_device(devices, resolved):
                actions.append(
                    {
                        "type": "insert_effect",
                        "track": name,
                        "role": role,
                        "effect": effect,
                        "resolved_effect": resolved,
                        "reason": f"{role} needs a basic {resolved} stage",
                    }
                )

        for field, value in role_profile.get("mix", {}).items():
            actions.append(_mix_action(name, role, field, value, profile))

        actions.extend(_parameter_actions(track, role, role_profile))

    return {
        "ok": True,
        "style": style,
        "mode": "recommend_only",
        "track_count": len(tracks),
        "action_count": len(actions),
        "tracks": track_summaries,
        "actions": actions,
        "execution_plan": build_execution_plan(actions),
    }


def build_execution_plan(
    actions: list[dict[str, Any]],
    *,
    action_types: set[str] | None = None,
) -> dict[str, Any]:
    allowed_types = _validate_action_types(action_types)
    insert_device_targets: list[dict[str, Any]] = []
    insert_effect_targets: list[dict[str, Any]] = []
    mix_changes: list[dict[str, Any]] = []
    parameter_changes: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for action in actions:
        action_type = str(action.get("type", ""))
        if action_type not in allowed_types:
            skipped.append({"action": action, "reason": "filtered_or_not_executable"})
            continue
        if action_type == "insert_device":
            insert_device_targets.append(
                {
                    "track": action["track"],
                    "device": action["device"],
                }
            )
        elif action_type == "insert_effect":
            insert_effect_targets.append(
                {
                    "track": action["track"],
                    "effect": action.get("effect") or action.get("resolved_effect"),
                }
            )
        elif action_type == "set_mix":
            change: dict[str, Any] = {
                "track": action["track"],
                "field": action["field"],
                "value": action["value"],
            }
            if action.get("field") == "send":
                change["send"] = action["send"]
            mix_changes.append(change)
        elif action_type == "set_parameter":
            parameter_changes.append(
                {
                    "track": action["track"],
                    "device": action["device"],
                    "parameter": action["parameter"],
                    "value": action["value"],
                }
            )

    batches = []
    if insert_device_targets:
        batches.extend(_target_batches("insert_devices", insert_device_targets))
    if insert_effect_targets:
        batches.extend(_target_batches("insert_effects", insert_effect_targets))
    if mix_changes:
        batches.extend(_change_batches("set_mix", mix_changes))
    if parameter_changes:
        batches.extend(_change_batches("set_parameters", parameter_changes))

    batches = _number_batches(batches)
    return {
        "executable_action_count": sum(batch["count"] for batch in batches),
        "batch_count": len(batches),
        "batches": batches,
        "skipped_count": len(skipped),
        "skipped": skipped,
    }


def execute_recommendations(
    recommendation: dict[str, Any],
    *,
    action_types: set[str] | None = None,
    commit: bool = False,
    timeout: float = 5.0,
    batch_numbers: set[int] | None = None,
    stop_on_error: bool = True,
    max_changes: int = 64,
    runners: dict[str, Callable[..., dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    actions = recommendation.get("actions", [])
    if not isinstance(actions, list):
        raise RecommenderError("recommendation must contain an actions list")
    plan = build_execution_plan(actions, action_types=action_types)
    runners = runners or {
        "insert_devices": insert_devices,
        "insert_effects": insert_effects,
        "set_mix": set_mix,
        "set_parameters": set_parameters,
    }
    selected_batches = _select_batches(plan["batches"], batch_numbers)
    selected_change_count = sum(int(batch.get("count", 0)) for batch in selected_batches)
    if max_changes < 1 or max_changes > 512:
        raise RecommenderError("max_changes must be 1..512")
    if selected_change_count > max_changes:
        raise RecommenderError(
            f"selected execution contains {selected_change_count} changes; max_changes is {max_changes}"
        )
    results: list[dict[str, Any]] = []

    for batch in selected_batches:
        batch_type = batch["type"]
        try:
            if batch_type == "insert_devices":
                result = runners[batch_type](batch["targets"], commit=commit, timeout=timeout)
            elif batch_type == "insert_effects":
                result = runners[batch_type](batch["targets"], commit=commit, timeout=timeout)
            elif batch_type == "set_mix":
                result = runners[batch_type](batch["changes"], commit=commit, timeout=timeout)
            elif batch_type == "set_parameters":
                result = runners[batch_type](batch["changes"], commit=commit, timeout=timeout)
            else:
                raise RecommenderError(f"Unsupported execution batch {batch_type!r}")
        except Exception as error:  # noqa: BLE001 - keep execution report machine-readable.
            results.append(
                {
                    "type": batch_type,
                    "ok": False,
                    "error": str(error),
                    "hint": _execution_hint(batch_type),
                }
            )
            if stop_on_error:
                break
            continue
        batch_ok = result.get("ok") is not False
        results.append({"type": batch_type, "ok": batch_ok, "result": result})
        if not batch_ok and stop_on_error:
            break

    unexecuted_batches = selected_batches[len(results) :]

    return {
        "ok": all(result["ok"] for result in results),
        "mode": "commit" if commit else "dry_run",
        "plan": plan,
        "selected_batch_numbers": [batch["batch_number"] for batch in selected_batches],
        "completed_batch_numbers": [batch["batch_number"] for batch in selected_batches[: len(results)]],
        "unexecuted_batch_numbers": [batch["batch_number"] for batch in unexecuted_batches],
        "stop_on_error": stop_on_error,
        "max_changes": max_changes,
        "results": results,
        "summary": summarize_execution(plan, results, selected_batches),
    }


def summarize_execution_plan(plan: dict[str, Any]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    for batch in plan.get("batches", []):
        by_type[batch["type"]] = by_type.get(batch["type"], 0) + int(batch["count"])
    return {
        "batch_count": int(plan.get("batch_count", 0)),
        "executable_action_count": int(plan.get("executable_action_count", 0)),
        "skipped_count": int(plan.get("skipped_count", 0)),
        "by_type": by_type,
        "batches": [
            {
                "batch_number": batch["batch_number"],
                "type": batch["type"],
                "count": batch["count"],
                "tracks": _batch_tracks(batch),
            }
            for batch in plan.get("batches", [])
        ],
    }


def summarize_execution(
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    selected_batches: list[dict[str, Any]],
) -> dict[str, Any]:
    successful = sum(1 for result in results if result.get("ok"))
    failed = len(results) - successful
    return {
        "planned": summarize_execution_plan(plan),
        "selected_batch_numbers": [batch["batch_number"] for batch in selected_batches],
        "executed_batch_count": len(results),
        "successful_batch_count": successful,
        "failed_batch_count": failed,
    }


def _device_names(track: dict[str, Any]) -> list[str]:
    return [str(device.get("name", "")) for device in track.get("devices", []) if device.get("name")]


def _target_batches(batch_type: str, targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"type": batch_type, "count": len(chunk), "targets": chunk}
        for chunk in _chunks(targets, BATCH_LIMITS[batch_type])
    ]


def _change_batches(batch_type: str, changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"type": batch_type, "count": len(chunk), "changes": chunk}
        for chunk in _chunks(changes, BATCH_LIMITS[batch_type])
    ]


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _number_batches(batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    numbered = []
    for index, batch in enumerate(batches, start=1):
        copied = dict(batch)
        copied["batch_number"] = index
        numbered.append(copied)
    return numbered


def _select_batches(batches: list[dict[str, Any]], batch_numbers: set[int] | None) -> list[dict[str, Any]]:
    if not batch_numbers:
        return list(batches)
    available = {int(batch["batch_number"]) for batch in batches}
    missing = batch_numbers - available
    if missing:
        raise RecommenderError(f"Unknown batch number(s): {', '.join(str(number) for number in sorted(missing))}")
    return [batch for batch in batches if int(batch["batch_number"]) in batch_numbers]


def _batch_tracks(batch: dict[str, Any]) -> list[str]:
    items = batch.get("targets") or batch.get("changes") or []
    tracks = []
    for item in items:
        track = str(item.get("track", ""))
        if track and track not in tracks:
            tracks.append(track)
    return tracks


def _has_device(devices: list[str], expected: str) -> bool:
    normalized_expected = _normalize(expected)
    return any(normalized_expected in _normalize(device) for device in devices)


def _has_instrument_like(track: dict[str, Any], expected: str) -> bool:
    target = str(track.get("target_device") or "")
    if target and _normalize(expected) in _normalize(target):
        return True
    return _has_device(_device_names(track), expected)


def _mix_action(track: str, role: str, field: str, value: float, profile: dict[str, Any]) -> dict[str, Any]:
    style_name = str(profile.get("name") or profile.get("slug") or "style")
    if field.startswith("send:"):
        return {
            "type": "set_mix",
            "track": track,
            "role": role,
            "field": "send",
            "send": field.split(":", 1)[1],
            "value": value,
            "reason": f"{role} send balance for {style_name} space",
        }
    return {
        "type": "set_mix",
        "track": track,
        "role": role,
        "field": field,
        "value": value,
        "reason": f"{role} starting mix balance",
    }


def _parameter_actions(track: dict[str, Any], role: str, role_profile: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions = role_profile.get("parameters", [])
    if not suggestions:
        return []
    actions: list[dict[str, Any]] = []
    for device in track.get("devices", []):
        device_name = str(device.get("name", ""))
        for parameter in device.get("parameters", []):
            parameter_name = str(parameter.get("name", ""))
            normalized = _normalize(parameter_name)
            for suggestion in suggestions:
                expected_name = str(suggestion.get("match", ""))
                value = suggestion.get("value")
                if _normalize(expected_name) in normalized:
                    actions.append(
                        {
                            "type": "set_parameter",
                            "track": track.get("name", ""),
                            "role": role,
                            "device": device_name,
                            "parameter": parameter_name,
                            "value": value,
                            "reason": f"{role} preset-style parameter starting point",
                        }
                    )
    return actions


def _note_action(track: str, reason: str) -> dict[str, Any]:
    return {"type": "note", "track": track, "reason": reason}


def _normalize(text: str) -> str:
    return "".join(character for character in text.lower() if character.isalnum())


def _validate_action_types(action_types: set[str] | None) -> set[str]:
    if action_types is None:
        return set(ACTION_TYPES)
    unknown = set(action_types) - ACTION_TYPES
    if unknown:
        raise RecommenderError(f"Unknown action type(s): {', '.join(sorted(unknown))}")
    return set(action_types)


def _parse_action_types(values: list[str]) -> set[str] | None:
    if not values:
        return None
    parsed: set[str] = set()
    for value in values:
        parsed.update(part.strip() for part in value.split(",") if part.strip())
    return _validate_action_types(parsed)


def _parse_batch_numbers(values: list[str]) -> set[int] | None:
    if not values:
        return None
    parsed: set[int] = set()
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                batch_number = int(part)
            except ValueError as error:
                raise RecommenderError(f"Invalid batch number: {part!r}") from error
            if batch_number < 1:
                raise RecommenderError("Batch numbers start at 1")
            parsed.add(batch_number)
    return parsed


def _execution_hint(batch_type: str) -> str:
    if batch_type in ["insert_devices", "insert_effects"]:
        return "Load Ableton Agent Hub.amxd or Ableton Agent Inserter.amxd, then retry this batch."
    if batch_type == "set_mix":
        return "Load Ableton Agent Hub.amxd or Ableton Agent Mixer Control.amxd, then retry this batch."
    if batch_type == "set_parameters":
        return "Load Ableton Agent Hub.amxd or Ableton Agent Multi Parameter Control.amxd, then retry this batch."
    return "Load the matching Ableton Agent device, then retry."


def _load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str, payload: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _unwrap_result(payload: dict[str, Any]) -> dict[str, Any]:
    if "result" in payload and isinstance(payload["result"], dict):
        return payload["result"]
    return payload


def _load_recommendation(path: str) -> dict[str, Any]:
    payload = _unwrap_result(_load_json(path))
    if "actions" not in payload or not isinstance(payload["actions"], list):
        raise RecommenderError("recommendation JSON must contain an actions list")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Recommend safe UK Garage Ableton actions without applying changes")
    parser.add_argument("--parameter-summary-json", help="JSON file from ableton_bridge.parameter_summary")
    parser.add_argument("--recommendation-json", help="JSON file from a previous ableton_bridge.recommender run")
    parser.add_argument("--output-recommendation", help="Write the recommendation result JSON to this file")
    parser.add_argument("--read-live", action="store_true", help="Read Ableton Agent Hub parameter summary before recommending")
    parser.add_argument("--max-devices-per-track", type=int, default=1)
    parser.add_argument("--max-parameters-per-device", type=int, default=4)
    parser.add_argument("--include-display-values", action="store_true")
    parser.add_argument("--style", default="uk_garage")
    parser.add_argument("--execute", action="store_true", help="Dry-run executable batches after recommending")
    parser.add_argument("--commit", action="store_true", help="Actually apply executable batches; requires --execute")
    parser.add_argument("--summary", action="store_true", help="Print a compact execution-plan summary")
    parser.add_argument("--batch", action="append", default=[], help="Execute only specific 1-based batch number(s), e.g. --batch 1 or --batch 1,3")
    parser.add_argument(
        "--action-type",
        action="append",
        default=[],
        help="Limit execution plan to types: insert_device, insert_effect, set_mix, set_parameter",
    )
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--max-changes", type=int, default=64)
    parser.add_argument("--continue-on-error", action="store_true", help="Continue later bounded batches after one fails")
    args = parser.parse_args()

    try:
        if args.commit and not args.execute:
            raise RecommenderError("--commit requires --execute")
        action_types = _parse_action_types(args.action_type)
        batch_numbers = _parse_batch_numbers(args.batch)
        if batch_numbers and not args.execute:
            raise RecommenderError("--batch requires --execute")
        if args.recommendation_json:
            result = _load_recommendation(args.recommendation_json)
        elif args.parameter_summary_json:
            summary = _unwrap_result(_load_json(args.parameter_summary_json))
            result = recommend(summary, style=args.style)
        elif args.read_live:
            summary = read_parameter_summary(
                max_devices_per_track=args.max_devices_per_track,
                max_parameters_per_device=args.max_parameters_per_device,
                include_display_values=args.include_display_values,
                timeout=args.timeout,
            )
            result = recommend(summary, style=args.style)
        else:
            raise RecommenderError("Use --recommendation-json, --parameter-summary-json, or --read-live")
        if action_types is not None:
            result["execution_plan"] = build_execution_plan(result["actions"], action_types=action_types)
        result["execution_plan_summary"] = summarize_execution_plan(result["execution_plan"])
        if args.output_recommendation:
            _write_json(args.output_recommendation, {"ok": True, "result": result})
        if args.execute:
            result["execution"] = execute_recommendations(
                result,
                action_types=action_types,
                commit=args.commit,
                timeout=args.timeout,
                batch_numbers=batch_numbers,
                stop_on_error=not args.continue_on_error,
                max_changes=args.max_changes,
            )
    except (RecommenderError, StyleProfileError, ParameterSummaryError, json.JSONDecodeError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1

    output = {"ok": True, "result": result}
    if args.summary:
        output = {
            "ok": True,
            "summary": result.get("execution", {}).get("summary", result["execution_plan_summary"]),
        }
    print(json.dumps(output, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

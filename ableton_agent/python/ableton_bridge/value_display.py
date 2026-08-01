from __future__ import annotations

from typing import Any


VALUE_DISPLAY_MODES = {"both", "internal", "ui"}


class ValueDisplayError(ValueError):
    pass


def normalize_value_display_mode(mode: str) -> str:
    normalized = str(mode or "both").strip().lower()
    if normalized not in VALUE_DISPLAY_MODES:
        raise ValueDisplayError("value display mode must be one of: both, internal, ui")
    return normalized


def format_value_display(payload: Any, mode: str) -> Any:
    normalized = normalize_value_display_mode(mode)
    return _format_value(payload, normalized)


def _format_value(value: Any, mode: str) -> Any:
    if isinstance(value, list):
        return [_format_value(item, mode) for item in value]
    if not isinstance(value, dict):
        return value

    result = {key: _format_value(item, mode) for key, item in value.items()}
    if "value" not in result or "display_value" not in result:
        return result

    internal_value = result["value"]
    display_value = result["display_value"]
    if mode == "internal":
        result.pop("display_value", None)
        return result
    if mode == "ui":
        result["internal_value"] = internal_value
        result["value"] = display_value
        result.pop("display_value", None)
        return result
    result["ui_value"] = display_value
    return result

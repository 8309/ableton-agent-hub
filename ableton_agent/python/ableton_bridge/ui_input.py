import math


def parse_ui_literal(value):
    if value.lower().startswith("ui:"):
        result = {"ui_value": value[3:].strip()}
        validate_value_input(result)
        return result
    return None


def validate_value_input(change):
    numeric = change.get("value") is not None
    ui = change.get("ui_value") is not None
    if numeric == ui:
        raise ValueError("provide exactly one of value or ui_value")
    if ui and (not isinstance(change["ui_value"], str) or not change["ui_value"].strip()):
        raise ValueError("ui_value must be a nonempty string")
    for key in ("value", "expected_before"):
        value = change.get(key)
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError(f"{key} must be a finite number")

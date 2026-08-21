# Parameter Value Display Contract

Live parameter values have three distinct representations:

```json
{
  "value": 0.04,
  "display_value": "-65.0 dB",
  "display_text": "-65.0 dB",
  "display_numeric_value": -65.0,
  "display_value_source": "lom_display_value"
}
```

- `value` is the exact internal `DeviceParameter.value` and remains the source
  of truth for writes and readback.
- `display_numeric_value` is the current numeric GUI-scale value read from the
  official `DeviceParameter.display_value` property. It is `null` when that
  property is unavailable or cannot be represented as finite JSON.
- `display_text` is Live's formatted `str_for_value(value)` result, including
  units or labels when Live supplies them.
- `display_value` remains a compatibility alias for `display_text`; existing
  Python clients and saved payloads therefore keep their current behavior.
- `display_value_source` records how the display fields were produced:
  - `lom_display_value`: current direct GUI value was available; display text
    still comes from `str_for_value`.
  - `str_for_value_fallback`: the current direct GUI value was unavailable, so
    only formatted text is available.
  - `str_for_value_target`: a dry-run target was formatted without writing Live;
    `display_numeric_value` is intentionally `null`.

Dry-runs must never set a parameter merely to obtain its direct GUI value.
They preserve the requested internal target and call `str_for_value(target)`.
After commit, readback may report both the exact internal value and the direct
current GUI value.

Python `value_display` modes remain compatible:

- `ui`: user-facing `value` is the formatted text and `internal_value` preserves
  the exact Live value.
- `internal`: all display-only fields are removed.
- `both`: internal `value` is preserved and `ui_value` contains formatted text.

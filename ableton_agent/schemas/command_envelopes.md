# Ableton Agent Command Envelopes

Hub commands use one OSC route per capability:

```text
/<command> request_id payload_json mode
```

Fields:

- `request_id`: caller-generated id used to match replies.
- `payload_json`: JSON object. Use `{}` when no payload is needed.
- `mode`: `dry_run` or `commit`.

Replies use the same command route and include:

```text
/<command> request_id result_json
```

`result_json` should include `ok`, `dry_run`, and either `message` or `error`.

## Track Target Envelope

Commands that can address ordinary, Return, or Main tracks use the same target
fields inside `payload_json`:

```json
{"section":"return","track_id":501}
```

- `section`: `track`, `return`, or `main`; legacy `master` is accepted as an
  alias for `main`.
- `track_id`: the session-stable Live object id returned by a scan or dry-run.
- `track`, `track_name`, and `track_index`: compatibility selectors for ordinary
  tracks and for read/dry-run discovery.

Ordinary-track commands keep their existing selector behavior. A commit to a
Return or Main track must include its `track_id`; selected-track or index-only
special-track commits are rejected.

## Parameter Summary Inspection Actions

`/parameter_summary` keeps its original whole-Set summary behavior when no
`action` is supplied. Its `list_parameters` and `search_parameters` actions are
read-only bounded alternatives for inspecting one device. They always use
`dry_run` mode and accept:

```json
{
  "action": "search_parameters",
  "section": "track",
  "track_id": 101,
  "device_id": 202,
  "query": "unison",
  "read": {
    "cursor": 0,
    "limit": 16,
    "projection": ["identity", "metadata", "internal_value", "display_value"],
    "budget_ms": 1000,
    "expected_collection_token": null
  }
}
```

- `action`: `list_parameters` or `search_parameters`.
- Track target: shared `section + track_id` envelope; ordinary track name/index
  remains available for discovery.
- Device target: stable `device_id`, or a top-level device name/index. A stable
  ID may identify a Rack-chain nested device; the reply then includes depth,
  parent Rack/Chain IDs, and `chain_path`.
- `read.cursor` addresses the original parameter index, including for search;
  each page therefore inspects at most `read.limit` parameter names.
- `offset`, `limit`, `include_display_values`, and `include_enum_values` remain
  compatibility aliases for calls without `read`.
- The full paging, projection, token, budget, partial, and warning semantics are
  defined in `bounded_read_contract.md`.

Replies include the resolved stable target, exact original indices, selected
fields, and unified `read` metadata. Search match totals are known only after
the Python coordinator reaches the end of the raw parameter collection.

When `display_value` is projected, replies preserve the legacy formatted
`display_value` text and add `display_text`, direct current
`display_numeric_value`, and `display_value_source`. Dry-run targets use
`str_for_value(target)` without writing Live. See
`parameter_value_display_contract.md`.

Parameter `metadata` also reports Live's read-only `is_enabled` and
`automation_state` plus a
stable label: `none` (`0`), `active` (`1`), or `overridden` (`2`). Static
`/set_parameters` dry-runs and commit readbacks include the same fields. This is
diagnostic state only; the public Live Object Model does not expose Arrangement
automation envelopes or breakpoint authoring.

## Recursive Device Trees And Nested Writes

`/device_chain` action `scan_recursive` is read-only and resolves one ordinary
track before walking Rack `chains`, `return_chains`, and their nested devices.
It accepts `track_id` or the compatible name/index selectors, plus bounded
`max_depth` and `max_devices` limits. Every device record contains a stable
`device_id`, depth, parent Rack/Chain IDs, `chain_path`, exposed parameter count,
and Rack `has_macro_mappings` state.

For a complex track, pass a returned Rack ID as `root_device_id`:

```json
{
  "action": "scan_recursive",
  "track_id": 564,
  "root_device_id": 572,
  "max_depth": 2,
  "max_devices": 32,
  "budget_ms": 1000
}
```

The selected Rack is relative depth `0` and counts toward `max_devices`; all
descendants count cumulatively. Records retain their absolute parent/chain path
and add `relative_depth` plus `absolute_depth`. The reply reports
`truncation_reasons`, `elapsed_ms`, and `selectable_child_rack_ids`. Continue a
truncated scan by selecting one returned child Rack as the next
`root_device_id`. Without `root_device_id`, existing whole-track behavior is
preserved. Rooted scans default to a 1000 ms object-boundary budget; one blocking
LiveAPI property read cannot be interrupted mid-call.

`/set_parameters` retains all previous top-level behavior. A nested target uses:

```json
{
  "section": "track",
  "track_id": 101,
  "device_id": 202,
  "parameter_id": 303,
  "parameter": "Filter Freq",
  "value": 0.5
}
```

- Dry-run may discover using compatible selectors, but a nested commit requires
  all three stable IDs from the reviewed scan/read result.
- Rack Macro controls are writable as enabled parameters on the Rack device.
- Internal-device parameters are writable only when Live reports
  `is_enabled: true`.
- `is_enabled: false` is rejected before any write because the parameter may be
  Macro-controlled or otherwise disabled by Live.
- Commit replies read the parameter back and preserve internal and UI values.
- The API cannot enumerate or author the complete Macro mapping graph.

## Track Scan Actions

`/track_management` keeps legacy one-shot behavior for direct requests without
`read`. Python uses bounded scans by default for `scan_tracks` and
`scan_hierarchy`:

```json
{
  "action": "scan_hierarchy",
  "include_returns": true,
  "include_main": true,
  "read": {
    "cursor": 0,
    "limit": 16,
    "projection": ["identity", "hierarchy"],
    "budget_ms": 1000,
    "expected_collection_token": null
  }
}
```

Hub pages contain flat track records. Python safely aggregates them, then
rebuilds hierarchy and compatibility fields. Optional projections are `color`,
`fold`, and `device_count`; Return routing properties are never traversed.

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
- Device target: stable `device_id`, or a device name/index.
- `read.cursor` addresses the original parameter index, including for search;
  each page therefore inspects at most `read.limit` parameter names.
- `offset`, `limit`, `include_display_values`, and `include_enum_values` remain
  compatibility aliases for calls without `read`.
- The full paging, projection, token, budget, partial, and warning semantics are
  defined in `bounded_read_contract.md`.

Replies include the resolved stable target, exact original indices, selected
fields, and unified `read` metadata. Search match totals are known only after
the Python coordinator reaches the end of the raw parameter collection.

Parameter `metadata` also reports Live's read-only `automation_state` and a
stable label: `none` (`0`), `active` (`1`), or `overridden` (`2`). Static
`/set_parameters` dry-runs and commit readbacks include the same fields. This is
diagnostic state only; the public Live Object Model does not expose Arrangement
automation envelopes or breakpoint authoring.

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

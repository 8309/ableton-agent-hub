# Parameter Read Diagnostics Contract

This contract extends `/parameter_summary` without adding a new public Hub
route or changing bounded-read pagination semantics.

## Stage 1 Final Envelope

Python creates one `request_id`, places it in both the OSC arguments and JSON
payload, and accepts only a correlated final reply. The Hub final response keeps
the existing route and adds:

```json
{
  "request_id": "...",
  "diagnostics": {
    "stage": "reply_serializing",
    "operation": null,
    "parameter": {"index": 3, "id": 45, "name": "Filter Freq"},
    "property": null,
    "hub_elapsed_ms": 8,
    "stage_timings_ms": {}
  },
  "client_elapsed_ms": 11
}
```

The lightweight Hub stages are:

```text
hub_received
payload_validated
track_resolving / track_resolved
device_resolving / device_resolved
parameter_collection_loading / parameter_collection_loaded
collection_token_verifying / collection_token_verified
page_started
parameter_started / parameter_field_started / parameter_field_completed / parameter_completed
page_completed
reply_serializing
client_received
```

Parameter field operations are `identity`, `internal_value`, `metadata`,
`display_value`, and `enum_values`. A property failure contains the stable
parameter index/id/name when available and the exact property or conversion
operation.

Errors use `error_code`, `error_layer`, `request_id`, and `diagnostics`. Current
codes include:

```text
client_validation_failed
udp_send_failed
udp_reply_timeout
udp_reply_invalid
hub_route_failed
target_not_found
stale_collection
cursor_out_of_range
lom_collection_read_failed
lom_property_read_failed
response_serialization_failed
auto_collect_failed
```

`page_budget_exceeded` remains a successful bounded partial page, represented by
the existing `read.partial`, `read.warnings`, and cursor metadata rather than a
generic timeout.

Python keeps a process-local ring buffer of at most 64 compact journal records.
It stores request target/read metadata and the latest checkpoint, never returned
parameter arrays or complete Live Set snapshots.

## Stage 2 Progress Compatibility

Progress is opt-in and must not be emitted on `/parameter_summary`. Existing
clients treat the first correlated packet on that route as the final result.
The compatible future transport is:

```text
/parameter_summary_progress request_id progress_json
/parameter_summary          request_id final_json
```

Progress JSON must contain `kind: "progress"`, the same `request_id`, and a
`checkpoint`. Final JSON may contain `kind: "final"`; absence of `kind` remains
compatible with older Hub builds. Python already supports a separate progress
route and ignores unrelated request IDs. Normal reads do not subscribe to it.

Future Hub emission levels are reserved as `none`, `page`, `parameter`, and
`field`. No Hub emitter or public `trace_level` is claimed by this checkpoint.
A Hub-side ring buffer alone cannot close the hard-block blind spot: if a
synchronous LiveAPI call blocks Max's scheduling thread, another request cannot
reliably read that buffer. A progress packet sent immediately before the risky
call can identify the last reached checkpoint from Python.

## Stage 3 Read-Only Diagnostic Sequence

A future orchestration command should issue only sequential requests:

1. `/ping`.
2. One identity-only page.
3. Add `internal_value`.
4. Add `metadata`.
5. Add `display_value`, then `enum_values`.
6. Split one failing page to `limit=1`.
7. Probe the failing parameter one field at a time.
8. Validate token, cursor, and auto-collector behavior.
9. Finish with `/ping`.

It must have fixed attempt and time limits and must not immediately replay the
same timed-out request. Stage 3 is designed here but is not yet exposed as a CLI
command.

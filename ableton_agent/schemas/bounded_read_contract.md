# Bounded Read Contract

Bounded reads extend existing read-capable Hub routes. They do not introduce a
shared public route or change the ownership of track, parameter, clip, or device
semantics.

## Request

```json
{
  "read": {
    "cursor": 0,
    "limit": 16,
    "projection": ["identity", "metadata", "internal_value"],
    "budget_ms": 1000,
    "expected_collection_token": null
  }
}
```

- `cursor` is the zero-based index in the adapter's ordered source collection.
- `limit` is the maximum number of source objects inspected by one page. A
  search page can therefore return fewer items than it scans.
- `projection` selects adapter-owned fields. Unselected fields must not be read.
- `budget_ms` is checked between objects. It cannot interrupt one blocking
  LiveAPI property call.
- `expected_collection_token` is omitted or `null` on the first page and must
  match the first page token on every continuation page.

Requests without `read` retain their route's legacy behavior.

## Reply

```json
{
  "ok": true,
  "dry_run": true,
  "read": {
    "complete": false,
    "partial": false,
    "cursor": 0,
    "next_cursor": 16,
    "limit": 16,
    "scanned_count": 16,
    "returned_count": 16,
    "has_more": true,
    "collection_token": "fnv1a-1234abcd-93",
    "elapsed_ms": 82,
    "warnings": []
  },
  "items": []
}
```

`partial` means the page stopped at an object boundary because its budget was
reached. A clean partial page can continue from `next_cursor`. `complete` is
true only when the page is not partial and the source collection has no more
objects.

If the ordered Live IDs change, a continuation request is rejected with a
`stale_collection` error. Pages from different collection versions must never
be combined.

## Python Coordination

The shared coordinator sends pages sequentially over UDP 7400/7401. Defaults:

- 32 pages maximum
- 512 returned items maximum
- 30 seconds total
- 5 seconds per page

It continues through clean pages, including clean partial pages. It stops on a
warning or a safety limit and reports an incomplete aggregate. Hub business
errors, token changes, malformed metadata, and non-advancing cursors raise an
error so command-line callers return exit code `1`.

## Parameter Projection

`/parameter_summary` supports:

- `identity`: original parameter index, stable Live ID, and name
- `metadata`: minimum, maximum, and quantized state
- `internal_value`: exact Live parameter value
- `display_value`: requests the shared display bundle: legacy formatted
  `display_value`, explicit `display_text`, direct current
  `display_numeric_value`, and `display_value_source`
- `enum_values`: bounded labels for a quantized parameter

When a bounded parameter request omits `limit`, the Parameter adapter uses a
conservative default of `4`. Python sends that value explicitly so the request
is inspectable, while direct Hub requests with `read: {}` use the same adapter
default. Callers may still supply any valid `limit` from `1` through `32`.
`cursor`/legacy `offset` continues to default to `0`.

Internal values remain the source of truth. User-facing reports of a modified
parameter should preserve that value and request `display_value` when available.
The full current-value, dry-run-target, and old-Live fallback behavior is
defined in `parameter_value_display_contract.md`.

## Track Projection

`/track_management` applies bounded reads to `scan_tracks` and
`scan_hierarchy`:

- `identity`: section, section-local index, stable Live ID, name, and track type
- `hierarchy`: flat `parent_group_id`; Python rebuilds paths, children, roots,
  and the hierarchy tree only after all pages are collected
- `color`: Live color integer
- `fold`: foldable, grouped, visible, and fold-state fields
- `device_count`: number of devices on the track

The default is `identity + hierarchy`. Ordinary Tracks, Return Tracks, and Main
share one ordered page collection, while compatibility `tracks`,
`return_tracks`, `main_track`, `root_track_ids`, and `hierarchy` fields are
rebuilt by Python. Return records never read routing properties.

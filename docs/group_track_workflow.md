# Group Track Workflow

Ableton Agent exposes Group Track information through the existing
`/track_management` Hub route. The public Live Object Model supports hierarchy
reads and existing Group Track properties, but does not expose supported
functions for creating a Group Track or moving/reordering tracks.

## Scan Hierarchy

```powershell
$env:PYTHONPATH='ableton_agent/python'
python -m ableton_bridge.track_management --action scan_hierarchy --include-returns
```

The result includes:

- ordinary and Return Track counts
- session-stable `track_id` values
- `parent_group_id`, depth, and group path
- direct `child_track_ids`
- nested hierarchy output
- group visibility and fold state

Live object IDs protect a plan from index changes within the current Live
session. They are not persisted in project documentation and must be scanned
again after reopening Live or the Set.

## Existing Group Properties

First dry-run the intended change:

```powershell
python -m ableton_bridge.track_management `
  --action set_group_properties `
  --group-track-id 123 `
  --name DRUMS `
  --color '#D35F5F' `
  --fold-state 0
```

Review the target group, members, before/after order, and `plan_token`. Commit
using that exact token:

```powershell
python -m ableton_bridge.track_management `
  --action set_group_properties `
  --group-track-id 123 `
  --name DRUMS `
  --color '#D35F5F' `
  --fold-state 0 `
  --plan-token abc12345 `
  --commit
```

The commit is rejected if the current IDs, order, hierarchy, or group state no
longer match the dry-run. A successful response includes hierarchy readback.

## Structural Plans

The following actions are dry-run planning operations only:

- `create_group`
- `move_track_to_group`
- `move_track_out_of_group`
- `reorder_track`
- `plan_groups`

They resolve ordinary tracks by `track_id`, exclude Return Tracks, and return
the projected order and member IDs. `--commit` is intentionally rejected because
Live 12.3.5 does not expose the required public functions.

For multiple groups, provide a JSON array directly or through `@path`:

```json
[
  {"name": "DRUMS", "member_track_ids": [101, 102, 108]},
  {"name": "BASS", "member_track_ids": [103, 109]}
]
```

```powershell
python -m ableton_bridge.track_management `
  --action plan_groups `
  --groups-json '@group_plan.json'
```

Apply the plan manually in Live, then run `scan_hierarchy` again. Compare the
ordinary track order, each member's `parent_group_id`, and the Group Track's
`child_track_ids` before treating the manual change as verified.

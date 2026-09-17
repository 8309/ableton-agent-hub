# Ableton Agent MCP Server

## Reference Audio Search

`ableton_search_sounds` accepts optional `reference_audio` and `candidate_limit`
(default 24, maximum 64). Five ranked results are returned by default. This
updates only the local SQLite feature cache, never Live. Unsupported encodings
are explicitly skipped; see [Audio Similarity](audio_similarity.md). Restart
MCP after updating this Python schema; no Hub reload is needed for this feature.

## Diagnostic And Batch Tools (2026-09-17)

The current Python schema has 27 tools. `ableton_diagnose_parameters` performs
bounded sequential read-only field probes; `ableton_apply_batch` combines a mixer
batch followed by a parameter batch in one tool call, stopping on first failure.
Stable IDs, readback and restore receipts are retained. No transactional rollback
or faster individual LiveAPI calls are claimed. `ableton_status` adds 32 recent
operation summaries. Restart MCP; no Hub reload. Live acceptance is pending.
Details: `plugin_improvement_batches.md`. Counts below describe earlier batches.

## Saved Curve Reader (2026-09-09)

25 tools in the updated Python server. `ableton_read_saved_automation` takes an
explicit ALS path and reads saved Arrangement curve nodes locally. No Hub calls,
no live freshness claim, and no file/runtime ID equivalence. Restart MCP only
for these saved-file additions; see `docs/saved_automation.md` and
`docs/saved_als_reading.md`. Existing Hub reload issues
are independent. `ableton_scan_automation` still reads current parameter states,
not saved curve breakpoints.

`ableton_read_saved_set` is the complete local saved-ALS reader. It composes the
old snapshot, project, MIDI, automation and Groove readers, sharing one parsed
file document. It does not call the Hub or compete for UDP `7401`.

## Automation Inventory And Arrangement

The saved-reader batch's 25-tool server includes `ableton_scan_automation` and
`ableton_edit_arrangement`. The inventory uses a new lightweight
`identity + automation_state` projection; Arrangement reuses existing same-track
audio movement and MIDI note-data copying, without another whole-track guard layer.
Use this document for current scope and the capability matrix for validation
state. The detailed 2026-09-09 deployment record is archived at
`docs/history/validation/mcp_arrangement_automation_2026-09-09.md`.

## Automation-State Reads And Legacy Summary Timeouts

For multi-device inventory, prefer `ableton_scan_automation`; resume its bounded
continuation instead of composing whole-Set parameter summary calls. For a narrow
read on the updated Hub, use `projection:["identity","automation_state"]`.
The older `identity + metadata` path remains compatible.

Use `ableton_read_parameters` on a discovered track/device ID with
`projection:["identity","metadata"]`, `limit:4`. `metadata` contains
`automation_state` and its name. For a healthy single device, `collect_all:true`
aggregates sequential bounded pages; check complete/partial/warnings. Nested
devices need separate discovery. Do not infer full-Set coverage from one device.
State flags are not automation breakpoint/time-position data or a backup.

CLI fallback must explicitly use `--action list_parameters`. Without an action,
`ableton_bridge.parameter_summary` selects legacy whole-Set `summary`:
`--max-devices-per-track 8 --max-parameters-per-device 32 --include-display-values`
is a potentially large, unpaged scan. The ordinary `--limit` default does not
apply to summary. This compatibility path has not been migrated; do not use it
as the default way to list automation, or increase its limits to improve coverage.

After timeout: keep the failed request ID/payload, check status once, and if
healthy read one known parameter with metadata and `trace_level:"field"`.
Only expand after success. Do not blindly resend the large request or conclude
that a reload is needed. PARAM-001 records the 2026-09-09 reproduction and recovery.

## Creative Tools Update (historical batch, 2026-09-07)

MCP-005 adds nine tools: **21 total**, including the project enabled_tools list.
Partial Live acceptance passed at that historical checkpoint. The subsequent
color correction and MCP-006 device-containing deletion now passed Live acceptance.
At that historical checkpoint, `reload_required:false`, `mcp_restart_required:false`; older instances
in other Sets still need a future manual reload and older MCP processes a schema refresh.
User reloads Hub manually in the desired Set; no background task should reload
a different song. This section supersedes older no-reload statements below.

All nine tools use a typed `request` object. Creative writes default to
`execution:"inspect"`, return `plan_token`, and require `execution:"apply"` with
the exact same fields and token within 120 seconds. Plans are one-use and bounded
to 32 per module. Reinspect after changing intent or state. A plan is an impact
check, not an audible simulation. Existing fast scalar tools remain unchanged.

| Tool | Scope |
| --- | --- |
| `ableton_write_midi_clip` | New Session Clip using track_id + scene_id, or Arrangement Clip using track_id + start; empty destinations only. |
| `ableton_edit_midi_notes` | track_id + clip_id; shift_notes, quantize_notes, scale_velocity in a Clip-local beat window; retains note IDs and extra note fields. |
| `ableton_vary_midi_clip` | New Arrangement duplicate/fill/thin/mute note-data variant at target_start; source untouched. Zero-origin single-loop source only; no envelope/MPE/launch-state copying. |
| `ableton_search_sounds` | Existing SQLite catalog; query/role/kind/Pack/official tag/device/key/BPM/duration/loop filters, default 5 candidates. Checks real paths, no scan or Live requests. |
| `ableton_confirm_sample` | Direct Simpler or specific Drum Rack pad_note by track_id + device_id; read path after manual loading and compare intended_path. |
| `ableton_insert_device` | One whitelisted native instrument/effect by stable track_id; effects also support Return/Main. Reject duplicate effect or a second instrument. |
| `ableton_eq` | List presets or apply_preset on stable track_id + device_id; internal/UI readback, reject unresolved or disabled parameters. |
| `ableton_manage_tracks` | Append ordinary MIDI/audio tracks, rename/color stable ordinary/Return/Main targets, or `delete_track` by stable ID after inspection. Deletion excludes Group/Return/Main, the Hub host and last ordinary track. Never arm or select newly created tracks. |
| `ableton_manage_scenes` | Bounded list (16 default, 32 maximum), append/duplicate/rename/fire stable Scene. Fire requires explicit user intent and an inspected token. |

MIDI operations cap stored notes at 512 and new Clip length at 256 quarter-note
beats; wire requests above 48000 JSON bytes reject before dispatch (therefore
the usable note count can be lower). Do not split a rejected write into occupied
destinations automatically. Readback checks note content/count, metadata and
new IDs. Edits use native note modification, not remove/recreate. Creation,
Scene and EQ operations return their specific verification scope; a fire request
does not prove playback started. A failed partial apply/timeout means stop and
inspect, not blindly retry or assume automatic rollback.

Example inspection (fictional runtime IDs; first resolve current IDs):

```json
{"request":{"track_id":101,"scene_id":201,"length":4,"name":"Bass Test",
"notes":[{"pitch":36,"start_time":0,"duration":0.5,"velocity":90}]}}
```

Send the same request with execution=apply and the returned plan_token only
after impact acceptance. Existing legacy Python/Hub callers retain their old
schemas. Private creative envelopes intentionally fail closed on older Hubs.
Nested Rack insertion/EQ/sample targets, capture MIDI, other deleting, replacing and
group movement are not exposed by this batch.

### Track Deletion (MCP-006)

Creation and deletion share `ableton_manage_tracks` and `/track_management`.
Inspect with `{"request":{"action":"delete_track","track_id":117}}` (example ID
only). After explicit user intent and review, resend the same request with
`execution:"apply"` and its `plan_token`. No new tool or public route is added;
the legacy `delete_empty_track` action still refuses nonempty tracks.

The impact lists target ID/name/index, parent group, direct devices, Arrangement
and Session Clips, and before/expected-after ordinary track IDs. It covers an
entire track deletion, not just empty-track cleanup. Nested device contents,
notes, take lanes and automation are also removed but are not enumerated or
snapshotted; routing may change as a consequence. These omissions are explicitly
reported. The token guards the listed metadata/membership/order, not every
parameter or note value. Do not treat this as an exact-content restore receipt.

Inspection caps: 64 direct devices, 128 Arrangement Clips, 256 Session slots,
1500 ms between content objects and the existing 14000-byte plan limit. These
budgets cannot interrupt one blocking LiveAPI call. Exceeding a limit fails
closed with no token; use manual deletion rather than a truncated impact.
Hub ancestry is checked even inside a Rack. Apply resolves the current native
index, uses Live Undo grouping, and checks exact remaining ordinary IDs/order
plus unchanged Return/Main IDs. Failed apply/readback never triggers a retry.
Automated tests and real device-containing audio-track deletion pass. Live test
created temporary track 231 with Utility 232, deleted only that track, and verified
exact original ten-track order, unchanged Return/Main IDs and healthy final ping.
Hub-host protection passes; actual Clip-containing deletion and manual Undo
restoration remain untested. See
`docs/history/validation/mcp_creative_validation_2026-09-07.md` for the
historical evidence.
Decision: `docs/adr/0006-guarded-track-deletion.md`.

Live acceptance on 2026-09-07 confirmed host discovery of 21 tools, Session and
Arrangement MIDI creation, ID-preserving shifts, a new fill, Simpler/EQ insertion,
EQ preset UI/internal readback, Scene creation, local sound search, and empty
Simpler confirmation. Track creation exposed a false failure: Live maps arbitrary
RGB to its nearest palette color. Fixed results now return actual `color`,
`requested_color`, `color_exact_match` and `color_policy:"nearest_live_palette"`;
verified means a valid native readback, not exact RGB equality. This corrective
Hub build needs another manual reload. MCP-006 additionally changes the tool action schema. Loaded-sample
positive confirmation and playback acceptance still need user participation.

Validation: automated SDK discovery/invocation and Max mock acceptance pass;
see MCP-005 and the Live results below for the exact accepted operations.
Decision and packet boundaries: `docs/adr/0005-guarded-mcp-creative-tools.md`.

## Common Tools Update (2026-09-05)

MCP-004 added six tools to the original six. This was a Python facade update over
existing Hub routes: `reload_required:false`, `mcp_restart_required:true` for
already-running Codex/MCP processes. Do not re-drag Hub for this update.
The project `.codex/config.toml` enabled_tools allowlist must include all twelve;
SDK tool discovery alone does not validate the host's filtering. A regression
assertion checks that the configured allowlist matches the server inventory.

| Tool | State change | Purpose and defaults |
| --- | --- | --- |
| `ableton_transport` | ephemeral action | Default status is read-only. Requested play/stop/continue/jump/set_position auto-apply; inspect is available. Beat is a zero-based quarter-note position; play with beat auditions that position. |
| `ableton_tempo` | explicit apply | Read with no bpm; supplying bpm defaults to inspect. Apply writes live_set.tempo and returns before/current BPM, not an automation edit or guarded restore receipt. |
| `ableton_list_locators` | no | Read Arrangement locator IDs/names/beats. No creation/deletion or jump. |
| `ableton_scan_clips` | no | One Arrangement or Session metadata page, default 4 items. Optional zero-based track_index is a read filter; returned clip IDs are used for note reads. |
| `ableton_read_clip_notes` | no | One MIDI clip-local window, default 4 beats. Requires clip_id. Cursor and beat_window are beats, not note indexes/counts. |
| `ableton_read_meters` | no | One explicitly identified track/Return/Main, one instant, no polling or automatic playback. |

Both clip tools return the existing `read` metadata and a `continuation` with
cursor/token. Keep the target/filter/clip ID unchanged when continuing. Warnings
and errors suppress continuation; clean budget partial can continue. Clip metadata
collection is capped at 512; a reached cap warns to narrow by track_index, rather
than claiming a complete Set. Pagination still enumerates the collection per
request. Note tokens protect ID/length, not concurrent note edits; dense windows
can exceed UDP packet limits, and budgets cannot interrupt a blocking getter.

Transport retains the existing delayed status readback (including its 200 ms
wait). Failed apply stops immediately; failed readback reports `ok:false`, keeps
the original applied result/request ID and includes the failed readback. No blind
retry or automatic reversal is performed. Meter silence/clipping indications are
instantaneous and heuristic, not a whole-song measurement.

Validation: full suite 196 tests OK, including SDK tool schemas/calls, invalid
arguments rejected before dispatch, inspect/apply mapping, paging/token/warnings,
error propagation and cross-tool serialization. A fresh SDK STDIO subprocess
listed all 12 tools and sequentially passed status, transport status, tempo read
and inspect at 80 BPM, two locators, one clip metadata page, an 18-note one-beat
window (clip 971), track 894 meters, and final status. All Live calls were read-only.
Clip metadata took about 391 ms client time (394 ms Hub); notes took 5 ms Hub time.
These are individual observations, not a benchmark. Actual restarted Codex-host
discovery now exposes all twelve tools after correcting the allowlist. Its first
status timed out after 3031 ms; subsequent reads were not sent. After user-confirmed
Hub recovery, actual-host status, tempo (80 BPM) and locator listing (2) pass
sequentially without changes. Narrow host read acceptance passes; new MCP
write-path Live validation remains pending. No further restart is needed now.

## Discovery And Trace Update (2026-09-05)

MCP-003 discovery and PARAM-009 Stage 2 successful-read progress delivery are
Live-validated after manual Hub reload and MCP restart on 2026-09-05. The active
instance needs no further reload. Older instances must load the rebuilt Hub and
restart Codex/MCP before using the new arguments, when the user selects that Set.
No additional tool or public Hub request route is added.

- Device lookup now forwards `section` and defaults to `scan_mode="children"`:
  four direct devices per page, without parameter collection reads. Continue
  siblings using the returned `continuation` and then expand the returned
  `selectable_child_rack_ids` via `root_device_id`. A complete direct-child page
  does not mean all descendants were searched. `search_scope` makes this explicit.
- For the previous traversal behavior choose `scan_mode="recursive"`, with
  `max_depth` (0..12), `max_devices` (1..512) and `budget_ms` (1..5000).
- Parameter lookup defaults to identity-only pages of four, at most 32 pages per
  call. Resume past 128 raw positions with `continuation`; do not report no match
  until `source_complete` is true. `page_limit` and `max_pages` are overridable;
  each call remains capped at 512 scanned positions, 15 seconds and 32 pages.
- `limit` controls displayed matches, not source page size. `match_offset`
  continues undisplayed matches within the same source window; retain query,
  target IDs, root, mode and all limits. It rereads the bounded window and checks
  the token. After those matches, continuation moves to the next source cursor.
  Do not change names/structure during continuation; tokens validate ordered IDs,
  not a transactional snapshot of names. Warnings stop automatic continuation.
- Track lookup caches only complete identity/hierarchy directories for five
  seconds. Each hit checks `/track_management lookup_revision` (Hub generation,
  Song ID and ordered ordinary/Return/Main IDs), without per-track properties.
  Cache age/TTL/hit are returned. `refresh=true`, expiry, changed revision, new
  Set reads, writes and errors invalidate it. Rename/fold/hierarchy edits may be
  stale within that TTL; refresh to see manual edits immediately. Writes never
  trust this cache in place of Hub stable-target resolution.
- `ableton_read_parameters(trace_level="field")` subscribes to optional progress
  on the same sequential UDP exchange. `none` emits nothing, `page` traces the
  pipeline, `parameter` adds start/end, and `field` adds actual property/conversion
  boundaries. Timeout retains the last received checkpoint. Delivery is best-effort,
  does not interrupt a blocked LOM call. A successful Live read delivered 27
  correlated packets; delivery during a real synchronous hang remains unverified.

Direct clients expose `device_chain --action scan_children --section return`
and `parameter_summary --trace-level field`. ADR-0003 and
`ableton_agent/schemas/parameter_read_diagnostics_contract.md` define the limits.

The Ableton Agent MCP server is a local, persistent STDIO process that exposes a
small set of stable tools to Codex. It does not replace the Max for Live Hub and
does not add another Live API backend.

```text
Codex MCP client
  -> local STDIO process
  -> ableton_bridge Python clients
  -> OSC/UDP 7400
  -> Ableton Agent Hub.amxd
  -> Live Object Model
  -> UDP 7401 reply
```

The persistent process removes repeated Python startup and command-discovery
work. A service lock serializes its Hub operations, and every Python reply socket
now takes a shared OS-backed lock before binding UDP `7401`. This coordinates
updated MCP processes and direct CLI clients under the same OS user/temp directory.
The existing request IDs, bounded reads, risk-based
execution, UI/internal value handling, readback, and undo receipts remain the
source of truth.

## Install

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_ableton_mcp.ps1
```

This creates the ignored `.venv/` using uv and `.python-version`, then installs
the exact Windows runtime dependencies in `ableton_agent/requirements-mcp.lock.txt`.
`requirements-mcp.txt` retains the direct dependency declaration. The installer
does not alter global Python packages or the retained `.venv-mcp` rollback env.
See [Python Environment](python_environment.md) for the shared launcher and recovery.

The project-scoped `.codex/config.toml` starts the server through
`scripts/start_ableton_mcp.ps1`. On Windows, keep the PowerShell executable,
launcher, and repository `cwd` as absolute paths in the local config. Codex can
start or resume a task from a host process whose current directory is not the
repository, so relative launcher paths are not reliable for required MCP
servers.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_ableton_mcp.ps1
```

Codex Desktop, CLI, and the IDE extension read MCP configuration from
`.codex/config.toml` for this trusted workspace. Restart the Codex client after
installing or changing the MCP server. This is a Codex restart, not a Hub reload.

## Batch 1 Tools

| Tool | State change | Purpose |
| --- | --- | --- |
| `ableton_status` | no | Ping the Hub and report the active transport and serialization strategy. |
| `ableton_read_set` | no | Run the canonical current-Set reader; quick summary is the default. |
| `ableton_find_target` | no | Resolve track, device, or parameter names to stable IDs. |
| `ableton_read_parameters` | no | Read one four-item bounded page by default, with explicit paging and token support. |
| `ableton_set_mix` | scalar write | Apply or inspect guarded mixer changes by stable track ID. |
| `ableton_set_parameters` | scalar write | Apply or inspect guarded parameter changes by stable track/device/parameter IDs. |

No delete, clear, replace, create, clip mutation, or structural tool is exposed
in Batch 1. Read tools advertise the MCP read-only annotation. Scalar tools are
non-destructive but still write Live when `execution=auto` or `apply` succeeds.

## Recommended Workflow

1. Call `ableton_status` when the current Live/Hub state is unknown.
2. Use `ableton_find_target` to obtain stable IDs.
3. Read a narrow parameter page or current target value.
4. Apply one small scalar change with stable IDs.
5. Inspect the returned Hub readback and operation receipt.

Do not issue Ableton MCP tools in parallel. The server enforces serialization,
but parallel calls only wait in its queue and do not make Live faster.

## Output Contract

Every tool result includes an additive `mcp` object:

```json
{
  "operation": "ableton_read_parameters",
  "request_sequence": 3,
  "serialized": true,
  "queue_wait_ms": 0.012,
  "operation_elapsed_ms": 8.451
}
```

Hub request IDs and Hub result fields remain unchanged. Expected operational
exceptions retain source `error_code`, `error_layer`, `stage`, `request_id`, and
`details`, including auto-collector causes. Unstructured exceptions fall back
to `error_layer=mcp_service`; malformed
MCP inputs are rejected by the SDK schema before a Hub request is sent.

## Configuration

### Cross-Process Coordination And Lookup Evidence

- Restart existing Codex/MCP processes after updating this Python code. Old
  already-imported clients do not participate; no Ableton Hub reload is required.
- Each reply-port acquisition waits at most the request timeout, separately from
  the reply deadline. Busy results expose `reply_port_busy`, layer `udp_client`,
  and `request_sent:false`. Commands are never automatically retried.
- Ownership ends after the reply socket closes; OS termination releases it too.
  Updated clients share `%TEMP%/ableton-agent-reply-locks/udp-7401.lock` on Windows.
  Do not delete these lock files. A file existing does not mean it is locked.
- Coordination is per exchange, not a transaction across all pages. Existing
  collection tokens continue detecting collection changes. External unmodified
  clients, old MCP processes, and different users/temp directories are excluded.
- `mcp.queue_wait_ms` measures the service queue; `operation_elapsed_ms` also
  includes time waiting for the cross-process reply-port lock. Busy errors expose
  that port wait separately in `details.queue_wait_ms`.
- `ableton_find_target` preserves partial/truncated status, truncation reasons,
  warnings, pagination metadata, selectable child Rack IDs, and Hub errors.
  `source_complete:false` with no matches does not establish that a target is absent.
- Windows spawned-process tests cover exclusion, handover, timeout without send,
  and crash recovery. POSIX locking needs platform verification.

See `docs/adr/0002-coordinate-udp-reply-port-ownership.md` and finding `MCP-002`.

Optional environment variables:

| Variable | Default |
| --- | --- |
| `ABLETON_AGENT_HOST` | `127.0.0.1` |
| `ABLETON_AGENT_COMMAND_PORT` | `7400` |
| `ABLETON_AGENT_REPLY_PORT` | `7401` |
| `ABLETON_AGENT_TIMEOUT` | `5.0` seconds |

STDIO stdout belongs to the MCP protocol. Server diagnostics must use logging or
stderr; do not add ordinary startup `print()` output to `mcp_server.py` or the
launcher.

## Validation

Core tests work without the optional MCP dependency. Protocol tests run when the
MCP environment is present:

```powershell
$env:PYTHONPATH = "ableton_agent/python"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/python.ps1 -m unittest tests.test_mcp_tools tests.test_mcp_server
```

The MCP server is local orchestration only. Changes to these Python files and
scripts do not require rebuilding or reloading `Ableton Agent Hub.amxd`.
# Current Execution Policy (2026-09-17)

ADR-0008 supersedes older mandatory inspect/token examples below. Creative write
tools default to `execution=auto`, which applies directly; read actions remain
read-only. `inspect` and prior plan tokens are optional. Explicit tokens are
validated. Targets/ranges and readback remain checked within the request.
This update requires manual Hub reload plus MCP restart. Live acceptance pending.
# Module Diagnostics

`ableton_status(probe_modules=True)` adds four sequential read-only module probes
and running shared-helper build evidence. Default status remains ping-only and
reports unprobed modules as unknown. See `module_health.md`; ping success does not
imply modules or writes work. This schema update requires MCP restart and the
new helper/handlers require user-performed Hub reload.

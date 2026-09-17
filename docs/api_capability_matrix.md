# Ableton Agent Capability Matrix

Stage 4 Hub status panel: passive command/reply observation implemented on
codex/hub-status-panel; 292 tests passed, dev-78199897fe40-local built and synced,
32 manifest files verified. Dark jsui Overview/History/Diagnostics adds 32 bounded
records, intent labels, last-probe evidence and paginated errors. Offline actual
paint renders checked; native Max interaction and manual reload acceptance pending.
No added route or LOM polling. Displayed outcome describes
the module reply, not confirmed UDP delivery. See docs/hub_status_panel.md.

UI-unit input (stage 3): existing scalar setters and mixed batch accept mutually
exclusive `ui_value` text or internal `value`. Scoped EQ Eight, mixer volume/pan
and unique device enum labels; no generic plugin conversion. 289 tests pass;
Live volume/pan, EQ frequency/gain/Q and enum writes/readback/restoration passed
on the test track. Confirmed build dev-37844bbbec71-local; no further reload for
this Set. Scope is representative, not every device/value. See docs/ui_unit_input.md.

First-stage module health: `ableton_status(probe_modules=True)` checks four
handlers sequentially, read-only, with running helper build evidence and explicit
unknown/unprobed state. Default ping is unchanged. 281 tests passed; Live acceptance
pending manual Hub reload and MCP restart. See `module_health.md`.

This document is the current capability map for the single supported Live entrypoint:

`Ableton Agent Hub.amxd`

The built Hub displays `Version: dev-<12 hex digits>` at the bottom. This
deterministic builder/patch/JS source fingerprint identifies the built artifact,
not a verified runtime dependency version or public release. UI confirmation
after manual reload remains pending for the 2026-09-17 addition.

DEPLOY-001: optional local build pins entry JS and includes to an explicit
installation directory, with `-local` label and complete dependency cache.
273 automated tests pass; Live module loading remains pending manual reload.
Ping alone does not validate module availability. Local artifacts are not portable.

2026-09-17 D: installation acceptance: track read completed in 47 ms; tokenless
auto create returned applied:true/verified:true in 390 ms (Agent Write Test,
track_id 3014). This validates the track entry/shared creative helper path and
direct-create behavior only, not every module or write action.

Each row is one practical capability. Each column answers one fixed question, so the table works as a real two-dimensional matrix rather than a loose command list.

Status legend:

- `yes`: implemented and usable.
- `partial`: usable with a known scope limit.
- `planned`: designed, but not implemented yet.
- `blocked`: confirmed limitation of the public Max for Live / Live API surface.
- `n/a`: not applicable for this capability.

## Capability Matrix

Current saved-file layers are local tools, not Hub capabilities. `AUTO-001`
(`ableton_read_saved_automation`) reads saved Arrangement nodes, file targets
and boundary context. `ALS-002` (`ableton_read_saved_set`) composes the complete
saved-set reader and can be added to the canonical first read. Constant-meter
bar references are caller assumptions; neither tool reads unsaved data, maps
file IDs to Live IDs, or writes curves.
Automated tests/real-file acceptance recorded in `docs/saved_automation.md` and
the finding. The previous Hub live-curve limitation remains unchanged.

The old ALS snapshot experiment is now complete as a read-only saved-file layer:
`ableton_read_saved_set` composes track/device, Mixer/routing, Scene, Audio Clip,
MIDI, target-linked automation and GroovePool sections. It shares a bounded parsed
document with the legacy ALS readers. `scripts/read_current_set.ps1 -AlsPath ...`
adds this layer to the canonical Hub first read and reports a field-level
saved-vs-Live comparison without using XML IDs for writes. This is not a Hub
capability and needs an MCP restart, not a Hub reload.

The current MCP server advertises **27 tools**. MCP-007/MCP-008 introduced the
automation inventory and Arrangement adapters; their detailed deployment
record is archived at
`docs/history/validation/mcp_arrangement_automation_2026-09-09.md`.

| Latest MCP capability | Read / inspect | Apply | Live validation |
| --- | --- | --- | --- |
| `ableton_diagnose_parameters` | bounded sequential field probes, health and continuation checks; existing progress/errors retained | n/a | one-item Reverb Predelay plus next identity page passed in 63 ms on 2026-09-17; not full-device/failure-path coverage |
| `ableton_apply_batch` | existing mixer and parameter inspect, one MCP call | mixer group then parameter group; stops on error, not atomic; receipts retained | Test-track pan/EQ applies and exact restoration passed; ten rounds each: separate tool-wall median 127.5 ms vs batch 92 ms, service median both 62 ms. See docs/history/validation/2026-09-17-mixed-batch-benchmark.md; not a fixed LOM speedup. |
| `ableton_scan_automation` | bounded resumable device-parameter states, nested Racks and Track/Return/Main; lightweight automation_state projection | n/a; does not disable automation or block writes | pending; excludes mixer states and curve points; partial scans explicit |
| `ableton_edit_arrangement` | stable Clip target and existing destination checks | same-track audio move or MIDI note-data copy via existing token/Undo/readback helpers | pending for MCP facade; underlying audio move previously validated under CLIP-003 |
| `ableton_read_saved_set` | explicit saved `.als` path; snapshot/project/MIDI/automation/Groove sections; local-only | n/a | automated and synthetic-file validated; real saved-file/UI comparison pending |

### Historical Deployment Notes

MCP-005 (2026-09-07) introduced nine typed creative tools over existing routes.
The 21-tool count below is the count at that historical checkpoint. New private stable-ID/plan-token adapters
are automated-tested and **partially Live-validated** on a disposable test track.
MIDI creation/shift/fill, native insertion, EQ preset and Scene creation passed.
The Track RGB correction requires another manual Hub reload; actual MCP host
already exposes 21 tools. MCP-006 additionally extends `ableton_manage_tracks`
with guarded deletion. Current Set Hub reload and MCP schema refresh are complete;
device-containing audio-track deletion and the color correction passed Live tests.
Older Hub instances require future manual reload. Full scope and limitations:
`docs/mcp_server.md`, Creative Tools Update.

| New MCP capability | Read / inspect | Apply | Live validation |
| --- | --- | --- | --- |
| MIDI creation, ID-preserving edits, new note-data variations | yes | implemented; token required | partial: Session/Arrangement create, shift and fill passed |
| Local sound search with real path check | yes; local-only | n/a | no Hub required |
| Specific Simpler/Drum Rack sample confirmation | yes | n/a; manual loading | partial: empty Simpler correctly detected; loaded path pending |
| Whitelisted insertion and EQ preset | yes | implemented; token required | partial: Simpler/EQ Eight insert and lead preset passed |
| Append/rename/color tracks; list/create/duplicate/rename/fire scenes | yes | implemented; token required | partial: MIDI track/Scene creation passed; corrected color behavior awaits reload |
| Delete an ordinary non-Group track through `ableton_manage_tracks` (MCP-006) | bounded whole-track impact; direct devices/Clips/order | implemented; explicit intent + inspected token; rejects Hub host, last track and special tracks | yes: disposable audio track with Utility deleted, exact remaining IDs/order verified; Clip-containing impact read-only verified, actual Clip-containing deletion pending; legacy empty-track delete unchanged |

| Capability | Hub Route | Python Client | Read | Dry-run | Commit | Live Validated | Creative Validated | Limitation / Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hub connection check | `/ping` | `ableton_bridge.ping` | yes | n/a | n/a | yes | yes | Confirms Python can reach the Hub in Live. |
| Tempo | `/tempo` | `ableton_bridge.tempo` | yes | yes | yes | yes | yes | Reads and sets exact BPM float values, including 132 UKG. |
| Transport | `/transport` | `ableton_bridge.transport` | yes | yes | yes | yes | yes | Play, stop, continue, jump, set position. Use readback because Live can briefly report stale state. |
| Arrangement locators | `/locator` | `ableton_bridge.locator` | yes | yes | yes | yes | yes | List, create, delete, jump. Used for Intro, Drop 1, Hook 1, Breakdown, Outro. |
| Set snapshot | `/snapshot` | `ableton_bridge.snapshot` | yes | n/a | n/a | yes | yes | Reads tracks and device chains. |
| Parameter summary and discovery | `/parameter_summary` | `ableton_bridge.parameter_summary` | yes | yes | n/a | yes | yes | Preserves the whole-Set summary. Shared bounded reads are Live-validated for top-level Racks and nested Rack-chain `device_id` targets, including chain paths and `is_enabled`. Current reads preserve exact internal values, direct numeric GUI values from Live, and formatted UI text; dry-run targets retain the requested internal value and use `str_for_value` without writing. The old-Live fallback is automated-tested. The parameter adapter defaults omitted bounded `limit` values to `4` while preserving explicit `1..32` overrides. Stage 1 runtime diagnostics are Live-validated: correlated request IDs, structured Hub/LOM field errors, lightweight timings, and a bounded Python request journal correctly distinguish a successful all-field read from `target_not_found` at `device_resolving`, with final Hub health preserved. Opt-in progress packet delivery is Live-validated on successful reads (see MCP Reliability Update); delivery during a real synchronous hang remains unverified and the automated diagnostic CLI remains planned. Keep pages small and request UI display formatting only for selected parameters. |
| Mixer control | `/set_mix` | `ableton_bridge.mixer_control` | yes | yes | yes | yes | yes | Low-risk calls default to one guarded apply request; explicit inspect and legacy `commit=False` remain available. Live validation confirmed exact before-state, optional `expected_before`, no-op apply, UI/internal readback, timings, and a persisted undo receipt while preserving the audible value. Return/Main no longer need a redundant preceding dry-run when resolved in the same request. |
| Native instrument insertion | `/insert_device`, `/insert_devices` | `ableton_bridge.inserter` | partial | yes | yes | yes | yes | Whitelist-based native device insertion. |
| Native effect insertion | `/insert_effect`, `/insert_effects` | `ableton_bridge.inserter` | partial | yes | yes | yes | yes | Return/Main single and batch targets retain stable IDs. A real Utility insertion on a disposable Return verified the new device ID and device-chain readback. |
| Compatibility MIDI track creation | `/create_midi_track` | `ableton_bridge.inserter` | no | yes | yes | yes | partial | Older route kept for compatibility; prefer `/track_management`. |
| Track management | `/track_management` | `ableton_bridge.track_management` | yes | yes | partial | yes | yes | Existing writes and special-track controls are preserved. Shared bounded flat paging for `scan_tracks` / `scan_hierarchy` and Python hierarchy reconstruction are Live-validated across ordinary, Return, and Main sections. Group structure writes remain blocked. |
| Group structure planning | `/track_management` | `ableton_bridge.track_management` | yes | yes | blocked | yes | pending | `create_group`, `move_track_to_group`, `move_track_out_of_group`, `reorder_track`, and `plan_groups` validate ordinary `track_id` values and return before/after order plus manual steps, but reject commit because the public LOM has no corresponding functions. Return Tracks are always excluded. |
| Routing | `/routing` | `ableton_bridge.routing` | yes | yes | yes | yes | partial | Ordinary track output routing is validated. Input routing is opt-in with `include_input`. Return track routing is intentionally limited because Live can block on return routing properties. |
| Scene tools | `/scene` | `ableton_bridge.scene` | yes | yes | yes | partial | partial | List, create, duplicate, rename, capture MIDI, and fire scenes. Capture MIDI depends on Live's current capture state. |
| Session MIDI clip writing | `/write_clip` | `ableton_bridge.clip_writer` | partial | yes | yes | yes | yes | Writes Session View MIDI clips. |
| Arrangement MIDI clip writing | `/write_arrangement_clip` | `ableton_bridge.clip_writer` | partial | yes | yes | yes | yes | Writes Arrangement MIDI clips. |
| Detail clip single-note edit | `/transpose_detail_note` | `ableton_bridge.detail_clip_writer` | partial | yes | yes | yes | yes | Edits the current detail clip note. |
| Clip note tools | `/clip_note_tools` | `ableton_bridge.clip_note_tools` | yes | yes | yes | yes | pending | Legacy scan/read/edit by `candidate_index` is preserved. Bounded `scan_clips_metadata` and direct `read_notes_by_clip_id` time-window pages are Live-validated for faster song-context caching without full-note pre-scans. |
| Clip variation tools | `/clip_variation` | `ableton_bridge.clip_variation` | yes | yes | yes | yes | yes | Scans Arrangement MIDI clips; duplicate/fill/thin/mute into a new clip by default. |
| Arrangement region tools | `/arrangement_tools` | `ableton_bridge.arrangement_tools` | yes | yes | yes | yes | yes | Scan, clear, copy, duplicate, and rename Arrangement regions. Copy/duplicate remains MIDI-safe first. `move_audio_clip` is Live-validated for one stable-ID, same-track Arrangement audio clip with dry-run token, collision rejection, native duplicate preservation, bounded property readback, and failure restoration. Cross-track moves and replacement of unrelated clips remain excluded. |
| Device chain templates and Rack discovery | `/device_chain` | `ableton_bridge.device_chain` | yes | yes | yes | yes | partial | Existing whole-track discovery and templates remain compatible. `root_device_id` subtree scans are Live-validated with relative/absolute depth, cumulative device limits, object-boundary budgets, truncation reasons, and selectable child Rack IDs. Rooted scans avoided a reproduced whole-track timeout on a complex Instrument/Audio Effect Rack track. Full Macro mapping graphs remain blocked by the public LOM. |
| Macro / parameter snapshots | `/macro_parameters` | `ableton_bridge.macro_parameters` | yes | yes | yes | partial | partial | Scans/saves snapshots, applies snapshots, and morphs between two snapshot states. Large device scans should use limits. |
| EQ tools | `/eq_tools` | `ableton_bridge.eq_tools` | yes | yes | yes | yes | partial | Lists safe EQ Eight presets, reads EQ Eight parameters, applies conservative preset moves, and sets one band parameter. Presets avoid filter-type switching and skip missing parameter names. |
| Multi-parameter control | `/set_parameters` | `ableton_bridge.multi_parameter_control` | yes | yes | yes | yes | yes | Low-risk calls default to one guarded apply request; explicit inspect and legacy commit flags remain compatible. Live validation confirmed protected-parameter rejection before writing plus guarded no-op apply, exact UI/internal readback, timings, and a persisted restore receipt on a normal Simpler parameter. Nested devices still require stable `track_id + device_id + parameter_id`; disabled or Macro-controlled parameters are rejected before writing. |
| Meter monitor | `/meter_monitor` | `ableton_bridge.meter_monitor` | yes | n/a | n/a | yes | partial | Default scans remain ordinary-track-only. Explicit Return/Main `section + track_id` one-shot reads are Live-validated; no continuous polling. |
| Sample path preparation | `/load_sample` | `ableton_bridge.sample_loader` | partial | yes | blocked | partial | yes | Can validate and prepare sample paths, but Live does not expose supported arbitrary sample loading into Simpler/Drum Rack. |
| Manual sample confirmation | `/sample_confirm` | `ableton_bridge.sample_confirm` | yes | n/a | n/a | yes | yes | Scans loaded samples, confirms a chosen Simpler or Drum Rack pad sample path, and compares it with the intended path. Drum Rack pad traversal is best-effort. |
| Local sample index | local only | `ableton_bridge.sample_index` | yes | n/a | local file update | yes | yes | Verifies paths, rescans nearby folders when an indexed path is missing, updates the local index. |
| Local sample picker | local only | `ableton_bridge.sample_picker` | yes | n/a | local file update | yes | yes | Ranks existing audio candidates by role/category/style/query, explains ranking reasons, verifies paths, and refreshes nearby folders for missing indexed files. |
| Local sound catalog | local only | `ableton_bridge.sound_catalog` | yes | n/a | local file update | yes | pending | SQLite supports metadata/tag/preset searches and bounded reference-audio ranking. First 30 seconds: peak, RMS, centroid, flatness and heuristic transients, with versioned cache and explainable distance. Standard WAV/AIFF/FLAC tested; sampled compressed Pack AIF files could not decode. Creative listening, embeddings and feedback remain pending. See `audio_similarity.md`. Discovery never implies automatic insertion. |
| Generic current-Set initial read | local orchestration | `scripts/read_current_set.ps1` / `ableton_bridge.initial_read` | yes | n/a | n/a | yes | yes | The repository launcher removes per-session Python/path discovery and defaults to one progressive quick-then-deep process. It atomically exposes a quick checkpoint, then reuses the same metadata for bounded note/mixer reads. Dense pages retry at 4 beats and reuse that width on the same stable track ID. Two Sets are Live-validated: 120 clips at 0.328 s quick / 1.703 s full, and 25 clips at 0.094 s quick / 6.047 s full for 1,479 notes. No Hub reload is required. |
| Saved ALS combined read | local-only saved-file evidence | `ableton_bridge.als_bundle` / `ableton_read_saved_set` | yes | n/a | n/a | n/a | partial | Reads the last saved Gzip/XML document with shared caching; optional `-AlsPath` integration keeps Hub current state and saved state separate and compares tempo/locators/track structure. No ALS writes, no runtime-ID substitution, and unsaved edits remain outside the file layer. |
| Codex MCP Batch 1 | local STDIO orchestration | `ableton_bridge.mcp_server` / `.codex/config.toml` | yes | inherited | scalar only | partial | yes | Six stable tools cover Hub status, current-Set read, stable target lookup, bounded parameter pages, guarded mixer writes, and guarded parameter writes. One persistent process removes repeated Python startup and uses a global lock to serialize every UDP `7401` operation. Existing Hub routes and risk/readback contracts are unchanged. Official-SDK STDIO launch and tool discovery pass. With the project server marked `required = true`, a fresh Codex host completed a strictly sequential read-only workflow through the actual MCP tools: Hub status, stable track/device lookup, and a one-item parameter read, all with zero queue wait. It resolved track ID `2`, device ID `26`, and parameter ID `365` (`Device On` = internal `1`, display `On`). Hub reload is not required. |
| Project recommender | local only | `ableton_bridge.recommender` | yes | n/a | n/a | partial | partial | Read-only project/style helper. |

## MCP Common Tools Update (2026-09-05)

MCP-004 extends the six-tool facade to twelve tools without a Hub change.
`ableton_transport`, `ableton_tempo`, `ableton_list_locators`,
`ableton_scan_clips`, `ableton_read_clip_notes`, and `ableton_read_meters` reuse
existing production routes. Clip reads are single pages with explicit cursor/token;
note windows are measured in clip-local beats. Meters require one stable track ID.
Transport auto applies only requested ephemeral actions; tempo defaults to inspect
and explicit apply only changes live_set.tempo, not Song Tempo automation.

196 automated tests pass. A fresh SDK STDIO process discovered all twelve tools
and passed each read path plus tempo inspect and final status against Live on
2026-09-05. No Live writes were made. New MCP write paths and actual restarted
Codex-host acceptance remain pending. No Hub rebuild/reload is needed; restart
existing Codex/MCP processes to discover these tools. Full defaults, limits and
validation evidence are in `docs/mcp_server.md`.
Post-restart host status passed, but its old six-name enabled_tools allowlist
filtered out the additions. The project allowlist is now corrected and covered
by the SDK inventory test. The latest user restart exposes all twelve tools in
the actual host. Its first status timed out after 3031 ms, but after user-confirmed
Hub recovery actual status, tempo (80 BPM) and locator listing (2) all pass.
Discovery and narrow actual-host read acceptance pass. New MCP write-path Live
validation remains pending; no further Codex restart is required for this host.

## MCP Reliability Update (2026-09-05)

New batch (`MCP-003`, `PARAM-009` Stage 2): 186 automated tests pass; **bounded
discovery and successful-read progress delivery are Live-validated** following
user recovery/reload. Actual Codex MCP exposes the new arguments. Initial/final
status pass; all validation calls were read-only. The active instance needs no
further Hub reload or MCP restart; older instances still require user-performed
reload/restart when selected. The prior timeout cause remains unknown (see
PARAM-009); this round does not establish delivery during a synchronous hang.

| New Behavior | Implementation | Live Validation | Boundary |
| --- | --- | --- | --- |
| Return/Main device discovery | Section-aware `/device_chain` scans | yes (actual MCP) | Stable ID must belong to the selected section; Return Reverb and Main Limiter resolved. |
| Direct device pages | `scan_children`, cursor/token, child Rack IDs | yes | Return/Main siblings and targeted Rack 946 children continuation passed; not an exhaustive deep-tree test. Recursive mode remains configurable. |
| MCP search continuation | Source cursor/token and match_offset | yes (small pages) | Default page remains 4; cursor 0/4/8 and stable token passed. Beyond 128 positions and match overflow are automated-tested; warnings stop continuation. |
| Track directory cache | Five-second process-local cache with live revision probe | yes (hit/refresh) | Miss/hit/refresh-miss verified; TTL/Set-change invalidation automated-tested. No value cache or write authority; name/hierarchy edits may need refresh. |
| Parameter progress | Separate reply address, none/page/parameter/field | yes (successful read) | Callback received 27 correlated packets through reply_serialized; Device On = 1 / On, 16 ms client time. Normal reads emit none. Best-effort evidence, not cancellation or proven delivery during a hang. |

The automated diagnostic sequence CLI remains planned. See `docs/mcp_server.md`
for continuation and invalidation rules; no new public request route was added.

`MCP-002`: all Python bridge reply sockets now acquire a cooperative cross-process
port lock. Lookup results preserve source completeness/continuation metadata, and
structured errors retain their original layer and correlation details. Full tests:
177 passed, including real spawned-process locking tests. A fresh SDK MCP process
passed sequential status, invalid-target error propagation, and final status in
Live without changing the Set. Restart existing MCP processes to load the update;
`reload_required:false` for Hub. Old/external clients are outside lock coverage.

## Confirmed Live API Limits

| Area | Status | Practical Result |
| --- | --- | --- |
| Arbitrary sample load into Simpler/Drum Rack | blocked | User manually drags the sample; Agent can pick and confirm. |
| Browser contents from Max for Live | blocked | `live_app browser` and `live_app view browser` did not expose usable Browser items in the current environment. |
| `Sample.file_path` write | blocked | File path can be read for loaded samples, not assigned to load a new file. |
| Drum Rack pad sample traversal | partial | Works in the current project for the loaded hihat pad, but should stay best-effort. |
| Full routing menus | partial | Ordinary track routing values are stable. Available menus and input routing remain opt-in because behavior can vary by Live version and track type. Return routing property reads are avoided. |
| Group Track creation and track movement | blocked | Track hierarchy and existing Group Track properties are exposed. The public Live 12.3.5 LOM has no create-group or move/reorder-track function, so structural changes require manual Live UI actions followed by hierarchy readback. |
| EQ curve presets | partial | `/eq_tools` provides conservative EQ Eight parameter presets. It intentionally avoids automatic filter-type switching because parameter names and quantized type values can vary by Live version. |
| Arrangement device-parameter automation envelopes | blocked | `DeviceParameter` exposes current value, read-only `automation_state`, and `re_enable_automation`, but the public LOM exposes no envelope object, breakpoint list, or create/replace/clear function. Draw device automation manually in Live; the Agent may diagnose whether it is active or overridden after the Hub diagnostic update is reloaded. |
| Rack Macro mapping graph | blocked | Rack traversal and Macro values are exposed, and `has_macro_mappings` reports whether mappings exist. The public LOM does not provide a complete Macro-to-target list, mapping ranges, or supported mapping-authoring functions. |

## Latest Live Validations

- Generic initial read: `ableton_bridge.initial_read --depth quick` read tempo,
  transport, locators, 16 ordinary Tracks, 2 Returns, Main, and 120 Arrangement
  clips in `328 ms` internal time. `--depth full` reused those collections and
  added 81 MIDI clip note summaries (1,301 notes) plus 19 mixer targets in
  `1,703 ms` internal time. Both returned complete with zero warnings/errors and
  a healthy final ping; measured process wall times were 4.4 s and 3.7 s.

- Unified bounded track reads: the current Set returned 26 ordinary Tracks, 4
  Returns, and Main as 31 ordered records over 11 three-item pages. Python rebuilt
  five Group Tracks and nested parent paths. Optional color/fold/visibility/device
  fields completed without Return routing reads; stale token rejection left
  `/ping` healthy.
- Unified bounded parameter reads: Wavetable device ID `45` completed all 93
  parameters as 24 four-item pages with one stable collection token and no
  warnings. `Unison Amount` preserved internal value `0.30000001192092896` and
  Live UI value `30 %`; `Device On` returned `Off` / `On`. A stale token was
  rejected, business failure exited the CLI with code `1`, and `/ping` remained
  healthy.
- Parameter discovery: existing `/parameter_summary` now handles bounded
  `list_parameters` and `search_parameters` actions without adding another Hub
  route. On `10 Wide Chords`, track ID `17` and Wavetable device ID `45`, a
  four-parameter page returned from 93 exposed parameters; searching `unison`
  resolved exact parameter `Unison Amount` at index `89` with visible value
  `30 %`. Quantized discovery returned `Device On` labels `Off` and `On` through
  Live's display formatter. The legacy whole-Set summary still timed out after
  15 seconds on this larger Set, while `/ping` remained healthy.
- Return/Main control: `scan_special_tracks` read four Returns and Main with
  stable IDs without traversing ordinary tracks. A Return volume and Drum Buss
  Dry/Wet were committed at their exact current values and read back unchanged;
  Main volume passed the same no-op commit/readback. Return/Main one-shot meters
  resolved correctly. A duplicate-protected batch effect commit retained Return
  ID `35`, inserted zero devices, and preserved the two-device chain. Missing
  `expected_return_ids` and missing special-track `track_id` commits were safely
  rejected. A disposable `E-Agent Validation` Return was then created as the
  unique new ID `364`; inserting Utility created and verified device ID `365`.
  Token-guarded non-empty deletion then removed exactly ID `364`; independent
  readback confirmed surviving Return IDs remained `[6, 27, 7, 35]` in order.
- Group Track follow-up: `scan_hierarchy` read a manually created group with
  parent/child IDs and depth. A `create_group` commit was safely rejected and
  readback confirmed no change. `set_group_properties` dry-run returned a plan
  token; commit renamed the existing group, applied the nearest Live palette
  color, preserved fold state and members, and passed independent hierarchy
  readback. Validation Set contained 5 ordinary tracks including one Group Track
  and 2 Return Tracks.
- Step 10 `/device_chain`: `apply_parameter_preset` dry-run and commit succeeded on `5-Sax Lead`; Reverb `Dry/Wet` stayed at `5.0 %`.
- Step 11 `/macro_parameters`: scanned, applied, and morphed a limited `5-Sax Lead` / `Reverb` snapshot.
- Step 12 `/meter_monitor`: read active meters during playback; 2 ordinary tracks were active, 10 were silent at that instant, and 0 clipping-risk tracks were reported.
- Step 13 `sample_picker`: selected existing impact FX candidates from the local index: `Impact GE.wav`, `Blip Impact.wav`, and `Impact Shot.wav`.
- Step 10-13 completion pass: added device-chain parameter presets, macro snapshot apply/morph, meter balance/silent/clipping reports, and sample-picker rank reasons/refresh reporting. Hub was rebuilt, synced to User Library, reloaded in Live, and code validation passed with `115 tests OK`.
- Step 14 `/sample_confirm`: confirmed `Hihat Closed Sharp Garage.aif` loaded on `8-Top Percussion`; Live reported the project-collected copy under `Samples/Imported`.
- Step 14 follow-up: `/sample_confirm` now supports `scan_loaded_samples` so the Agent can scan first and then confirm by `candidate_index`.
- Step 14 Live validation: broad sample scan completed without deep Drum Rack traversal; targeted `8-Top Percussion` scan found `Hihat Closed Sharp Garage.aif` on pad index `42`, candidate index `0`.
- EQ follow-up: `/eq_tools` is implemented for `list_presets`, `read_eq`, `apply_preset`, and `set_band`; Live dry-run validation on `5-Sax Lead` confirmed safe truncated EQ reads and correct Hz-to-internal conversion for `350 Hz` and `2.80 kHz`.
- Current creative track setup: added `10-FX Hits`, `11-Vocal Chop`, and `12-Noise/Riser`; duplicate empty tracks were removed with `delete_empty_track`.
- Current arrangement organization: locators/scenes use `Intro`, `Drop 1`, `Hook 1`, `Breakdown`, and `Outro`.
- Step 6 follow-up: `/arrangement_tools` now supports `clear_region`, `copy_region`, `duplicate_region`, and `rename_region_clip` with dry-run first.
- Step 7 follow-up: `/track_management` now supports `create_return_track` and `color_track`.
- Step 6 Live validation: scanned beats 128-160, planned a 9-clip MIDI duplicate from beats 128-256 to beat 300, confirmed partial-overlap clear protection, and commit-tested a no-op region clip rename.
- Step 7 Live validation: scanned ordinary and return tracks, dry-run planned `color_track` and `create_return_track`, and commit-tested a no-op color write on `10-FX Hits`.
- Step 8 follow-up: `/routing` now supports `set_input_routing`; scan results include input/output current values and available raw/display menu entries.
- Step 9 follow-up: `/scene` now supports `duplicate` and `capture_midi`.
- Step 8 Live validation: ordinary-track `scan_routing --no-returns` and `scan_routing --include-returns` both work. Return tracks are listed with `routing_limited:true`. A no-op `set_output_routing --track-index 1 --output-routing-type Main --commit` succeeded.
- Step 9 Live validation: `duplicate` dry-run planned copying `Drop 1` to scene index `2`; `capture_midi` dry-run reported Live's capture-state dependency without changing the Set.
# Execution Policy Update (2026-09-17)

ADR-0008: direct user-requested writes replace risk-tier gating. Creative MCP
auto writes apply without a prior inspect/token; reads remain read-only. Optional
inspect/tokens, target checks and readback remain. Automated tests pass; updated
Hub reload and MCP restart required, Live acceptance pending. Older mandatory
inspection descriptions below are superseded for these creative MCP actions.

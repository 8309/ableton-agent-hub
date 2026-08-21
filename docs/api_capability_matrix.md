# Ableton Agent Capability Matrix

This document is the current capability map for the single supported Live entrypoint:

`Ableton Agent Hub.amxd`

Each row is one practical capability. Each column answers one fixed question, so the table works as a real two-dimensional matrix rather than a loose command list.

Status legend:

- `yes`: implemented and usable.
- `partial`: usable with a known scope limit.
- `planned`: designed, but not implemented yet.
- `blocked`: confirmed limitation of the public Max for Live / Live API surface.
- `n/a`: not applicable for this capability.

## Capability Matrix

| Capability | Hub Route | Python Client | Read | Dry-run | Commit | Live Validated | Creative Validated | Limitation / Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hub connection check | `/ping` | `ableton_bridge.ping` | yes | n/a | n/a | yes | yes | Confirms Python can reach the Hub in Live. |
| Tempo | `/tempo` | `ableton_bridge.tempo` | yes | yes | yes | yes | yes | Reads and sets exact BPM float values, including 132 UKG. |
| Transport | `/transport` | `ableton_bridge.transport` | yes | yes | yes | yes | yes | Play, stop, continue, jump, set position. Use readback because Live can briefly report stale state. |
| Arrangement locators | `/locator` | `ableton_bridge.locator` | yes | yes | yes | yes | yes | List, create, delete, jump. Used for Intro, Drop 1, Hook 1, Breakdown, Outro. |
| Set snapshot | `/snapshot` | `ableton_bridge.snapshot` | yes | n/a | n/a | yes | yes | Reads tracks and device chains. |
| Parameter summary and discovery | `/parameter_summary` | `ableton_bridge.parameter_summary` | yes | yes | n/a | yes | yes | Preserves the whole-Set summary. Shared bounded reads are Live-validated for top-level Racks and nested Rack-chain `device_id` targets, including chain paths and `is_enabled`. Current reads preserve exact internal values, direct numeric GUI values from Live, and formatted UI text; dry-run targets retain the requested internal value and use `str_for_value` without writing. The old-Live fallback is automated-tested. The parameter adapter defaults omitted bounded `limit` values to `4` while preserving explicit `1..32` overrides. Stage 1 runtime diagnostics are Live-validated: correlated request IDs, structured Hub/LOM field errors, lightweight timings, and a bounded Python request journal correctly distinguish a successful all-field read from `target_not_found` at `device_resolving`, with final Hub health preserved. Separate progress packets and the automated diagnostic CLI remain designed but not Hub-implemented. Keep pages small and request UI display formatting only for selected parameters. |
| Mixer control | `/set_mix` | `ableton_bridge.mixer_control` | yes | yes | yes | yes | yes | Ordinary-track behavior is preserved. Return/Main targets use `section + track_id`, require stable-id commit, and read values back. |
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
| Multi-parameter control | `/set_parameters` | `ableton_bridge.multi_parameter_control` | yes | yes | yes | yes | yes | Ordinary and Return/Main behavior is preserved. Rack parameters and enabled nested-device parameters are Live-validated through dry-run, stable `track_id + device_id + parameter_id` commit, and readback. Live-disabled, potentially Macro-controlled parameters are rejected before writing. |
| Meter monitor | `/meter_monitor` | `ableton_bridge.meter_monitor` | yes | n/a | n/a | yes | partial | Default scans remain ordinary-track-only. Explicit Return/Main `section + track_id` one-shot reads are Live-validated; no continuous polling. |
| Sample path preparation | `/load_sample` | `ableton_bridge.sample_loader` | partial | yes | blocked | partial | yes | Can validate and prepare sample paths, but Live does not expose supported arbitrary sample loading into Simpler/Drum Rack. |
| Manual sample confirmation | `/sample_confirm` | `ableton_bridge.sample_confirm` | yes | n/a | n/a | yes | yes | Scans loaded samples, confirms a chosen Simpler or Drum Rack pad sample path, and compares it with the intended path. Drum Rack pad traversal is best-effort. |
| Local sample index | local only | `ableton_bridge.sample_index` | yes | n/a | local file update | yes | yes | Verifies paths, rescans nearby folders when an indexed path is missing, updates the local index. |
| Local sample picker | local only | `ableton_bridge.sample_picker` | yes | n/a | local file update | yes | yes | Ranks existing audio candidates by role/category/style/query, explains ranking reasons, verifies paths, and refreshes nearby folders for missing indexed files. |
| Local sound catalog | local only | `ableton_bridge.sound_catalog` | yes | n/a | local file update | yes | pending | SQLite is the Agent-facing index. It provides stable Pack/resource IDs, FTS5, official XMP provenance, audio header fields, confidence-bearing filename BPM/key/root/loop hints, `.adg`/`.adv` device-chain/macro/FileRef parsing, resolved resource links, incremental fingerprint caching, and structured filters. JSON/Markdown remain compatibility outputs. Waveform-derived features, embeddings, feedback writes, and creative ranking validation remain pending. First full parsing is slow; missing filename evidence stays unknown. Discovery never implies automatic insertion. |
| Generic current-Set initial read | local orchestration | `scripts/read_current_set.ps1` / `ableton_bridge.initial_read` | yes | n/a | n/a | yes | yes | The repository launcher removes per-session Python/path discovery and defaults to one progressive quick-then-deep process. It atomically exposes a quick checkpoint, then reuses the same metadata for bounded note/mixer reads. Dense pages retry at 4 beats and reuse that width on the same stable track ID. Two Sets are Live-validated: 120 clips at 0.328 s quick / 1.703 s full, and 25 clips at 0.094 s quick / 6.047 s full for 1,479 notes. No Hub reload is required. |
| Project recommender | local only | `ableton_bridge.recommender` | yes | n/a | n/a | partial | partial | Read-only project/style helper. |

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

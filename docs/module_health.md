# Module Health And Acceptance

`ableton_status()` keeps its single ping exchange. `health.modules` is unknown
unless explicitly probed; `ok` means ping/connectivity, not module readiness.
`ableton_status(probe_modules=True)` sequentially probes tracks, parameters,
Clip writing and device insertion using existing routes in dry_run mode.
No track enumeration, device insertion or Clip creation occurs. Each probe has
at most a two-second receive timeout; the first exception stops further probes.

Read `health.all_probed_ready`, `health.build_consistent` and per-module replies.
The shared helper reports its executing build identity and a Live Set ID.
This proves handler/helper execution, not every included dependency, all device
properties or any write capability. A timeout means no reply, not proven missing
JS or a requirement to reload. Older Hubs may reject the private health action;
that is unsupported diagnostic protocol, not proof their normal functions fail.

The MCP process computes `mcp_build` at initialization. Hub build output includes
`hub_build_manifest.json` with file SHA-256 hashes, mode and dependency directory.
Disk evidence and running helper evidence must be compared explicitly. Local
build IDs include the install directory; machine-bound artifacts are not published.

Failed service replies retain existing error fields and add `error_category`:
client_validation_failed, target_not_found, stale_state, module_no_reply,
lom_read_failed, readback_failed, write_result_unknown or operation_failed.
Unknown write results take precedence; never automatically replay them. Existing
MCP schema validation can still return native MCP validation errors before dispatch.

First-stage code tests passed (281 tests); Live acceptance is pending reload and
MCP restart. Previously tested track creation, mixer pan/mute and EQ gain writes
are retained as earlier evidence, not proof for this newly built installation.
After reload, probe modules, resolve Agent Write Test, and validate Session MIDI
creation/editing there without playback or saving the Set. Other families remain
unverified until individually tested. Steps 2-5 follow this acceptance gate.

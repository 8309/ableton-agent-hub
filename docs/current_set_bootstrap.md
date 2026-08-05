# Current Set Bootstrap

This is the canonical first-read entry point for every creative or development
session in this workspace:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/read_current_set.ps1
```

It automatically resolves the local Python runtime, configures `PYTHONPATH`,
runs the production Hub reader, and uses a progressive default:

1. Write the quick Set map to
   `ableton_agent/runtime/current_set_initial_read.quick.json`.
2. Reuse the same track and clip metadata for MIDI-note and mixer depth.
3. Write the completed context to:

```text
ableton_agent/runtime/current_set_initial_read.json
```

Before scanning, the launcher invalidates prior current-Set caches and checks:

1. An Ableton Live process is running.
2. `Ableton Agent Hub.amxd` responds from the currently open Set.

Failure returns `stage: preflight` with either `ableton_not_running` or
`hub_not_responding`; no track, clip, note, or mixer scan is attempted.

The cache is local and Git-ignored. Its `generated_at` value identifies when the
currently open Set was read.

## Depth Rule

1. Use the default `progressive` depth for a new Set.
2. The quick checkpoint becomes available before deep stages finish.
3. Reuse the completed cache for follow-up summaries and planning.
4. Use `-Depth quick` only for an explicitly metadata-only refresh.
5. If one stage fails, diagnose that stage instead of replacing the bootstrap
   with an unbounded scan.

Metadata-only example:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/read_current_set.ps1 -Depth quick
```

The launcher and both depths are read-only. They do not modify the Live Set and
do not require a Hub rebuild or reload.

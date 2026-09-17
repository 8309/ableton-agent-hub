# Current Set Bootstrap

This is the canonical first-read entry point for every creative or development
session in this workspace:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/read_current_set.ps1
```

It uses the same fixed `.venv` resolver as the MCP and Python launchers,
configures `PYTHONPATH`, runs the production Hub reader, and uses a progressive
default. An explicit `ABLETON_AGENT_PYTHON` override is supported; missing
interpreters fail without searching system aliases or Codex caches. See
[Python Environment](python_environment.md).

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

## Optional Saved ALS Layer

When the matching `.als` file has been saved manually and its absolute path is
known, add it to the same first read:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/read_current_set.ps1 `
  -AlsPath "C:\\path\\Song.als"
```

This does not replace the Hub read. It adds `saved_als` and
`saved_live_comparison` to the context. The saved layer is static last-saved
evidence; the Hub layer remains authoritative for current Live state and writes.
Use `-IncludeSavedDeviceParameters` or `-IncludeSavedMidiNotes` only when those
larger fields are needed.

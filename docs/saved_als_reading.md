# Saved ALS Reading

The workspace has two complementary read sources:

| Source | What it represents | Authority |
| --- | --- | --- |
| Ableton Agent Hub | Live's current in-memory Set, including unsaved edits | Current state and all writes |
| ALS reader | The last saved `.als` file on disk | Static evidence only |

The ALS reader never writes Live, never rewrites the `.als`, and never treats
XML file IDs as Live runtime IDs.

## Complete Reader

The old snapshot experiment is now available in the current bridge as:

```text
ableton_bridge.als_snapshot
ableton_bridge.als_project
ableton_bridge.als_midi
ableton_bridge.als_bundle
ableton_bridge.als_verify
ableton_bridge.als_midi_verify
```

`als_bundle` is the combined entry point. It keeps the old section boundaries
while sharing one cached parsed XML document for one path and file revision:

- snapshot metadata, tracks, Group paths, locators, file references and saved tempo;
- saved Mixer/routing, top-level and nested Rack devices and optional exact
  internal device parameters;
- Scenes, Arrangement/Session Audio Clips, samples and Warp Markers;
- Arrangement/Session MIDI Clips, bounded notes, probability/deviation and raw
  per-note structures where present;
- target-linked device and Main Tempo Automation events;
- GroovePool definitions;
- bounded MIDI pagination and source hash/token metadata.

Direct CLI example:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/python.ps1 `
  -m ableton_bridge.als_bundle "C:\\path\\Song.als" `
  --include-midi-notes
```

Use `--sections tracks,automation` or the individual `als_project` and
`als_midi` CLIs when only one bounded section is needed.

## MCP And First Read

The local-only MCP tool is:

```text
ableton_read_saved_set
```

It requires an explicit absolute `.als` path and accepts section, MIDI page,
device-parameter, and bounded event limits. It does not call `ableton_status`
or the Hub, so it does not compete for UDP reply port `7401`.

The normal cross-session first read remains:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/read_current_set.ps1
```

When the matching saved file has been saved manually and its absolute path is
known, add it to the same first read:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/read_current_set.ps1 `
  -AlsPath "C:\\path\\Song.als"
```

The launcher still preflights and reads the current Hub first. The optional
saved layer is then placed beside it in the same JSON context:

```text
sources.live             -> current Hub result
sources.saved_als        -> saved path/hash/status
saved_als                -> complete static saved result
saved_live_comparison    -> tempo/locators/track field comparison
```

`current_live_set` remains the context's primary source label. A successful
comparison proves only the compared fields at that moment. If Live contains
unsaved edits, the saved file can legitimately be stale. If a comparison is
`inconclusive`, do not infer equality; use the Hub read for current state.

## Identity And Value Rules

- ALS `Id` values belong to the saved XML document. They are useful for linking
  saved XML nodes to each other, not for issuing Live commands.
- Saved device values are exact serialized/internal values. They are not Live UI
  strings and should not be presented as UI values without a separate Live read.
- Saved automation points are saved-file nodes. They do not prove unsaved curve
  edits or a currently active Live target.
- The shared document cache is invalidated by path, file size, and modification
  time. The source SHA-256/file token is returned for continuation and evidence.

## Verification Helpers

`als_verify` compares saved tempo, locators, and track structure against narrow
Hub reads. `als_midi_verify` compares one exact saved MIDI clip to current Hub
notes. These commands are read-only and return `verified`, `mismatch`, or
`inconclusive`/`partial`; they do not automatically save, reload, or modify Live.

No Hub rebuild or Hub reload is needed for this Python-only backend. Restart the
MCP process after installing the new `ableton_read_saved_set` schema.

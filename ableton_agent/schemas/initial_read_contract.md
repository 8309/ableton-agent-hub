# Initial Read Contract

`ableton_bridge.initial_read` is a local Python orchestration capability. It
does not add a Hub route and does not write to Live.

The command reads the currently open Live Set through existing production Hub
routes in a fixed sequential order:

```text
ping -> tempo -> transport -> locators -> bounded tracks
     -> bounded Arrangement clip metadata -> optional MIDI notes/mixer
     -> health ping
```

The repository launcher additionally checks for a running Ableton Live process.
The initial ping uses a separate short timeout and must complete before any Set
scan. A failed preflight invalidates old current-Set caches and returns a direct
error instead of falling through to other read methods.

## Depths

- `quick` is the default. It reads Set state, hierarchy, and Arrangement clip
  metadata without note bodies or mixer values.
- `full` reuses the same hierarchy and clip metadata, then reads MIDI notes by
  stable `clip_id` and mixer values in small dry-run batches.

The repository launcher calls full depth as a progressive first read. After the
shared metadata stages, `--quick-output` receives an atomic quick checkpoint;
the same process then continues into note and mixer stages without rescanning
tracks or clips.

MIDI note pages start at 16 beats by default. If a dense page times out, the
reader retries that clip with a 4-beat window and records the attempted and used
window sizes. Later clips on the same stable `track_id` reuse the smaller window
without waiting for another timeout. The fallback remains read-only and is
reported as a warning.

`--notes-track` limits full note reads to exact track names. `--include-raw-notes`
keeps note bodies in the machine context; otherwise only per-clip summaries are
stored. The CLI prints a compact summary by default. `--output PATH` atomically
writes the complete context JSON.

## Safety And Completion

- Every Hub request is sequential because UDP `7401` is shared.
- No request uses commit mode.
- Track and clip collections use the existing bounded-read token contract.
- Metadata is scanned once and reused by later stages.
- Stage timing, warnings, errors, final health, and total elapsed time are
  included in the result.
- A failed initial ping exits immediately. Later stage failures return partial
  context and CLI exit code `1`.

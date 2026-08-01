# Live API Limits

Ableton Agent Hub uses the public Max for Live Live Object Model. A Max device
can access many Live objects, but it does not expose every action available in
Live's graphical interface or every element stored in an ALS file.

The limits below are confirmed for the first alpha's validated environment.
They may change with future Live versions and should be re-tested before code
claims broader support.

| Area | Current Status | Practical Workflow |
| --- | --- | --- |
| Arrangement tempo automation | Blocked | The Hub can read/write global `live_set.tempo`, but cannot read, replace, or clear breakpoint envelopes. Edit Song Tempo automation manually. |
| Device-parameter automation envelopes | Blocked | The Hub can report parameter automation state and current value, but not author Arrangement breakpoints. |
| Arbitrary sample loading | Blocked | Pick and verify a real path, drag the file into Simpler or Drum Rack manually, then use sample confirmation. |
| Live Browser contents | Blocked | Browser items are not available as a reliable public object tree in the validated environment. Browse or drag manually. |
| Group Track creation and movement | Blocked for writes | Existing hierarchy, parent IDs, color, and fold state can be read. Creation, moving, and reordering use a manual plan followed by readback. |
| Return routing traversal | Limited | Ordinary routing is supported. Return routing properties are deliberately avoided where they can block. |
| Arrangement region copy | Partial | MIDI-first. Audio clips are reported and skipped by the current region tools. |
| Drum Rack sample traversal | Best effort | Targeted pads can work; broad traversal may be incomplete or expensive. Confirm visible pad state in Live. |
| Third-party plugins and presets | Manual-first | Discovery does not imply safe insertion or parameter support. Load manually unless a specific path is Live-validated. |
| Metering | Snapshot only | One-shot output-meter and rough balance reads are available. Continuous polling is not enabled by default. |
| Large object collections | Bounded reads | Parameters and tracks support paging/projection. One individual Live property call can still block and cannot be force-cancelled from Max JS. |

## Global Tempo Versus Effective Playback Tempo

`live_set.tempo` is the Set's global tempo value. If Arrangement Song Tempo
automation is active later on the timeline, playback can move to a different
effective BPM even after the global value was set successfully. The Hub must not
claim that changing `live_set.tempo` removed or replaced that automation.

## ALS Files Are Not A Runtime Control API

An ALS file is a gzip-compressed XML project document. Reading a saved file can
support offline inspection, but it is not authoritative for unsaved Live state
and editing it while Live is open can corrupt or conflict with the Set. This
alpha does not use ALS rewriting as a fallback for missing Live Object Model
operations.

## Object IDs And Session Lifetime

Live object IDs are safer than list indices inside a running Set, but callers
should not assume they remain valid after closing/reopening a Set or replacing
objects. Rescan after structural changes and before a commit.

## Parameter Representation

An internal parameter value and its visible UI string are separate. The Hub
keeps the precise internal value as data and asks Live to format the UI value
when requested. Units, scaling curves, and enum labels must not be inferred from
the numeric range alone.

For current command-by-command status, including Live and creative validation,
see the [capability matrix](api_capability_matrix.md).

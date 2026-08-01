# v0.1.0-alpha Release Scope

Frozen on: 2026-08-01

## Snapshot Basis

The public alpha scope is based on private workspace commit `54896fd`, plus the
software-only working-tree updates for the capability matrix, sound catalog
client, and their tests. Song projects, local catalogs, generated indexes,
experiments, session handoffs, and private workspace instructions are excluded.

## Confirmed Environment

| Component | Confirmed version or scope |
| --- | --- |
| Operating system | Windows |
| Ableton Live | Live 12.3.5 |
| Max for Live | The Max for Live environment bundled with the validated Live installation |
| Python | 3.12.13 |
| Transport | Local UDP request port 7400 and reply port 7401 |

Other Live, Python, macOS, and Linux combinations are unverified for the first
alpha and must not be presented as supported without testing.

## Stable Alpha Capabilities

These capabilities have both implementation coverage and direct Live validation
for their documented scope:

- Hub connection check.
- Tempo read/write.
- Transport play, stop, continue, and position control.
- Arrangement locator list/create/delete/jump.
- Set snapshot.
- Bounded parameter discovery and summary.
- Mixer control for ordinary, Return, and Main targets.
- Whitelisted native device/effect insertion.
- Existing-track management and special-track controls.
- Session and Arrangement MIDI clip writing.
- Detail-clip single-note editing.
- Clip note reading, shifting, quantizing, deleting, and velocity scaling.
- Clip variation generation.
- Multi-parameter control with dry-run and readback.
- Manual sample confirmation after user drag-in.

The new parameter `automation_state` diagnostic remains alpha until the latest
Hub build is reloaded and read-only Live validation is repeated.

## Experimental Capabilities

These are included but must be labeled with their current scope limits:

- Ordinary-track routing and opt-in input routing.
- Scene duplicate/capture workflows.
- Arrangement region copy/duplicate/rename tools.
- Device-chain templates.
- Macro parameter snapshots and morphing.
- One-shot meter and rough balance reports.
- Conservative EQ Eight presets.
- Local sample indexing and ranking.
- Local sound catalog discovery.
- Project/style recommendation helpers.

## Confirmed Limits

- Arbitrary audio files cannot be reliably loaded into Simpler or Drum Rack via
  the public Live Object Model. The user drags the file; the Hub confirms it.
- Group Track creation, track movement, and reordering are planning-only because
  the public Live Object Model does not expose the required mutations.
- Return routing reads are intentionally limited because they can block in the
  validated Live environment.
- Arrangement device-parameter automation breakpoint authoring is unavailable.
  The Hub can report automation state but cannot create or edit envelopes.
- Arrangement region copying is MIDI-first; audio clips are reported and skipped.
- Drum Rack sample traversal is best-effort.

## Release Acceptance Gate

The alpha cannot be tagged until all of the following pass in the public repo:

1. Python unit tests.
2. Hub build with every declared JavaScript dependency present.
3. Clean install into a temporary destination.
4. Public-path and secret scan.
5. Manual Hub reload in Live.
6. Ping, representative read, dry-run, minimal commit, and readback.

The detailed row-by-row truth remains in `docs/api_capability_matrix.md` after
the curated source export is completed.

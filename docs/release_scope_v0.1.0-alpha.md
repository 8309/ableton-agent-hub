# v0.1.0-alpha Release Scope

Scope frozen on 2026-08-01. The Python package version is `0.1.0a0`. This is a
release candidate and is not yet a tagged GitHub release.

## Distribution Boundary

The public repository is a curated software export. It includes Hub source,
built Hub files, Python clients, schemas, styles, tests, packaging, and public
documentation. It excludes songs, ALS files, samples, local indexes, machine
catalogs, experiments, session handoffs, and local workspace instructions.

`PUBLIC_EXPORT_MANIFEST.json` records the imported software snapshot. Public
packaging and documentation remain owned by this repository so a later source
sync cannot overwrite them accidentally.

## Confirmed Environment

| Component | Confirmed version or scope |
| --- | --- |
| Operating system | Windows |
| Ableton Live | Live 12.3.5 |
| Max for Live | Bundled with the validated Live installation |
| Python | 3.12.13 |
| Transport | Local UDP request port 7400 and reply port 7401 |

Python 3.11 or newer is accepted by package metadata. Other combinations remain
unverified for the first alpha.

## Stable Alpha Capabilities

- Hub connection check.
- Tempo read/write for the global Live Set tempo.
- Transport and Arrangement locator control.
- Set snapshot and bounded track/parameter inspection.
- Mixer and multi-parameter control with dry-run and readback.
- Whitelisted native device/effect insertion.
- Existing-track and special-track controls within the matrix.
- Session and Arrangement MIDI clip writing.
- Clip note and variation tools.
- Manual sample confirmation after user drag-in.

## Experimental Capabilities

- Ordinary-track routing and opt-in input routing.
- Scene duplicate/capture workflows.
- Arrangement MIDI region tools.
- Device-chain templates and conservative EQ Eight presets.
- Macro snapshots and morphing.
- One-shot meter and rough balance reports.
- Local sample and sound-catalog helpers.
- Project/style recommendation helpers.

Experimental means included and tested at a narrower scope, not absent.

## Confirmed Limits

- Arrangement tempo and device-parameter breakpoint envelopes are not exposed
  for authoring through the public Live Object Model.
- Arbitrary sample loading into Simpler or Drum Rack remains manual.
- Group creation, track movement, and reordering are planning-only.
- Return routing property traversal is limited.
- Arrangement region copy is MIDI-first.
- Drum Rack sample traversal is best-effort.

## Completed Publication Work

- Capability scope frozen.
- Independent public repository boundary created and privacy-tested.
- Installable wheel and unified `ableton-agent` CLI created.
- Hash-verified dry-run/commit-style Hub installer validated in a clean temporary
  virtual environment.
- Public README, license, changelog, contribution guide, safety model, setup
  guide, and API-limit documentation added.
- Clean Windows checkout, deterministic Hub rebuild, wheel installation, actual
  User Library installation, manual Hub reload, read, bounded-read, dry-run,
  same-value commit, and readback validation completed. See
  [the release validation record](release_validation_v0.1.0-alpha.md).

## Remaining Release Gate

Before tagging the alpha:

1. Create the GitHub remote.
2. Push the reviewed public history.
3. Create the alpha tag and GitHub release.
4. Upload the wheel, source archive, and checksum file.

The [capability matrix](api_capability_matrix.md) remains the command-by-command
source of truth.

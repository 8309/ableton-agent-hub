# Changelog

All notable changes to this project will be documented in this file. The format
follows Keep a Changelog, and version numbers follow semantic versioning.

## [Unreleased]

## [0.4.0-alpha] - 2026-09-17

### Added

- 27 typed MCP tools, serialized transport, module health and runtime diagnostics.
- MIDI/Arrangement editing, automation-state inventory and local saved-ALS readers.
- Mixed scalar batches, explicit UI-unit setters, and a compact Hub status dashboard.
- Bounded local waveform analysis, versioned cache and reference-audio ranking.
- Portable build manifest, 33 installer assets and a public MCP configuration example.

### Changed

- Explicit user-requested MCP writes apply directly; inspect remains optional.
- Source-only export followed by portable rebuild prevents local dependency paths
  entering the distributed Hub. Public agent instructions match current behavior.

### Validation Limits

- Native Live visual acceptance of the dashboard and portable Live reload are pending.
- Compressed Pack AIF decoding and creative listening acceptance remain pending.
- No audio generation model, automatic sample loading or embeddings are included.

## [0.3.0-alpha] - 2026-08-21

### Added

- Targeted recursive Rack/device-tree scans with stable IDs, bounded depth,
  cumulative device limits, time budgets, and truncation reasons.
- Runtime diagnostics for parameter reads, including correlated request IDs,
  structured Hub/LOM errors, stage timings, and a bounded client journal.
- Safe same-track Arrangement audio clip moves with dry-run plan tokens,
  collision checks, native duplicate preservation, and readback.
- Parameter display contracts that preserve exact internal values while
  returning Live's GUI value and formatted UI text when requested.

### Changed

- Parameter reads now default to four-item pages when the caller omits a limit;
  explicit limits from 1 to 32 continue to override the default.
- Rack parameter writes use stable track, device, and parameter IDs and reject
  disabled parameters that may be controlled by a Macro.
- The public exporter now follows every Hub JavaScript dependency and tolerates
  legacy standalone-device tests that have already been removed upstream.
- Packaged Hub resources increase from 24 to 27 files.

## [0.2.0-alpha] - 2026-08-05

### Added

- Progressive current-Set onboarding with quick and full JSON caches, stable
  clip-ID note reads, dense-page fallback, stage timing, and final Hub health
  verification.
- Windows checkout launcher with Ableton-process and current-Set Hub preflight.
- `ableton-agent initial-read` for installed-package users.
- SQLite Sound Catalog v2 with official Pack XMP tags, audio header and filename
  metadata, Ableton preset-chain parsing, resource relationships, structured
  filters, and incremental analysis caching.
- Recommended project-level coding-agent instructions in `docs/agent_setup.md`.

### Changed

- Hub timeout errors consistently name `Ableton Agent Hub.amxd`.
- Public export manifests now report overlays only for exported files, so
  unrelated private song edits do not taint a clean source checkpoint.

## [0.1.0-alpha] - 2026-08-01

This is the first public alpha release of Ableton Agent Hub.

### Added

- Single `Ableton Agent Hub.amxd` entrypoint with modular Max JavaScript
  capabilities.
- Python clients for Live inspection, bounded reads, dry-run planning, commits,
  and readback.
- Track, parameter, mixer, clip, arrangement, scene, routing, locator, transport,
  device-chain, EQ, macro, meter, and sample-confirm workflows within the
  published capability matrix.
- Local sample, sound-catalog, and recommendation helpers.
- Installable Python package and `ableton-agent` console command.
- Hash-verified Hub installer with custom destination and dry-run support.
- Curated public export boundary that excludes songs, local catalogs, handoffs,
  experiments, and machine-specific data.
- Public installation, safety, API-limit, and contribution documentation.

### Known Limits

- Arrangement automation breakpoints cannot be read or authored through the
  public Live Object Model used by the Hub.
- Arbitrary samples must be dragged into Simpler or Drum Rack manually.
- Group creation and track movement are planning-only.
- The first alpha is validated only on the environment listed in the README.
- A same-value tempo commit reports `changed:true` to indicate that the write
  path executed; compare before, target, and readback values for numeric change.

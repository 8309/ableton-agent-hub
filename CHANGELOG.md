# Changelog

All notable changes to this project will be documented in this file. The format
follows Keep a Changelog, and version numbers follow semantic versioning.

## [Unreleased]

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

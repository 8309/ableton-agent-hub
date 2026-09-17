# v0.4.0-alpha Release Gate

Status: alpha publication authorized on 2026-09-17 with the known limits below.
This is not a claim of complete portable Live or creative listening acceptance.

## Release Highlights

- 27 typed MCP tools for inspection, MIDI/Arrangement editing, mixing and devices.
- Serialized transport, correlated diagnostics, mixed batches and UI-unit input.
- Saved-ALS read-only evidence and a passive graphical Hub status dashboard.
- Local sound catalog and bounded, cached reference-audio similarity ranking.

## Known Limits And Upgrade Notes

- Standard decodable WAV/AIFF/FLAC is supported for waveform analysis. Eight
  sampled Pack AIF files across eight Packs use AIFC `able` encoding and all
  failed decoding. Metadata search remains available; no waveform similarity
  score is fabricated for unsupported audio. An unsupported reference fails
  explicitly. Installing FFmpeg is not an established fix.
- ALC metadata/sample-reference parsing is a development prototype, not a
  shipped MCP feature. Five tested ALCs were MIDI clips; audio ALC support has
  not been accepted. ALC is not directly treated as an audio waveform.
- Native dashboard visual validation, portable Hub reload validation and
  human listening evaluation remain pending. This release is a prerelease.
- Update the Python/MCP installation and restart its host. Install the complete
  Hub dependency bundle, then manually reload the Hub in the intended Set.
  Recheck project AGENTS.md against docs/agent_setup.md and the supplied AGENTS.md;
  explicit requested writes no longer require a separate mandatory dry-run.
- No automatic sample loading, audio generation model or embeddings are included.

## 2026-09-17 Verification

- Exported source checkpoint: ad15203. Source-only allowlist; no local dist import.
- 27 MCP tools and 33 portable installer assets (Hub, 31 JS, build manifest).
- Development: 295 tests pass. Public candidate: 314 tests pass.
- Wheel and sdist build succeeded. Clean wheel environment lists 27 tools and
  installs/verifies 33 files in a temporary directory; repeat install changes zero.
- Privacy tests cover text, source manifest, no private directories, and AMXD
  JavaScript paths. No local Ableton installation, Set, playback or save changed.
- Direct-intent rules and public AGENTS instructions now match development.
- Stage-4 native dashboard visual acceptance, portable Hub reload and stage-5
  listening acceptance remain pending. Pack AIF decoding is explicitly limited.
- Windows push and pull-request CI passed. The remaining manual acceptance was
  reviewed and deferred explicitly for this alpha publication.

The checklist below is the historical preparation audit, superseded by the
verification results above where explicitly covered.

The development source integration is 423a076 (software cleanup 99575ef;
representative Live acceptance 7d1d3ed). Export only allowlisted software files,
not development Git history or song records. Existing public working-tree edits
are preserved and must be reviewed independently.

## Required Before Publication

- Update exporter and builder coverage for health, creative_control and ui_input.
- Export source only; build portable Hub artifacts in this repository. Do not
  import local-install binaries with absolute dependency paths.
- Inspect AMXD patch JSON for machine paths and dependency completeness; the
  existing exporter text scan does not inspect AMXD payloads.
- Update package resources, version and changelog consistently.
- Align public instructions with the direct-intent execution contract. Existing
  public instructions still mandate a dry-run before every mutation.
- Include tests and docs for new MCP, diagnostics, batches and UI-unit features.
- Run full tests, package build, manifest checks and clean-install validation.
- Keep previously validated development behavior distinct from validation of
  this newly built portable distribution. Installation/reload requires the user.
- Review the public diff for private data before pushing or creating a Release.

## Preliminary Audit

The old exporter dry-run selected 149 files and exited successfully. This is
not release acceptance: its static list misses new modules and its text-only
privacy scan does not validate embedded binary patch content.

No existing local Ableton installation was changed by release preparation.

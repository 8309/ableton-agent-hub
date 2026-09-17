# v0.4.0-alpha Release Gate

Status: preparation only; not exported, tagged, pushed or published.

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

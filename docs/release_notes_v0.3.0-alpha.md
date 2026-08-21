# Ableton Agent Hub v0.3.0-alpha

This alpha focuses on safer inspection and editing of complex Ableton Live Sets.

## Highlights

- Target a specific Rack and recursively inspect only its device subtree instead
  of scanning an entire complex track.
- Read exact parameter values together with Live's GUI value and formatted UI
  text, while keeping expensive display projections opt-in.
- Diagnose parameter-read failures by request ID, processing stage, target,
  parameter, property and elapsed time.
- Use safer four-item parameter pages by default; callers may still choose any
  valid page size from 1 to 32.
- Move one Arrangement audio clip within its existing track through dry-run,
  collision validation, stable IDs, commit and readback.
- Install one Hub package containing the AMXD and all 26 required JavaScript
  modules.

## Safety Boundaries

- Writes remain dry-run unless explicitly committed.
- Audio clip movement is limited to one existing Arrangement clip on the same
  track. Cross-track movement and replacement of unrelated clips are excluded.
- Rack traversal cannot expose or author a complete Macro mapping graph because
  the public Live Object Model does not provide it.
- Progress packets and the automated parameter-diagnostics CLI are not yet part
  of this release; the current diagnostics cover final replies and structured
  failures.

## Quick Start

```powershell
pip install ableton_agent_hub-0.3.0a0-py3-none-any.whl
ableton-agent install
ableton-agent ping
```

Load exactly one `Ableton Agent Hub.amxd` in the current Live Set. Coding-agent
users should also apply the current recommendations in
[`docs/agent_setup.md`](agent_setup.md); the installer never edits an existing
`AGENTS.md` automatically.

This remains an early alpha. Review every dry-run target before committing a
change to a Live Set.

## Validation

- 164 public repository tests passed.
- The Hub and all 27 packaged resources were rebuilt and synchronized.
- A clean wheel installation wrote and verified all 27 files, then completed an
  idempotent second install with no changes.
- Wheel SHA-256:
  `a6c958518cc149b46d9866f0f97639b77c0111cc72660d22b21dc83425bf0017`
- Source archive SHA-256:
  `e83c9454da2e23d65b228ee796eed6437273a867bfc0fbfa4de01d2a7d4c4faa`

# Coding Agent Setup

The Ableton Agent Hub source repository includes a root `AGENTS.md`, which
coding agents load automatically when working in that checkout. Users who
install the package into a different project should append the section below to
that project's `AGENTS.md` or equivalent instructions file so new sessions use
the supported first-read path. The installer never overwrites an existing
instructions file.

## Recommended Instructions

```markdown
## Ableton Agent Hub

- Before reading the current Live Set, confirm Ableton Live is open and exactly
  one `Ableton Agent Hub.amxd` is loaded in that Set.
- For a source checkout, run:
  `powershell -ExecutionPolicy Bypass -File scripts/read_current_set.ps1`.
- For an installed package, run: `ableton-agent initial-read`.
- Use the default progressive read: write the quick checkpoint first, then reuse
  the same track and clip metadata for MIDI-note and mixer depth.
- Reuse the generated JSON cache for follow-up summaries. Do not rescan merely
  to reformat the same Live state.
- Never send concurrent Hub requests. UDP 7401 is one sequential reply channel.
- A preflight failure must stop the scan and be reported to the user. Do not use
  an older Set cache as current state.
- Apply explicit user-requested writes directly with stable IDs and readback.
  Do not introduce risk tiers or mandatory inspect/dry-run. Legacy CLI uses
  `--commit`; inspection is read-only, not a simulation.
- After a write timeout, verify affected state before any retry.
- Parameter reads default to four-item pages; use bounded continuation.
- Saved ALS evidence is not unsaved Live state. Never use saved XML IDs for writes.
- Reference-audio search is local and decoder-limited; load samples manually.
- After software updates, restart MCP. Reload Hub manually only when its files
  changed, after switching to the intended Set. Never reload a background Set.
```

The PowerShell launcher checks both the Ableton process and Hub response. The
installed cross-platform CLI always checks the Hub response; on non-Windows
systems, confirm the Live process manually.

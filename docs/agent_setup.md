# Coding Agent Setup

Ableton Agent Hub does not overwrite a repository's `AGENTS.md` or equivalent
instructions file. Coding-agent users should append a project-level section so
new sessions consistently use the supported first-read path.

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
- All write-capable commands remain dry-run unless the user explicitly reviews
  and requests commit. Read back state after every commit where supported.
```

The PowerShell launcher checks both the Ableton process and Hub response. The
installed cross-platform CLI always checks the Hub response; on non-Windows
systems, confirm the Live process manually.

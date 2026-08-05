# Ableton Agent Hub v0.2.0-alpha

This alpha adds a faster and safer way for coding agents to understand the
currently open Ableton Live Set, plus a reusable local sound catalog.

## Highlights

- Progressive current-Set onboarding: a quick structural scan first, followed
  by bounded deeper reads only when needed.
- Hub preflight: initial reads stop with a clear error unless Live is running
  and exactly one Ableton Agent Hub is responding.
- New public CLI command: `ableton-agent initial-read`.
- Local Sound Catalog v2 for searching installed Ableton Packs, presets,
  samples, Live Clips, MIDI files, devices, tags, tempo, key and duration.
- Bounded MIDI clip and note reads using stable clip identities.
- Updated public capability matrix and setup documentation.

## Coding Agent Setup

Coding-agent users should add the project rules in
[`docs/agent_setup.md`](agent_setup.md) to their repository-level `AGENTS.md`.
These rules tell an agent to run Hub preflight, use quick-first progressive
reads, reuse fresh caches, serialize UDP requests, and keep writes in dry-run
until explicitly committed. The installer does not modify an existing
`AGENTS.md` automatically.

## Quick Start

```powershell
pip install ableton_agent_hub-0.2.0a0-py3-none-any.whl
ableton-agent install
ableton-agent initial-read
```

Load exactly one `Ableton Agent Hub.amxd` in the current Live Set before the
initial read. See [`docs/getting_started.md`](getting_started.md) for the full
installation and validation workflow.

## Validation

- 148 public repository tests passed.
- Hub package resources were rebuilt and synchronized.
- Installed-wheel smoke test passed against a running Live Set.
- Wheel SHA-256:
  `6792c431564cf9f8f5ea1f797413d01f184a8bab30f1007fceb64ced8e859eec`
- Source archive SHA-256:
  `22561db74d63b08a2b2d929cf68f597ed645c6dc529282c54f048b7dd18c6efb`

This remains an early alpha. Mutating commands default to dry-run, and manual
review is recommended before committing changes to a Live Set.

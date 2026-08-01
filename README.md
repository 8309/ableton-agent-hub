# Ableton Agent Hub

Ableton Agent Hub is an unofficial local Max for Live bridge and Python toolkit
for inspecting Ableton Live Sets and applying reviewed changes. Mutating
commands default to dry-run and require an explicit commit.

This repository is currently being prepared for the first public alpha release.
Installation and packaging are not yet finalized. See
`docs/release_scope_v0.1.0-alpha.md` for the frozen capability scope.

## Architecture

```text
Python client -> UDP 7400 -> Ableton Agent Hub.amxd -> Live Object Model
Python client <- UDP 7401 <- Ableton Agent Hub.amxd
```

The Hub is the only supported Max for Live entry point. The Python clients send
requests sequentially because all commands share one reply port.

## Safety

- Read operations do not modify the Live Set.
- Write operations default to dry-run.
- A commit must identify the target before changing it.
- Commits read the affected state back when the Live API permits it.

## Status

Target release: `v0.1.0-alpha`.

This project is not affiliated with or endorsed by Ableton.

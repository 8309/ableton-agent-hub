# Safety Model

Ableton Agent Hub can modify an open Live Set. Its safety model reduces
accidental writes, but it cannot replace backups, careful target review, or
Live's own undo and save workflows.

## Operation Levels

| Level | Meaning | Expected Behavior |
| --- | --- | --- |
| Read | Inspect Live state | No intentional Set mutation |
| Dry-run | Resolve and preview a write | Validate target and values without writing |
| Commit | Apply a reviewed write | Explicit opt-in, narrow mutation, then readback where possible |

Write-capable Python clients default to dry-run. `--commit` is the explicit
boundary between a plan and a Live mutation.

## Target Resolution

Track names and indices are convenient for discovery but can become ambiguous
or move as the Set changes. The Hub prefers stable Live object IDs for commits,
especially for Return and Main targets. A dry-run should return the resolved
section, object ID, name, and relevant before-state.

Do not reuse a plan after changing track order or replacing devices. Rescan and
generate a new dry-run.

## Readback

A successful method call is not always proof that Live changed as expected.
Commit-capable modules should read the target again and report the observed
after-state when the Live Object Model exposes it. Device insertion uses
before/after device IDs; protected deletion verifies the intended ID vanished
without reordering survivors.

Readback has limits. Live can briefly report stale transport state, and some
properties or automation envelopes are not exposed. The command must state when
verification is partial.

## Internal And UI Parameter Values

Live stores an exact internal value. The visible control may show a formatted
value such as `30 %`, `350 Hz`, or a quantized label. Structured results should
retain the internal value and request Live's display formatter only when needed.
Code must not guess units or assume a linear conversion.

## Destructive Operations

- Work on a duplicate Set for initial validation.
- Save before a commit and keep Live's undo history available.
- Never delete a non-empty track, clip, scene, or device without an explicit
  reviewed plan.
- Prefer no-op or same-value commits when validating a new write path.
- Treat partial errors as a reason to inspect Live before retrying.

The Hub does not silently fall back to keyboard, mouse, or Browser automation
when the public Live API cannot perform an operation.

## Local Transport Security

The Python clients default to `127.0.0.1`, but the Max UDP receiver provides no
authentication or encryption. This project is intended for one trusted local
machine.

- Do not forward or expose UDP ports `7400` and `7401`.
- Do not run untrusted local programs while a write-capable Hub is loaded.
- Keep firewall rules limited to the local machine.
- Do not place secrets in Hub payloads or logs.

## Concurrency

All requests share reply port `7401`. Run one Hub command at a time. Parallel
clients can compete for a reply and make correlation fail even though each
request has an ID.

## Failure Behavior

A safe failure should return a clear error, avoid follow-up writes, and leave
enough target context to diagnose the problem. After a timeout or error:

1. wait for the original request to finish;
2. ping the Hub;
3. rescan the target;
4. create a new dry-run;
5. commit only after the new plan is correct.

See the [dry-run/commit contract](../ableton_agent/schemas/dry_run_commit_contract.md)
for the machine-facing rules.

# Dry-Run And Commit Compatibility Contract

The authoritative execution model is
`risk_based_execution_contract.md`. Existing Hub wire modes remain compatible:

- `dry_run` means inspect without changing Live.
- `commit` means apply and verify.

Python clients may expose these as `inspect` and `apply`. Low-risk scalar writes
can default to guarded apply; destructive actions continue to inspect first and
use stable identities or plan tokens where supported.

Inspection/dry-run must:

- validate target objects and payload shape
- report targets, projected scalar values, or destructive impact
- avoid changing the Live Set
- never claim it simulated audible or structural post-state
- return stable target ids for Return/Main writes and the current Return id list
  before Return creation

Apply/commit must:

- perform only the validated action
- report the changed target and after-state when practical
- return a clear error without partial follow-up actions when validation fails
- resolve Return/Main writes by the stable id returned by dry-run
- verify Return creation by observing exactly one new Return track id before
  applying its name, color, or selection
- require stable Return `track_id`, expected name, a content/order-derived plan
  token, and explicit non-empty approval before Return deletion; verify exactly
  that ID disappeared and all surviving Return IDs kept their order
- verify device insertion through a before/after device-id readback; a call that
  returns without an observable new device is not reported as applied

Read-only commands may ignore `commit` and should return `dry_run: true`.

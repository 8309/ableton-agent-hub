# Dry-Run And Commit Contract

All write-capable commands default to dry-run.

Dry-run must:

- validate target objects and payload shape
- report what would change
- avoid changing the Live Set
- return stable target ids for Return/Main writes and the current Return id list
  before Return creation

Commit must:

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

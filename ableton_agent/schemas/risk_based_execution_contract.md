# Direct Intent Execution Contract

The historical filename is retained for compatibility. ADR-0008 supersedes
risk-based selection: reads are direct and explicit user-requested writes apply
directly. Inspection is optional, not a mandatory extra round trip.

Ableton Agent separates target inspection from execution. Inspection is useful
when it exposes identity, affected content, dependencies, or a stale-state
guard. It is not a simulation of the audible or structural result.

## Public Intent

Migrated Python write clients use these execution values:

- `auto`: apply writes directly; read-only actions remain inspect/read-only.
- `inspect`: resolve targets and report projected values or impact without
  changing Live.
- `apply`: perform the action and read back the affected state.

Legacy `commit=False` maps to `inspect`; `commit=True` maps to `apply`. On the
Hub wire, `inspect` remains `dry_run` and `apply` remains `commit` so installed
and older clients remain compatible.

## Action Policy

All writes use direct apply under auto; legacy risk labels are metadata only.
Stable identity, range checks, target restrictions and readback remain within the
request. Explicit inspect remains non-mutating. Old clients that explicitly pass
`commit=False` retain their non-writing behavior.

## Guarded Apply

`/set_mix` and `/set_parameters` perform one sequential Hub request:

1. Resolve the target and capture the exact internal before-value.
2. Validate type, range, enabled state, and optional `expected_before`.
3. Apply all bounded changes.
4. Read back exact internal and Live UI values.
5. Return `timings` and an `undo_receipt` containing stable IDs, exact
   before-values, and the after-values used as restore guards.

If a later write or readback fails, the Hub restores already-written values in
reverse order. It reports `rolled_back`, `rollback_errors`, and
`completed_before_failure`; it never labels a partially restored operation as
success.

## Restore

Python stores at most 64 compact receipts in
`%LOCALAPPDATA%\AbletonAgentHub\operation_journal.json`, or the path selected by
`ABLETON_AGENT_OPERATION_JOURNAL`. Restore writes the exact before-value, not an
arithmetic inverse. It supplies the recorded after-value as `expected_before`;
if Live has changed since the operation, the restore is rejected as stale.

Live's own Undo remains available independently. The local receipt is a narrow
recovery mechanism, not a replacement for Live's undo history and not a full
Live Set transaction.

## Destructive Inspection

Creative actions accept direct apply without a prior token. Explicit tokens
retain their checks; legacy wire calls without the direct-apply flag retain the
old protocol. Optional non-writing responses describe impact inspection:

- which object is targeted
- current content or dependency summary where exposed
- current order and stable IDs where relevant
- whether the action is reversible by this Agent
- an optional token to guard a later apply

Inspection does not claim to predict sound, plug-in side effects, or all Live UI
consequences. A successful apply must verify the observed postcondition.

## Batch Bounds

Hub scalar writes remain bounded (`32` mixer changes, `16` parameter changes).
Callers should normally send `4..8` changes per sequential batch on UDP `7401`.
Batch orchestration must report completed and unexecuted work and stop after a
failure unless the caller explicitly chooses otherwise.

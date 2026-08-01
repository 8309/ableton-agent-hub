# Ableton Agent Hub Workflow

This workspace uses one Max for Live entrypoint:

```text
Ableton Agent Hub/Ableton Agent Hub.amxd
```

Do not normally load old single-purpose Agent devices. They can compete for the same UDP ports and make it unclear which code Live is running.

## Runtime

- Hub command port: UDP `7400`
- Hub reply port: UDP `7401`
- Python clients: `ableton_agent/python/ableton_bridge/`
- Max modules: `ableton_agent/max/`
- Built Hub output: `ableton_agent/dist/Ableton Agent Hub.amxd`
- Recommended Live install folder:

```text
User Library/Presets/MIDI Effects/Max MIDI Effect/Ableton Agent Hub/
```

## Command Pattern

Hub commands follow the same envelope:

```text
/command request_id payload_json mode
```

Modes:

- `dry_run`: default for all Python clients unless `--commit` is passed
- `commit`: allowed only after reviewing the planned target/change

Replies should include:

- `ok`
- `dry_run`
- `request_id`
- `message` or `error`

Mutating commands should report their target track, clip, scene, device, or beat before commit.

## Normal Use

1. Load one `Ableton Agent Hub.amxd` in the current Live Set.
2. Check the connection:

```bash
PYTHONPATH=ableton_agent/python python -m ableton_bridge.ping
```

3. Use a read or dry-run command first.
4. Review the reported target and planned change.
5. Run the same command with `--commit` only when the target is correct.
6. Read back the changed state where possible.

## Development Loop

Each new capability should stay small:

1. Add one internal Max JS module when Live API access is needed.
2. Add one Python client or local Python helper.
3. Add the Hub route if the feature needs Live.
4. Add the JS file to `build_hub_device.py`.
5. Add unit/static tests.
6. Rebuild the Hub.
7. Sync the built Hub and JS files to the User Library Hub folder.
8. Stop and wait for the user to reload the Hub in Live.
9. Run Live dry-run/read validation.
10. Commit one tiny safe Live change only when useful and confirmed.
11. Update `SESSION_HANDOFF.md`.
12. Create a Git checkpoint.

## Rebuild

From the repository root:

```bash
python ableton_agent/build_hub_device.py
```

Then copy the rebuilt Hub and any new JS module into:

```text
User Library/Presets/MIDI Effects/Max MIDI Effect/Ableton Agent Hub/
```

After copying, reload or re-drag the Hub in Live before testing the new route.

## Validation Checklist

Use this checklist before calling a capability complete:

- Unit tests pass.
- Hub JSON validates.
- New JS module is copied by `build_hub_device.py`.
- Hub route contains the new command.
- `ping` works after user reloads Hub.
- Dry-run/read command works in Live.
- Commit validation, if applicable, is tiny and reversible or same-value.
- Readback confirms the result.
- `SESSION_HANDOFF.md` records current state only.

## Current Docs

- `docs/api_capability_matrix.md`: current command status and safety level.
- `docs/manual_sample_workflow.md`: sample picking, manual drag-in, and loaded-sample confirmation.
- `ableton_agent/schemas/command_envelopes.md`: request/reply shape.
- `ableton_agent/schemas/dry_run_commit_contract.md`: dry-run/commit expectations.

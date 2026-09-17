# Ableton Agent Hub Workflow

The supported Live entrypoint is:

```text
Ableton Agent Hub/Ableton Agent Hub.amxd
```

Load one Hub in the current Set. Multiple copies can compete for the same UDP
ports and make it unclear which JavaScript version is responding.

## Runtime

- Command port: UDP `7400`
- Reply port: UDP `7401`
- Python package: `ableton_bridge`
- Max source modules: `ableton_agent/max/`
- Built Hub files: `ableton_agent/dist/`
- Packaged installer resources: `ableton_agent/python/ableton_bridge/resources/hub/`

The usual Live install directory is:

```text
User Library/Presets/MIDI Effects/Max MIDI Effect/Ableton Agent Hub/
```

## Request Contract

Capability routes use a correlated request ID, JSON payload, and operation mode.
The detailed shape is defined in
[`command_envelopes.md`](../ableton_agent/schemas/command_envelopes.md).

Modes:

- `dry_run`: optional read-only validation (legacy wire name).
- `commit`: explicit apply. MCP maps user-requested writes to apply directly.

Replies should include `ok`, `dry_run`, `request_id`, and either a useful result
or a clear error. A mutating command should resolve its target before commit and
read the changed state back where possible.

## Normal Use

1. Install the Hub with `ableton-agent install --dry-run`, then
   `ableton-agent install`.
2. Load one Hub device in the open Set.
3. Run `ableton-agent ping`.
4. Read directly, or apply an explicit user-requested change.
5. Resolve the object ID, name and section; preserve before-state.
6. Use `--commit` for legacy CLI writes. A separate dry-run is optional.
7. Inspect Live and the structured readback.

Send commands sequentially. All clients share reply port `7401`.

## Development Loop

1. Add or update one focused Max JavaScript module.
2. Add or update its Python client.
3. Keep the existing Hub route compatible when possible.
4. Add the module to `build_hub_device.py` when it is new.
5. Add unit and static tests.
6. Rebuild the Hub.
7. Sync built files into the Python package resources.
8. Install into a test User Library destination.
9. Manually reload the Hub in Live.
10. Ping, dry-run, perform one minimal commit, and read back.
11. Update the capability matrix and API-limit documentation.

## Build And Package

From the repository root:

```powershell
python ableton_agent/build_hub_device.py
python tools/sync_package_resources.py
python -m unittest discover -s tests -p "test_*.py"
python -m pip wheel . --no-deps --wheel-dir dist
```

The builder validates every declared JavaScript dependency. The sync script
copies the built Hub plus all required JS modules into package resources. The
installer then hash-verifies those packaged bytes at the destination.

## Reload Boundary

Copying files does not guarantee that an already loaded Max device is executing
the new code. Reload or remove/re-add the Hub manually after each installed
update. Do not run Live validation until the reload is complete.

## Validation Checklist

- Unit tests pass.
- Hub JSON validates.
- Source and built JS files match.
- Packaged resources match the built distribution.
- Installation dry-run resolves the intended destination.
- Clean temporary installation writes and verifies 27 files.
- Hub is manually reloaded.
- Ping succeeds.
- One read or dry-run succeeds.
- A minimal commit and readback succeed for changed write behavior.
- Capability matrix states the actual validation level.

Related documentation:

- [Getting Started](getting_started.md)
- [Safety Model](safety_model.md)
- [Capability Matrix](api_capability_matrix.md)
- [Live API Limits](live_api_limits.md)
- [Manual Sample Workflow](manual_sample_workflow.md)

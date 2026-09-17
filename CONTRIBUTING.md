# Contributing

Thanks for helping improve Ableton Agent Hub. The project is an early alpha, so
small changes with explicit safety and Live validation evidence are preferred.

## Development Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Do not test write operations on the only copy of an important Set.

## Change Shape

A Live-facing capability normally includes:

- one focused Max JavaScript module;
- a Python client or helper;
- a route in the Hub patch when Live access is required;
- builder and installer-resource coverage;
- unit/static tests;
- one explicit-intent minimal apply and readback when the operation writes.

Keep existing routes compatible unless a breaking change is explicitly planned.
Use Live's stable object IDs for commits where indices can change.

## Build And Verify

```powershell
python ableton_agent/build_hub_device.py
python tools/sync_package_resources.py
python -m unittest discover -s tests -p "test_*.py"
python -m pip wheel . --no-deps --wheel-dir dist
```

After changing Max code, install the rebuilt Hub into a test destination, reload
the device manually in Live, ping it, and validate the smallest useful action.
Live validation is manual and is not replaced by unit tests.

## Safety Requirements

- MCP applies explicit user intent; legacy CLI commands retain `--commit`.
- Dry-run must not mutate Live state.
- Commit must resolve and report its target before writing.
- Commit should read back the affected state whenever Live exposes it.
- Unsupported or ambiguous operations must fail clearly.
- Do not add simulated mouse/keyboard control as a silent fallback.

## Public Data Boundary

Do not commit songs, ALS files, samples, local catalogs, machine paths, secrets,
session handoffs, or generated experiment data. `PUBLIC_EXPORT_MANIFEST.json`
records the curated source snapshot. Public-owned packaging files are protected
from later source exports by `tools/export_from_workspace.py`. The exporter
normalizes exported text to LF before hashing it so the manifest matches a clean
Git checkout on every platform. Regenerate the manifest through the exporter;
do not edit its hashes by hand.

## Pull Request Checklist

- Scope and user-visible behavior are described.
- Tests pass.
- Hub build and packaged resources match.
- Direct apply, optional inspect and readback behavior are documented.
- Live version and validation evidence are stated.
- Capability matrix and API-limit docs are updated when behavior changes.
- No personal paths or private project data are included.

By contributing, you agree that your contribution may be distributed under the
MIT License.

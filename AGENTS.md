# Ableton Agent Hub

## Repository Contract

- Read `README.md` and `CONTRIBUTING.md` before changing behavior.
- For Live-facing changes, also read `docs/safety_model.md`,
  `docs/api_capability_matrix.md`, `docs/hub_workflow.md`, and the relevant
  contract under `ableton_agent/schemas/`.
- Keep changes bounded and preserve existing routes unless a breaking change is
  explicitly planned.

## Current Live Set

- Before reading the current Set, confirm Ableton Live is open and exactly one
  `Ableton Agent Hub.amxd` is loaded in that Set.
- For a source checkout, use only:
  `powershell -ExecutionPolicy Bypass -File scripts/read_current_set.ps1`.
- Use the progressive default, then reuse the generated JSON cache for follow-up
  summaries. Do not rescan merely to reformat the same state.
- Never send concurrent Hub requests. UDP 7401 is one sequential reply channel.
- If preflight fails, stop and report it. Never present an older cache as the
  current Live Set.

## Write Safety

- Read directly. Apply explicit user-requested writes directly with resolved
  stable targets; do not require risk tiers or a separate dry-run.
- `--commit` remains the explicit write flag for legacy CLI commands.
- Inspect/dry-run must never mutate Live and is not a simulation of its result.
- After commit, read back the affected state where supported.
- A timed-out write has unknown outcome: check affected state before retrying.
- Do not silently fall back to mouse or keyboard automation.

## Development Workflow

- Treat `ableton_agent/max/` as source. Do not hand-edit generated copies in
  `ableton_agent/dist/` or packaged Hub resources.
- Rebuild with `python ableton_agent/build_hub_device.py`.
- Synchronize packaged resources with `python tools/sync_package_resources.py`.
- After installing an updated Hub, require a manual device reload before Live
  validation.

## Done When

- Run `git diff --check`.
- Run `python -m unittest discover -s tests -p "test_*.py"`.
- For Max changes, rebuild and verify source, distribution, and packaged
  resources agree.
- Update the capability matrix and API-limit documentation when behavior or
  validation status changes.
- Report changed files, checks run, risks, assumptions, and unverified Live
  behavior.

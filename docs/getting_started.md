# Getting Started

This guide installs Ableton Agent Hub from a local checkout and validates it
without changing the current Live Set.

## 1. Check Prerequisites

You need:

- Ableton Live with Max for Live;
- Python 3.11 or newer;
- a local clone or downloaded source checkout;
- permission to write to your Ableton User Library.

The first alpha has been tested on Windows, Live 12.3.5, and Python 3.12.13.

## 2. Create An Isolated Python Environment

From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\ableton-agent.exe --version
```

The expected package version is `0.3.0a0` for this alpha candidate.

## 3. Preview The Hub Installation

```powershell
.\.venv\Scripts\ableton-agent.exe install --dry-run
```

The JSON result reports:

- the resolved destination;
- every packaged Hub file;
- whether each file would be created, updated, or left unchanged;
- the expected SHA-256 hash.

Dry-run does not create the destination folder.

The usual destination is:

```text
User Library/Presets/MIDI Effects/Max MIDI Effect/Ableton Agent Hub/
```

If Ableton uses a custom User Library, pass it explicitly:

```powershell
.\.venv\Scripts\ableton-agent.exe install `
  --destination "D:\Ableton User Library\Presets\MIDI Effects\Max MIDI Effect\Ableton Agent Hub" `
  --dry-run
```

## 4. Install And Load The Hub

After reviewing the destination:

```powershell
.\.venv\Scripts\ableton-agent.exe install
```

The installer writes only the known Hub files and verifies them after copying.
It does not remove unrelated files.

Open Ableton Live, find `Ableton Agent Hub` in the User Library, and add exactly
one `Ableton Agent Hub.amxd` to a MIDI track. When updating the software, remove
and re-add or reload the device manually so Live uses the new JavaScript files.

## 5. Run A Read-Only Connection Check

```powershell
.\.venv\Scripts\ableton-agent.exe ping
```

A successful reply contains `"ok": true`. The Python client sends to UDP
`7400` and waits for the correlated reply on UDP `7401`.

Read the global tempo:

```powershell
.\.venv\Scripts\ableton-agent.exe tempo
```

Neither command changes the Set.

Run the standard progressive first read:

```powershell
.\.venv\Scripts\ableton-agent.exe initial-read
```

The command first writes `.ableton-agent/current_set_initial_read.quick.json`,
then reuses the same metadata for MIDI-note and mixer depth and writes
`.ableton-agent/current_set_initial_read.json`. It is read-only. Checkout users
can alternatively run `scripts/read_current_set.ps1`, which additionally checks
for a running Ableton Live process before contacting the Hub.

When using Codex or another coding agent, follow
[Agent Setup](agent_setup.md) so new sessions use this entrypoint instead of
rediscovering or parallelizing the underlying UDP commands.

## 6. Preview Before A Write

```powershell
.\.venv\Scripts\ableton-agent.exe tempo --bpm 128
```

Review the returned current and planned values. To apply the same target:

```powershell
.\.venv\Scripts\ableton-agent.exe tempo --bpm 128 --commit
```

Use `Save As` or a disposable Set for the first commit. Arrangement tempo
automation can override the global tempo and must currently be edited manually.

## 7. Explore Focused Clients

Each larger capability exposes its own Python module:

```powershell
.\.venv\Scripts\python.exe -m ableton_bridge.track_management --help
.\.venv\Scripts\python.exe -m ableton_bridge.parameter_summary --help
.\.venv\Scripts\python.exe -m ableton_bridge.clip_note_tools --help
```

Use a scan/read action before selecting a target. Prefer stable IDs returned by
the scan over a remembered track index.

## Troubleshooting

### Ping Times Out

- Confirm the Hub device is present and enabled in the currently open Set.
- Reload the Hub after installing an update.
- Confirm only one Hub is loaded.
- Confirm another Python request is not already waiting on reply port `7401`.
- Check that local firewall rules are not blocking UDP `7400` and `7401`.

### The Hub Does Not Appear In Live

- Compare the install destination with Live's configured User Library path.
- Rescan the User Library or restart Live.
- Use `install --destination PATH` when Documents is redirected by OneDrive or
  the User Library lives elsewhere.

### A Large Read Times Out

Use a bounded client action with a smaller page limit or projection. Commands
must run sequentially. A timeout does not prove that Live is frozen; ping the
Hub again after the request ends.

### A Commit Targets The Wrong Index

Stop and rescan. Track indices can change when tracks are inserted, deleted,
grouped, or reordered. Commit-capable special-track operations require stable
Live object IDs for this reason.

Continue with the [safety model](safety_model.md), [Hub workflow](hub_workflow.md),
and [capability matrix](api_capability_matrix.md).

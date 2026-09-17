# Ableton Agent Hub

Ableton Agent Hub is an unofficial, local Max for Live bridge and Python toolkit
for inspecting Ableton Live Sets and applying reviewed changes. It uses one Hub
device in Live and a collection of focused Python clients outside Live.

This repository is an early public alpha. MCP applies explicit write intent
directly with stable targets and readback; inspection remains optional and
read-only. Legacy CLI clients retain explicit `--commit`. Test on a copy of a Set.

## 0.4 Alpha Update

- Typed MCP tools for discovery, MIDI/Arrangement editing, device/mixer writes,
  automation-state inventory, diagnostics and local saved-ALS evidence.
- Mixed scalar batches and verified UI-unit input, without mandatory dry-runs.
- Compact Hub Overview/History/Diagnostics panel with runtime build identity.
- Local reference-audio feature ranking and cache; no model download or upload.

The graphical panel still needs native Live visual acceptance. Audio ranking is
tested on standard PCM WAV/AIFF/FLAC, but sampled compressed Pack AIF files could
not decode. Listening acceptance remains pending. See
[audio limits](docs/audio_similarity.md) and [release validation](docs/release_v0.4.0-alpha.md).
Upgrading agents should reread [Agent Setup](docs/agent_setup.md) and update their
own `AGENTS.md`; the installer never edits those instructions automatically.

## What It Does

- Reads Live Set, track, device, parameter, clip, scene, locator, routing, and
  meter information within documented limits.
- Controls tempo, transport, mixer values, selected device parameters, clips,
  scenes, locators, routing, and a whitelist of native devices.
- Uses bounded, sequential reads for larger parameter and track collections.
- Runs one progressive first read that exposes a quick Set map, then reuses the
  same metadata for bounded MIDI-note and mixer depth.
- Builds a machine-local SQLite sound catalog for searching Packs, presets,
  samples, Live Clips, MIDI files, and installed plugins without publishing the
  user's catalog data.
- Preserves Live's exact internal parameter values and can request the visible
  UI value when Live exposes a safe formatter.
- Helps select local samples and confirms manually loaded Simpler or Drum Rack
  samples where the Live API exposes their paths.

The row-by-row source of truth is the
[capability matrix](docs/api_capability_matrix.md). Experimental and blocked
areas are summarized in [Live API limits](docs/live_api_limits.md).

## Requirements

The first alpha has been validated on:

- Windows
- Ableton Live 12.3.5 with Max for Live
- Python 3.12.13

Python 3.11 or newer is accepted by the package. Other Live versions and
operating systems are currently unverified.

## Install From A Checkout

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[mcp,audio]"
.\.venv\Scripts\ableton-agent.exe install --dry-run
.\.venv\Scripts\ableton-agent.exe install
```

The installer copies the Hub and its JavaScript modules to the usual Ableton
User Library location and verifies every file with SHA-256. It does not delete
other files. Use `--destination PATH` when your User Library is elsewhere.

In Ableton Live:

1. Find `Ableton Agent Hub` under Max MIDI Effects in the User Library.
2. Add exactly one `Ableton Agent Hub.amxd` to a MIDI track in the open Set.
3. Check the connection:

```powershell
.\.venv\Scripts\ableton-agent.exe ping
```

Read and preview tempo changes:

```powershell
.\.venv\Scripts\ableton-agent.exe tempo
.\.venv\Scripts\ableton-agent.exe tempo --bpm 132
.\.venv\Scripts\ableton-agent.exe tempo --bpm 132 --commit
```

Run the standard read-only first scan of the currently open Set:

```powershell
.\.venv\Scripts\ableton-agent.exe initial-read
```

This writes a quick checkpoint first, then completes MIDI-note and mixer depth
without rescanning the track and clip collections. Use `--depth quick` for an
explicitly metadata-only refresh.

This source repository includes a root `AGENTS.md` so coding agents load the
supported development and Live-safety workflow automatically. Users who install
the package into another project should add the recommended rules from
[Agent Setup](docs/agent_setup.md) to that project's instructions file. The
installer never overwrites an existing instructions file.

The second command is a dry-run. Only the third command writes Live's global
tempo. Arrangement tempo automation is not editable through this Hub and can
override the global value during playback.

See [Getting Started](docs/getting_started.md) for custom destinations,
troubleshooting, and the first safe validation loop.

## Architecture

See the [current structure and boundaries](docs/architecture.md) and
[MCP configuration example](examples/mcp.toml). Install `.[mcp,audio]` for all
optional features, then run `python -m ableton_bridge.mcp_server` via your agent.

```text
Python client -> UDP 7400 -> Ableton Agent Hub.amxd -> Live Object Model
Python client <- UDP 7401 <- Ableton Agent Hub.amxd
```

The transport is local, unauthenticated UDP. Do not expose ports `7400` or
`7401` to untrusted networks. Send commands sequentially because all clients
share the reply port.

## Safety Model

- Reads do not intentionally modify the Live Set.
- Mutating commands preview by default.
- `--commit` is required for a supported write.
- Stable Live object IDs are preferred over changing track indices.
- A commit reads affected state back when the Live API permits it.
- Unsupported writes fail rather than silently falling back to UI automation.

Read the complete [safety model](docs/safety_model.md) before using commits on
important work.

## Advanced Clients

The unified `ableton-agent` command covers installation, connection checks,
tempo, and low-level requests. Focused clients remain available as Python
modules, for example:

```powershell
.\.venv\Scripts\python.exe -m ableton_bridge.track_management --help
.\.venv\Scripts\python.exe -m ableton_bridge.parameter_summary --help
.\.venv\Scripts\python.exe -m ableton_bridge.sample_confirm --help
```

For a low-level read request:

```powershell
.\.venv\Scripts\ableton-agent.exe raw snapshot '{}' --timeout 10
```

Low-level commands expose internal payloads. Consult the schemas and capability
matrix before using them.

## Development

```powershell
python -m unittest discover -s tests -p "test_*.py"
python ableton_agent/build_hub_device.py
python tools/sync_package_resources.py
```

The source Max modules, built distribution, and packaged installer resources
must agree before a release. See [Contributing](CONTRIBUTING.md) and the
[Hub workflow](docs/hub_workflow.md).

## License And Disclaimer

Released under the [MIT License](LICENSE).

Ableton, Ableton Live, and Max for Live are trademarks of their respective
owners. This project is not affiliated with or endorsed by Ableton.

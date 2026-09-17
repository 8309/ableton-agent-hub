# Architecture

```text
Coding agent / CLI
  -> Python MCP server (27 typed tools)
     -> sequential reply-port lock
        -> UDP 7400 -> Max for Live Hub -> Live Object Model
        <- UDP 7401 <- correlated progress/final replies
     -> local SQLite sound catalog / bounded waveform cache
     -> read-only saved ALS parser (separate saved evidence)

Hub UI: passive event observer -> Overview / History / Diagnostics
```

## Repository Map

- `ableton_agent/python/ableton_bridge`: clients, MCP orchestration and local readers.
- `ableton_agent/max`: authoritative Max JavaScript and patch source.
- `ableton_agent/build_hub_device.py`: portable or explicit local-path build.
- `ableton_agent/dist`: portable distribution and content-hash build manifest.
- `ableton_agent/python/ableton_bridge/resources/hub`: wheel installer assets.
- `ableton_agent/schemas`: request, pagination, diagnosis and execution contracts.
- `docs`, `examples`, `tests`: public operational rules, configuration and tests.
- `tools/export_from_workspace.py`: curated source boundary; never imports local dist.
- `tools/sync_package_resources.py`: copies built portable assets into the package.

Live runtime IDs and saved XML IDs are different domains. The Hub is authoritative
for current Live state; saved-file results are explicitly the last saved state.
Reads and writes share one reply channel. A batch is sequential, not atomic.
Only user intent authorizes writes. Inspect is optional; after-state readback
and exact scalar receipts are retained. A timed-out write is not automatically
retried. No tool silently falls back to GUI automation or saves a Set.

Catalog databases, media, songs, local runtime caches and private development
history are intentionally not included. Installers never update agent instruction
files automatically: reread `docs/agent_setup.md` when upgrading.

# Manual Sample Workflow

Ableton Agent can discover or verify local sample paths, but the public Max for
Live API does not provide a supported way to load an arbitrary file into
Simpler or a Drum Rack pad.

The supported workflow is:

1. Discover or choose a candidate path.
2. Verify that the file still exists.
3. Drag the file into Live manually.
4. Confirm the sample path that Live exposes.
5. Continue with MIDI, mix, effects, arrangement, routing, and meter tools.

## Build A Machine-Local Catalog

The public repository does not contain anyone's local catalog. Generate one on
your own machine and keep it outside version control:

```powershell
.\.venv\Scripts\python.exe -m ableton_bridge.sound_catalog scan `
  --catalog .\local_sound_catalog.json
```

Search the generated catalog:

```powershell
.\.venv\Scripts\python.exe -m ableton_bridge.sound_catalog search `
  --catalog .\local_sound_catalog.json `
  --role percussion `
  --limit 5
```

Catalog discovery does not mean the Agent can insert a preset or load a sample.
Check the returned `exists`, `load_mode`, and `auto_insert` fields.

## Verify A Known Path

Before recommending a file, verify it immediately:

```powershell
.\.venv\Scripts\python.exe -m ableton_bridge.sample_index `
  --sample-path "C:\path\to\sample.wav" `
  --index-path .\local_sample_index.json
```

If an indexed path is missing, the helper can rescan nearby category folders and
report replacement candidates. It must not claim a missing file is usable.

## Drag Into Live

For Simpler:

1. Select the target MIDI track.
2. Open Simpler.
3. Drop the file on the sample display.
4. Confirm that the waveform and sample name appear.

For Drum Rack:

1. Open the Drum Rack.
2. Select the intended pad.
3. Drop the file directly on that pad.
4. Confirm the pad label and nested sample device.

## Confirm The Loaded Sample

Scan loaded samples without broad Drum Rack traversal:

```powershell
.\.venv\Scripts\python.exe -m ableton_bridge.sample_confirm `
  --action scan_loaded_samples `
  --limit 12
```

Confirm one scan candidate against the intended path:

```powershell
.\.venv\Scripts\python.exe -m ableton_bridge.sample_confirm `
  --candidate-index 0 `
  --intended-path "C:\path\to\sample.wav"
```

Target a known Simpler:

```powershell
.\.venv\Scripts\python.exe -m ableton_bridge.sample_confirm `
  --track-index 5 `
  --target simpler `
  --intended-path "C:\path\to\sample.wav"
```

Target a known Drum Rack pad:

```powershell
.\.venv\Scripts\python.exe -m ableton_bridge.sample_confirm `
  --track-index 7 `
  --target drum_rack_pad `
  --pad-note 42 `
  --intended-path "C:\path\to\sample.wav"
```

Interpretation:

- `exact_match: true` means Live reports the same path.
- `basename_match: true` can mean Live copied the same named sample into the
  project, commonly under `Samples/Imported`.
- A missing result is not proof that no sample is loaded; Drum Rack traversal is
  best-effort and should be checked in the Live UI.

`/load_sample` remains a path-validation/preparation route. It does not perform
arbitrary sample loading.

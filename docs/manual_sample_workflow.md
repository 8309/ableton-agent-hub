# Manual Sample Workflow

Ableton Agent can choose and verify local sample paths, but public Max for Live APIs do not provide a supported way to load an arbitrary local audio file into Simpler or Drum Rack.

The supported workflow is:

1. Agent picks sample candidates from the local index.
2. Agent confirms the candidate path exists.
3. User manually drags the chosen file into Simpler or a Drum Rack pad.
4. Agent reads back the loaded sample path where Live exposes it.
5. Agent continues with MIDI, mix, effects, sends, arrangement, routing, scenes, and meter checks.

## Pick Candidates

Pick hihats:

```bash
PYTHONPATH=ableton_agent/python python -m ableton_bridge.sample_picker --category hat --style garage --limit 5
```

Pick shakers:

```bash
PYTHONPATH=ableton_agent/python python -m ableton_bridge.sample_picker --category shaker --limit 5
```

Pick percussion by query:

```bash
PYTHONPATH=ableton_agent/python python -m ableton_bridge.sample_picker --category perc --query rim --limit 5
```

Returned candidates are filtered so `exists` is true. If an indexed path is missing, the picker can refresh nearby folders and use the updated index.

## Manual Drag-In

For Simpler:

1. Select the target track.
2. Drop the sample onto Simpler.
3. Keep the target device visible if you want immediate visual confirmation.

For Drum Rack:

1. Open the Drum Rack.
2. Drop the sample onto the intended pad.
3. The visible pad label should change to the sample name.

## Confirm Loaded Sample

Scan loaded samples first:

```bash
PYTHONPATH=ableton_agent/python python -m ableton_bridge.sample_confirm --action scan_loaded_samples --limit 12
```

Then confirm a chosen scan result:

```bash
PYTHONPATH=ableton_agent/python python -m ableton_bridge.sample_confirm --candidate-index 0 --intended-path "C:\path\to\sample.aif"
```

Confirm a manually loaded Drum Rack pad:

```bash
PYTHONPATH=ableton_agent/python python -m ableton_bridge.sample_confirm --track-index 7 --target drum_rack_pad --pad-index 42 --intended-path "C:\path\to\sample.aif"
```

Confirm a Simpler:

```bash
PYTHONPATH=ableton_agent/python python -m ableton_bridge.sample_confirm --track-index 5 --target simpler --intended-path "C:\path\to\sample.aif"
```

Interpretation:

- `candidate_index` is produced by `scan_loaded_samples`.
- `exact_match: true` means Live is using that exact filesystem path.
- `basename_match: true` means the loaded file name matches, even if Live copied the file into the project.
- A project copy usually appears under:

```text
Current Project/Samples/Imported/
```

## Current UKG Hihat

Original chosen path:

```text
C:\ProgramData\Ableton\Live 12 Trial\Resources\Core Library\Samples\One Shots\Drums\Hihat\Hihat Closed Sharp Garage.aif
```

Live-confirmed project copy:

```text
C:/path/to/Ableton Project/Samples/Imported/Hihat Closed Example.aif
```

Current Drum Rack confirmation:

```text
Track: 8-Top Percussion
Pad index: 42
MIDI note: 42
Pad name: Hihat Closed Sharp Garage
```

## Known Limit

`/load_sample` remains a validation/preparation route. It cannot perform arbitrary local file loading into Simpler or Drum Rack in the current public Max for Live API surface.

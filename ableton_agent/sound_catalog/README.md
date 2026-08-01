# Local Sound Catalog

`local_sound_catalog_summary.md` is the lightweight overview all creative
sessions read first. `local_sound_catalog.json` is the full machine-specific
inventory queried by the CLI. Both are regenerated locally and excluded from
Git because they contain absolute paths.

Refresh from the repository root:

```powershell
$env:PYTHONPATH='ableton_agent/python'
python -m ableton_bridge.sound_catalog scan
```

Search without rescanning:

```powershell
python -m ableton_bridge.sound_catalog search --pack "Lost and Found" --kind ableton_preset
python -m ableton_bridge.sound_catalog search --kind plugin
```

- `exists` means the path was present during the latest scan.
- `manual_load` means load it through Live's Browser or plugin chooser.
- `control_after_load` means parameter inspection may be attempted after loading.
- `auto_insert: false` means discovery did not whitelist automatic insertion.

Default roots are local C-drive Ableton and plugin directories. External drives
are excluded unless the user explicitly supplies them.

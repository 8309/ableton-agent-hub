# Local Sound Catalog

`local_sound_catalog.sqlite3` is the Agent-facing source of truth. It contains
stable Pack/resource identities, structured fields, provenance-aware tags,
FTS5 search, scan evidence, audio header and filename metadata, parsed Ableton
preset structure, and preset-to-resource links. Feedback and embedding tables
remain reserved for later versions.

`local_sound_catalog_summary.md` is the detailed human-readable inventory all
creative and development sessions read first. It includes scan scope, Pack
sizes, resource breakdowns, role coverage, examples, update instructions, and
capability boundaries. `local_sound_catalog.json` remains the compatibility and
debug export. All three are regenerated locally and excluded from Git because
they contain absolute machine paths.

Refresh from the repository root:

```powershell
$env:PYTHONPATH='ableton_agent/python'
python -m ableton_bridge.sound_catalog scan
```

If the system Python is unavailable, use the workspace interpreter:

```powershell
$env:PYTHONPATH='ableton_agent/python'
& '.\experiments\text2midi\.venv\Scripts\python.exe' -m ableton_bridge.sound_catalog scan
```

Search without rescanning:

```powershell
python -m ableton_bridge.sound_catalog search --pack "Lost and Found" --kind ableton_preset
python -m ableton_bridge.sound_catalog search --kind plugin
python -m ableton_bridge.sound_catalog search --official-tag "Genres|House"
python -m ableton_bridge.sound_catalog search --query "deep bass" --role bass
python -m ableton_bridge.sound_catalog search --bpm-min 124 --bpm-max 130 --loop
python -m ableton_bridge.sound_catalog search --root-note C2 --one-shot
python -m ableton_bridge.sound_catalog search --duration-max 0.25 --one-shot
python -m ableton_bridge.sound_catalog search --device OriginalSimpler --rack-type Instrument
```

When the SQLite database exists, `search` uses it automatically. Inspect the
database coverage with:

```powershell
python -m ableton_bridge.sound_catalog db-stats
```

Rebuild only the database from the current JSON compatibility export with:

```powershell
python -m ableton_bridge.sound_catalog build-db
```

- `exists` means the path was present during the latest scan.
- `manual_load` means load it through Live's Browser or plugin chooser.
- `control_after_load` means parameter inspection may be attempted after loading.
- `auto_insert: false` means discovery did not whitelist automatic insertion.
- `ableton_factory:*` tags come from Pack XMP metadata with confidence `1.0`.
- `--official-tag` matches a complete path exactly when the query contains `|`
  (`Key|D` does not match `Key|D♯`); a leaf query such as `Synth Bass` matches
  only an exact final path segment.
- `filename_inferred:*` tags come from filename/path regexes with confidence
  `0.55`; they are useful hints, not official Ableton classifications.
- Duration, sample rate, channels, bit depth, and encoding come from audio file
  headers. No waveform decoding is required for these fields.
- BPM, key, root note, and Loop/One-shot values are conservative filename/path
  inferences with per-field confidence and provenance. Missing evidence stays
  `NULL`; it is not guessed.
- `.adg` and `.adv` files are read as Ableton gzip/XML. The index stores Rack
  type, device chain, top-level macros, nested macro groups, FileRefs, preview
  paths where present, and resolved local resource links.

The default Factory Packs root follows the newest Ableton Live `Library.cfg`
`PreferredFactoryPacksInstallationPath`. User Library and plugin fallbacks stay
on the local C drive. Other external roots are excluded unless the user
explicitly supplies them.

After a refresh, compare the generated Pack count with Live's Browser and
spot-check newly installed Packs. An install still in progress can produce a
temporarily incomplete scan; rerun after the Pack finishes installing.

## Version 2 Scope

Implemented in the SQLite index:

- registered Pack IDs from the latest Live `Library.cfg`;
- Pack versions and official per-resource tags from supported Pack XMP files;
- stable resource IDs based on Pack identity and relative path;
- structured Pack/kind/role/official-tag filters and FTS5 text search;
- explicit provenance, confidence, method version, and observation time;
- audio header fields plus filename/path BPM, key, root-note, and loop inference;
- `.adg`/`.adv` device-chain, macro, FileRef, preview, and resource-link parsing;
- filters for BPM, key, root note, duration, Loop/One-shot, device, and Rack type;
- fingerprint/version caching that reuses unchanged audio and preset analysis;
- empty typed tables reserved for user feedback and embedding references.

Not yet implemented: waveform-derived loudness/timbre/transient/pitch analysis,
audio/text embeddings, feedback-writing commands, and creative ranking based on
listening evidence. A first full build can be slow because every preset is
decompressed and parsed; unchanged rebuilds use the incremental cache.

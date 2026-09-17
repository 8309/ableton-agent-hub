# Local Audio Similarity

Stage 5 adds bounded waveform evidence to the existing local SQLite catalog.
It does not modify Live, load samples, start playback, or download a model.

## Use

`ableton_search_sounds` accepts `reference_audio` (absolute existing file),
`candidate_limit` (24 by default, at most 64) and existing catalog filters.
The reference must be decodable. `limit` defaults to five results.
Without a reference, metadata search is unchanged.

CLI: `python -m ableton_bridge.sound_catalog search --reference-audio "C:/path/reference.wav" --role drums --candidate-limit 24 --limit 5`

Requires NumPy 2.2.6 and SoundFile 0.13.1 in the project environment.
Restart MCP after updating Python code; no Hub reload is needed.

## Evidence And Limits

- WAV, AIFF/AIFC and FLAC are attempted using available libsndfile. An extension
  is not proof of a supported encoding. Compressed Ableton Pack AIFC may return
  `decode_failed`; no invented features or score follows.
- Streaming blocks analyze at most the first 30 seconds with explicit coverage.
  Sample peak, RMS, power spectral centroid, flatness and heuristic transient
  density are not true peak, LUFS, pitch or semantic tags.
- Size/mtime, algorithm and decoder versions key a SQLite waveform cache.
  Unchanged files reuse it; catalog rebuilds preserve it. No full-library scan.
- Ranking uses fixed-scale distance over a bounded filtered candidate pool,
  not the whole library. Lower distance is closer, not better sounding.
  Results include feature reasons, actual paths and existence checks.
- Silent, missing, unsupported and timed-out candidates are explicitly unranked.
  Work budgets are 10 seconds per file and 25 seconds per search, checked between
  blocks; a blocking decoder call itself cannot be interrupted.
- Users load samples manually. Listening remains essential.

## Validation

PCM WAV/AIFF/FLAC tests cover known tones, antiphase stereo, nearest-frequency
ranking, 30-second coverage, missing/corrupt/silent files, cache reuse,
invalidation, rebuild preservation, MCP integration and bounds.
On 2026-09-17 the catalog had 21,336 AIF audio entries. The first 64 one-shot and
first 64 loop candidates had no decodable reference. This is a compatibility
limit, not successful ranking or listening acceptance. Creative one-shot/loop
listening acceptance and embeddings remain pending.

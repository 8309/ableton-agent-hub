# Arrangement Audio Clip Move Contract

`/arrangement_tools` action `move_audio_clip` repositions one existing
Arrangement audio clip on its current ordinary track.

## Target

The request must use stable Live IDs rather than mutable indices:

```json
{
  "action": "move_audio_clip",
  "track_id": 4,
  "clip_id": 1394,
  "target_start": 15.0
}
```

The dry-run resolves the current clip, rejects MIDI and Session clips, checks
that no unrelated Arrangement clip overlaps the destination, and returns a
`plan_token`. Commit must repeat the same stable IDs, destination, and token.

## Commit Strategy

Live exposes `Track.duplicate_clip_to_arrangement`, but Arrangement Clip
`start_time` is read-only. To support moves whose source and destination ranges
overlap, commit:

1. duplicates the source to a temporary empty position on the same track;
2. verifies a bounded audio-clip fingerprint;
3. deletes the source;
4. duplicates the temporary clip to the requested beat;
5. verifies position and fingerprint readback;
6. deletes the temporary clip.

If the destination copy fails after source deletion, the Hub attempts to restore
the clip at its original beat from the temporary copy. If restoration also
fails, the error reports the retained temporary clip ID and beat.

The fingerprint covers the sample path, name, length, markers, loop state,
gain, transpose/detune, Warp state/mode, RAM mode, mute, color, and whether clip
envelopes exist. It does not claim to serialize or compare every envelope point
or Warp Marker; preservation relies on Live's native duplicate operation.

## Scope

- One existing Arrangement audio clip per request.
- Same ordinary track only.
- No replacement of unrelated destination clips.
- Dry-run by default; commit requires the current `plan_token`.
- The resulting clip receives a new stable Live clip ID because the public LOM
  does not expose a writable Arrangement position property.

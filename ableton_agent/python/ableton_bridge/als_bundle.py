"""Compose the legacy ALS readers into one bounded saved-set read.

This module is deliberately local-only. It combines the saved XML readers for
one request, while the Hub remains the source of current Live state and every
Live write path.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any, Iterable

from .als_midi import (
    DEFAULT_MAX_NOTES_PER_CLIP,
    DEFAULT_MAX_OCCURRENCES_PER_CLIP,
    read_als_midi,
)
from .als_project import (
    ALL_SECTIONS as PROJECT_SECTIONS,
    DEFAULT_MAX_AUDIO_CLIPS,
    DEFAULT_MAX_AUTOMATION_EVENTS,
    DEFAULT_MAX_DEVICES,
    DEFAULT_MAX_PARAMETERS_PER_DEVICE,
    DEFAULT_MAX_WARP_MARKERS_PER_CLIP,
    read_als_project,
)
from .als_snapshot import (
    DEFAULT_MAX_FILE_REFERENCES,
    DEFAULT_MAX_UNCOMPRESSED_BYTES,
    AlsSnapshotError,
    read_als_snapshot,
)


MIDI_SECTION = "midi"
ALL_SECTIONS = set(PROJECT_SECTIONS) | {MIDI_SECTION}
DEFAULT_SECTIONS = tuple(sorted(ALL_SECTIONS))


class AlsBundleError(RuntimeError):
    """Raised when a combined saved-set request is invalid."""


def _unique_warnings(*groups: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    for group in groups:
        for warning in group:
            if warning not in result:
                result.append(warning)
    return result


def _format_summary(
    snapshot: dict[str, Any],
    project: dict[str, Any] | None,
    midi: dict[str, Any] | None,
) -> dict[str, Any]:
    counts = snapshot.get("track_counts", {})
    scenes = (project or {}).get("scenes", {})
    audio = (project or {}).get("audio_clips", {})
    automation = (project or {}).get("automation", {})
    grooves = (project or {}).get("grooves", {})
    main = snapshot.get("main_track", {})
    tempo = main.get("tempo", {}) if isinstance(main, dict) else {}
    midi_read = (midi or {}).get("read", {})
    midi_clips = (midi or {}).get("clips", [])
    midi_note_count = sum(
        int(item.get("returned_note_count", 0))
        for item in midi_clips
        if isinstance(item, dict)
    )
    return {
        "ordinary_track_count": counts.get("ordinary", 0),
        "group_track_count": counts.get("GroupTrack", 0),
        "midi_track_count": counts.get("MidiTrack", 0),
        "audio_track_count": counts.get("AudioTrack", 0),
        "return_track_count": counts.get("ReturnTrack", 0),
        "track_count": counts.get("total", 0),
        "locator_count": snapshot.get("locator_count", len(snapshot.get("locators", []))),
        "file_reference_count": snapshot.get("file_references", {}).get(
            "unique_nonempty_count", 0
        ),
        "scene_count": scenes.get("count", len(scenes)) if isinstance(scenes, dict) else len(scenes),
        "audio_clip_count": audio.get("count", 0),
        "midi_clip_count": midi_read.get("matched_clip_count", len(midi_clips)),
        "returned_midi_clip_count": len(midi_clips),
        "returned_midi_note_count": midi_note_count,
        "automation_envelope_count": automation.get("envelope_count", 0),
        "tempo_automation_envelope_count": len(automation.get("tempo_envelopes", [])),
        "groove_count": grooves.get("count", 0),
        "saved_manual_bpm": tempo.get("manual_bpm"),
        "main_track_present": bool(main.get("present")) if isinstance(main, dict) else False,
    }


def read_saved_set(
    path: str | Path,
    *,
    sections: set[str] | None = None,
    include_device_parameters: bool = False,
    include_midi_notes: bool = False,
    midi_track_name: str | None = None,
    midi_clip_name: str | None = None,
    midi_clip_source: str = "all",
    midi_cursor: int = 0,
    midi_limit: int = 64,
    midi_start_beat: float | None = None,
    midi_end_beat: float | None = None,
    max_parameters_per_device: int = DEFAULT_MAX_PARAMETERS_PER_DEVICE,
    max_automation_events: int = DEFAULT_MAX_AUTOMATION_EVENTS,
    max_audio_clips: int = DEFAULT_MAX_AUDIO_CLIPS,
    max_warp_markers_per_clip: int = DEFAULT_MAX_WARP_MARKERS_PER_CLIP,
    max_devices: int = DEFAULT_MAX_DEVICES,
    max_notes_per_clip: int = DEFAULT_MAX_NOTES_PER_CLIP,
    max_occurrences_per_clip: int = DEFAULT_MAX_OCCURRENCES_PER_CLIP,
    max_file_references: int = DEFAULT_MAX_FILE_REFERENCES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> dict[str, Any]:
    """Read the saved ALS sources once and return a unified read-only envelope.

    The `midi` section is a bounded page. Its `read.has_more` and cursor fields
    remain authoritative; callers can request the next MIDI page with the same
    file token. Other sections are bounded by their section-specific limits.
    """
    selected = set(ALL_SECTIONS if sections is None else sections)
    source_path = Path(path).expanduser()
    if not source_path.is_absolute() or source_path.suffix.casefold() != ".als":
        raise AlsBundleError("als_path must be an explicit absolute .als path")
    unknown = selected - ALL_SECTIONS
    if unknown:
        raise AlsBundleError(f"Unknown saved-set sections: {', '.join(sorted(unknown))}")
    if not selected:
        raise AlsBundleError("At least one saved-set section is required")
    if midi_clip_source not in {"arrangement", "session", "all"}:
        raise AlsBundleError("midi_clip_source must be arrangement, session, or all")
    if midi_cursor < 0 or midi_limit < 1 or midi_limit > 64:
        raise AlsBundleError("midi_cursor must be non-negative and midi_limit must be 1..64")

    started = time.perf_counter()
    try:
        snapshot = read_als_snapshot(
            path,
            max_uncompressed_bytes=max_uncompressed_bytes,
            max_file_references=max_file_references,
        )
    except AlsSnapshotError as error:
        raise AlsBundleError(str(error)) from error

    result: dict[str, Any] = {
        "ok": True,
        "read_only": True,
        "source": dict(snapshot["source"]),
        "format": dict(snapshot["format"]),
        "sections": sorted(selected),
        "snapshot": snapshot,
        # These base fields preserve the old snapshot's easy-to-consume shape.
        "tracks": snapshot.get("tracks", []),
        "track_counts": snapshot.get("track_counts", {}),
        "main_track": snapshot.get("main_track"),
        "locators": snapshot.get("locators", []),
        "file_references": snapshot.get("file_references", {}),
        "timing_ms": {"snapshot": snapshot.get("elapsed_ms")},
    }
    warnings = list(snapshot.get("warnings", []))

    project: dict[str, Any] | None = None
    project_sections = selected & PROJECT_SECTIONS
    if project_sections:
        project_started = time.perf_counter()
        project = read_als_project(
            path,
            sections=project_sections,
            include_device_parameters=include_device_parameters,
            max_parameters_per_device=max_parameters_per_device,
            max_automation_events=max_automation_events,
            max_audio_clips=max_audio_clips,
            max_warp_markers_per_clip=max_warp_markers_per_clip,
            max_devices=max_devices,
            max_uncompressed_bytes=max_uncompressed_bytes,
        )
        for key in project_sections:
            if key in project:
                result[key] = project[key]
        if "tracks" in project_sections:
            result["tracks"] = project.get("tracks", result["tracks"])
            result["main_track"] = project.get("main_track", result["main_track"])
        warnings = _unique_warnings(warnings, project.get("warnings", []))
        result["timing_ms"]["project"] = round(
            (time.perf_counter() - project_started) * 1000.0, 3
        )

    if MIDI_SECTION in selected:
        midi_started = time.perf_counter()
        midi = read_als_midi(
            path,
            track_name=midi_track_name,
            clip_name=midi_clip_name,
            clip_source=midi_clip_source,
            start_beat=midi_start_beat,
            end_beat=midi_end_beat,
            cursor=midi_cursor,
            limit=midi_limit,
            include_notes=include_midi_notes,
            max_notes_per_clip=max_notes_per_clip,
            max_occurrences_per_clip=max_occurrences_per_clip,
            max_uncompressed_bytes=max_uncompressed_bytes,
        )
        result["midi"] = midi
        warnings = _unique_warnings(warnings, midi.get("warnings", []))
        result["timing_ms"]["midi"] = round(
            (time.perf_counter() - midi_started) * 1000.0, 3
        )

    result["summary"] = _format_summary(snapshot, project, result.get("midi"))
    result["warnings"] = warnings
    result["timing_ms"]["total"] = round((time.perf_counter() - started) * 1000.0, 3)
    result["cache"] = {
        "shared_document": True,
        "snapshot_cache_hit": bool(snapshot.get("source", {}).get("cache_hit")),
        "message": "Snapshot, project and MIDI readers share one cached parsed ALS document.",
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read a saved Ableton .als file through the combined read-only backend"
    )
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--sections",
        default=",".join(DEFAULT_SECTIONS),
        help="Comma-separated: tracks,scenes,audio_clips,automation,grooves,midi",
    )
    parser.add_argument("--include-device-parameters", action="store_true")
    parser.add_argument("--include-midi-notes", action="store_true")
    parser.add_argument("--midi-track-name")
    parser.add_argument("--midi-clip-name")
    parser.add_argument("--midi-clip-source", choices=("arrangement", "session", "all"), default="all")
    parser.add_argument("--midi-cursor", type=int, default=0)
    parser.add_argument("--midi-limit", type=int, default=64)
    parser.add_argument("--midi-start-beat", type=float)
    parser.add_argument("--midi-end-beat", type=float)
    parser.add_argument("--max-uncompressed-mb", type=int, default=128)
    args = parser.parse_args()
    try:
        result = read_saved_set(
            args.path,
            sections={item.strip() for item in args.sections.split(",") if item.strip()},
            include_device_parameters=args.include_device_parameters,
            include_midi_notes=args.include_midi_notes,
            midi_track_name=args.midi_track_name,
            midi_clip_name=args.midi_clip_name,
            midi_clip_source=args.midi_clip_source,
            midi_cursor=args.midi_cursor,
            midi_limit=args.midi_limit,
            midi_start_beat=args.midi_start_beat,
            midi_end_beat=args.midi_end_beat,
            max_uncompressed_bytes=args.max_uncompressed_mb * 1024 * 1024,
        )
    except (AlsBundleError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

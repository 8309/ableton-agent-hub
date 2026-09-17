from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from .als_loader import AlsDocumentError, load_als_document
from .als_snapshot import (
    DEFAULT_MAX_UNCOMPRESSED_BYTES,
    AlsSnapshotError,
    _float_value,
    _int_value,
    _track_name,
    _value,
)


DEFAULT_CLIP_LIMIT = 16
MAX_CLIP_LIMIT = 64
DEFAULT_MAX_NOTES_PER_CLIP = 4096
MAX_NOTES_PER_CLIP = 16384
DEFAULT_MAX_OCCURRENCES_PER_CLIP = 16384
MAX_OCCURRENCES_PER_CLIP = 65536


class AlsMidiError(RuntimeError):
    pass


def _bool_value(value: str, default: bool = False) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    return default


def _required_float(element: ET.Element, path: str, label: str) -> float:
    value = _float_value(_value(element, path))
    if value is None or not math.isfinite(value):
        raise AlsMidiError(f"MIDI clip has no valid {label}")
    return value


def _load_live_set(
    path: str | Path,
    max_uncompressed_bytes: int,
) -> tuple[Path, bytes, bytes, ET.Element, ET.Element, dict[str, Any], list[str]]:
    try:
        document = load_als_document(
            path, max_uncompressed_bytes=max_uncompressed_bytes
        )
    except AlsDocumentError as error:
        raise AlsMidiError(str(error)) from error
    return (
        document.path,
        document.raw,
        document.xml,
        document.root,
        document.live_set,
        {**document.source_info, "cache_hit": document.cache_hit},
        document.warnings,
    )


def _occurrence_positions(
    note_time: float,
    *,
    arrangement_start: float,
    arrangement_end: float,
    loop_start: float,
    loop_end: float,
    start_relative: float,
    loop_on: bool,
    maximum: int,
) -> tuple[int, list[float], bool]:
    epsilon = 1e-9
    base = arrangement_start + note_time - start_relative
    if not loop_on:
        count = 1 if arrangement_start - epsilon <= base < arrangement_end - epsilon else 0
        return count, [base] if count and maximum > 0 else [], count > maximum

    loop_length = loop_end - loop_start
    if loop_length <= 0:
        return 0, [], False
    first_cycle = math.ceil((arrangement_start - base - epsilon) / loop_length)
    last_cycle = math.floor((arrangement_end - base - epsilon) / loop_length)
    if last_cycle < first_cycle:
        return 0, [], False
    count = last_cycle - first_cycle + 1
    returned = min(count, maximum)
    positions = [base + (first_cycle + index) * loop_length for index in range(returned)]
    return count, positions, returned < count


def _read_clip_notes(
    clip: ET.Element,
    *,
    arrangement_start: float,
    arrangement_end: float,
    loop: dict[str, Any],
    max_notes: int,
    max_occurrences: int,
) -> dict[str, Any]:
    notes: list[dict[str, Any]] = []
    for key_track in clip.findall("./Notes/KeyTracks/KeyTrack"):
        pitch = _int_value(_value(key_track, "MidiKey"))
        if pitch is None or not 0 <= pitch <= 127:
            continue
        for event in key_track.findall("./Notes/MidiNoteEvent"):
            start_time = _float_value(event.attrib.get("Time", ""))
            duration = _float_value(event.attrib.get("Duration", ""))
            velocity = _float_value(event.attrib.get("Velocity", ""))
            off_velocity = _float_value(event.attrib.get("OffVelocity", ""))
            if None in {start_time, duration, velocity, off_velocity}:
                continue
            enabled = _bool_value(event.attrib.get("IsEnabled", "true"), True)
            notes.append(
                {
                    "pitch": pitch,
                    "start_time": start_time,
                    "duration": duration,
                    "velocity": velocity,
                    "off_velocity": off_velocity,
                    "enabled": enabled,
                    "mute": 0 if enabled else 1,
                    "note_id": _int_value(event.attrib.get("NoteId", "")),
                    "probability": _float_value(event.attrib.get("Probability", "")),
                    "velocity_deviation": _float_value(
                        event.attrib.get("VelocityDeviation", "")
                    ),
                    "probability_group_id": _int_value(
                        event.attrib.get("ProbabilityGroupId", "")
                    ),
                }
            )
    notes.sort(key=lambda item: (item["start_time"], item["pitch"], item["note_id"] or -1))

    returned_notes = notes[:max_notes]
    remaining_occurrences = max_occurrences
    occurrence_total = 0
    occurrence_partial = False
    for note in returned_notes:
        count, positions, partial = _occurrence_positions(
            note["start_time"],
            arrangement_start=arrangement_start,
            arrangement_end=arrangement_end,
            loop_start=loop["loop_start"],
            loop_end=loop["loop_end"],
            start_relative=loop["start_relative"],
            loop_on=loop["loop_on"],
            maximum=max(0, remaining_occurrences),
        )
        note["arrangement_occurrence_count"] = count
        note["arrangement_occurrences"] = positions
        occurrence_total += count
        remaining_occurrences -= len(positions)
        occurrence_partial = occurrence_partial or partial

    probability_groups = []
    probability_node = clip.find("./Notes/NoteProbabilityGroups")
    if probability_node is not None:
        for group in list(probability_node)[:max_notes]:
            probability_groups.append(
                {
                    "tag": group.tag,
                    "attributes": dict(group.attrib),
                    "values": {
                        child.tag: child.attrib.get("Value")
                        for child in list(group)
                        if "Value" in child.attrib
                    },
                }
            )

    per_note_events = []
    event_lists = clip.find("./Notes/PerNoteEventStore/EventLists")
    if event_lists is not None:
        for event_list in list(event_lists)[:max_notes]:
            per_note_events.append(
                {
                    "tag": event_list.tag,
                    "attributes": dict(event_list.attrib),
                    "events": [
                        {"tag": event.tag, "attributes": dict(event.attrib)}
                        for event in list(event_list)[:max_notes]
                    ],
                    "events_has_more": len(event_list) > max_notes,
                }
            )

    return {
        "stored_note_count": len(notes),
        "returned_note_count": len(returned_notes),
        "notes_has_more": len(returned_notes) < len(notes),
        "arrangement_occurrence_count": occurrence_total,
        "occurrences_partial": occurrence_partial,
        "probability_groups": probability_groups,
        "per_note_event_lists": per_note_events,
        "notes": returned_notes,
    }


def _read_follow_action(clip: ET.Element) -> dict[str, Any]:
    node = clip.find("FollowAction")
    return {
        "enabled": _bool_value(_value(node, "FollowActionEnabled")),
        "follow_time": _float_value(_value(node, "FollowTime")),
        "linked": _bool_value(_value(node, "IsLinked")),
        "loop_iterations": _int_value(_value(node, "LoopIterations")),
        "action_a": _int_value(_value(node, "FollowActionA")),
        "action_b": _int_value(_value(node, "FollowActionB")),
        "chance_a": _float_value(_value(node, "FollowChanceA")),
        "chance_b": _float_value(_value(node, "FollowChanceB")),
        "jump_index_a": _int_value(_value(node, "JumpIndexA")),
        "jump_index_b": _int_value(_value(node, "JumpIndexB")),
    }


def _read_clip_envelopes(clip: ET.Element, maximum: int = 256) -> dict[str, Any]:
    container = clip.find("./Envelopes/Envelopes")
    envelopes = []
    if container is not None:
        for envelope in list(container)[:maximum]:
            events_node = envelope.find("./Automation/Events")
            events = list(events_node) if events_node is not None else []
            envelopes.append(
                {
                    "tag": envelope.tag,
                    "file_id": _int_value(envelope.attrib.get("Id", "")),
                    "target_id": _int_value(
                        _value(envelope, "EnvelopeTarget/PointeeId")
                    ),
                    "event_count": len(events),
                    "events": [
                        {"type": event.tag, "attributes": dict(event.attrib)}
                        for event in events[:maximum]
                    ],
                    "events_has_more": len(events) > maximum,
                }
            )
    return {
        "count": len(container) if container is not None else 0,
        "returned_count": len(envelopes),
        "has_more": container is not None and len(container) > maximum,
        "items": envelopes,
    }


def _clip_metadata(clip: ET.Element) -> dict[str, Any]:
    return {
        "annotation": _value(clip, "Annotation"),
        "launch_mode": _int_value(_value(clip, "LaunchMode")),
        "launch_quantisation": _int_value(_value(clip, "LaunchQuantisation")),
        "legato": _bool_value(_value(clip, "Legato")),
        "disabled": _bool_value(_value(clip, "Disabled")),
        "velocity_amount": _float_value(_value(clip, "VelocityAmount")),
        "groove_id": _int_value(_value(clip, "GrooveSettings/GrooveId")),
        "follow_action": _read_follow_action(clip),
        "clip_envelopes": _read_clip_envelopes(clip),
    }


def _read_arrangement_clip(
    track: ET.Element,
    track_order: int,
    clip: ET.Element,
    *,
    include_notes: bool,
    max_notes_per_clip: int,
    max_occurrences_per_clip: int,
) -> dict[str, Any]:
    track_name, _, _ = _track_name(track)
    arrangement_start = _required_float(clip, "CurrentStart", "CurrentStart")
    arrangement_end = _required_float(clip, "CurrentEnd", "CurrentEnd")
    loop_node = clip.find("Loop")
    loop = {
        "loop_start": _float_value(_value(loop_node, "LoopStart"), 0.0),
        "loop_end": _float_value(
            _value(loop_node, "LoopEnd"), arrangement_end - arrangement_start
        ),
        "start_relative": _float_value(_value(loop_node, "StartRelative"), 0.0),
        "loop_on": _bool_value(_value(loop_node, "LoopOn"), False),
    }
    result: dict[str, Any] = {
        "source": "arrangement",
        "track_order": track_order,
        "track_file_id": _int_value(track.attrib.get("Id", "")),
        "track_name": track_name,
        "clip_file_id": _int_value(clip.attrib.get("Id", "")),
        "clip_lom_id": _int_value(_value(clip, "LomId")),
        "clip_name": _value(clip, "Name"),
        "color": _int_value(_value(clip, "Color")),
        "arrangement_start": arrangement_start,
        "arrangement_end": arrangement_end,
        "arrangement_length": max(0.0, arrangement_end - arrangement_start),
        "loop": loop,
        **_clip_metadata(clip),
    }
    if include_notes:
        result.update(
            _read_clip_notes(
                clip,
                arrangement_start=arrangement_start,
                arrangement_end=arrangement_end,
                loop=loop,
                max_notes=max_notes_per_clip,
                max_occurrences=max_occurrences_per_clip,
            )
        )
    return result


def _read_session_clip(
    track: ET.Element,
    track_order: int,
    slot: ET.Element,
    clip: ET.Element,
    *,
    include_notes: bool,
    max_notes_per_clip: int,
) -> dict[str, Any]:
    track_name, _, _ = _track_name(track)
    current_start = _float_value(_value(clip, "CurrentStart"), 0.0) or 0.0
    current_end = _float_value(_value(clip, "CurrentEnd"), current_start)
    if current_end is None:
        current_end = current_start
    loop_node = clip.find("Loop")
    loop = {
        "loop_start": _float_value(_value(loop_node, "LoopStart"), 0.0),
        "loop_end": _float_value(_value(loop_node, "LoopEnd"), current_end),
        "start_relative": _float_value(_value(loop_node, "StartRelative"), 0.0),
        "loop_on": _bool_value(_value(loop_node, "LoopOn"), False),
    }
    result: dict[str, Any] = {
        "source": "session",
        "track_order": track_order,
        "track_file_id": _int_value(track.attrib.get("Id", "")),
        "track_name": track_name,
        "scene_index": _int_value(slot.attrib.get("Id", "")),
        "slot_lom_id": _int_value(_value(slot, "LomId")),
        "has_stop": _bool_value(_value(slot, "HasStop"), True),
        "clip_file_id": _int_value(clip.attrib.get("Id", "")),
        "clip_lom_id": _int_value(_value(clip, "LomId")),
        "clip_name": _value(clip, "Name"),
        "color": _int_value(_value(clip, "Color")),
        "clip_start": current_start,
        "clip_end": current_end,
        "clip_length": max(0.0, current_end - current_start),
        "loop": loop,
        **_clip_metadata(clip),
    }
    if include_notes:
        result.update(
            _read_clip_notes(
                clip,
                arrangement_start=current_start,
                arrangement_end=current_end,
                loop=loop,
                max_notes=max_notes_per_clip,
                max_occurrences=0,
            )
        )
        for note in result["notes"]:
            note.pop("arrangement_occurrence_count", None)
            note.pop("arrangement_occurrences", None)
        result.pop("arrangement_occurrence_count", None)
        result.pop("occurrences_partial", None)
    return result


def read_als_midi(
    path: str | Path,
    *,
    track_name: str | None = None,
    clip_name: str | None = None,
    clip_source: str = "arrangement",
    start_beat: float | None = None,
    end_beat: float | None = None,
    cursor: int = 0,
    limit: int = DEFAULT_CLIP_LIMIT,
    include_notes: bool = True,
    max_notes_per_clip: int = DEFAULT_MAX_NOTES_PER_CLIP,
    max_occurrences_per_clip: int = DEFAULT_MAX_OCCURRENCES_PER_CLIP,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> dict[str, Any]:
    if clip_source not in {"arrangement", "session", "all"}:
        raise AlsMidiError("clip_source must be arrangement, session, or all")
    if cursor < 0:
        raise AlsMidiError("cursor must be non-negative")
    if limit < 1 or limit > MAX_CLIP_LIMIT:
        raise AlsMidiError(f"limit must be 1..{MAX_CLIP_LIMIT}")
    if max_notes_per_clip < 1 or max_notes_per_clip > MAX_NOTES_PER_CLIP:
        raise AlsMidiError(f"max_notes_per_clip must be 1..{MAX_NOTES_PER_CLIP}")
    if max_occurrences_per_clip < 1 or max_occurrences_per_clip > MAX_OCCURRENCES_PER_CLIP:
        raise AlsMidiError(
            f"max_occurrences_per_clip must be 1..{MAX_OCCURRENCES_PER_CLIP}"
        )
    if start_beat is not None and end_beat is not None and end_beat <= start_beat:
        raise AlsMidiError("end_beat must be greater than start_beat")

    _, _, _, root, live_set, source_info, warnings = _load_live_set(
        path, max_uncompressed_bytes
    )
    tracks_node = live_set.find("Tracks")
    clips: list[dict[str, Any]] = []
    track_filter = track_name.casefold() if track_name else None
    clip_filter = clip_name.casefold() if clip_name else None

    if tracks_node is not None:
        for track_order, track in enumerate(list(tracks_node)):
            if track.tag != "MidiTrack":
                continue
            resolved_track_name, _, _ = _track_name(track)
            if track_filter is not None and resolved_track_name.casefold() != track_filter:
                continue
            clip_nodes = (
                track.findall(
                    "./DeviceChain/MainSequencer/ClipTimeable/ArrangerAutomation/Events/MidiClip"
                )
                if clip_source in {"arrangement", "all"}
                else []
            )
            for clip in clip_nodes:
                name = _value(clip, "Name")
                if clip_filter is not None and clip_filter not in name.casefold():
                    continue
                arrangement_start = _float_value(_value(clip, "CurrentStart"))
                arrangement_end = _float_value(_value(clip, "CurrentEnd"))
                if arrangement_start is None or arrangement_end is None:
                    continue
                if start_beat is not None and arrangement_end <= start_beat:
                    continue
                if end_beat is not None and arrangement_start >= end_beat:
                    continue
                clips.append(
                    _read_arrangement_clip(
                        track,
                        track_order,
                        clip,
                        include_notes=include_notes,
                        max_notes_per_clip=max_notes_per_clip,
                        max_occurrences_per_clip=max_occurrences_per_clip,
                    )
                )

            if clip_source in {"session", "all"}:
                for slot in track.findall(
                    "./DeviceChain/MainSequencer/ClipSlotList/ClipSlot"
                ):
                    clip = slot.find("./ClipSlot/Value/MidiClip")
                    if clip is None:
                        continue
                    name = _value(clip, "Name")
                    if clip_filter is not None and clip_filter not in name.casefold():
                        continue
                    clips.append(
                        _read_session_clip(
                            track,
                            track_order,
                            slot,
                            clip,
                            include_notes=include_notes,
                            max_notes_per_clip=max_notes_per_clip,
                        )
                    )

    clips.sort(
        key=lambda item: (
            item["track_order"],
            0 if item["source"] == "arrangement" else 1,
            item.get("arrangement_start", item.get("scene_index", 0)),
            item.get("arrangement_end", item.get("scene_index", 0)),
            item["clip_name"],
        )
    )
    returned = clips[cursor : cursor + limit]
    next_cursor = cursor + len(returned)
    return {
        "ok": True,
        "read_only": True,
        "source": source_info,
        "format": {
            "container": "gzip",
            "document": "xml",
            "root": root.tag,
            "major_version": root.attrib.get("MajorVersion", ""),
            "minor_version": root.attrib.get("MinorVersion", ""),
            "creator": root.attrib.get("Creator", ""),
            "revision": root.attrib.get("Revision", ""),
        },
        "scope": {
            "clip_source": clip_source,
            "session_clips": "implemented for saved Live 12.4 ClipSlotList schema",
            "per_note_expression": "returned as bounded raw event lists when present; semantic lane mapping is not validated",
            "groove_pool_clips": "excluded",
        },
        "filters": {
            "track_name": track_name,
            "clip_name_contains": clip_name,
            "clip_source": clip_source,
            "start_beat": start_beat,
            "end_beat": end_beat,
        },
        "read": {
            "cursor": cursor,
            "next_cursor": next_cursor,
            "limit": limit,
            "matched_clip_count": len(clips),
            "returned_clip_count": len(returned),
            "has_more": next_cursor < len(clips),
            "include_notes": include_notes,
            "max_notes_per_clip": max_notes_per_clip,
            "max_occurrences_per_clip": max_occurrences_per_clip,
        },
        "clips": returned,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read bounded Arrangement MIDI clips and notes from a saved ALS file"
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--track-name")
    parser.add_argument("--clip-name", help="Case-insensitive clip-name substring")
    parser.add_argument(
        "--clip-source",
        choices=("arrangement", "session", "all"),
        default="arrangement",
    )
    parser.add_argument("--start-beat", type=float)
    parser.add_argument("--end-beat", type=float)
    parser.add_argument("--cursor", type=int, default=0)
    parser.add_argument("--limit", type=int, default=DEFAULT_CLIP_LIMIT)
    parser.add_argument("--no-notes", action="store_true")
    parser.add_argument("--max-notes-per-clip", type=int, default=DEFAULT_MAX_NOTES_PER_CLIP)
    parser.add_argument(
        "--max-occurrences-per-clip", type=int, default=DEFAULT_MAX_OCCURRENCES_PER_CLIP
    )
    parser.add_argument("--max-uncompressed-mb", type=int, default=128)
    args = parser.parse_args()
    try:
        result = read_als_midi(
            args.path,
            track_name=args.track_name,
            clip_name=args.clip_name,
            clip_source=args.clip_source,
            start_beat=args.start_beat,
            end_beat=args.end_beat,
            cursor=args.cursor,
            limit=args.limit,
            include_notes=not args.no_notes,
            max_notes_per_clip=args.max_notes_per_clip,
            max_occurrences_per_clip=args.max_occurrences_per_clip,
            max_uncompressed_bytes=args.max_uncompressed_mb * 1024 * 1024,
        )
    except (AlsMidiError, AlsSnapshotError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

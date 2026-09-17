from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Callable

from .als_midi import AlsMidiError, read_als_midi
from .clip_note_tools import clip_note_tools


DEFAULT_CANDIDATE_LIMIT = 128
MAX_HUB_NOTE_LIMIT = 256


class AlsMidiVerificationError(RuntimeError):
    pass


def _scan_hub_clips(track_name: str, candidate_limit: int, timeout: float) -> dict[str, Any]:
    return clip_note_tools(
        "scan_clips",
        target="arrangement",
        track=track_name,
        candidate_limit=candidate_limit,
        timeout=timeout,
    )


def _read_hub_notes(
    track_name: str,
    candidate_index: int,
    candidate_limit: int,
    note_limit: int,
    timeout: float,
) -> dict[str, Any]:
    return clip_note_tools(
        "read_notes",
        target="arrangement",
        track=track_name,
        candidate_index=candidate_index,
        candidate_limit=candidate_limit,
        limit=note_limit,
        timeout=timeout,
    )


def _numbers_match(left: Any, right: Any, tolerance: float = 0.000001) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance)
    return left == right


def compare_als_clip_to_hub(
    als_clip: dict[str, Any],
    hub_reply: dict[str, Any],
    *,
    maximum_differences: int = 20,
) -> dict[str, Any]:
    if hub_reply.get("ok") is not True:
        raise AlsMidiVerificationError(f"Hub note read failed: {hub_reply!r}")
    hub_notes = hub_reply.get("notes")
    if not isinstance(hub_notes, list):
        raise AlsMidiVerificationError("Hub note reply did not contain notes")

    als_notes = list(als_clip.get("notes", []))
    fields = ["pitch", "start_time", "duration", "velocity", "mute"]
    differences: list[dict[str, Any]] = []
    for index in range(max(len(als_notes), len(hub_notes))):
        als_note = als_notes[index] if index < len(als_notes) else None
        hub_note = hub_notes[index] if index < len(hub_notes) else None
        changed_fields: list[str] = []
        if als_note is None or hub_note is None:
            changed_fields.append("missing")
        else:
            for field in fields:
                als_value = als_note.get(field)
                if field in {"pitch", "velocity"} and isinstance(als_value, (int, float)):
                    als_value = round(float(als_value))
                if not _numbers_match(als_value, hub_note.get(field)):
                    changed_fields.append(field)
        if changed_fields and len(differences) < maximum_differences:
            differences.append(
                {
                    "index": index,
                    "fields": changed_fields,
                    "als": als_note,
                    "hub": hub_note,
                }
            )

    als_count = int(als_clip.get("stored_note_count", len(als_notes)))
    hub_count = int(hub_reply.get("note_count", len(hub_notes)))
    truncated = als_clip.get("notes_has_more") is True or int(
        hub_reply.get("selected_count", len(hub_notes))
    ) < hub_count
    if differences or als_count != hub_count:
        status = "mismatch"
    elif truncated:
        status = "partial"
    else:
        status = "verified"
    return {
        "status": status,
        "compared_fields": fields,
        "unsupported_fields": ["off_velocity", "note_id", "per_note_expression"],
        "als_note_count": als_count,
        "hub_note_count": hub_count,
        "compared_note_count": min(len(als_notes), len(hub_notes)),
        "difference_count": len(differences),
        "differences": differences,
        "truncated": truncated,
    }


def verify_als_midi_clip_against_hub(
    path: str | Path,
    *,
    track_name: str,
    clip_name: str,
    arrangement_start: float | None = None,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    note_limit: int = MAX_HUB_NOTE_LIMIT,
    timeout: float = 8.0,
    hub_scan_reader: Callable[[str, int, float], dict[str, Any]] = _scan_hub_clips,
    hub_note_reader: Callable[[str, int, int, int, float], dict[str, Any]] = _read_hub_notes,
) -> dict[str, Any]:
    if not track_name.strip() or not clip_name.strip():
        raise AlsMidiVerificationError("track_name and clip_name are required")
    if candidate_limit < 1 or candidate_limit > 256:
        raise AlsMidiVerificationError("candidate_limit must be 1..256")
    if note_limit < 1 or note_limit > MAX_HUB_NOTE_LIMIT:
        raise AlsMidiVerificationError(f"note_limit must be 1..{MAX_HUB_NOTE_LIMIT}")

    als_result = read_als_midi(
        path,
        track_name=track_name,
        clip_name=clip_name,
        limit=64,
        max_notes_per_clip=note_limit,
    )
    als_candidates = [
        clip
        for clip in als_result["clips"]
        if clip["clip_name"].casefold() == clip_name.casefold()
        and (
            arrangement_start is None
            or _numbers_match(clip["arrangement_start"], arrangement_start)
        )
    ]
    if len(als_candidates) != 1:
        raise AlsMidiVerificationError(
            f"ALS target must resolve to exactly one clip; resolved {len(als_candidates)}"
        )
    als_clip = als_candidates[0]

    scan_reply = hub_scan_reader(track_name, candidate_limit, timeout)
    if scan_reply.get("ok") is not True or not isinstance(scan_reply.get("candidates"), list):
        raise AlsMidiVerificationError(f"Hub clip scan failed: {scan_reply!r}")
    hub_candidates = [
        candidate
        for candidate in scan_reply["candidates"]
        if str(candidate.get("source", "")) == "arrangement"
        and str(candidate.get("track_name", "")).casefold() == track_name.casefold()
        and str(candidate.get("clip_name", "")).casefold() == clip_name.casefold()
        and _numbers_match(
            candidate.get("start_time"),
            als_clip["arrangement_start"] if arrangement_start is None else arrangement_start,
        )
    ]
    if len(hub_candidates) != 1:
        raise AlsMidiVerificationError(
            f"Hub target must resolve to exactly one clip; resolved {len(hub_candidates)}"
        )
    hub_candidate = hub_candidates[0]
    candidate_index = hub_candidate.get("candidate_index")
    if not isinstance(candidate_index, int):
        raise AlsMidiVerificationError("Hub candidate did not contain an integer candidate_index")

    note_reply = hub_note_reader(
        track_name, candidate_index, candidate_limit, note_limit, timeout
    )
    comparison = compare_als_clip_to_hub(als_clip, note_reply)
    return {
        "ok": comparison["status"] == "verified",
        "read_only": True,
        "overall_status": comparison["status"],
        "source": als_result["source"],
        "target": {
            "track_name": als_clip["track_name"],
            "clip_name": als_clip["clip_name"],
            "arrangement_start": als_clip["arrangement_start"],
            "arrangement_end": als_clip["arrangement_end"],
            "hub_candidate_index": candidate_index,
            "hub_clip_id": hub_candidate.get("clip_id"),
        },
        "comparison": comparison,
        "freshness": {
            "status": "unknown",
            "message": (
                "An exact note match verifies this saved clip only. Other unsaved Live clips "
                "or edits remain outside the verified scope."
            ),
        },
        "warnings": als_result.get("warnings", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare one saved ALS Arrangement MIDI clip with current Hub notes"
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--track-name", required=True)
    parser.add_argument("--clip-name", required=True)
    parser.add_argument("--arrangement-start", type=float)
    parser.add_argument("--candidate-limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
    parser.add_argument("--note-limit", type=int, default=MAX_HUB_NOTE_LIMIT)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()
    try:
        result = verify_als_midi_clip_against_hub(
            args.path,
            track_name=args.track_name,
            clip_name=args.clip_name,
            arrangement_start=args.arrangement_start,
            candidate_limit=args.candidate_limit,
            note_limit=args.note_limit,
            timeout=args.timeout,
        )
    except (AlsMidiError, AlsMidiVerificationError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    return 0 if result["overall_status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())

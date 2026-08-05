from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .bounded_read import BoundedReadTimeoutError
from .clip_note_tools import clip_note_tools_bounded
from .locator import locator
from .mixer_control import set_mix
from .ping import ping
from .tempo import tempo
from .track_management import track_management
from .transport import transport


class InitialReadError(RuntimeError):
    pass


ProgressCallback = Callable[[str, dict[str, Any]], None]
QuickReadyCallback = Callable[[dict[str, Any]], None]


def _read_clip_notes_adaptive(
    clip_id: int,
    *,
    note_window_beats: int,
    total_timeout: float,
    connection: dict[str, Any],
) -> tuple[dict[str, Any], list[int]]:
    windows = list(dict.fromkeys([note_window_beats, min(note_window_beats, 4)]))
    attempted: list[int] = []
    for index, window_beats in enumerate(windows):
        attempted.append(window_beats)
        try:
            return clip_note_tools_bounded(
                "read_notes_by_clip_id",
                clip_id=clip_id,
                projection=["notes"],
                limit=window_beats,
                max_pages=32,
                max_items=512,
                total_timeout=total_timeout,
                **connection,
            ), attempted
        except BoundedReadTimeoutError:
            if index == len(windows) - 1:
                raise
    raise InitialReadError(f"No note-read window available for clip_id={clip_id}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _elapsed_ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000.0, 1)


def _clip_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "clip_id": item.get("clip_id"),
        "track_id": item.get("track_id"),
        "track_index": item.get("track_index"),
        "track_name": item.get("track_name"),
        "clip_name": item.get("clip_name"),
        "clip_type": item.get("clip_type"),
        "start_time": item.get("start_time"),
        "end_time": item.get("end_time"),
        "length": item.get("length"),
    }


def _note_summary(notes: list[dict[str, Any]]) -> dict[str, Any]:
    pitches = [int(note["pitch"]) for note in notes if note.get("pitch") is not None]
    starts = [float(note["start_time"]) for note in notes if note.get("start_time") is not None]
    durations = [float(note["duration"]) for note in notes if note.get("duration") is not None]
    return {
        "note_count": len(notes),
        "pitch_min": min(pitches) if pitches else None,
        "pitch_max": max(pitches) if pitches else None,
        "unique_pitches": sorted(set(pitches)),
        "pitch_classes": sorted({pitch % 12 for pitch in pitches}),
        "first_note_time": min(starts) if starts else None,
        "last_note_time": max(starts) if starts else None,
        "duration_values": sorted({round(duration, 4) for duration in durations})[:24],
    }


def _mixer_records(
    records: list[dict[str, Any]],
    *,
    host: str,
    command_port: int,
    reply_port: int,
    timeout: float,
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for start in range(0, len(records), 8):
        changes: list[dict[str, Any]] = []
        for record in records[start : start + 8]:
            target = {"section": record["section"], "track_id": record["track_id"]}
            changes.append({**target, "field": "volume", "value": 0.5})
            changes.append({**target, "field": "mute", "value": 0})
        result = set_mix(
            changes,
            commit=False,
            value_display="both",
            host=host,
            command_port=command_port,
            reply_port=reply_port,
            timeout=timeout,
        )
        values.extend(result.get("results", []))

    by_target: dict[str, dict[str, Any]] = {}
    for item in values:
        key = f"{item.get('section')}:{item.get('track_id')}"
        entry = by_target.setdefault(
            key,
            {
                "section": item.get("section"),
                "track_id": item.get("track_id"),
                "track_name": item.get("track_name"),
            },
        )
        if item.get("field") == "volume":
            before = item.get("before") or {}
            entry["volume_internal"] = before.get("value")
            entry["volume_ui"] = before.get("display_value") or before.get("ui_value")
        elif item.get("field") == "mute":
            entry["mute"] = bool(item.get("before"))
    return list(by_target.values())


def _build_summary(context: dict[str, Any]) -> dict[str, Any]:
    tracks = context.get("tracks", [])
    clips = context.get("clips", [])
    notes = context.get("midi_notes", {})
    clip_tracks: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"midi_clips": 0, "audio_clips": 0, "first_beat": None, "last_beat": None}
    )
    for clip in clips:
        entry = clip_tracks[str(clip.get("track_name") or "")]
        kind = "audio_clips" if clip.get("clip_type") == "audio" else "midi_clips"
        entry[kind] += 1
        start = float(clip.get("start_time") or 0.0)
        end = float(clip.get("end_time") or start)
        entry["first_beat"] = start if entry["first_beat"] is None else min(entry["first_beat"], start)
        entry["last_beat"] = end if entry["last_beat"] is None else max(entry["last_beat"], end)

    ordinary = [item for item in tracks if item.get("section") == "track"]
    returns = [item for item in tracks if item.get("section") == "return"]
    main = [item for item in tracks if item.get("section") == "main"]
    midi_clips = [item for item in clips if item.get("clip_type") == "midi"]
    audio_clips = [item for item in clips if item.get("clip_type") == "audio"]
    return {
        "status": context.get("status"),
        "depth": context.get("depth"),
        "tempo": context.get("set", {}).get("tempo"),
        "transport": context.get("set", {}).get("transport"),
        "locator_count": len(context.get("set", {}).get("locators", [])),
        "ordinary_track_count": len(ordinary),
        "group_track_count": sum(1 for item in ordinary if item.get("track_type") == "group"),
        "return_track_count": len(returns),
        "main_track_count": len(main),
        "arrangement_clip_count": len(clips),
        "midi_clip_count": len(midi_clips),
        "audio_clip_count": len(audio_clips),
        "arrangement_end_beat": max(
            (float(item.get("end_time") or 0.0) for item in clips), default=0.0
        ),
        "midi_note_clip_count": len(notes),
        "midi_note_count": sum(int(item.get("summary", {}).get("note_count", 0)) for item in notes.values()),
        "mixer_target_count": len(context.get("mixer", [])),
        "track_hierarchy": context.get("hierarchy", []),
        "clip_tracks": dict(sorted(clip_tracks.items())),
        "stages": context.get("stages", {}),
        "errors": context.get("errors", []),
        "warnings": context.get("warnings", []),
        "total_elapsed_ms": context.get("total_elapsed_ms"),
    }


def initial_read(
    *,
    depth: str = "quick",
    include_raw_notes: bool = False,
    note_tracks: list[str] | None = None,
    max_note_clips: int = 512,
    note_window_beats: int = 16,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 5.0,
    ping_timeout: float = 1.5,
    total_timeout: float = 30.0,
    on_progress: ProgressCallback | None = None,
    on_quick_ready: QuickReadyCallback | None = None,
) -> dict[str, Any]:
    if depth not in {"quick", "full"}:
        raise InitialReadError("depth must be quick or full")
    if max_note_clips < 1 or max_note_clips > 512:
        raise InitialReadError("max_note_clips must be 1..512")
    if note_window_beats < 1 or note_window_beats > 64:
        raise InitialReadError("note_window_beats must be 1..64")
    if ping_timeout <= 0:
        raise InitialReadError("ping_timeout must be greater than zero")

    started = time.monotonic()
    context: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "source": "current_live_set",
        "read_only": True,
        "depth": depth,
        "status": "complete",
        "set": {},
        "tracks": [],
        "hierarchy": [],
        "clips": [],
        "midi_notes": {},
        "mixer": [],
        "stages": {},
        "errors": [],
        "warnings": [],
    }

    def progress(stage: str, **details: Any) -> None:
        if on_progress is not None:
            on_progress(stage, details)

    def stage(name: str, operation: Callable[[], Any], *, required: bool = False) -> Any:
        stage_started = time.monotonic()
        progress(name, state="started")
        try:
            result = operation()
            context["stages"][name] = {"ok": True, "elapsed_ms": _elapsed_ms(stage_started)}
            progress(name, state="completed", elapsed_ms=context["stages"][name]["elapsed_ms"])
            return result
        except Exception as exc:
            error = {"stage": name, "error": f"{type(exc).__name__}: {exc}"}
            context["errors"].append(error)
            context["stages"][name] = {
                "ok": False,
                "elapsed_ms": _elapsed_ms(stage_started),
                "error": error["error"],
            }
            context["status"] = "partial"
            progress(name, state="failed", error=error["error"])
            if required:
                raise InitialReadError(error["error"]) from exc
            return None

    connection = {
        "host": host,
        "command_port": command_port,
        "reply_port": reply_port,
        "timeout": timeout,
    }
    ping_connection = {
        "host": host,
        "command_port": command_port,
        "reply_port": reply_port,
        "timeout": ping_timeout,
    }
    stage("ping", lambda: ping(**ping_connection), required=True)

    tempo_result = stage("tempo", lambda: tempo(**connection))
    if tempo_result:
        context["set"]["tempo"] = tempo_result.get("tempo")

    transport_result = stage("transport", lambda: transport("status", **connection))
    if transport_result:
        context["set"]["transport"] = transport_result.get("before") or transport_result.get("after")

    locator_result = stage("locators", lambda: locator("list", **connection))
    if locator_result:
        context["set"]["locators"] = locator_result.get("after") or locator_result.get("before") or []

    hierarchy = stage(
        "tracks",
        lambda: track_management(
            "scan_hierarchy",
            projection=["identity", "hierarchy", "color", "fold", "device_count"],
            include_returns=True,
            limit=8,
            max_pages=32,
            max_items=512,
            total_timeout=total_timeout,
            page_timeout=timeout,
            **connection,
        ),
    )
    if hierarchy:
        ordinary = [item for item in hierarchy.get("tracks", []) if item.get("section") == "track"]
        returns = hierarchy.get("return_tracks", [])
        main = [hierarchy["main_track"]] if hierarchy.get("main_track") else []
        context["tracks"] = ordinary + returns + main
        context["hierarchy"] = hierarchy.get("hierarchy", [])
        context["warnings"].extend(hierarchy.get("warnings", []))

    metadata = stage(
        "clips",
        lambda: clip_note_tools_bounded(
            "scan_clips_metadata",
            target="arrangement",
            projection=["identity", "timing", "type"],
            limit=16,
            max_pages=32,
            max_items=512,
            total_timeout=total_timeout,
            **connection,
        ),
    )
    if metadata:
        context["clips"] = [_clip_record(item) for item in metadata.get("items", [])]
        context["warnings"].extend(metadata.get("warnings", []))

    quick_context = copy.deepcopy(context)
    quick_context["depth"] = "quick"
    quick_context["total_elapsed_ms"] = _elapsed_ms(started)
    quick_context["summary"] = _build_summary(quick_context)
    progress("quick", state="ready", summary=quick_context["summary"])
    if on_quick_ready is not None:
        on_quick_ready(quick_context)

    if depth == "full" and metadata:
        selected_names = {name.casefold() for name in (note_tracks or [])}
        midi_clips = [item for item in metadata.get("items", []) if item.get("is_midi_clip")]
        if selected_names:
            midi_clips = [
                item for item in midi_clips if str(item.get("track_name") or "").casefold() in selected_names
            ]
        midi_clips = midi_clips[:max_note_clips]

        notes_started = time.monotonic()
        note_errors = 0
        track_note_windows: dict[int, int] = {}
        for index, clip in enumerate(midi_clips, 1):
            try:
                track_id = int(clip["track_id"])
                preferred_window = track_note_windows.get(track_id, note_window_beats)
                result, attempted_windows = _read_clip_notes_adaptive(
                    int(clip["clip_id"]),
                    note_window_beats=preferred_window,
                    total_timeout=total_timeout,
                    connection=connection,
                )
                notes = result.get("notes", [])
                used_window = attempted_windows[-1]
                if len(attempted_windows) > 1:
                    track_note_windows[track_id] = used_window
                adaptive_warning = None
                if len(attempted_windows) > 1:
                    adaptive_warning = {
                        "stage": "midi_notes",
                        "type": "adaptive_note_window",
                        "clip_id": clip.get("clip_id"),
                        "track_name": clip.get("track_name"),
                        "attempted_windows": attempted_windows,
                        "used_window_beats": used_window,
                    }
                    context["warnings"].append(adaptive_warning)
                entry = {
                    "clip_id": clip.get("clip_id"),
                    "clip_name": clip.get("clip_name"),
                    "track_id": clip.get("track_id"),
                    "track_name": clip.get("track_name"),
                    "summary": _note_summary(notes),
                    "window_beats": used_window,
                    "window_source": (
                        "inherited_track_fallback"
                        if preferred_window != note_window_beats
                        else "adaptive_retry"
                        if len(attempted_windows) > 1
                        else "default"
                    ),
                    "complete": result.get("complete", True),
                    "warnings": result.get("warnings", []),
                }
                if adaptive_warning:
                    entry["warnings"] = [*entry["warnings"], adaptive_warning]
                if include_raw_notes:
                    entry["notes"] = notes
                context["midi_notes"][str(clip["clip_id"])] = entry
            except Exception as exc:
                note_errors += 1
                context["errors"].append(
                    {
                        "stage": "midi_notes",
                        "clip_id": clip.get("clip_id"),
                        "track_name": clip.get("track_name"),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                context["status"] = "partial"
            if index % 10 == 0 or index == len(midi_clips):
                progress("midi_notes", state="progress", completed=index, total=len(midi_clips))
        context["stages"]["midi_notes"] = {
            "ok": note_errors == 0,
            "elapsed_ms": _elapsed_ms(notes_started),
            "attempted": len(midi_clips),
            "completed": len(context["midi_notes"]),
            "errors": note_errors,
        }

    if depth == "full" and context["tracks"]:
        mixer = stage(
            "mixer",
            lambda: _mixer_records(
                context["tracks"],
                host=host,
                command_port=command_port,
                reply_port=reply_port,
                timeout=timeout,
            ),
        )
        if mixer is not None:
            context["mixer"] = mixer

    stage("health_ping", lambda: ping(**ping_connection))
    context["total_elapsed_ms"] = _elapsed_ms(started)
    context["summary"] = _build_summary(context)
    return context


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read the currently open Live Set once through the production Hub"
    )
    parser.add_argument("--depth", choices=["quick", "full"], default="quick")
    parser.add_argument("--output", type=Path, help="Optional path for the complete machine-readable context")
    parser.add_argument("--quick-output", type=Path, help="Optional quick checkpoint written before full-depth stages")
    parser.add_argument("--include-raw-notes", action="store_true")
    parser.add_argument("--notes-track", action="append", default=[], help="In full mode, only read this exact track name; repeat as needed")
    parser.add_argument("--max-note-clips", type=int, default=512)
    parser.add_argument("--note-window-beats", type=int, default=16, help="Initial full-mode note page width; dense clips automatically retry at 4 beats")
    parser.add_argument("--print-full", action="store_true", help="Print the complete context instead of the compact summary")
    parser.add_argument("--quiet-progress", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--ping-timeout", type=float, default=1.5)
    parser.add_argument("--total-timeout", type=float, default=30.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    def show_progress(stage: str, details: dict[str, Any]) -> None:
        if args.quiet_progress:
            return
        if details.get("state") == "progress":
            print(
                f"[{stage}] {details.get('completed')}/{details.get('total')}",
                file=sys.stderr,
                flush=True,
            )

    def quick_ready(quick_context: dict[str, Any]) -> None:
        if args.quick_output:
            _write_json(args.quick_output, quick_context)
        if not args.quiet_progress:
            print(
                json.dumps(
                    {
                        "event": "quick_ready",
                        "summary": quick_context["summary"],
                        "output": str(args.quick_output.resolve()) if args.quick_output else None,
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
                flush=True,
            )

    try:
        context = initial_read(
            depth=args.depth,
            include_raw_notes=args.include_raw_notes,
            note_tracks=args.notes_track,
            max_note_clips=args.max_note_clips,
            note_window_beats=args.note_window_beats,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
            ping_timeout=args.ping_timeout,
            total_timeout=args.total_timeout,
            on_progress=show_progress,
            on_quick_ready=quick_ready,
        )
    except InitialReadError as exc:
        message = str(exc)
        payload = {
            "ok": False,
            "stage": "preflight" if "PingTimeoutError" in message else "initial_read",
            "error_code": "hub_not_responding" if "PingTimeoutError" in message else "initial_read_failed",
            "error": message,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    if args.output:
        _write_json(args.output, context)
    payload = context if args.print_full else {
        "ok": context["status"] == "complete",
        "summary": context["summary"],
        "output": str(args.output.resolve()) if args.output else None,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if context["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())

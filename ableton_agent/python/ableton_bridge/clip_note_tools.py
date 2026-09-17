from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .bounded_read import collect_pages, request_page
from .osc import OscDecodeError, decode_message, encode_message
from .reply_port_lock import reply_port_lock


class ClipNoteToolsError(RuntimeError):
    pass


class ClipNoteToolsTimeoutError(ClipNoteToolsError):
    pass


def clip_note_tools(
    action: str = "read_notes",
    *,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
    **payload_fields: Any,
) -> dict[str, Any]:
    payload = {"action": action}
    payload.update({key: value for key, value in payload_fields.items() if value is not None})
    return _request_clip_note_tools(
        payload,
        commit=commit,
        host=host,
        command_port=command_port,
        reply_port=reply_port,
        timeout=timeout,
    )


def clip_note_tools_bounded(
    action: str,
    *,
    item_key: str | None = None,
    cursor: int = 0,
    limit: int = 16,
    projection: list[str] | None = None,
    budget_ms: int = 1000,
    max_pages: int = 32,
    max_items: int = 512,
    total_timeout: float = 30.0,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 5.0,
    **payload_fields: Any,
) -> dict[str, Any]:
    resolved_item_key = item_key or ("notes" if action == "read_notes_by_clip_id" else "items")
    payload = {"action": action}
    payload.update({key: value for key, value in payload_fields.items() if value is not None})
    payload["read"] = {
        "cursor": cursor,
        "limit": limit,
        "budget_ms": budget_ms,
    }
    if projection is not None:
        payload["read"]["projection"] = projection

    def fetch_page(page_payload: dict[str, Any], page_timeout: float) -> dict[str, Any]:
        return request_page(
            "/clip_note_tools",
            page_payload,
            mode="dry_run",
            host=host,
            command_port=command_port,
            reply_port=reply_port,
            timeout=page_timeout,
        )

    return collect_pages(
        fetch_page,
        payload,
        item_key=resolved_item_key,
        max_pages=max_pages,
        max_items=max_items,
        total_timeout=total_timeout,
        page_timeout=timeout,
    )


def _request_clip_note_tools(
    payload: dict[str, Any],
    *,
    commit: bool,
    host: str,
    command_port: int,
    reply_port: int,
    timeout: float,
) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    mode = "commit" if commit else "dry_run"
    packet = encode_message("/clip_note_tools", [request_id, json.dumps(payload, ensure_ascii=False), mode])

    with reply_port_lock(reply_port, timeout=timeout), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reply_socket:
        reply_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reply_socket.bind((host, reply_port))
        reply_socket.settimeout(min(timeout, 0.2))

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as command_socket:
            command_socket.sendto(packet, (host, command_port))

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ClipNoteToolsTimeoutError(
                    f"No clip_note_tools reply from Ableton Agent Hub on UDP {reply_port}; reload Ableton Agent Hub.amxd"
                )
            reply_socket.settimeout(min(remaining, 0.2))
            try:
                reply_packet, address = reply_socket.recvfrom(65535)
            except socket.timeout:
                continue
            try:
                path, arguments = decode_message(reply_packet)
            except OscDecodeError:
                continue
            if path not in ["/clip_note_tools", "clip_note_tools"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read or edit notes in the current Ableton detail MIDI clip")
    parser.add_argument(
        "--action",
        default="scan_clips",
        choices=[
            "scan_clips",
            "scan_clips_metadata",
            "read_notes",
            "read_notes_by_clip_id",
            "shift_notes",
            "quantize_notes",
            "delete_notes_in_range",
            "scale_velocity",
        ],
    )
    parser.add_argument("--start", type=float, help="Only affect notes whose start is at or after this beat in the clip")
    parser.add_argument("--end", type=float, help="Only affect notes whose start is before this beat in the clip")
    parser.add_argument("--target", choices=["auto", "detail", "arrangement", "session"], help="Where to look for a MIDI clip")
    parser.add_argument("--track", help="Optional track name or zero-based track index to search within")
    parser.add_argument("--candidate-index", type=int, dest="candidate_index", help="Candidate index returned by scan_clips")
    parser.add_argument("--candidate-limit", type=int, dest="candidate_limit", help="Maximum MIDI clip candidates to return")
    parser.add_argument("--clip-id", type=int, dest="clip_id", help="Advanced: clip id returned by scan_clips")
    parser.add_argument("--pitch-min", type=int, dest="pitch_min")
    parser.add_argument("--pitch-max", type=int, dest="pitch_max")
    parser.add_argument("--delta-beats", type=float, dest="delta_beats", help="Beat offset for shift_notes")
    parser.add_argument("--semitones", type=int, help="Pitch offset for shift_notes")
    parser.add_argument("--grid", type=float, help="Quantize grid in beats, e.g. 0.25 for 1/16")
    parser.add_argument("--scale", type=float, help="Velocity multiplier for scale_velocity")
    parser.add_argument("--offset", type=float, help="Velocity offset for scale_velocity")
    parser.add_argument("--limit", type=int, default=64, help="Maximum notes to show for read_notes")
    parser.add_argument("--commit", action="store_true", help="Actually edit the current clip. Without this, only dry-runs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--cursor", type=int, default=0, help="Bounded read cursor for scan_clips_metadata/read_notes_by_clip_id")
    parser.add_argument("--page-limit", type=int, default=16, help="Bounded page size; for read_notes_by_clip_id this is a beat window")
    parser.add_argument("--projection", action="append", help="Bounded read projection field; repeat as needed")
    parser.add_argument("--budget-ms", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=32)
    parser.add_argument("--max-items", type=int, default=512)
    parser.add_argument("--total-timeout", type=float, default=30.0)
    parser.add_argument("--single-page", action="store_true", help="Do not auto-collect bounded pages")
    args = parser.parse_args()

    try:
        common_payload = {
            "target": args.target,
            "track": int(args.track) if args.track and args.track.isdigit() else args.track,
            "candidate_index": args.candidate_index,
            "candidate_limit": args.candidate_limit,
            "clip_id": args.clip_id,
            "start": args.start,
            "end": args.end,
            "pitch_min": args.pitch_min,
            "pitch_max": args.pitch_max,
            "delta_beats": args.delta_beats,
            "semitones": args.semitones,
            "grid": args.grid,
            "scale": args.scale,
            "offset": args.offset,
            "limit": args.limit,
        }
        if args.action in {"scan_clips_metadata", "read_notes_by_clip_id"}:
            bounded_payload = {key: value for key, value in common_payload.items() if key != "limit"}
            if args.single_page:
                read = {
                    "cursor": args.cursor,
                    "limit": args.page_limit,
                    "budget_ms": args.budget_ms,
                }
                if args.projection is not None:
                    read["projection"] = args.projection
                result = clip_note_tools(
                    args.action,
                    commit=False,
                    host=args.host,
                    command_port=args.command_port,
                    reply_port=args.reply_port,
                    timeout=args.timeout,
                    read=read,
                    **bounded_payload,
                )
            else:
                result = clip_note_tools_bounded(
                    args.action,
                    host=args.host,
                    command_port=args.command_port,
                    reply_port=args.reply_port,
                    timeout=args.timeout,
                    cursor=args.cursor,
                    limit=args.page_limit,
                    projection=args.projection,
                    budget_ms=args.budget_ms,
                    max_pages=args.max_pages,
                    max_items=args.max_items,
                    total_timeout=args.total_timeout,
                    **bounded_payload,
                )
        else:
            result = clip_note_tools(
                args.action,
                commit=args.commit,
                host=args.host,
                command_port=args.command_port,
                reply_port=args.reply_port,
                timeout=args.timeout,
                **common_payload,
            )
    except (ClipNoteToolsError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

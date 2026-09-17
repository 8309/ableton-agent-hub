from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .reply_port_lock import reply_port_lock


class ClipWriteError(RuntimeError):
    pass


class ClipWriteTimeoutError(ClipWriteError):
    pass


def note_from_text(text: str) -> dict[str, Any]:
    parts = [part.strip() for part in text.split(",")]
    if len(parts) not in [3, 4]:
        raise ClipWriteError("Note format must be pitch,start,duration or pitch,start,duration,velocity")
    note = {
        "pitch": int(parts[0]),
        "start_time": float(parts[1]),
        "duration": float(parts[2]),
        "velocity": int(parts[3]) if len(parts) == 4 else 100,
    }
    return note


def write_clip(
    *,
    track: str | int,
    scene_index: int,
    length: float,
    notes: list[dict[str, Any]],
    name: str = "",
    replace: bool = False,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
) -> dict[str, Any]:
    if not notes:
        raise ClipWriteError("notes cannot be empty")
    if len(notes) > 512:
        raise ClipWriteError("too many notes; maximum is 512")

    request_id = uuid.uuid4().hex
    mode = "commit" if commit else "dry_run"
    payload = json.dumps(
        {
            "track": track,
            "scene_index": scene_index,
            "length": length,
            "name": name,
            "replace": replace,
            "notes": notes,
        },
        ensure_ascii=False,
    )
    packet = encode_message("/write_clip", [request_id, payload, mode])

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
                raise ClipWriteTimeoutError(
                    f"No write_clip reply from Ableton Agent Clip Writer on UDP {reply_port}; "
                    "load Ableton Agent Clip Writer.amxd in the current Set"
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
            if path not in ["/write_clip", "write_clip"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def write_arrangement_clip(
    *,
    track: str | int,
    start: float,
    length: float,
    notes: list[dict[str, Any]],
    name: str = "",
    replace: bool = False,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
) -> dict[str, Any]:
    if start < 0:
        raise ClipWriteError("start must be non-negative")
    if length <= 0:
        raise ClipWriteError("length must be greater than zero")
    if not notes:
        raise ClipWriteError("notes cannot be empty")
    if len(notes) > 512:
        raise ClipWriteError("too many notes; maximum is 512")

    request_id = uuid.uuid4().hex
    mode = "commit" if commit else "dry_run"
    payload = json.dumps(
        {
            "track": track,
            "start": start,
            "length": length,
            "name": name,
            "replace": replace,
            "notes": notes,
        },
        ensure_ascii=False,
    )
    packet = encode_message("/write_arrangement_clip", [request_id, payload, mode])

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
                raise ClipWriteTimeoutError(
                    f"No write_arrangement_clip reply from Ableton Agent Clip Writer on UDP {reply_port}; "
                    "load Ableton Agent Hub.amxd or Ableton Agent Clip Writer.amxd in the current Set"
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
            if path not in ["/write_arrangement_clip", "write_arrangement_clip"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run or write one Session or Arrangement MIDI clip")
    parser.add_argument(
        "--arrangement",
        action="store_true",
        help="Write an Arrangement clip at --start instead of a Session clip slot",
    )
    parser.add_argument("--track", required=True, help="Track name or zero-based track index")
    parser.add_argument("--scene", type=int, default=0, help="Zero-based Session scene index")
    parser.add_argument("--start", type=float, default=0.0, help="Arrangement clip start in beats")
    parser.add_argument("--length", type=float, default=4.0, help="Clip length in beats")
    parser.add_argument("--name", default="", help="Optional clip name")
    parser.add_argument("--replace", action="store_true", help="Allow replacing notes if the slot already has a MIDI clip")
    parser.add_argument("--commit", action="store_true", help="Actually write the clip. Without this, only dry-runs.")
    parser.add_argument("--note", action="append", required=True, help="pitch,start,duration or pitch,start,duration,velocity")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    track: str | int = int(args.track) if args.track.isdigit() else args.track
    try:
        notes = [note_from_text(note) for note in args.note]
        if args.arrangement:
            result = write_arrangement_clip(
                track=track,
                start=args.start,
                length=args.length,
                name=args.name,
                replace=args.replace,
                commit=args.commit,
                notes=notes,
                host=args.host,
                command_port=args.command_port,
                reply_port=args.reply_port,
                timeout=args.timeout,
            )
        else:
            result = write_clip(
                track=track,
                scene_index=args.scene,
                length=args.length,
                name=args.name,
                replace=args.replace,
                commit=args.commit,
                notes=notes,
                host=args.host,
                command_port=args.command_port,
                reply_port=args.reply_port,
                timeout=args.timeout,
            )
    except (ClipWriteError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

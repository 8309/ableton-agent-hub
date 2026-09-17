from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .reply_port_lock import reply_port_lock


class DetailClipWriteError(RuntimeError):
    pass


class DetailClipWriteTimeoutError(DetailClipWriteError):
    pass


def transpose_detail_note(
    *,
    note_index: int = 0,
    semitones: int = 12,
    selector: str = "first_musical",
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
) -> dict[str, Any]:
    if note_index < 0:
        raise DetailClipWriteError("note_index must be non-negative")
    if semitones == 0:
        raise DetailClipWriteError("semitones cannot be zero")

    request_id = uuid.uuid4().hex
    mode = "commit" if commit else "dry_run"
    payload = json.dumps(
        {
            "note_index": note_index,
            "semitones": semitones,
            "selector": selector,
        },
        ensure_ascii=False,
    )
    packet = encode_message("/transpose_detail_note", [request_id, payload, mode])

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
                raise DetailClipWriteTimeoutError(
                    f"No transpose_detail_note reply from Ableton Agent Detail Clip Writer on UDP {reply_port}; "
                    "load Ableton Agent Detail Clip Writer.amxd in the current Set"
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
            if path not in ["/transpose_detail_note", "transpose_detail_note"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run or transpose one note in the current detail MIDI clip")
    parser.add_argument("--note-index", type=int, default=0, help="Zero-based note index after sorting by start time")
    parser.add_argument("--semitones", type=int, default=12, help="Transpose amount in semitones")
    parser.add_argument(
        "--selector",
        choices=["first_musical", "absolute"],
        default="first_musical",
        help="first_musical skips tiny/velocity-1 utility notes; absolute uses the raw Live API note index",
    )
    parser.add_argument("--commit", action="store_true", help="Actually change the clip. Without this, only dry-runs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    try:
        result = transpose_detail_note(
            note_index=args.note_index,
            semitones=args.semitones,
            selector=args.selector,
            commit=args.commit,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
        )
    except (DetailClipWriteError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

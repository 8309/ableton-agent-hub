from __future__ import annotations

import argparse
import json
import socket
import time
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .reply_port_lock import reply_port_lock


class NoteError(RuntimeError):
    pass


class NoteTimeoutError(NoteError):
    pass


def send_note(
    pitch: int,
    velocity: int = 100,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 2.0,
) -> dict[str, Any]:
    if pitch < 0 or pitch > 127:
        raise ValueError("pitch must be between 0 and 127")
    if velocity < 1 or velocity > 127:
        raise ValueError("velocity must be between 1 and 127")

    packet = encode_message("/note", [pitch, velocity])

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
                raise NoteTimeoutError(
                    f"No note_ack from Ableton Agent Notes on UDP {reply_port}; "
                    "load Ableton Agent Notes.amxd in the current Set"
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
            if path not in ["/note_ack", "note_ack"] or len(arguments) < 2:
                continue
            if int(arguments[0]) != pitch or int(arguments[1]) != velocity:
                continue
            return {
                "pitch": pitch,
                "velocity": velocity,
                "from": address[0],
                "port": address[1],
            }


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a short MIDI note through Ableton Agent Notes.amxd")
    parser.add_argument("pitch", type=int)
    parser.add_argument("velocity", nargs="?", type=int, default=100)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()

    try:
        result = send_note(
            args.pitch,
            args.velocity,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
        )
    except (NoteError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

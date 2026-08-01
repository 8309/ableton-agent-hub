from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .value_display import ValueDisplayError, format_value_display, normalize_value_display_mode


class MultiParameterControlError(RuntimeError):
    pass


class MultiParameterControlTimeoutError(MultiParameterControlError):
    pass


def parse_change(text: str) -> dict[str, Any]:
    parts = [part.strip() for part in text.split("|")]
    if len(parts) == 3:
        track, parameter, value = parts
        return {"track": track, "parameter": parameter, "value": float(value)}
    if len(parts) == 4:
        track, device, parameter, value = parts
        return {"track": track, "device": device, "parameter": parameter, "value": float(value)}
    raise MultiParameterControlError(
        "Change format must be TRACK|PARAMETER|VALUE or TRACK|DEVICE|PARAMETER|VALUE"
    )


def set_parameters(
    changes: list[dict[str, Any]],
    *,
    commit: bool = False,
    value_display: str = "ui",
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
) -> dict[str, Any]:
    value_display = normalize_value_display_mode(value_display)
    if not changes:
        raise MultiParameterControlError("changes cannot be empty")
    if len(changes) > 16:
        raise MultiParameterControlError("too many changes; maximum is 16")

    request_id = uuid.uuid4().hex
    mode = "commit" if commit else "dry_run"
    payload = json.dumps({"changes": changes}, ensure_ascii=False)
    packet = encode_message("/set_parameters", [request_id, payload, mode])

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reply_socket:
        reply_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reply_socket.bind((host, reply_port))
        reply_socket.settimeout(min(timeout, 0.2))

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as command_socket:
            command_socket.sendto(packet, (host, command_port))

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MultiParameterControlTimeoutError(
                    f"No set_parameters reply from Ableton Agent Multi Parameter Control on UDP {reply_port}; "
                    "load Ableton Agent Multi Parameter Control.amxd in the current Set"
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
            if path not in ["/set_parameters", "set_parameters"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            result["value_display"] = value_display
            return format_value_display(result, value_display)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run or set device parameters on ordinary, Return, or Main Live tracks")
    parser.add_argument(
        "--change",
        action="append",
        required=True,
        help="TRACK|PARAMETER|VALUE or TRACK|DEVICE|PARAMETER|VALUE; repeat for multiple tracks",
    )
    parser.add_argument("--commit", action="store_true", help="Actually change the Set. Without this, only dry-runs.")
    parser.add_argument("--section", choices=["track", "return", "main", "master"], help="Apply one section to every --change")
    parser.add_argument("--track-id", type=int, help="Session-stable target id; use one change per command with this option")
    parser.add_argument(
        "--value-display",
        choices=["both", "internal", "ui"],
        default="ui",
        help="Show returned parameter values as both forms, internal 0..1 values, or Ableton UI values",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    try:
        changes = [parse_change(change) for change in args.change]
        if args.track_id is not None and len(changes) != 1:
            raise MultiParameterControlError("--track-id requires exactly one --change")
        for change in changes:
            if args.section:
                change["section"] = "main" if args.section == "master" else args.section
            if args.track_id is not None:
                change["track_id"] = args.track_id
        result = set_parameters(
            changes,
            commit=args.commit,
            value_display=args.value_display,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
        )
    except (MultiParameterControlError, ValueDisplayError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

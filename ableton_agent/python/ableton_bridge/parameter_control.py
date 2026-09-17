from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .reply_port_lock import reply_port_lock
from .value_display import ValueDisplayError, format_value_display, normalize_value_display_mode


class ParameterControlError(RuntimeError):
    pass


class ParameterControlTimeoutError(ParameterControlError):
    pass


def set_parameter(
    parameter: str | int,
    value: float,
    *,
    commit: bool = False,
    value_display: str = "ui",
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 2.0,
) -> dict[str, Any]:
    value_display = normalize_value_display_mode(value_display)
    request_id = uuid.uuid4().hex
    mode = "commit" if commit else "dry_run"
    packet = encode_message("/set_parameter", [request_id, str(parameter), float(value), mode])

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
                raise ParameterControlTimeoutError(
                    f"No set_parameter reply from Ableton Agent Parameter Control on UDP {reply_port}; "
                    "load Ableton Agent Parameter Control.amxd in the current Set"
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
            if path not in ["/set_parameter", "set_parameter"] or len(arguments) < 2:
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
    parser = argparse.ArgumentParser(description="Dry-run or set one parameter on the selected track target device")
    parser.add_argument("parameter", help="Parameter name or index on the selected track target device")
    parser.add_argument("value", type=float, help="Absolute value in that parameter's native range")
    parser.add_argument("--commit", action="store_true", help="Actually change the Set. Without this, only dry-runs.")
    parser.add_argument(
        "--value-display",
        choices=["both", "internal", "ui"],
        default="ui",
        help="Show returned parameter values as both forms, internal values, or Ableton UI values",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()

    try:
        result = set_parameter(
            args.parameter,
            args.value,
            commit=args.commit,
            value_display=args.value_display,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
        )
    except (ParameterControlError, ValueDisplayError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

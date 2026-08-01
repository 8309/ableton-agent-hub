from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .value_display import ValueDisplayError, format_value_display, normalize_value_display_mode


class EqToolsError(RuntimeError):
    pass


class EqToolsTimeoutError(EqToolsError):
    pass


def eq_tools(
    action: str = "list_presets",
    *,
    commit: bool = False,
    value_display: str = "ui",
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
    **payload_fields: Any,
) -> dict[str, Any]:
    value_display = normalize_value_display_mode(value_display)
    payload = {"action": action}
    payload.update({key: value for key, value in payload_fields.items() if value is not None})
    result = _request(payload, commit=commit, host=host, command_port=command_port, reply_port=reply_port, timeout=timeout)
    result["value_display"] = value_display
    return format_value_display(result, value_display)


def _request(payload: dict[str, Any], *, commit: bool, host: str, command_port: int, reply_port: int, timeout: float) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    mode = "commit" if commit else "dry_run"
    packet = encode_message("/eq_tools", [request_id, json.dumps(payload, ensure_ascii=False), mode])
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
                raise EqToolsTimeoutError(f"No eq_tools reply from Ableton Agent Hub on UDP {reply_port}; reload Ableton Agent Hub.amxd")
            reply_socket.settimeout(min(remaining, 0.2))
            try:
                reply_packet, address = reply_socket.recvfrom(65535)
            except socket.timeout:
                continue
            try:
                path, arguments = decode_message(reply_packet)
            except OscDecodeError:
                continue
            if path not in ["/eq_tools", "eq_tools"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read EQ Eight or apply conservative EQ presets")
    parser.add_argument("--action", default="list_presets", choices=["list_presets", "read_eq", "apply_preset", "set_band"])
    parser.add_argument("--track")
    parser.add_argument("--track-index", type=int, dest="track_index")
    parser.add_argument("--device")
    parser.add_argument("--device-index", type=int, dest="device_index")
    parser.add_argument("--preset")
    parser.add_argument("--band", type=int)
    parser.add_argument("--parameter")
    parser.add_argument("--value", type=float)
    parser.add_argument("--limit", type=int, help="Maximum EQ parameters to return for read_eq")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument(
        "--value-display",
        choices=["both", "internal", "ui"],
        default="ui",
        help="Show returned parameter values as both forms, internal Live values, or Ableton UI values",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    try:
        result = eq_tools(
            args.action,
            commit=args.commit,
            value_display=args.value_display,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
            track=int(args.track) if args.track and args.track.isdigit() else args.track,
            track_index=args.track_index,
            device=args.device,
            device_index=args.device_index,
            preset=args.preset,
            band=args.band,
            parameter=args.parameter,
            value=args.value,
            limit=args.limit,
        )
    except (EqToolsError, ValueDisplayError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

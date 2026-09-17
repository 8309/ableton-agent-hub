from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .reply_port_lock import reply_port_lock


class RoutingError(RuntimeError):
    pass


class RoutingTimeoutError(RoutingError):
    pass


def routing(
    action: str = "scan_routing",
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
    return _request_routing(payload, commit=commit, host=host, command_port=command_port, reply_port=reply_port, timeout=timeout)


def _request_routing(
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
    packet = encode_message("/routing", [request_id, json.dumps(payload, ensure_ascii=False), mode])

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
                raise RoutingTimeoutError(f"No routing reply from Ableton Agent Hub on UDP {reply_port}; reload Ableton Agent Hub.amxd")
            reply_socket.settimeout(min(remaining, 0.2))
            try:
                reply_packet, address = reply_socket.recvfrom(65535)
            except socket.timeout:
                continue
            try:
                path, arguments = decode_message(reply_packet)
            except OscDecodeError:
                continue
            if path not in ["/routing", "routing"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read or set Ableton track routing through the unified Hub")
    parser.add_argument("--action", default="scan_routing", choices=["scan_routing", "set_input_routing", "set_output_routing"])
    parser.add_argument("--track", help="Track name or zero-based track index")
    parser.add_argument("--track-index", type=int, dest="track_index")
    parser.add_argument("--section", choices=["track", "return"])
    parser.add_argument("--input-routing-type", dest="input_routing_type")
    parser.add_argument("--input-routing-channel", dest="input_routing_channel")
    parser.add_argument("--output-routing-type", dest="output_routing_type")
    parser.add_argument("--output-routing-channel", dest="output_routing_channel")
    parser.add_argument("--include-returns", action="store_true")
    parser.add_argument("--no-returns", action="store_true")
    parser.add_argument("--include-input", action="store_true", help="Also ask Live for input routing values; slower and track-type sensitive")
    parser.add_argument("--include-available", action="store_true", help="Also ask Live for available routing values; slower and version-sensitive")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    include_returns: bool | None = None
    if args.include_returns:
        include_returns = True
    if args.no_returns:
        include_returns = False

    try:
        result = routing(
            args.action,
            commit=args.commit,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
            track=int(args.track) if args.track and args.track.isdigit() else args.track,
            track_index=args.track_index,
            section=args.section,
            input_routing_type=args.input_routing_type,
            input_routing_channel=args.input_routing_channel,
            output_routing_type=args.output_routing_type,
            output_routing_channel=args.output_routing_channel,
            include_returns=include_returns,
            include_input=args.include_input if args.include_input else None,
            include_available=args.include_available if args.include_available else None,
        )
    except (RoutingError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

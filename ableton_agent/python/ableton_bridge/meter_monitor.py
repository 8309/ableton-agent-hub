from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .reply_port_lock import reply_port_lock


class MeterMonitorError(RuntimeError):
    pass


class MeterMonitorTimeoutError(MeterMonitorError):
    pass


def meter_monitor(
    action: str = "read_meters",
    *,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
    **payload_fields: Any,
) -> dict[str, Any]:
    payload = {"action": action}
    payload.update({key: value for key, value in payload_fields.items() if value is not None})
    return _request(payload, host=host, command_port=command_port, reply_port=reply_port, timeout=timeout)


def _request(payload: dict[str, Any], *, host: str, command_port: int, reply_port: int, timeout: float) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    packet = encode_message("/meter_monitor", [request_id, json.dumps(payload, ensure_ascii=False), "dry_run"])
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
                raise MeterMonitorTimeoutError(f"No meter_monitor reply from Ableton Agent Hub on UDP {reply_port}; reload Ableton Agent Hub.amxd")
            reply_socket.settimeout(min(remaining, 0.2))
            try:
                reply_packet, address = reply_socket.recvfrom(65535)
            except socket.timeout:
                continue
            try:
                path, arguments = decode_message(reply_packet)
            except OscDecodeError:
                continue
            if path not in ["/meter_monitor", "meter_monitor"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read Ableton track meters once and produce balance reports")
    parser.add_argument("--action", default="read_meters", choices=["read_meters", "detect_silent", "detect_clipping", "balance_report"])
    parser.add_argument("--track-index", type=int, dest="track_index")
    parser.add_argument("--track-id", type=int, dest="track_id", help="Session-stable target id")
    parser.add_argument("--section", choices=["track", "return", "main", "master"], help="Target section; Return/Main require an explicit target")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    try:
        result = meter_monitor(
            args.action,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
            track_index=args.track_index,
            track_id=args.track_id,
            section="main" if args.section == "master" else args.section,
            limit=args.limit,
        )
    except (MeterMonitorError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

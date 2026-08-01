from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message


class PingError(RuntimeError):
    pass


class PingTimeoutError(PingError):
    pass


def ping(
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 2.0,
) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    packet = encode_message("/ping", [request_id])

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
                raise PingTimeoutError(
                    f"No pong from Ableton Agent Ping on UDP {reply_port}; "
                    "load Ableton Agent Ping.amxd in the current Set"
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
            if path not in ["/pong", "pong"] or not arguments:
                continue
            if arguments[0] != request_id:
                continue
            return {"request_id": request_id, "from": address[0], "port": address[1]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ping Ableton Agent Ping.amxd")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()

    try:
        result = ping(
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
        )
    except PingError as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

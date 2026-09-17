from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .reply_port_lock import reply_port_lock


class TransportError(RuntimeError):
    pass


class TransportTimeoutError(TransportError):
    pass


def transport(
    action: str = "status",
    *,
    beat: float | None = None,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"action": action}
    if beat is not None:
        payload["beat"] = float(beat)
    result = _request_transport(payload, commit=commit, host=host, command_port=command_port, reply_port=reply_port, timeout=timeout)
    if result.get("ok") and commit and action != "status":
        time.sleep(0.2)
        try:
            status = _request_transport(
                {"action": "status"},
                commit=False,
                host=host,
                command_port=command_port,
                reply_port=reply_port,
                timeout=timeout,
            )
        except (TransportError, OSError, ValueError) as error:
            status = {"ok": False, "error": str(error), "error_type": type(error).__name__}
        result["confirmed_after"] = status.get("before")
        result["readback"] = status
        if not status.get("ok"):
            result["ok"] = False
            result["error_code"] = "transport_readback_failed"
            result["error"] = "Transport was applied but its follow-up status failed"
    return result


def _request_transport(
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
    packet = encode_message("/transport", [request_id, json.dumps(payload, ensure_ascii=False), mode])

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
                raise TransportTimeoutError(
                    f"No transport reply from Ableton Agent Hub on UDP {reply_port}; reload Ableton Agent Hub.amxd"
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
            if path not in ["/transport", "transport"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run or apply Ableton transport actions")
    parser.add_argument("--action", default="status", choices=["status", "play", "stop", "continue", "jump", "set_position"])
    parser.add_argument("--beat", type=float, help="Target beat for jump/set_position")
    parser.add_argument("--commit", action="store_true", help="Actually change Live transport. Without this, only dry-runs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    try:
        result = transport(
            args.action,
            beat=args.beat,
            commit=args.commit,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
        )
    except (TransportError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

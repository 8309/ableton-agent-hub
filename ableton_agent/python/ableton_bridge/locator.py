from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .transport import transport


class LocatorError(RuntimeError):
    pass


class LocatorTimeoutError(LocatorError):
    pass


def locator(
    action: str = "list",
    *,
    name: str | None = None,
    beat: float | None = None,
    locator_id: int | None = None,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"action": action}
    if name is not None:
        payload["name"] = name
    if beat is not None:
        payload["beat"] = float(beat)
    if locator_id is not None:
        payload["id"] = int(locator_id)
    if commit and action == "create" and beat is not None:
        jump_result = transport(
            "jump",
            beat=beat,
            commit=True,
            host=host,
            command_port=command_port,
            reply_port=reply_port,
            timeout=timeout,
        )
        time.sleep(0.2)
        current_payload = {"action": "create_current", "name": name}
        result = _request_locator(
            current_payload,
            commit=True,
            host=host,
            command_port=command_port,
            reply_port=reply_port,
            timeout=timeout,
        )
        result["pre_locator_transport"] = jump_result
        return result
    return _request_locator(payload, commit=commit, host=host, command_port=command_port, reply_port=reply_port, timeout=timeout)


def _request_locator(
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
    packet = encode_message("/locator", [request_id, json.dumps(payload, ensure_ascii=False), mode])

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
                raise LocatorTimeoutError(
                    f"No locator reply from Ableton Agent Hub on UDP {reply_port}; reload Ableton Agent Hub.amxd"
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
            if path not in ["/locator", "locator"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run or apply Ableton locator actions")
    parser.add_argument("--action", default="list", choices=["list", "create", "jump", "delete"])
    parser.add_argument("--name", help="Locator name")
    parser.add_argument("--beat", type=float, help="Locator beat/time")
    parser.add_argument("--id", dest="locator_id", type=int, help="Locator id")
    parser.add_argument("--commit", action="store_true", help="Actually change Live locators. Without this, only dry-runs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    try:
        result = locator(
            args.action,
            name=args.name,
            beat=args.beat,
            locator_id=args.locator_id,
            commit=args.commit,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
        )
    except (LocatorError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

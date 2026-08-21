from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message


class DeviceChainError(RuntimeError):
    pass


class DeviceChainTimeoutError(DeviceChainError):
    pass


def device_chain(
    action: str = "list_templates",
    *,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
    **payload_fields: Any,
) -> dict[str, Any]:
    if action == "scan_recursive":
        root_device_id = payload_fields.get("root_device_id")
        budget_ms = payload_fields.get("budget_ms")
        if root_device_id is not None and (not isinstance(root_device_id, int) or root_device_id <= 0):
            raise DeviceChainError("root_device_id must be a positive integer")
        if budget_ms is not None and (not isinstance(budget_ms, int) or budget_ms < 1 or budget_ms > 5000):
            raise DeviceChainError("budget_ms must be an integer from 1 to 5000")
    payload = {"action": action}
    payload.update({key: value for key, value in payload_fields.items() if value is not None})
    return _request(payload, commit=commit, host=host, command_port=command_port, reply_port=reply_port, timeout=timeout)


def _request(payload: dict[str, Any], *, commit: bool, host: str, command_port: int, reply_port: int, timeout: float) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    mode = "commit" if commit else "dry_run"
    packet = encode_message("/device_chain", [request_id, json.dumps(payload, ensure_ascii=False), mode])
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
                raise DeviceChainTimeoutError(f"No device_chain reply from Ableton Agent Hub on UDP {reply_port}; reload Ableton Agent Hub.amxd")
            reply_socket.settimeout(min(remaining, 0.2))
            try:
                reply_packet, address = reply_socket.recvfrom(65535)
            except socket.timeout:
                continue
            try:
                path, arguments = decode_message(reply_packet)
            except OscDecodeError:
                continue
            if path not in ["/device_chain", "device_chain"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Rack device trees or apply safe Ableton device chain templates")
    parser.add_argument("--action", default="list_templates", choices=["list_templates", "scan_recursive", "apply_template", "apply_parameter_preset"])
    parser.add_argument("--template")
    parser.add_argument("--preset")
    parser.add_argument("--track")
    parser.add_argument("--track-index", type=int, dest="track_index")
    parser.add_argument("--track-id", type=int, dest="track_id")
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("--max-devices", type=int, default=None)
    parser.add_argument("--root-device-id", type=int, default=None)
    parser.add_argument("--budget-ms", type=int, default=None)
    parser.add_argument("--apply-preset", action="store_true")
    parser.add_argument("--allow-duplicate", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    try:
        result = device_chain(
            args.action,
            commit=args.commit,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
            template=args.template,
            preset=args.preset,
            track=int(args.track) if args.track and args.track.isdigit() else args.track,
            track_index=args.track_index,
            track_id=args.track_id,
            max_depth=args.max_depth,
            max_devices=args.max_devices,
            root_device_id=args.root_device_id,
            budget_ms=args.budget_ms,
            apply_preset=args.apply_preset if args.apply_preset else None,
            allow_duplicate=args.allow_duplicate if args.allow_duplicate else None,
        )
    except (DeviceChainError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

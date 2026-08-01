from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message


class ArrangementToolsError(RuntimeError):
    pass


class ArrangementToolsTimeoutError(ArrangementToolsError):
    pass


def arrangement_tools(
    action: str = "scan_region",
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
    return _request_arrangement_tools(
        payload,
        commit=commit,
        host=host,
        command_port=command_port,
        reply_port=reply_port,
        timeout=timeout,
    )


def _request_arrangement_tools(
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
    packet = encode_message("/arrangement_tools", [request_id, json.dumps(payload, ensure_ascii=False), mode])

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
                raise ArrangementToolsTimeoutError(
                    f"No arrangement_tools reply from Ableton Agent Hub on UDP {reply_port}; reload Ableton Agent Hub.amxd"
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
            if path not in ["/arrangement_tools", "arrangement_tools"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or edit Arrangement regions through the unified Hub")
    parser.add_argument(
        "--action",
        default="scan_region",
        choices=["scan_region", "clear_region", "copy_region", "duplicate_region", "rename_region_clip"],
    )
    parser.add_argument("--start", type=float, default=0.0, help="Arrangement beat where the region starts")
    parser.add_argument("--length", type=float, default=32.0, help="Beat length to inspect")
    parser.add_argument("--track", help="Optional track name or zero-based track index")
    parser.add_argument("--target-start", type=float, dest="target_start", help="Destination beat for copy/duplicate actions")
    parser.add_argument("--replace", action="store_true", help="Allow copy/duplicate to replace matching target clips")
    parser.add_argument("--include-partial", action="store_true", help="Allow clear_region to affect whole clips that only partially overlap the region")
    parser.add_argument("--name", help="New clip name for rename_region_clip")
    parser.add_argument("--name-prefix", dest="name_prefix", help="Prefix added by rename_region_clip")
    parser.add_argument("--name-suffix", dest="name_suffix", help="Suffix for copied or renamed clips")
    parser.add_argument("--limit", type=int, help="Maximum clips to return")
    parser.add_argument("--commit", action="store_true", help="Actually change Live. Without this, only dry-runs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    try:
        result = arrangement_tools(
            args.action,
            commit=args.commit,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
            start=args.start,
            length=args.length,
            track=int(args.track) if args.track and args.track.isdigit() else args.track,
            target_start=args.target_start,
            replace=args.replace if args.replace else None,
            include_partial=args.include_partial if args.include_partial else None,
            name=args.name,
            name_prefix=args.name_prefix,
            name_suffix=args.name_suffix,
            limit=args.limit,
        )
    except (ArrangementToolsError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

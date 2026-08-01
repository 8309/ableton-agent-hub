from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message


class MacroParametersError(RuntimeError):
    pass


class MacroParametersTimeoutError(MacroParametersError):
    pass


def macro_parameters(
    action: str = "scan_snapshot",
    *,
    save: Path | None = None,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
    **payload_fields: Any,
) -> dict[str, Any]:
    payload = {"action": action}
    payload.update({key: value for key, value in payload_fields.items() if value is not None})
    result = _request(payload, commit=commit, host=host, command_port=command_port, reply_port=reply_port, timeout=timeout)
    if save is not None and result.get("ok") and result.get("snapshot"):
        save.parent.mkdir(parents=True, exist_ok=True)
        save.write_text(json.dumps(result["snapshot"], indent=2, ensure_ascii=False), encoding="utf-8")
        result["saved_to"] = str(save)
    return result


def _request(payload: dict[str, Any], *, commit: bool, host: str, command_port: int, reply_port: int, timeout: float) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    mode = "commit" if commit else "dry_run"
    packet = encode_message("/macro_parameters", [request_id, json.dumps(payload, ensure_ascii=False), mode])
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
                raise MacroParametersTimeoutError(f"No macro_parameters reply from Ableton Agent Hub on UDP {reply_port}; reload Ableton Agent Hub.amxd")
            reply_socket.settimeout(min(remaining, 0.2))
            try:
                reply_packet, address = reply_socket.recvfrom(65535)
            except socket.timeout:
                continue
            try:
                path, arguments = decode_message(reply_packet)
            except OscDecodeError:
                continue
            if path not in ["/macro_parameters", "macro_parameters"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def _load_snapshot(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan, save, apply, or morph Ableton parameter snapshots")
    parser.add_argument("--action", default="scan_snapshot", choices=["scan_snapshot", "apply_snapshot", "morph_snapshots"])
    parser.add_argument("--track")
    parser.add_argument("--track-index", type=int, dest="track_index")
    parser.add_argument("--device")
    parser.add_argument("--device-index", type=int, dest="device_index")
    parser.add_argument("--snapshot-name")
    parser.add_argument("--snapshot-file", type=Path, help="Snapshot JSON file for apply_snapshot")
    parser.add_argument("--from-snapshot", type=Path, help="Source snapshot JSON file for morph_snapshots")
    parser.add_argument("--to-snapshot", type=Path, help="Target snapshot JSON file for morph_snapshots")
    parser.add_argument("--amount", type=float, help="Morph amount from 0.0 to 1.0")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--save", type=Path)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    snapshot = _load_snapshot(args.snapshot_file) if args.snapshot_file else None
    from_snapshot = _load_snapshot(args.from_snapshot) if args.from_snapshot else None
    to_snapshot = _load_snapshot(args.to_snapshot) if args.to_snapshot else None
    try:
        result = macro_parameters(
            args.action,
            save=args.save,
            commit=args.commit,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
            track=int(args.track) if args.track and args.track.isdigit() else args.track,
            track_index=args.track_index,
            device=args.device,
            device_index=args.device_index,
            snapshot_name=args.snapshot_name,
            snapshot=snapshot,
            from_snapshot=from_snapshot,
            to_snapshot=to_snapshot,
            amount=args.amount,
            limit=args.limit,
        )
    except (MacroParametersError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

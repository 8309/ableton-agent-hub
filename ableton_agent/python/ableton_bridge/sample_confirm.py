from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .reply_port_lock import reply_port_lock


class SampleConfirmError(RuntimeError):
    pass


class SampleConfirmTimeoutError(SampleConfirmError):
    pass


def sample_confirm(
    action: str = "confirm_loaded_sample",
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
    return _request(payload, commit=commit, host=host, command_port=command_port, reply_port=reply_port, timeout=timeout)


def _request(payload: dict[str, Any], *, commit: bool, host: str, command_port: int, reply_port: int, timeout: float) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    mode = "commit" if commit else "dry_run"
    packet = encode_message("/sample_confirm", [request_id, json.dumps(payload, ensure_ascii=False), mode])
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
                raise SampleConfirmTimeoutError(f"No sample_confirm reply from Ableton Agent Hub on UDP {reply_port}; reload Ableton Agent Hub.amxd")
            reply_socket.settimeout(min(remaining, 0.2))
            try:
                reply_packet, address = reply_socket.recvfrom(65535)
            except socket.timeout:
                continue
            try:
                path, arguments = decode_message(reply_packet)
            except OscDecodeError:
                continue
            if path not in ["/sample_confirm", "sample_confirm"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Confirm the sample currently loaded in Simpler or a Drum Rack pad")
    parser.add_argument("--action", default="confirm_loaded_sample", choices=["confirm_loaded_sample", "scan_loaded_samples"])
    parser.add_argument("--track", help="Track name, selected, or zero-based track index")
    parser.add_argument("--track-index", type=int, dest="track_index")
    parser.add_argument("--device", help="Device name")
    parser.add_argument("--device-index", type=int, dest="device_index")
    parser.add_argument("--target", choices=["auto", "simpler", "drum_rack_pad"], default="auto")
    parser.add_argument("--pad-index", type=int, dest="pad_index")
    parser.add_argument("--pad-note", type=int, dest="pad_note")
    parser.add_argument("--candidate-index", type=int, dest="candidate_index")
    parser.add_argument("--limit", type=int, help="Maximum ordinary tracks to scan when no track is specified")
    parser.add_argument("--include-empty", action="store_true", help="Report target Drum Rack pads that exist but have no loaded sample")
    parser.add_argument("--include-drum-rack", action="store_true", help="Allow Drum Rack pad traversal during broad scans")
    parser.add_argument("--intended-path", dest="intended_path")
    parser.add_argument("--commit", action="store_true", help="Accepted for envelope consistency; this command is read-only")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    try:
        result = sample_confirm(
            args.action,
            commit=args.commit,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
            track=int(args.track) if args.track and args.track.isdigit() else args.track,
            track_index=args.track_index,
            device=args.device,
            device_index=args.device_index,
            target=args.target,
            pad_index=args.pad_index,
            pad_note=args.pad_note,
            candidate_index=args.candidate_index,
            limit=args.limit,
            include_empty=args.include_empty if args.include_empty else None,
            include_drum_rack=args.include_drum_rack if args.include_drum_rack else None,
            intended_path=args.intended_path,
        )
    except (SampleConfirmError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .reply_port_lock import reply_port_lock


class ClipVariationError(RuntimeError):
    pass


class ClipVariationTimeoutError(ClipVariationError):
    pass


def clip_variation(
    action: str = "scan_clips",
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
    return _request_clip_variation(
        payload,
        commit=commit,
        host=host,
        command_port=command_port,
        reply_port=reply_port,
        timeout=timeout,
    )


def _request_clip_variation(
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
    packet = encode_message("/clip_variation", [request_id, json.dumps(payload, ensure_ascii=False), mode])

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
                raise ClipVariationTimeoutError(
                    f"No clip_variation reply from Ableton Agent Hub on UDP {reply_port}; reload Ableton Agent Hub.amxd"
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
            if path not in ["/clip_variation", "clip_variation"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Create small Arrangement MIDI clip variations")
    parser.add_argument(
        "--action",
        default="scan_clips",
        choices=["scan_clips", "duplicate_clip", "make_fill", "thin_notes", "mute_notes_in_range"],
    )
    parser.add_argument("--track", help="Optional track name or zero-based track index to scan within")
    parser.add_argument("--candidate-index", type=int, dest="candidate_index", help="Candidate index returned by scan_clips")
    parser.add_argument("--candidate-limit", type=int, dest="candidate_limit")
    parser.add_argument("--clip-id", type=int, dest="clip_id")
    parser.add_argument("--target-start", type=float, dest="target_start", help="Arrangement beat where the variation clip should be written")
    parser.add_argument("--replace", action="store_true", help="Edit the source clip instead of writing a new variation clip")
    parser.add_argument("--name-suffix", dest="name_suffix", default=None)
    parser.add_argument("--start", type=float, help="Only affect notes whose start is at or after this beat in the clip")
    parser.add_argument("--end", type=float, help="Only affect notes whose start is before this beat in the clip")
    parser.add_argument("--pitch-min", type=int, dest="pitch_min")
    parser.add_argument("--pitch-max", type=int, dest="pitch_max")
    parser.add_argument("--keep-every", type=int, dest="keep_every", help="For thin_notes, keep every Nth selected note")
    parser.add_argument("--fill-length", type=float, dest="fill_length", help="For make_fill, final beat length to add extra hits into")
    parser.add_argument("--commit", action="store_true", help="Actually create/edit the variation clip. Without this, only dry-runs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    try:
        result = clip_variation(
            args.action,
            commit=args.commit,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
            track=int(args.track) if args.track and args.track.isdigit() else args.track,
            candidate_index=args.candidate_index,
            candidate_limit=args.candidate_limit,
            clip_id=args.clip_id,
            target_start=args.target_start,
            replace=args.replace if args.replace else None,
            name_suffix=args.name_suffix,
            start=args.start,
            end=args.end,
            pitch_min=args.pitch_min,
            pitch_max=args.pitch_max,
            keep_every=args.keep_every,
            fill_length=args.fill_length,
        )
    except (ClipVariationError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from pathlib import Path
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .sample_index import ensure_sample_available


class SampleLoaderError(RuntimeError):
    pass


class SampleLoaderTimeoutError(SampleLoaderError):
    pass


AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".flac", ".mp3"}


def load_sample(
    *,
    sample_path: str | Path,
    track: str | int = "selected",
    target: str = "simpler",
    scan_browser: bool = False,
    scan_limit: int = 1500,
    commit: bool = False,
    check_index: bool = True,
    category: str | None = None,
    allow_replacement: bool = False,
    debug_browser: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 8.0,
) -> dict[str, Any]:
    path = Path(sample_path)
    if path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise SampleLoaderError("sample_path must end with wav, aif, aiff, flac, or mp3")
    index_check: dict[str, Any] | None = None
    if check_index:
        index_check = ensure_sample_available(
            path,
            preferred_category=category,
            allow_replacement=allow_replacement,
        )
        if not index_check["ok"]:
            candidates = index_check.get("candidates", [])
            hint = f"; {len(candidates)} replacement candidate(s) found" if candidates else ""
            raise SampleLoaderError(f"sample path does not exist after whitelist refresh: {path}{hint}")
        path = Path(index_check["path"])
    payload: dict[str, Any] = {
        "sample_path": str(path),
        "track": track,
        "target": target,
        "scan_browser": scan_browser,
        "scan_limit": scan_limit,
    }
    if debug_browser:
        payload["debug_browser"] = True
    request_id = uuid.uuid4().hex
    mode = "commit" if commit else "dry_run"
    packet = encode_message("/load_sample", [request_id, json.dumps(payload, ensure_ascii=False), mode])

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
                raise SampleLoaderTimeoutError(
                    f"No load_sample reply from Ableton Agent Hub on UDP {reply_port}; "
                    "reload Ableton Agent Hub.amxd in the current Set"
                )
            reply_socket.settimeout(min(remaining, 0.2))
            try:
                reply_packet, address = reply_socket.recvfrom(65535)
            except socket.timeout:
                continue
            try:
                path_name, arguments = decode_message(reply_packet)
            except OscDecodeError:
                continue
            if path_name not in ["/load_sample", "load_sample"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            if index_check is not None:
                result["index_check"] = index_check
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run or load a local audio sample through Ableton Live Browser")
    parser.add_argument("--sample-path", required=True, help="Absolute path to wav/aif/aiff/flac/mp3 sample")
    parser.add_argument("--track", default="selected", help="Track name, index, or selected")
    parser.add_argument(
        "--target",
        default="simpler",
        choices=["simpler", "drum_rack", "drum_rack_pad"],
        help="Load target. Drum Rack pad loading depends on Live's selected pad/focus behavior.",
    )
    parser.add_argument("--scan-browser", action="store_true", help="Dry-run browser search instead of only validating route/track/path")
    parser.add_argument("--scan-limit", type=int, default=1500, help="Maximum BrowserItem count to scan")
    parser.add_argument("--commit", action="store_true", help="Actually load the sample. Without this, only dry-runs.")
    parser.add_argument("--no-index-check", action="store_true", help="Skip local whitelist/path verification")
    parser.add_argument("--category", help="Preferred sample category for replacement suggestions, such as hat or shaker")
    parser.add_argument("--allow-replacement", action="store_true", help="Use the first available replacement if the saved path is gone")
    parser.add_argument("--debug-browser", action="store_true", help="Return Live Browser root diagnostics instead of loading")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()

    track: str | int = int(args.track) if str(args.track).isdigit() else args.track
    try:
        result = load_sample(
            sample_path=args.sample_path,
            track=track,
            target=args.target,
            scan_browser=args.scan_browser,
            scan_limit=args.scan_limit,
            commit=args.commit,
            check_index=not args.no_index_check,
            category=args.category,
            allow_replacement=args.allow_replacement,
            debug_browser=args.debug_browser,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
        )
    except (SampleLoaderError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

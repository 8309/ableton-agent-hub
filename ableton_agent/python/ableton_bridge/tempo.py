from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message


class TempoError(RuntimeError):
    pass


class TempoTimeoutError(TempoError):
    pass


def get_tempo(
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 2.0,
) -> dict[str, Any]:
    return tempo(command_port=command_port, reply_port=reply_port, host=host, timeout=timeout)


def tempo(
    tempo_value: float | None = None,
    *,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 2.0,
) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    payload: dict[str, Any] = {}
    if tempo_value is not None:
        payload["tempo"] = float(tempo_value)
    mode = "commit" if commit else "dry_run"
    packet = encode_message("/tempo", [request_id, json.dumps(payload, ensure_ascii=False), mode])

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
                raise TempoTimeoutError(
                    f"No tempo reply from Ableton Agent Hub or Tempo on UDP {reply_port}; "
                    "reload Ableton Agent Hub.amxd or load Ableton Agent Tempo.amxd in the current Set"
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
            if path not in ["/tempo", "tempo"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            try:
                result = json.loads(str(arguments[1]))
            except json.JSONDecodeError:
                result = {"ok": True, "dry_run": True, "tempo": float(arguments[1]), "changed": False}
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read or set tempo through Ableton Agent Hub.amxd")
    parser.add_argument("--tempo", type=float, help="Target BPM. Without this, reads the current tempo.")
    parser.add_argument("--commit", action="store_true", help="Actually set tempo. Without this, set requests are dry-runs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()

    try:
        result = tempo(
            args.tempo,
            commit=args.commit,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
        )
    except TempoError as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

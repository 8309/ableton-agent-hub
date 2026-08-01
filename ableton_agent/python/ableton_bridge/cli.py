from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .client import AbletonBridgeClient, BridgeError


def parse_payload(value: str) -> dict:
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control Ableton Live through Agent Bridge")
    parser.add_argument("command", help="Bridge command, for example ping, state, or tracks")
    parser.add_argument("payload", nargs="?", default="{}", type=parse_payload)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = AbletonBridgeClient(
        host=args.host,
        command_port=args.command_port,
        reply_port=args.reply_port,
        timeout=args.timeout,
    )
    try:
        result = client.request(args.command, args.payload)
    except BridgeError as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

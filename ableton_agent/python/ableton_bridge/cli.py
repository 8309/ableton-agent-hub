from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .client import AbletonBridgeClient, BridgeError
from .initial_read import InitialReadError, _write_json, initial_read
from .install import install_hub
from .ping import PingError, ping
from .tempo import TempoError, tempo


def parse_payload(value: str) -> dict:
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def add_network_arguments(parser: argparse.ArgumentParser, *, timeout: float = 2.0) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=timeout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control Ableton Live through Ableton Agent Hub")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="action", required=True)

    install_parser = subparsers.add_parser("install", help="Install Hub assets into Ableton's User Library")
    install_parser.add_argument("--destination", type=Path)
    install_parser.add_argument("--dry-run", action="store_true")

    ping_parser = subparsers.add_parser("ping", help="Check whether the Hub is responding")
    add_network_arguments(ping_parser)

    tempo_parser = subparsers.add_parser("tempo", help="Read or preview/set Live's global tempo")
    tempo_parser.add_argument("--tempo", "--bpm", dest="tempo_value", type=float)
    tempo_parser.add_argument("--commit", action="store_true")
    add_network_arguments(tempo_parser)

    initial_parser = subparsers.add_parser(
        "initial-read",
        help="Run a progressive, read-only first scan of the current Live Set",
    )
    initial_parser.add_argument(
        "--depth",
        choices=["progressive", "quick", "full"],
        default="progressive",
    )
    initial_parser.add_argument(
        "--output",
        type=Path,
        default=Path(".ableton-agent/current_set_initial_read.json"),
    )
    initial_parser.add_argument("--include-raw-notes", action="store_true")
    initial_parser.add_argument("--notes-track", action="append", default=[])
    initial_parser.add_argument("--max-note-clips", type=int, default=512)
    initial_parser.add_argument("--ping-timeout", type=float, default=1.5)
    initial_parser.add_argument("--total-timeout", type=float, default=30.0)
    add_network_arguments(initial_parser, timeout=5.0)

    raw_parser = subparsers.add_parser("raw", help="Send a low-level bridge command")
    raw_parser.add_argument("command", help="Bridge command name")
    raw_parser.add_argument("payload", nargs="?", default="{}", type=parse_payload)
    add_network_arguments(raw_parser)
    return parser


def print_result(result: dict, *, stream=None) -> None:
    print(json.dumps(result, indent=2, ensure_ascii=False), file=stream)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "install":
        try:
            result = install_hub(args.destination, dry_run=args.dry_run)
        except (OSError, ValueError) as error:
            print_result({"ok": False, "error": str(error)}, stream=sys.stderr)
            return 1
        print_result(result)
        return 0 if result.get("ok") else 1

    if args.action == "ping":
        try:
            result = ping(
                host=args.host,
                command_port=args.command_port,
                reply_port=args.reply_port,
                timeout=args.timeout,
            )
        except PingError as error:
            print_result({"ok": False, "error": str(error)}, stream=sys.stderr)
            return 1
        print_result({"ok": True, "result": result})
        return 0

    if args.action == "tempo":
        try:
            result = tempo(
                args.tempo_value,
                commit=args.commit,
                host=args.host,
                command_port=args.command_port,
                reply_port=args.reply_port,
                timeout=args.timeout,
            )
        except TempoError as error:
            print_result({"ok": False, "error": str(error)}, stream=sys.stderr)
            return 1
        print_result({"ok": result.get("ok", True), "result": result})
        return 0 if result.get("ok", True) else 1

    if args.action == "initial-read":
        output = args.output.resolve()
        quick_output = output.with_name(f"{output.stem}.quick{output.suffix}")
        for cache_path in (quick_output, output):
            cache_path.unlink(missing_ok=True)
        python_depth = "full" if args.depth == "progressive" else args.depth
        try:
            context = initial_read(
                depth=python_depth,
                include_raw_notes=args.include_raw_notes,
                note_tracks=args.notes_track,
                max_note_clips=args.max_note_clips,
                host=args.host,
                command_port=args.command_port,
                reply_port=args.reply_port,
                timeout=args.timeout,
                ping_timeout=args.ping_timeout,
                total_timeout=args.total_timeout,
                on_quick_ready=lambda value: _write_json(quick_output, value),
            )
            _write_json(output, context)
        except (InitialReadError, OSError, ValueError) as error:
            print_result(
                {"ok": False, "stage": "preflight", "error": str(error)},
                stream=sys.stderr,
            )
            return 1
        print_result(
            {
                "ok": context["status"] == "complete",
                "summary": context["summary"],
                "quick_output": str(quick_output),
                "output": str(output),
            }
        )
        return 0 if context["status"] == "complete" else 1

    client = AbletonBridgeClient(
        host=args.host,
        command_port=args.command_port,
        reply_port=args.reply_port,
        timeout=args.timeout,
    )
    try:
        result = client.request(args.command, args.payload)
    except BridgeError as error:
        print_result({"ok": False, "error": str(error)}, stream=sys.stderr)
        return 1
    print_result({"ok": True, "result": result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message


class InserterError(RuntimeError):
    pass


class InserterTimeoutError(InserterError):
    pass


ROLE_DEVICES = {
    "drums": "Drum Rack",
    "percussion": "Drum Rack",
    "bass": "Operator",
    "chords": "Electric",
    "keys": "Electric",
    "piano": "Electric",
    "lead": "Drift",
    "pad": "Wavetable",
    "synth": "Drift",
    "fm": "Operator",
    "analog": "Analog",
    "wavetable": "Wavetable",
    "meld": "Meld",
    "mallet": "Collision",
    "string": "Tension",
    "sample": "Simpler",
    "sampler": "Simpler",
    "vocal": "Simpler",
    "fx": "Drum Rack",
    "rack": "Instrument Rack",
}

DEVICE_ALIASES = {
    "analog": "Analog",
    "collision": "Collision",
    "drift": "Drift",
    "drumrack": "Drum Rack",
    "drumsampler": "Drum Sampler",
    "electric": "Electric",
    "impulse": "Impulse",
    "instrumentrack": "Instrument Rack",
    "meld": "Meld",
    "operator": "Operator",
    "sampler": "Sampler",
    "simpler": "Simpler",
    "tension": "Tension",
    "wavetable": "Wavetable",
}

ALLOWED_DEVICES = {
    "Analog",
    "Collision",
    "Drift",
    "Drum Rack",
    "Drum Sampler",
    "Electric",
    "Impulse",
    "Instrument Rack",
    "Meld",
    "Operator",
    "Sampler",
    "Simpler",
    "Tension",
    "Wavetable",
}

EFFECT_ROLE_DEVICES = {
    "reverb": "Reverb",
    "room": "Reverb",
    "hybridreverb": "Hybrid Reverb",
    "delay": "Delay",
    "echo": "Echo",
    "compressor": "Compressor",
    "sidechain": "Compressor",
    "glue": "Glue Compressor",
    "limiter": "Limiter",
    "eq": "EQ Eight",
    "eq8": "EQ Eight",
    "filter": "Auto Filter",
    "autofilter": "Auto Filter",
    "saturation": "Saturator",
    "saturator": "Saturator",
    "drive": "Overdrive",
    "overdrive": "Overdrive",
    "utility": "Utility",
    "width": "Utility",
    "gain": "Utility",
    "chorus": "Chorus-Ensemble",
    "redux": "Redux",
    "erosion": "Erosion",
    "beatrepeat": "Beat Repeat",
    "drumbuss": "Drum Buss",
    "amp": "Amp",
    "cabinet": "Cabinet",
    "pedal": "Pedal",
}

EFFECT_ALIASES = {
    "amp": "Amp",
    "autofilter": "Auto Filter",
    "beatrepeat": "Beat Repeat",
    "cabinet": "Cabinet",
    "chorusensemble": "Chorus-Ensemble",
    "compressor": "Compressor",
    "delay": "Delay",
    "drumbuss": "Drum Buss",
    "echo": "Echo",
    "eqeight": "EQ Eight",
    "erosion": "Erosion",
    "gluecompressor": "Glue Compressor",
    "hybridreverb": "Hybrid Reverb",
    "limiter": "Limiter",
    "overdrive": "Overdrive",
    "pedal": "Pedal",
    "redux": "Redux",
    "reverb": "Reverb",
    "saturator": "Saturator",
    "utility": "Utility",
}

ALLOWED_EFFECTS = {
    "Amp",
    "Auto Filter",
    "Beat Repeat",
    "Cabinet",
    "Chorus-Ensemble",
    "Compressor",
    "Delay",
    "Drum Buss",
    "Echo",
    "EQ Eight",
    "Erosion",
    "Glue Compressor",
    "Hybrid Reverb",
    "Limiter",
    "Overdrive",
    "Pedal",
    "Redux",
    "Reverb",
    "Saturator",
    "Utility",
}


def resolve_device(role_or_device: str) -> str:
    normalized = "".join(character for character in role_or_device.lower() if character.isalnum())
    device = ROLE_DEVICES.get(normalized, DEVICE_ALIASES.get(normalized, role_or_device))
    if device not in ALLOWED_DEVICES:
        allowed = ", ".join(sorted(ALLOWED_DEVICES | set(ROLE_DEVICES)))
        raise InserterError(f"{role_or_device!r} is not in the safe inserter whitelist. Allowed: {allowed}")
    return device


def resolve_effect(role_or_effect: str) -> str:
    normalized = "".join(character for character in role_or_effect.lower() if character.isalnum())
    effect = EFFECT_ROLE_DEVICES.get(normalized, EFFECT_ALIASES.get(normalized, role_or_effect))
    if effect not in ALLOWED_EFFECTS:
        allowed = ", ".join(sorted(ALLOWED_EFFECTS | set(EFFECT_ROLE_DEVICES)))
        raise InserterError(f"{role_or_effect!r} is not in the safe audio-effect whitelist. Allowed: {allowed}")
    return effect


def insert_device(
    role_or_device: str,
    *,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 2.0,
) -> dict[str, Any]:
    device = resolve_device(role_or_device)
    mode = "commit" if commit else "dry_run"
    request_id = uuid.uuid4().hex
    packet = encode_message("/insert_device", [request_id, device, mode])

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
                raise InserterTimeoutError(
                    f"No inserter reply from Ableton Agent Inserter on UDP {reply_port}; "
                    "load Ableton Agent Inserter.amxd in the current Set"
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
            if path not in ["/insert_device", "insert_device"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def parse_target(text: str) -> dict[str, Any]:
    parts = [part.strip() for part in text.split("|")]
    if len(parts) != 2:
        raise InserterError("Target format must be track|role_or_device")
    track, role_or_device = parts
    if not track or not role_or_device:
        raise InserterError("Target format must include both track and role_or_device")
    selector: str | int = int(track) if track.isdigit() else track
    return {"track": selector, "role": role_or_device}


def insert_devices(
    targets: list[dict[str, Any]] | None = None,
    *,
    role_or_device: str = "",
    auto_empty: bool = False,
    allow_existing: bool = False,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
) -> dict[str, Any]:
    targets = targets or []
    if not targets and not auto_empty:
        raise InserterError("Provide at least one target or set auto_empty=True")
    if role_or_device:
        resolve_device(role_or_device)
    for target in targets:
        requested = str(target.get("device") or target.get("role") or role_or_device or "")
        if not requested:
            raise InserterError("Each target needs role/device or a default role_or_device")
        resolve_device(requested)

    mode = "commit" if commit else "dry_run"
    request_id = uuid.uuid4().hex
    payload = json.dumps(
        {
            "targets": targets,
            "role": role_or_device,
            "auto_empty": auto_empty,
            "allow_existing": allow_existing,
        },
        ensure_ascii=False,
    )
    packet = encode_message("/insert_devices", [request_id, payload, mode])

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
                raise InserterTimeoutError(
                    f"No batch inserter reply from Ableton Agent Inserter on UDP {reply_port}; "
                    "load Ableton Agent Inserter.amxd in the current Set"
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
            if path not in ["/insert_devices", "insert_devices"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def create_midi_track(
    *,
    name: str = "",
    index: int | None = None,
    role_or_device: str = "",
    select: bool = False,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
) -> dict[str, Any]:
    if index is not None and index < 0:
        raise InserterError("index must be non-negative")
    device = resolve_device(role_or_device) if role_or_device else ""
    payload: dict[str, Any] = {
        "name": name,
        "select": select,
    }
    if index is not None:
        payload["index"] = index
    if device:
        payload["device"] = device
    return _request_json_command(
        "/create_midi_track",
        payload,
        commit=commit,
        host=host,
        command_port=command_port,
        reply_port=reply_port,
        timeout=timeout,
    )


def _request_json_command(
    path: str,
    payload: dict[str, Any],
    *,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
) -> dict[str, Any]:
    mode = "commit" if commit else "dry_run"
    request_id = uuid.uuid4().hex
    packet = encode_message(path, [request_id, json.dumps(payload, ensure_ascii=False), mode])
    expected_paths = [path, path.lstrip("/")]

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
                raise InserterTimeoutError(
                    f"No {path} reply from Ableton Agent Inserter on UDP {reply_port}; "
                    "load Ableton Agent Inserter.amxd in the current Set"
                )
            reply_socket.settimeout(min(remaining, 0.2))
            try:
                reply_packet, address = reply_socket.recvfrom(65535)
            except socket.timeout:
                continue
            try:
                reply_path, arguments = decode_message(reply_packet)
            except OscDecodeError:
                continue
            if reply_path not in expected_paths or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def parse_effect_target(text: str) -> dict[str, Any]:
    parts = [part.strip() for part in text.split("|")]
    if len(parts) != 2:
        raise InserterError("Effect target format must be track|effect_or_role")
    track, role_or_effect = parts
    if not track or not role_or_effect:
        raise InserterError("Effect target format must include both track and effect_or_role")
    selector: str | int = int(track) if track.isdigit() else track
    return {"track": selector, "effect": role_or_effect}


def insert_effect(
    role_or_effect: str,
    *,
    track: str | int = "selected",
    section: str | None = None,
    track_id: int | None = None,
    allow_duplicate: bool = False,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
) -> dict[str, Any]:
    resolve_effect(role_or_effect)
    payload: dict[str, Any] = {
        "track": track,
        "effect": role_or_effect,
        "allow_duplicate": allow_duplicate,
    }
    if section:
        payload["section"] = "main" if section == "master" else section
    if track_id is not None:
        payload["track_id"] = track_id
    return _request_json_command(
        "/insert_effect",
        payload,
        commit=commit,
        host=host,
        command_port=command_port,
        reply_port=reply_port,
        timeout=timeout,
    )


def insert_effects(
    targets: list[dict[str, Any]],
    *,
    role_or_effect: str = "",
    allow_duplicate: bool = False,
    commit: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
) -> dict[str, Any]:
    if not targets:
        raise InserterError("Provide at least one effect target")
    if role_or_effect:
        resolve_effect(role_or_effect)
    for target in targets:
        requested = str(target.get("effect") or target.get("role") or target.get("device") or role_or_effect or "")
        if not requested:
            raise InserterError("Each effect target needs effect/role or a default role_or_effect")
        resolve_effect(requested)
    return _request_json_command(
        "/insert_effects",
        {"targets": targets, "effect": role_or_effect, "allow_duplicate": allow_duplicate},
        commit=commit,
        host=host,
        command_port=command_port,
        reply_port=reply_port,
        timeout=timeout,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Insert whitelisted native Live devices on MIDI tracks")
    parser.add_argument(
        "role_or_device",
        nargs="?",
        default="",
        help="Role or native device for selected track or default batch target: drums, bass, chords, Operator...",
    )
    parser.add_argument("--target", action="append", default=[], help="Batch target as track|role_or_device, e.g. '3-Operator|bass'")
    parser.add_argument("--track", default="selected", help="Track selector for --effect: name, zero-based index, selected, or master")
    parser.add_argument("--section", choices=["track", "return", "main", "master"], help="Track section for --effect")
    parser.add_argument("--track-id", type=int, help="Session-stable target id; required when committing to Return/Main")
    parser.add_argument("--effect", default="", help="Audio effect role/device: reverb, delay, eq, filter, compressor, Utility...")
    parser.add_argument("--effect-target", action="append", default=[], help="Batch effect target as track|effect_or_role")
    parser.add_argument("--create-midi-track", action="store_true", help="Create a new MIDI track")
    parser.add_argument("--name", default="", help="Name for --create-midi-track")
    parser.add_argument("--index", type=int, default=None, help="Insertion index for --create-midi-track; default is the end")
    parser.add_argument("--select", action="store_true", help="Select the created MIDI track")
    parser.add_argument("--allow-duplicate", action="store_true", help="Allow inserting an audio effect even if the target already has it")
    parser.add_argument("--auto-empty", action="store_true", help="Infer devices from all empty MIDI track names and insert them")
    parser.add_argument("--allow-existing", action="store_true", help="Allow inserting even if a target already has an instrument")
    parser.add_argument("--commit", action="store_true", help="Actually insert the device. Without this, only checks readiness.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()

    try:
        if args.effect_target:
            result = insert_effects(
                [parse_effect_target(target) for target in args.effect_target],
                role_or_effect=args.effect,
                allow_duplicate=args.allow_duplicate,
                commit=args.commit,
                host=args.host,
                command_port=args.command_port,
                reply_port=args.reply_port,
                timeout=args.timeout,
            )
        elif args.effect:
            track: str | int = int(args.track) if str(args.track).isdigit() else args.track
            result = insert_effect(
                args.effect,
                track=track,
                section=args.section,
                track_id=args.track_id,
                allow_duplicate=args.allow_duplicate,
                commit=args.commit,
                host=args.host,
                command_port=args.command_port,
                reply_port=args.reply_port,
                timeout=args.timeout,
            )
        elif args.create_midi_track:
            result = create_midi_track(
                name=args.name,
                index=args.index,
                role_or_device=args.role_or_device,
                select=args.select,
                commit=args.commit,
                host=args.host,
                command_port=args.command_port,
                reply_port=args.reply_port,
                timeout=args.timeout,
            )
        elif args.target or args.auto_empty:
            result = insert_devices(
                [parse_target(target) for target in args.target],
                role_or_device=args.role_or_device,
                auto_empty=args.auto_empty,
                allow_existing=args.allow_existing,
                commit=args.commit,
                host=args.host,
                command_port=args.command_port,
                reply_port=args.reply_port,
                timeout=args.timeout,
            )
        else:
            if not args.role_or_device:
                raise InserterError("role_or_device is required for single-track insert")
            result = insert_device(
                args.role_or_device,
                commit=args.commit,
                host=args.host,
                command_port=args.command_port,
                reply_port=args.reply_port,
                timeout=args.timeout,
            )
    except (InserterError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": True, "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

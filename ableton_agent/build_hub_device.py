from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
HUB_PATCH_SOURCE = ROOT / "max" / "agent_hub.maxpat.json"
DEFAULT_TEMPLATE = Path(
    "/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/Misc/Max Devices/Max MIDI Effect.amxd"
)
FALLBACK_TEMPLATE = ROOT / "dist" / "Ableton Agent Hub.amxd"
JAVASCRIPT_SOURCES = [
    ROOT / "max" / name
    for name in (
        "ableton_agent_read_core.js",
        "ableton_agent_snapshot.js",
        "ableton_agent_parameter_summary.js",
        "ableton_agent_mixer_control.js",
        "ableton_agent_inserter.js",
        "ableton_agent_sample_loader.js",
        "ableton_agent_multi_parameter_control.js",
        "ableton_agent_clip_writer.js",
        "ableton_agent_detail_clip_writer.js",
        "ableton_agent_clip_note_tools.js",
        "ableton_agent_clip_variation.js",
        "ableton_agent_arrangement_tools.js",
        "ableton_agent_track_management.js",
        "ableton_agent_routing.js",
        "ableton_agent_scene.js",
        "ableton_agent_device_chain.js",
        "ableton_agent_macro_parameters.js",
        "ableton_agent_meter_monitor.js",
        "ableton_agent_sample_confirm.js",
        "ableton_agent_eq_tools.js",
        "ableton_agent_tempo.js",
        "ableton_agent_transport.js",
        "ableton_agent_locator.js",
    )
]


def _template_prefix(template_path: Path) -> bytes:
    data = template_path.read_bytes()
    marker = data.find(b"ptch")
    if not data.startswith(b"ampf") or marker < 0:
        raise ValueError(f"Unsupported AMXD template: {template_path}")
    return data[:marker]


def extract_patch_json(amxd_path: Path) -> dict:
    data = amxd_path.read_bytes()
    marker = data.find(b"ptch")
    if not data.startswith(b"ampf") or marker < 0 or marker + 8 > len(data):
        raise ValueError(f"Not a supported AMXD file: {amxd_path}")
    length = int.from_bytes(data[marker + 4 : marker + 8], "little")
    payload = data[marker + 8 : marker + 8 + length].rstrip(b"\x00")
    return json.loads(payload.decode("utf-8"))


def build_hub_amxd(
    output_path: Path,
    patch_source: Path = HUB_PATCH_SOURCE,
    template_path: Path = DEFAULT_TEMPLATE,
) -> Path:
    if not template_path.exists():
        template_path = FALLBACK_TEMPLATE
    patch = json.loads(patch_source.read_text(encoding="utf-8"))
    payload = json.dumps(patch, ensure_ascii=False, indent=2).encode("utf-8") + b"\x00"
    container = _template_prefix(template_path) + b"ptch" + len(payload).to_bytes(4, "little") + payload
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(container)
    for source in JAVASCRIPT_SOURCES:
        shutil.copy2(source, output_path.parent / source.name)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Ableton Agent Hub.amxd")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dist" / "Ableton Agent Hub.amxd"
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    args = parser.parse_args()
    print(build_hub_amxd(args.output, template_path=args.template))


if __name__ == "__main__":
    main()

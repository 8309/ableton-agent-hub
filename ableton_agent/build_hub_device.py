from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

from amxd_container import FALLBACK_TEMPLATE, _template_prefix, extract_patch_json


ROOT = Path(__file__).resolve().parent
HUB_PATCH_SOURCE = ROOT / "max" / "agent_hub.maxpat.json"
WINDOWS_HUB_TEMPLATE = (
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    / "Ableton" / "Live 12 Suite" / "Resources" / "Misc"
    / "Max Devices" / "Max MIDI Effect.amxd"
)
MACOS_HUB_TEMPLATE = Path(
    "/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/Misc/Max Devices/Max MIDI Effect.amxd"
)
HUB_DEFAULT_TEMPLATE = WINDOWS_HUB_TEMPLATE if os.name == "nt" else MACOS_HUB_TEMPLATE
JAVASCRIPT_SOURCES = [
    ROOT / "max" / "ableton_agent_dashboard.js",
    ROOT / "max" / "ableton_agent_status_panel.js",
    ROOT / "max" / "ableton_agent_health.js",
    ROOT / "max" / "ableton_agent_creative_control.js",
    ROOT / "max" / "ableton_agent_read_core.js",
    ROOT / "max" / "ableton_agent_device_tree.js",
    ROOT / "max" / "ableton_agent_value_display.js",
    ROOT / "max" / "ableton_agent_ui_input.js",
    ROOT / "max" / "ableton_agent_parameter_diagnostics.js",
    ROOT / "max" / "ableton_agent_snapshot.js",
    ROOT / "max" / "ableton_agent_parameter_summary.js",
    ROOT / "max" / "ableton_agent_mixer_control.js",
    ROOT / "max" / "ableton_agent_inserter.js",
    ROOT / "max" / "ableton_agent_sample_loader.js",
    ROOT / "max" / "ableton_agent_multi_parameter_control.js",
    ROOT / "max" / "ableton_agent_clip_writer.js",
    ROOT / "max" / "ableton_agent_detail_clip_writer.js",
    ROOT / "max" / "ableton_agent_clip_note_tools.js",
    ROOT / "max" / "ableton_agent_clip_variation.js",
    ROOT / "max" / "ableton_agent_arrangement_tools.js",
    ROOT / "max" / "ableton_agent_track_management.js",
    ROOT / "max" / "ableton_agent_routing.js",
    ROOT / "max" / "ableton_agent_scene.js",
    ROOT / "max" / "ableton_agent_device_chain.js",
    ROOT / "max" / "ableton_agent_macro_parameters.js",
    ROOT / "max" / "ableton_agent_meter_monitor.js",
    ROOT / "max" / "ableton_agent_sample_confirm.js",
    ROOT / "max" / "ableton_agent_eq_tools.js",
    ROOT / "max" / "ableton_agent_tempo.js",
    ROOT / "max" / "ableton_agent_transport.js",
    ROOT / "max" / "ableton_agent_locator.js",
]


def add_status_panel(patch: dict) -> None:
    """Tap wire events without placing UI code in the command/reply path."""
    patcher = patch["patcher"]
    boxes = {item["box"]["id"]: item["box"] for item in patcher["boxes"]}
    patcher["openrect"] = [0.0, 0.0, 620.0, 169.0]
    for identifier in ("obj-title", "obj-description", "obj-status", "obj-version"):
        boxes[identifier]["presentation"] = 0
    panel = {"id": "obj-status-panel", "maxclass": "newobj",
             "text": "js ableton_agent_status_panel.js", "numinlets": 2,
             "numoutlets": 4, "patching_rect": [24.0, 680.0, 240.0, 22.0]}
    patcher["boxes"].append({"box": panel})
    patcher["boxes"].append({"box": {
        "id": "obj-dashboard", "maxclass": "jsui",
        "filename": "ableton_agent_dashboard.js", "numinlets": 1, "numoutlets": 0,
        "parameter_enable": 0, "border": 0, "presentation": 1,
        "patching_rect": [24.0, 720.0, 620.0, 148.0],
        "presentation_rect": [0.0, 0.0, 620.0, 148.0]}})
    patcher["lines"].append({"patchline": {
        "source": [panel["id"], 3], "destination": ["obj-dashboard", 0]}})
    taps = []
    for item in patcher["lines"]:
        line = item["patchline"]
        if line["source"] == ["obj-udp-receive", 0]:
            line["order"] = 1
            taps.append({"patchline": {"source": line["source"],
                "destination": [panel["id"], 0], "order": 0}})
        if line["destination"] == ["obj-udp-send", 0] and line["source"][0] != "obj-creative-packet-size":
            line["order"] = 0
            taps.append({"patchline": {"source": line["source"],
                "destination": [panel["id"], 1], "order": 1}})
    patcher["lines"].extend(taps)


def hub_build_version(patch_source: Path = HUB_PATCH_SOURCE, dependency_dir: Path | None = None) -> str:
    digest = hashlib.sha256()
    digest.update((dependency_dir.as_posix() if dependency_dir else "portable").encode("utf-8"))
    for source in [Path(__file__), patch_source, *JAVASCRIPT_SOURCES]:
        digest.update(source.name.encode("utf-8") + b"\x00")
        digest.update(source.read_bytes() + b"\x00")
    return "dev-" + digest.hexdigest()[:12]


def build_hub_amxd(
    output_path: Path,
    patch_source: Path = HUB_PATCH_SOURCE,
    template_path: Path = HUB_DEFAULT_TEMPLATE,
    dependency_dir: Path | None = None,
) -> Path:
    if not template_path.exists() and FALLBACK_TEMPLATE.exists():
        template_path = FALLBACK_TEMPLATE
    patch = json.loads(patch_source.read_text(encoding="utf-8"))
    add_status_panel(patch)
    names = {source.name for source in JAVASCRIPT_SOURCES}
    scripts = {source.name: source.read_text(encoding="utf-8") for source in JAVASCRIPT_SOURCES}
    version = hub_build_version(patch_source, dependency_dir) + ("-local" if dependency_dir else "")
    scripts["ableton_agent_health.js"] = scripts["ableton_agent_health.js"].replace("__HUB_BUILD_ID__", version)
    scripts["ableton_agent_dashboard.js"] = scripts["ableton_agent_dashboard.js"].replace("__HUB_BUILD_ID__", version)
    if dependency_dir is not None:
        if not dependency_dir.is_absolute():
            raise ValueError("dependency_dir must be an absolute installation directory")
        directory = dependency_dir.as_posix()
        for item in patch["patcher"]["boxes"]:
            box = item["box"]
            text = box.get("text", "")
            if box.get("maxclass") == "jsui":
                if box["filename"] not in names:
                    raise ValueError("Unbundled dashboard script")
                box["filename"] = directory + "/" + box["filename"]
            if box.get("maxclass") == "newobj" and text.startswith("js "):
                name = text[3:].strip()
                if name not in names:
                    raise ValueError("Unbundled Hub script: " + name)
                box["text"] = "js " + json.dumps(directory + "/" + name)
        # Max can open a device in a temporary project. Pin both entry scripts
        # and nested includes, without changing the user's global search path.
        for name, source_text in scripts.items():
            for dependency in names:
                source_text = source_text.replace(
                    'include("' + dependency + '")',
                    "include(" + json.dumps(directory + "/" + dependency) + ")")
            scripts[name] = source_text
    patch["patcher"]["dependency_cache"] = [
        {"name": source.name, "bootpath": dependency_dir.as_posix() if dependency_dir else ".",
         "type": "TEXT", "implicit": 1} for source in JAVASCRIPT_SOURCES
    ]
    version_box = next(item["box"] for item in patch["patcher"]["boxes"]
                       if item["box"]["id"] == "obj-version")
    version_box["text"] = "Version: " + version
    payload = json.dumps(patch, ensure_ascii=False, indent=2).encode("utf-8") + b"\x00"
    container = _template_prefix(template_path) + b"ptch" + len(payload).to_bytes(4, "little") + payload
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(container)
    for source in JAVASCRIPT_SOURCES:
        if dependency_dir is None and source.name not in ("ableton_agent_health.js", "ableton_agent_dashboard.js"):
            shutil.copy2(source, output_path.parent / source.name)
        else:
            (output_path.parent / source.name).write_text(scripts[source.name], encoding="utf-8", newline="\n")
    manifest = {"build_id": version, "mode": "local" if dependency_dir else "portable",
                "dependency_dir": dependency_dir.as_posix() if dependency_dir else None,
                "files": {name: hashlib.sha256((output_path.parent / name).read_bytes()).hexdigest()
                          for name in [output_path.name, *sorted(names)]}}
    (output_path.parent / "hub_build_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Ableton Agent Hub.amxd")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "Ableton Agent Hub.amxd")
    parser.add_argument("--template", type=Path, default=HUB_DEFAULT_TEMPLATE)
    parser.add_argument("--dependency-dir", type=Path, help="Local-only absolute JS installation path; not for distribution")
    args = parser.parse_args()
    print(build_hub_amxd(args.output, template_path=args.template, dependency_dir=args.dependency_dir))


if __name__ == "__main__":
    main()

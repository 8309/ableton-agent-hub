"""Export the public Ableton Agent source boundary from a private workspace."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Iterable


HUB_JAVASCRIPT = (
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

STATIC_FILES = (
    "ableton_agent/max/agent_hub.maxpat.json",
    "ableton_agent/dist/Ableton Agent Hub.amxd",
    "ableton_agent/sound_catalog/README.md",
    "docs/api_capability_matrix.md",
    "docs/group_track_workflow.md",
    "docs/hub_workflow.md",
    "tests/test_ableton_bridge.py",
    "tests/fixtures/.gitkeep",
)

GLOB_RULES = (
    "ableton_agent/python/ableton_bridge/*.py",
    "ableton_agent/schemas/*.md",
    "ableton_agent/styles/*.json",
)

FORBIDDEN_DESTINATIONS = (
    "AGENTS.md",
    "SESSION_HANDOFF.md",
    "projects",
    "experiments",
    "ableton_agent/legacy",
    "ableton_agent/disabled_backup",
    "ableton_agent/sample_index/local_sample_index.json",
    "ableton_agent/sound_catalog/local_sound_catalog.json",
    "ableton_agent/sound_catalog/local_sound_catalog_summary.md",
)

FORBIDDEN_TEXT_PATTERNS = (
    (
        "named Windows user profile",
        re.compile(
            r"[A-Za-z]:[\\/]+Users[\\/]+(?!example(?:[\\/]|$)|username(?:[\\/]|$)|path(?:[\\/]|$))[^\\/\s]+",
            re.IGNORECASE,
        ),
    ),
    (
        "private workspace path",
        re.compile(
            r"[A-Za-z]:[\\/]+Documents[\\/]+codex[_-]f(?:[\\/]|$)",
            re.IGNORECASE,
        ),
    ),
    (
        "private workspace name",
        re.compile("ableton_agent_" + "workspace", re.IGNORECASE),
    ),
)

PUBLIC_TEST_PATH = Path("tests/test_ableton_bridge.py")
LEGACY_DEVICE_TEST_METHODS = {
    "test_builds_amxd_with_required_bridge_objects",
    "test_builds_ping_only_amxd_without_js_or_liveapi",
    "test_builds_notes_amxd_without_js_or_liveapi",
    "test_builds_tempo_amxd_with_deferred_liveapi_reader",
    "test_builds_clip_amxd_with_deferred_liveapi_reader",
    "test_builds_note_reader_amxd_with_deferred_liveapi_reader",
    "test_builds_clip_writer_amxd_with_deferred_liveapi_writer",
    "test_builds_detail_clip_writer_amxd_with_deferred_liveapi_writer",
    "test_builds_universal_clip_writer_amxd_with_session_and_detail_writers",
    "test_builds_tracks_amxd_with_deferred_liveapi_reader",
    "test_builds_snapshot_amxd_with_deferred_whole_set_reader",
    "test_builds_devices_amxd_with_deferred_liveapi_reader",
    "test_builds_parameters_amxd_with_deferred_liveapi_reader",
    "test_builds_parameter_summary_amxd_with_deferred_liveapi_reader",
    "test_builds_parameter_control_amxd_with_deferred_writer",
    "test_builds_multi_parameter_control_amxd_with_deferred_writer",
    "test_builds_mixer_control_amxd_with_deferred_writer",
    "test_builds_inserter_amxd_with_deferred_whitelisted_writer",
    "test_max_script_declares_mvp_commands",
    "test_step15_docs_cover_hub_capabilities_and_sample_limits",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_export_files(source: Path) -> list[Path]:
    relative_paths = {Path(value) for value in STATIC_FILES}
    relative_paths.update(
        Path("ableton_agent/max") / name for name in HUB_JAVASCRIPT
    )
    relative_paths.update(
        Path("ableton_agent/dist") / name for name in HUB_JAVASCRIPT
    )
    for pattern in GLOB_RULES:
        relative_paths.update(path.relative_to(source) for path in source.glob(pattern))
    missing = [path for path in sorted(relative_paths) if not (source / path).is_file()]
    if missing:
        formatted = "\n".join(f"- {path.as_posix()}" for path in missing)
        raise FileNotFoundError(f"Required public export files are missing:\n{formatted}")
    return sorted(relative_paths)


def ensure_isolated(source: Path, destination: Path) -> None:
    if source == destination or destination.is_relative_to(source):
        raise ValueError("The public destination must be outside the private workspace")
    for relative in FORBIDDEN_DESTINATIONS:
        if (destination / relative).exists():
            raise ValueError(f"Forbidden public path exists: {relative}")


def scan_text_files(paths: Iterable[Path], destination: Path) -> None:
    violations: list[str] = []
    for path in paths:
        if path.suffix.lower() not in {".py", ".js", ".json", ".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in FORBIDDEN_TEXT_PATTERNS:
            if pattern.search(text):
                relative = path.relative_to(destination).as_posix()
                violations.append(f"{relative}: contains {label}")
    if violations:
        formatted = "\n".join(f"- {violation}" for violation in violations)
        raise ValueError(f"Private path scan failed:\n{formatted}")


def export_public_tests(source_path: Path, destination_path: Path) -> None:
    text = source_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    removed_lines: set[int] = set()
    found: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "DevicePackageTest":
            continue
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if child.name not in LEGACY_DEVICE_TEST_METHODS:
                continue
            found.add(child.name)
            start = min(
                [child.lineno]
                + [decorator.lineno for decorator in child.decorator_list]
            )
            end = child.end_lineno or child.lineno
            removed_lines.update(range(start - 1, end))
    missing = LEGACY_DEVICE_TEST_METHODS - found
    if missing:
        raise ValueError(
            "Legacy test filter is stale; methods were not found: "
            + ", ".join(sorted(missing))
        )
    filtered = "".join(
        line for index, line in enumerate(lines) if index not in removed_lines
    )
    filtered = filtered.replace(
        "from build_device import extract_patch_json",
        "from build_hub_device import extract_patch_json",
    )
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_text(filtered, encoding="utf-8", newline="\n")


def git_value(source: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def export(source: Path, destination: Path, *, dry_run: bool = False) -> dict:
    source = source.resolve()
    destination = destination.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Private workspace does not exist: {source}")
    ensure_isolated(source, destination)
    relative_paths = resolve_export_files(source)
    scan_text_files((source / path for path in relative_paths), source)

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "file_count": len(relative_paths),
            "files": [path.as_posix() for path in relative_paths],
        }

    destination.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for relative in relative_paths:
        source_path = source / relative
        destination_path = destination / relative
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if relative == PUBLIC_TEST_PATH:
            export_public_tests(source_path, destination_path)
        else:
            shutil.copy2(source_path, destination_path)
        copied.append(destination_path)

    scan_text_files(copied, destination)
    manifest = {
        "schema_version": 1,
        "source_commit": git_value(source, "rev-parse", "HEAD"),
        "source_has_working_tree_overlay": bool(
            git_value(source, "status", "--porcelain")
        ),
        "exported_file_count": len(copied),
        "files": {
            path.relative_to(destination).as_posix(): sha256(path) for path in copied
        },
    }
    manifest_path = destination / "PUBLIC_EXPORT_MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "dry_run": False, **manifest}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Copy the allowlisted Ableton Agent source into this public repo"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = export(args.source, args.destination, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Iterable


ABLETON_AGENT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ABLETON_AGENT_ROOT / "sound_catalog"
LOCAL_CATALOG = CATALOG_DIR / "local_sound_catalog.json"
LOCAL_SUMMARY = CATALOG_DIR / "local_sound_catalog_summary.md"
LOCAL_DATABASE = CATALOG_DIR / "local_sound_catalog.sqlite3"

FALLBACK_ROOTS = (
    Path.home() / "Documents" / "Ableton" / "Factory Packs",
    Path.home() / "Documents" / "Ableton" / "User Library",
    Path("C:/Program Files/Common Files/VST3"),
    Path("C:/Program Files/VstPlugins"),
)


def default_roots() -> tuple[Path, ...]:
    """Resolve Live's current Pack location while keeping portable fallbacks."""
    from .sound_catalog_db import find_latest_library_config, parse_library_config

    library = parse_library_config(find_latest_library_config())
    configured = library.get("preferred_factory_packs_path")
    factory_packs = Path(configured) if configured else FALLBACK_ROOTS[0]
    return (factory_packs, *FALLBACK_ROOTS[1:])

PRESET_EXTENSIONS = {".adg", ".adv", ".amxd", ".fxp", ".vstpreset"}
PLUGIN_EXTENSIONS = {".vst3", ".dll", ".clap"}
AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".flac", ".mp3"}
LIVE_CONTENT_EXTENSIONS = {
    ".alc": "live_clip",
    ".als": "live_set",
    ".agr": "groove",
    ".mid": "midi_file",
    ".midi": "midi_file",
    ".ascl": "tuning",
    ".scl": "tuning",
}

ROLE_PATTERNS = {
    "drums": re.compile(r"\b(?:drum|kit|kick|snare|clap)\b", re.IGNORECASE),
    "percussion": re.compile(r"\b(?:perc|percussion|hat|shaker|rim|cymbal)\b", re.IGNORECASE),
    "bass": re.compile(r"\b(?:bass|sub|808)\b", re.IGNORECASE),
    "chords": re.compile(r"\b(?:chord|stab|keys|piano|rhodes)\b", re.IGNORECASE),
    "lead": re.compile(r"\b(?:lead|hook|pluck|solo)\b", re.IGNORECASE),
    "pad": re.compile(r"\b(?:pad|atmosphere|ambient|texture|string)\b", re.IGNORECASE),
    "vocal": re.compile(r"\b(?:vocal|voice|choir|vox)\b", re.IGNORECASE),
    "fx": re.compile(r"\b(?:fx|effect|riser|impact|noise|sweep)\b", re.IGNORECASE),
}


def scan_sound_catalog(
    roots: Iterable[str | Path] | None = None,
    *,
    output_path: str | Path | None = LOCAL_CATALOG,
    summary_path: str | Path | None = LOCAL_SUMMARY,
) -> dict[str, Any]:
    roots = default_roots() if roots is None else roots
    resources: list[dict[str, Any]] = []
    packs: list[dict[str, Any]] = []
    root_results: list[dict[str, Any]] = []
    for root_value in roots:
        root = Path(root_value)
        if not root.exists():
            root_results.append({"path": str(root), "exists": False, "resource_count": 0})
            continue
        root_kind = _root_kind(root)
        before = len(resources)
        if root_kind == "ableton_factory_packs":
            for pack_dir in sorted((path for path in root.iterdir() if path.is_dir()), key=lambda path: path.name.casefold()):
                pack_resources = list(_scan_tree(pack_dir, root_kind, pack_dir.name))
                resources.extend(pack_resources)
                packs.append(_pack_record(pack_dir, pack_resources))
        else:
            resources.extend(_scan_tree(root, root_kind, None))
        root_results.append({"path": str(root), "exists": True, "kind": root_kind, "resource_count": len(resources) - before})

    resources.sort(key=lambda item: str(item["path"]).casefold())
    kind_counts = Counter(item["kind"] for item in resources)
    role_counts: Counter[str] = Counter()
    for item in resources:
        role_counts.update(item["roles"])
    catalog = {
        "schema_version": 2,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "local_machine",
        "roots": root_results,
        "summary": {
            "pack_count": len(packs),
            "resource_count": len(resources),
            "kind_counts": dict(sorted(kind_counts.items())),
            "role_counts": dict(sorted(role_counts.items())),
        },
        "capability_levels": {
            "discovered": "The path exists in the local catalog.",
            "manual_load": "Load through Live's Browser or the plugin chooser.",
            "control_after_load": "The Agent may inspect exposed parameters after the device is loaded.",
            "auto_insert": "Reserved for separately whitelisted and Live-validated devices; discovery alone does not grant it.",
        },
        "packs": packs,
        "resources": resources,
    }
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    if summary_path is not None:
        destination = Path(summary_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_summary(catalog), encoding="utf-8")
    return catalog


def load_catalog(path: str | Path = LOCAL_CATALOG) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def search_catalog(
    catalog: dict[str, Any], *, query: str | None = None, role: str | None = None,
    kind: str | None = None, pack: str | None = None, limit: int = 20,
) -> list[dict[str, Any]]:
    terms = [term for term in re.split(r"\s+", str(query or "").casefold()) if term]
    wanted_role = str(role or "").casefold()
    wanted_kind = str(kind or "").casefold()
    wanted_pack = str(pack or "").casefold()
    matches = []
    for item in catalog.get("resources", []):
        haystack = " ".join((str(item.get("name", "")), str(item.get("path", "")))).casefold()
        if terms and any(term not in haystack for term in terms):
            continue
        if wanted_role and wanted_role not in {str(value).casefold() for value in item.get("roles", [])}:
            continue
        if wanted_kind and wanted_kind != str(item.get("kind", "")).casefold():
            continue
        if wanted_pack and wanted_pack not in str(item.get("pack", "")).casefold():
            continue
        matches.append(item)
    return matches[: max(1, limit)]


def render_summary(catalog: dict[str, Any], database: dict[str, Any] | None = None) -> str:
    summary = catalog.get("summary", {})
    lines = [
        "# Local Sound Catalog Summary", "",
        f"Generated: {catalog.get('generated_at', '')}", "",
        "This is the machine-specific inventory all creative and development",
        "sessions in this workspace should read before recommending sounds.",
        "Refresh it after installing, updating, moving, or removing Packs.", "",
        "## Scan Scope", "",
        f"- Ableton Packs: {summary.get('pack_count', 0)}",
        f"- Indexed resources: {summary.get('resource_count', 0)}",
        f"- Kind counts: {json.dumps(summary.get('kind_counts', {}), ensure_ascii=False)}",
        f"- Role counts: {json.dumps(summary.get('role_counts', {}), ensure_ascii=False)}",
        "- External drives: excluded unless explicitly supplied with `--root`", "",
        "| Root | Exists | Indexed resources |", "| --- | --- | ---: |",
    ]
    for root in catalog.get("roots", []):
        lines.append(
            f"| `{root.get('path', '')}` | {'yes' if root.get('exists') else 'no'} | "
            f"{root.get('resource_count', 0)} |"
        )
    if database:
        counts = database.get("counts", {})
        lines.extend([
            "", "## Agent Database", "",
            f"- SQLite path: `{database.get('database_path', '')}`",
            f"- Registered Packs: {database.get('registered_packs', 0)}",
            f"- Resources: {counts.get('resources', 0)}",
            f"- Unique tags: {counts.get('tags', 0)}",
            f"- Tag assignments: {counts.get('resource_tags', 0)}",
            f"- Resources with official Ableton XMP tags: "
            f"{database.get('official_tagged_resources', 0)}",
            f"- Unmatched Ableton XMP items: {database.get('unmatched_xmp_items', 0)}",
            f"- Live registry: {database.get('library_creator') or '-'}",
            f"- Audio metadata rows: {counts.get('audio_features', 0)} "
            f"(analyzed {database.get('audio_analyzed', 0)}, "
            f"reused {database.get('audio_reused', 0)}, "
            f"errors {database.get('audio_errors', 0)})",
            f"- Parsed preset rows: {counts.get('preset_details', 0)} "
            f"(parsed {database.get('presets_parsed', 0)}, "
            f"reused {database.get('presets_reused', 0)}, "
            f"errors {database.get('preset_errors', 0)})",
            f"- Resolved preset resource links: {counts.get('resource_links', 0)} "
            f"(unresolved references {database.get('resource_links_unresolved', 0)})",
            "",
            "Official XMP tags use confidence `1.0`. Filename/path role tags use",
            "confidence `0.55` and must be treated as inferred hints. BPM, key,",
            "root-note, and loop fields also retain their own inference confidence",
            "and provenance; audio header fields come from file headers.",
        ])
    lines.extend([
        "", "## Ableton Packs", "",
        "| Pack | Disk size | Files | Indexed | Presets | Samples | Clips | MIDI | M4L | Main roles |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for pack in catalog.get("packs", []):
        kinds = pack.get("kind_counts", {})
        roles = pack.get("role_counts", {})
        main_roles = sorted(roles, key=lambda role: (-int(roles[role]), role))[:5]
        lines.append(
            f"| {pack['name']} | {_human_size(pack.get('disk_size_bytes', 0))} | "
            f"{pack.get('disk_file_count', 0)} | {pack.get('resource_count', 0)} | "
            f"{kinds.get('ableton_preset', 0)} | {kinds.get('audio_sample', 0)} | "
            f"{kinds.get('live_clip', 0)} | {kinds.get('midi_file', 0)} | "
            f"{kinds.get('max_for_live_device', 0)} | {', '.join(main_roles) or '-'} |"
        )
    lines.extend(["", "## Pack Details", ""])
    for pack in catalog.get("packs", []):
        kinds = pack.get("kind_counts", {})
        role_counts = pack.get("role_counts", {})
        lines.extend([
            f"### {pack['name']}", "",
            f"- Path: `{pack.get('path', '')}`",
            f"- Disk footprint: {_human_size(pack.get('disk_size_bytes', 0))} across "
            f"{pack.get('disk_file_count', 0)} files",
            f"- Recognized resources: {pack.get('resource_count', 0)} "
            f"({kinds.get('ableton_preset', 0)} presets, "
            f"{kinds.get('audio_sample', 0)} samples, "
            f"{kinds.get('live_clip', 0)} Live Clips, "
            f"{kinds.get('midi_file', 0)} MIDI files, "
            f"{kinds.get('max_for_live_device', 0)} Max for Live devices)",
            f"- Role index: {_format_counts(role_counts)}",
            f"- Top-level folders: {', '.join(pack.get('top_level_directories', [])) or '-'}",
            f"- Example presets/devices: {', '.join(pack.get('preset_examples', [])) or '-'}",
            f"- Example samples: {', '.join(pack.get('sample_examples', [])) or '-'}",
            "- Loading: manual through Live's Browser; catalog discovery does not grant auto-insert",
            "",
        ])
    plugins = [item for item in catalog.get("resources", []) if item.get("kind") == "plugin"]
    lines.extend(["", "## Plugins", "", "| Plugin | Load | Agent control |", "| --- | --- | --- |"])
    for plugin in plugins:
        lines.append(f"| {plugin['name']} | {plugin['load_mode']} | {plugin['agent_control']} |")
    if not plugins:
        lines.append("| None discovered | - | - |")
    lines.extend([
        "", "## Update Workflow", "",
        "From the repository root:", "",
        "```powershell",
        "$env:PYTHONPATH='ableton_agent/python'",
        "python -m ableton_bridge.sound_catalog scan",
        "```", "",
        "If the system Python is unavailable in this workspace, use the verified",
        "shared interpreter:", "",
        "```powershell",
        "$env:PYTHONPATH='ableton_agent/python'",
        "& '.\\experiments\\text2midi\\.venv\\Scripts\\python.exe' -m ableton_bridge.sound_catalog scan",
        "```", "",
        "Then verify the Pack count against Live's `Packs` browser section and",
        "spot-check any newly installed Pack before creative use. Search without",
        "rescanning with:", "",
        "```powershell",
        "python -m ableton_bridge.sound_catalog search --pack \"Pack Name\" --kind ableton_preset",
        "python -m ableton_bridge.sound_catalog search --role drums --kind audio_sample",
        "python -m ableton_bridge.sound_catalog search --bpm-min 124 --bpm-max 130 --loop",
        "python -m ableton_bridge.sound_catalog search --device Simpler --kind ableton_preset",
        "```", "",
        "## Capability Boundary", "",
        "- Discovery does not grant automatic insertion.",
        "- Verify a path immediately before recommending it.",
        "- Presets, Packs, and third-party plugins are loaded manually unless a",
        "  separate Hub capability is Live-validated in the capability matrix.",
        "- Role counts are filename/path heuristics, not Ableton's complete tag database.",
        "- BPM, key, root-note, and loop inference are filename/path hints, not",
        "  acoustic analysis.",
        "- The JSON catalog is the searchable detail source; this Markdown file is",
        "  the shared human-readable entry point.", "",
    ])
    return "\n".join(lines)


def _scan_tree(root: Path, root_kind: str, pack: str | None) -> Iterable[dict[str, Any]]:
    plugin_bundles: set[str] = set()
    for path in root.rglob("*"):
        suffix = path.suffix.casefold()
        is_plugin_bundle = path.is_dir() and suffix in {".vst3", ".clap"}
        if not path.is_file() and not is_plugin_bundle:
            continue
        if any(str(path).casefold().startswith(bundle + "\\") for bundle in plugin_bundles):
            continue
        kind = _resource_kind(path, root_kind)
        if kind is None:
            continue
        if is_plugin_bundle:
            plugin_bundles.add(str(path).casefold())
        text = " ".join(path.parts[-7:])
        stat = path.stat()
        agent_control = (
            "control_after_load"
            if kind in {"plugin", "ableton_preset", "max_for_live_device"}
            else "sample_workflow"
            if kind == "audio_sample"
            else "manual_load_only"
        )
        yield {
            "name": path.stem if suffix else path.name,
            "path": str(path),
            "extension": suffix,
            "kind": kind,
            "source": root_kind,
            "pack": pack,
            "roles": _infer_roles(text),
            "exists": True,
            "load_mode": "manual_load",
            "agent_control": agent_control,
            "auto_insert": False,
            "size_bytes": stat.st_size if path.is_file() else 0,
            "mtime_ns": stat.st_mtime_ns,
        }


def _resource_kind(path: Path, root_kind: str) -> str | None:
    suffix = path.suffix.casefold()
    if suffix in PLUGIN_EXTENSIONS and root_kind == "plugin_directory":
        return "plugin"
    if suffix == ".amxd":
        return "max_for_live_device"
    if suffix in PRESET_EXTENSIONS:
        return "ableton_preset"
    if suffix in AUDIO_EXTENSIONS:
        return "audio_sample"
    if suffix in LIVE_CONTENT_EXTENSIONS:
        return LIVE_CONTENT_EXTENSIONS[suffix]
    return None


def _root_kind(root: Path) -> str:
    text = str(root).casefold()
    if "factory packs" in text:
        return "ableton_factory_packs"
    if "user library" in text:
        return "ableton_user_library"
    return "plugin_directory"


def _infer_roles(text: str) -> list[str]:
    return [role for role, pattern in ROLE_PATTERNS.items() if pattern.search(text)]


def _pack_record(pack_dir: Path, resources: list[dict[str, Any]]) -> dict[str, Any]:
    kind_counts = Counter(item["kind"] for item in resources)
    role_counts: Counter[str] = Counter()
    for item in resources:
        role_counts.update(item["roles"])
    all_files = [path for path in pack_dir.rglob("*") if path.is_file()]
    presets = [
        item["name"] for item in resources
        if item["kind"] in {"ableton_preset", "max_for_live_device"}
    ]
    samples = [item["name"] for item in resources if item["kind"] == "audio_sample"]
    return {
        "name": pack_dir.name,
        "path": str(pack_dir),
        "exists": True,
        "resource_count": len(resources),
        "kind_counts": dict(sorted(kind_counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
        "roles": sorted({role for item in resources for role in item["roles"]}),
        "disk_file_count": len(all_files),
        "disk_size_bytes": sum(path.stat().st_size for path in all_files),
        "top_level_directories": sorted(
            path.name for path in pack_dir.iterdir() if path.is_dir()
        ),
        "preset_examples": presets[:4],
        "sample_examples": samples[:4],
        "load_mode": "ableton_browser",
        "auto_insert": False,
    }


def _human_size(value: int | float) -> str:
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def _format_counts(values: dict[str, Any]) -> str:
    if not values:
        return "-"
    ordered = sorted(values.items(), key=lambda item: (-int(item[1]), item[0]))
    return ", ".join(f"{name} {count}" for name, count in ordered)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan or search the local Ableton sound catalog")
    parser.add_argument(
        "action",
        choices=["scan", "summary", "search", "build-db", "db-stats"],
        nargs="?",
        default="summary",
    )
    parser.add_argument("--root", action="append", default=[])
    parser.add_argument("--catalog", default=str(LOCAL_CATALOG))
    parser.add_argument("--database", default=str(LOCAL_DATABASE))
    parser.add_argument("--library-config")
    parser.add_argument("--query")
    parser.add_argument("--role")
    parser.add_argument("--kind")
    parser.add_argument("--pack")
    parser.add_argument("--official-tag")
    parser.add_argument("--bpm-min", type=float)
    parser.add_argument("--bpm-max", type=float)
    parser.add_argument("--key")
    parser.add_argument("--root-note")
    parser.add_argument("--duration-min", type=float)
    parser.add_argument("--duration-max", type=float)
    loop_group = parser.add_mutually_exclusive_group()
    loop_group.add_argument("--loop", dest="is_loop", action="store_true")
    loop_group.add_argument("--one-shot", dest="is_loop", action="store_false")
    parser.set_defaults(is_loop=None)
    parser.add_argument("--device")
    parser.add_argument("--rack-type")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.action == "scan":
        from .sound_catalog_db import build_catalog_database

        catalog = scan_sound_catalog(args.root or None, output_path=args.catalog)
        database = build_catalog_database(
            catalog,
            database_path=args.database,
            library_config_path=args.library_config,
            source_json=args.catalog,
        )
        LOCAL_SUMMARY.write_text(render_summary(catalog, database), encoding="utf-8")
        result = {
            "ok": True,
            "catalog_path": str(Path(args.catalog)),
            "summary_path": str(LOCAL_SUMMARY),
            "database": database,
            "roots": catalog["roots"],
            "summary": catalog["summary"],
        }
    elif args.action == "build-db":
        from .sound_catalog_db import build_catalog_database

        catalog = load_catalog(args.catalog)
        result = build_catalog_database(
            catalog,
            database_path=args.database,
            library_config_path=args.library_config,
            source_json=args.catalog,
        )
        LOCAL_SUMMARY.write_text(render_summary(catalog, result), encoding="utf-8")
    elif args.action == "db-stats":
        from .sound_catalog_db import database_stats

        result = {"ok": True, **database_stats(args.database)}
    elif args.action == "search" and Path(args.database).exists():
        from .sound_catalog_db import search_database

        result = {
            "ok": True,
            "backend": "sqlite",
            "database_path": str(Path(args.database)),
            "matches": search_database(
                args.database,
                query=args.query,
                role=args.role,
                kind=args.kind,
                pack=args.pack,
                official_tag=args.official_tag,
                bpm_min=args.bpm_min,
                bpm_max=args.bpm_max,
                key=args.key,
                root_note=args.root_note,
                duration_min=args.duration_min,
                duration_max=args.duration_max,
                is_loop=args.is_loop,
                device=args.device,
                rack_type=args.rack_type,
                limit=args.limit,
            ),
        }
    else:
        catalog = load_catalog(args.catalog)
        result = catalog.get("summary", {}) if args.action == "summary" else {
            "ok": True,
            "backend": "json",
            "matches": search_catalog(catalog, query=args.query, role=args.role, kind=args.kind, pack=args.pack, limit=args.limit),
        }
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

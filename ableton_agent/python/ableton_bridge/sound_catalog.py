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

DEFAULT_ROOTS = (
    Path.home() / "Documents" / "Ableton" / "Factory Packs",
    Path.home() / "Documents" / "Ableton" / "User Library",
    Path("C:/Program Files/Common Files/VST3"),
    Path("C:/Program Files/VstPlugins"),
)

PRESET_EXTENSIONS = {".adg", ".adv", ".amxd", ".fxp", ".vstpreset"}
PLUGIN_EXTENSIONS = {".vst3", ".dll", ".clap"}
AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".flac", ".mp3"}

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
    roots: Iterable[str | Path] = DEFAULT_ROOTS,
    *,
    output_path: str | Path | None = LOCAL_CATALOG,
    summary_path: str | Path | None = LOCAL_SUMMARY,
) -> dict[str, Any]:
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
        "schema_version": 1,
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


def render_summary(catalog: dict[str, Any]) -> str:
    summary = catalog.get("summary", {})
    lines = [
        "# Local Sound Catalog Summary", "",
        f"Generated: {catalog.get('generated_at', '')}", "",
        f"- Ableton Packs: {summary.get('pack_count', 0)}",
        f"- Indexed resources: {summary.get('resource_count', 0)}",
        f"- Kind counts: {json.dumps(summary.get('kind_counts', {}), ensure_ascii=False)}",
        f"- Role counts: {json.dumps(summary.get('role_counts', {}), ensure_ascii=False)}",
        "", "## Ableton Packs", "",
        "| Pack | Resources | Roles |", "| --- | ---: | --- |",
    ]
    for pack in catalog.get("packs", []):
        lines.append(f"| {pack['name']} | {pack['resource_count']} | {', '.join(pack.get('roles', [])) or '-'} |")
    plugins = [item for item in catalog.get("resources", []) if item.get("kind") == "plugin"]
    lines.extend(["", "## Plugins", "", "| Plugin | Load | Agent control |", "| --- | --- | --- |"])
    for plugin in plugins:
        lines.append(f"| {plugin['name']} | {plugin['load_mode']} | {plugin['agent_control']} |")
    if not plugins:
        lines.append("| None discovered | - | - |")
    lines.extend(["", "Discovery does not grant automatic insertion. Use the search CLI for", "specific presets or samples, then verify the path before recommending it.", ""])
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
            "agent_control": "control_after_load" if kind in {"plugin", "ableton_preset", "max_for_live_device"} else "sample_workflow",
            "auto_insert": False,
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
    return {
        "name": pack_dir.name,
        "path": str(pack_dir),
        "exists": True,
        "resource_count": len(resources),
        "kind_counts": dict(sorted(kind_counts.items())),
        "roles": sorted({role for item in resources for role in item["roles"]}),
        "load_mode": "ableton_browser",
        "auto_insert": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan or search the local Ableton sound catalog")
    parser.add_argument("action", choices=["scan", "summary", "search"], nargs="?", default="summary")
    parser.add_argument("--root", action="append", default=[])
    parser.add_argument("--catalog", default=str(LOCAL_CATALOG))
    parser.add_argument("--query")
    parser.add_argument("--role")
    parser.add_argument("--kind")
    parser.add_argument("--pack")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.action == "scan":
        catalog = scan_sound_catalog(args.root or DEFAULT_ROOTS, output_path=args.catalog)
        result = {
            "ok": True,
            "catalog_path": str(Path(args.catalog)),
            "summary_path": str(LOCAL_SUMMARY),
            "roots": catalog["roots"],
            "summary": catalog["summary"],
        }
    else:
        catalog = load_catalog(args.catalog)
        result = catalog.get("summary", {}) if args.action == "summary" else {
            "ok": True,
            "matches": search_catalog(catalog, query=args.query, role=args.role, kind=args.kind, pack=args.pack, limit=args.limit),
        }
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Iterable


AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".flac", ".mp3"}
PRESET_EXTENSIONS = {".adg", ".adv", ".amxd"}
CLIP_EXTENSIONS = {".alc"}
INDEXED_EXTENSIONS = AUDIO_EXTENSIONS | PRESET_EXTENSIONS | CLIP_EXTENSIONS

CATEGORY_PATTERNS = {
    "hat": re.compile(r"\b(?:hat|hihat|hi hat|hi-hat|closed|open)\b", re.IGNORECASE),
    "shaker": re.compile(r"\bshak(?:e|er)", re.IGNORECASE),
    "rim": re.compile(r"\b(?:rim|rimshot)\b", re.IGNORECASE),
    "perc": re.compile(r"\b(?:perc|percussion|clave|conga|bongo|tom|wood|click|tick)\b", re.IGNORECASE),
    "clap": re.compile(r"\bclap\b", re.IGNORECASE),
    "snare": re.compile(r"\b(?:snare|sidestick|side stick)\b", re.IGNORECASE),
    "kick": re.compile(r"\b(?:kick|bd)\b", re.IGNORECASE),
    "fx": re.compile(r"\b(?:fx|noise|riser|sweep|impact|vinyl)\b", re.IGNORECASE),
}

ABLETON_AGENT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_INDEX_DIR = ABLETON_AGENT_ROOT / "sample_index"
LOCAL_SAMPLE_INDEX = SAMPLE_INDEX_DIR / "local_sample_index.json"
UKG_SHORTLIST = SAMPLE_INDEX_DIR / "ukg_percussion_shortlist.json"


def load_index(index_path: str | Path = LOCAL_SAMPLE_INDEX) -> dict[str, Any]:
    path = Path(index_path)
    if not path.exists():
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "roots_scanned": [],
            "total_matches": 0,
            "kind_counts": {},
            "category_counts": {},
            "samples": [],
        }
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_index(index: dict[str, Any], index_path: str | Path = LOCAL_SAMPLE_INDEX) -> None:
    path = Path(index_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _refresh_counts(index)
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


def ensure_sample_available(
    sample_path: str | Path,
    *,
    index_path: str | Path = LOCAL_SAMPLE_INDEX,
    preferred_category: str | None = None,
    allow_replacement: bool = False,
) -> dict[str, Any]:
    path = Path(sample_path)
    index = load_index(index_path)
    if path.exists():
        return {
            "ok": True,
            "path": str(path),
            "exists": True,
            "rescanned": False,
            "replacement_used": False,
            "index_path": str(Path(index_path)),
        }

    rescan = rescan_missing_sample_path(path, index=index, index_path=index_path)
    if path.exists():
        return {
            "ok": True,
            "path": str(path),
            "exists": True,
            "rescanned": True,
            "replacement_used": False,
            "index_path": str(Path(index_path)),
            **rescan,
        }

    candidates = find_replacement_candidates(index, path, preferred_category=preferred_category)
    if allow_replacement and candidates:
        return {
            "ok": True,
            "path": candidates[0]["path"],
            "exists": True,
            "rescanned": True,
            "replacement_used": True,
            "replacement": candidates[0],
            "candidates": candidates,
            "index_path": str(Path(index_path)),
            **rescan,
        }

    return {
        "ok": False,
        "path": str(path),
        "exists": False,
        "rescanned": True,
        "replacement_used": False,
        "candidates": candidates,
        "index_path": str(Path(index_path)),
        **rescan,
    }


def rescan_missing_sample_path(
    sample_path: str | Path,
    *,
    index: dict[str, Any] | None = None,
    index_path: str | Path = LOCAL_SAMPLE_INDEX,
) -> dict[str, Any]:
    path = Path(sample_path)
    active_index = index if index is not None else load_index(index_path)
    roots = _rescan_roots_for(path)
    before_paths = {item.get("path") for item in active_index.get("samples", [])}
    scanned_items: list[dict[str, Any]] = []

    for root in roots:
        scanned_items.extend(scan_sample_root(root))

    _merge_samples(active_index, scanned_items)
    save_index(active_index, index_path)
    if _same_path(index_path, LOCAL_SAMPLE_INDEX) and UKG_SHORTLIST.exists():
        refresh_ukg_percussion_shortlist(active_index, UKG_SHORTLIST)
    after_paths = {item.get("path") for item in active_index.get("samples", [])}
    return {
        "rescanned_roots": [str(root) for root in roots if root.exists()],
        "scanned_count": len(scanned_items),
        "updated_count": len(after_paths - before_paths),
    }


def scan_sample_root(root: str | Path) -> list[dict[str, Any]]:
    root_path = Path(root)
    if not root_path.exists():
        return []
    return [_describe_path(path, root_path) for path in root_path.rglob("*") if _should_index_path(path)]


def find_replacement_candidates(
    index: dict[str, Any],
    missing_path: str | Path,
    *,
    preferred_category: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    missing = Path(missing_path)
    missing_stem = missing.stem.casefold()
    missing_suffix = missing.suffix.casefold()
    samples = [item for item in index.get("samples", []) if Path(str(item.get("path", ""))).exists()]

    def score(item: dict[str, Any]) -> tuple[int, str]:
        item_path = Path(str(item.get("path", "")))
        categories = set(item.get("categories", []))
        value = 0
        if item_path.name.casefold() == missing.name.casefold():
            value += 100
        if item_path.stem.casefold() == missing_stem:
            value += 60
        if item_path.suffix.casefold() == missing_suffix:
            value += 10
        if preferred_category and preferred_category in categories:
            value += 35
        value += len(set(_categorize_text(missing.name)) & categories) * 20
        return (-value, item_path.name.casefold())

    ranked = sorted(samples, key=score)
    return [item for item in ranked[:limit] if score(item)[0] < 0]


def refresh_ukg_percussion_shortlist(
    index: dict[str, Any],
    shortlist_path: str | Path = UKG_SHORTLIST,
    *,
    per_category: int = 24,
) -> None:
    picks: dict[str, list[dict[str, Any]]] = {}
    samples = [
        item
        for item in index.get("samples", [])
        if item.get("kind") == "audio_sample" and Path(str(item.get("path", ""))).exists()
    ]
    for category in ["hat", "shaker", "rim", "perc", "clap", "snare", "kick", "fx"]:
        category_items = [item for item in samples if category in item.get("categories", [])]
        picks[category] = [_shortlist_item(item) for item in sorted(category_items, key=_ukg_pick_score)[:per_category]]
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_index": Path(LOCAL_SAMPLE_INDEX).name,
        "picks": picks,
    }
    path = Path(shortlist_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _describe_path(path: Path, root: Path) -> dict[str, Any]:
    stat = path.stat()
    suffix = path.suffix.lower()
    return {
        "name": path.name,
        "path": str(path),
        "extension": suffix,
        "kind": _kind_for_suffix(suffix),
        "categories": _categorize_text(" ".join(path.parts[-6:])),
        "size_bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "root": str(root),
    }


def _should_index_path(path: Path) -> bool:
    if not path.is_file():
        return False
    suffix = path.suffix.lower()
    if suffix not in INDEXED_EXTENSIONS:
        return False
    path_text = str(path)
    if "ImpulseResponses" in path_text:
        return False
    if suffix in PRESET_EXTENSIONS:
        return _is_instrument_or_drum_preset(path_text)
    if suffix in CLIP_EXTENSIONS:
        return "MIDI Clips" in path_text and re.search(r"Drums|Percussion", path_text, re.IGNORECASE)
    return True


def _is_instrument_or_drum_preset(path_text: str) -> bool:
    if re.search(r"Audio Effects|MIDI Effects|Max MIDI Effect", path_text, re.IGNORECASE):
        return False
    return bool(re.search(r"Devices\\Instruments|Presets\\Instruments|Drum Rack|Drums|Drum Synth", path_text, re.IGNORECASE))


def _kind_for_suffix(suffix: str) -> str:
    if suffix in AUDIO_EXTENSIONS:
        return "audio_sample"
    if suffix in PRESET_EXTENSIONS:
        return "instrument_or_drum_preset"
    return "midi_clip"


def _categorize_text(text: str) -> list[str]:
    return [category for category, pattern in CATEGORY_PATTERNS.items() if pattern.search(text)]


def _rescan_roots_for(path: Path) -> list[Path]:
    candidates: list[Path] = []
    if path.parent != path:
        candidates.append(path.parent)
    if path.parent.parent != path.parent:
        candidates.append(path.parent.parent)
    for parent in path.parents:
        if parent.name.casefold() in {"loops", "one shots", "samples"}:
            candidates.append(parent)
            break
    return _unique_existing_or_nearby(candidates)


def _unique_existing_or_nearby(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    roots: list[Path] = []
    for path in paths:
        resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.exists():
            roots.append(path)
    return roots


def _merge_samples(index: dict[str, Any], samples: Iterable[dict[str, Any]]) -> None:
    existing = {item.get("path"): item for item in index.get("samples", [])}
    for item in samples:
        existing[item["path"]] = item
    index["samples"] = sorted(existing.values(), key=lambda item: str(item.get("path", "")).casefold())


def _refresh_counts(index: dict[str, Any]) -> None:
    samples = index.get("samples", [])
    kind_counts = Counter(item.get("kind", "unknown") for item in samples)
    category_counts: Counter[str] = Counter()
    roots = set(index.get("roots_scanned", []))
    for item in samples:
        category_counts.update(item.get("categories", []))
        if item.get("root"):
            roots.add(item["root"])
    index["generated_at"] = datetime.now().isoformat(timespec="seconds")
    index["roots_scanned"] = sorted(roots)
    index["total_matches"] = len(samples)
    index["kind_counts"] = dict(sorted(kind_counts.items()))
    index["category_counts"] = dict(sorted(category_counts.items()))


def _shortlist_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("name"),
        "path": item.get("path"),
        "extension": item.get("extension"),
        "kind": item.get("kind"),
        "categories": item.get("categories", []),
        "size_bytes": item.get("size_bytes"),
    }


def _ukg_pick_score(item: dict[str, Any]) -> tuple[int, int, str]:
    name = str(item.get("name", ""))
    path = str(item.get("path", ""))
    text = f"{name} {path}".casefold()
    tempo_match = re.search(r"\b(\d{2,3})\s*bpm\b", text)
    tempo_penalty = 0
    if tempo_match:
        tempo_penalty = abs(int(tempo_match.group(1)) - 132)
    garage_bonus = -30 if "garage" in text or "uk garage" in text else 0
    one_shot_bonus = -12 if "one shots" in text else 0
    loop_bonus = -8 if "loops" in text and tempo_penalty <= 5 else 0
    return (garage_bonus + one_shot_bonus + loop_bonus + tempo_penalty, len(path), name.casefold())


def _same_path(left: str | Path, right: str | Path) -> bool:
    try:
        return Path(left).resolve() == Path(right).resolve()
    except OSError:
        return Path(left).absolute() == Path(right).absolute()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check and refresh the local Ableton sample whitelist")
    parser.add_argument("--sample-path", required=True)
    parser.add_argument("--index-path", default=str(LOCAL_SAMPLE_INDEX))
    parser.add_argument("--category")
    parser.add_argument("--allow-replacement", action="store_true")
    args = parser.parse_args()

    result = ensure_sample_available(
        args.sample_path,
        index_path=args.index_path,
        preferred_category=args.category,
        allow_replacement=args.allow_replacement,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

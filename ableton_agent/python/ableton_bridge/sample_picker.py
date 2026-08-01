from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from .sample_index import LOCAL_SAMPLE_INDEX, load_index, rescan_missing_sample_path


AUDIO_KINDS = {"audio_sample"}
DEFAULT_LIMIT = 5


def pick_samples(
    *,
    role: str | None = None,
    category: str | None = None,
    style: str | None = None,
    query: str | None = None,
    limit: int = DEFAULT_LIMIT,
    index_path: str | Path = LOCAL_SAMPLE_INDEX,
    refresh_missing: bool = True,
) -> dict[str, Any]:
    index_file = Path(index_path)
    index = load_index(index_file)
    wanted_category = _normalize_category(category or role)
    candidates = [
        item
        for item in index.get("samples", [])
        if item.get("kind") in AUDIO_KINDS and _matches(item, wanted_category=wanted_category, query=query)
    ]
    ranked = sorted(
        (_score_item(item, wanted_category=wanted_category, style=style, query=query), item)
        for item in candidates
    )

    picks: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    refresh_results: list[dict[str, Any]] = []
    for score, item in ranked:
        path = Path(str(item.get("path", "")))
        if path.exists():
            picks.append(_candidate_payload(item, exists=True, missing=False, score=score[0], reasons=_score_reasons(item, wanted_category=wanted_category, style=style, query=query)))
        else:
            missing.append(_candidate_payload(item, exists=False, missing=True, score=score[0], reasons=["path missing at indexed location"]))
            if refresh_missing:
                refresh_results.append({"missing_path": str(path), **rescan_missing_sample_path(path, index=index, index_path=index_file)})
        if len(picks) >= max(1, limit):
            break

    if len(picks) < max(1, limit) and refresh_missing and missing:
        refreshed_index = load_index(index_file)
        refreshed = [
            item
            for item in refreshed_index.get("samples", [])
            if item.get("kind") in AUDIO_KINDS and _matches(item, wanted_category=wanted_category, query=query)
        ]
        seen_paths = {item["path"] for item in picks}
        for score, item in sorted(
            (_score_item(item, wanted_category=wanted_category, style=style, query=query), item)
            for item in refreshed
        ):
            path = str(item.get("path", ""))
            if path in seen_paths or not Path(path).exists():
                continue
            picks.append(_candidate_payload(item, exists=True, missing=False, score=score[0], reasons=_score_reasons(item, wanted_category=wanted_category, style=style, query=query)))
            seen_paths.add(path)
            if len(picks) >= max(1, limit):
                break

    return {
        "ok": True,
        "action": "pick",
        "role": role,
        "category": wanted_category,
        "style": style,
        "query": query,
        "limit": max(1, limit),
        "index_path": str(index_file),
        "picked_count": len(picks),
        "missing_considered_count": len(missing),
        "refresh_count": len(refresh_results),
        "refresh_results": refresh_results,
        "candidates": picks,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "message": "Sample candidates picked from local index; all returned candidates exist",
    }


def _normalize_category(value: str | None) -> str | None:
    text = str(value or "").strip().casefold()
    aliases = {
        "hihat": "hat",
        "hi hat": "hat",
        "hi-hat": "hat",
        "closed_hat": "hat",
        "percussion": "perc",
        "top": "hat",
        "top_percussion": "hat",
        "tops": "hat",
    }
    return aliases.get(text, text or None)


def _matches(item: dict[str, Any], *, wanted_category: str | None, query: str | None) -> bool:
    categories = {str(category).casefold() for category in item.get("categories", [])}
    if wanted_category and wanted_category not in categories and wanted_category not in _search_text(item):
        return False
    if query:
        terms = [term for term in re.split(r"\s+", query.casefold().strip()) if term]
        haystack = _search_text(item)
        if any(term not in haystack for term in terms):
            return False
    return True


def _score_item(
    item: dict[str, Any],
    *,
    wanted_category: str | None,
    style: str | None,
    query: str | None,
) -> tuple[int, int, str]:
    text = _search_text(item)
    path = str(item.get("path", ""))
    name = str(item.get("name", ""))
    categories = {str(category).casefold() for category in item.get("categories", [])}
    score = 0
    if wanted_category and wanted_category in categories:
        score -= 80
    if style and style.casefold() in text:
        score -= 40
    if query:
        for term in re.split(r"\s+", query.casefold().strip()):
            if term and term in name.casefold():
                score -= 20
            elif term and term in text:
                score -= 8
    if "one shots" in text or "one-shots" in text:
        score -= 18
    tempo_match = re.search(r"\b(\d{2,3})\s*bpm\b", text)
    if tempo_match:
        score += abs(int(tempo_match.group(1)) - 132)
    if "garage" in text or "ukg" in text or "uk garage" in text:
        score -= 30
    return (score, len(path), name.casefold())


def _score_reasons(
    item: dict[str, Any],
    *,
    wanted_category: str | None,
    style: str | None,
    query: str | None,
) -> list[str]:
    text = _search_text(item)
    name = str(item.get("name", ""))
    categories = {str(category).casefold() for category in item.get("categories", [])}
    reasons: list[str] = []
    if wanted_category and wanted_category in categories:
        reasons.append(f"category match: {wanted_category}")
    if style and style.casefold() in text:
        reasons.append(f"style text match: {style}")
    if query:
        for term in re.split(r"\s+", query.casefold().strip()):
            if term and term in name.casefold():
                reasons.append(f"name contains query term: {term}")
            elif term and term in text:
                reasons.append(f"path/category contains query term: {term}")
    if "one shots" in text or "one-shots" in text:
        reasons.append("one-shot source")
    if "garage" in text or "ukg" in text or "uk garage" in text:
        reasons.append("garage/UKG text match")
    if not reasons:
        reasons.append("general local-index match")
    return reasons


def _candidate_payload(item: dict[str, Any], *, exists: bool, missing: bool, score: int | None = None, reasons: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": item.get("name"),
        "path": item.get("path"),
        "extension": item.get("extension"),
        "kind": item.get("kind"),
        "categories": item.get("categories", []),
        "size_bytes": item.get("size_bytes"),
        "exists": exists,
        "missing": missing,
        "rank_score": score,
        "rank_reasons": reasons or [],
    }


def _search_text(item: dict[str, Any]) -> str:
    return " ".join([
        str(item.get("name", "")),
        str(item.get("path", "")),
        " ".join(str(category) for category in item.get("categories", [])),
    ]).casefold()


def main() -> int:
    parser = argparse.ArgumentParser(description="Pick usable local samples from the Ableton Agent sample index")
    parser.add_argument("--role")
    parser.add_argument("--category")
    parser.add_argument("--style")
    parser.add_argument("--query")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--index-path", default=str(LOCAL_SAMPLE_INDEX))
    parser.add_argument("--no-refresh-missing", action="store_true")
    args = parser.parse_args()

    result = pick_samples(
        role=args.role,
        category=args.category,
        style=args.style,
        query=args.query,
        limit=args.limit,
        index_path=args.index_path,
        refresh_missing=not args.no_refresh_missing,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

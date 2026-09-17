from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable

from .als_snapshot import AlsSnapshotError, read_als_snapshot
from .locator import locator
from .tempo import get_tempo
from .track_management import track_management


DEFAULT_PAGE_SIZE = 8
DEFAULT_MAX_PAGES = 64
DEFAULT_MAX_ITEMS = 512
DEFAULT_PAGE_TIMEOUT = 5.0
DEFAULT_TOTAL_TIMEOUT = 30.0

ALS_TRACK_TYPES = {
    "MidiTrack": "midi",
    "AudioTrack": "audio",
    "GroupTrack": "group",
    "ReturnTrack": "return",
}


class AlsHubVerificationError(RuntimeError):
    pass


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 3)


def _hub_tempo_reader(timeout: float) -> dict[str, Any]:
    return get_tempo(timeout=timeout)


def _hub_locator_reader(timeout: float) -> dict[str, Any]:
    return locator("list", timeout=timeout)


def _hub_track_page_reader(
    cursor: int,
    limit: int,
    expected_collection_token: str | None,
    timeout: float,
) -> dict[str, Any]:
    return track_management(
        "scan_tracks",
        timeout=timeout,
        include_returns=True,
        include_main=True,
        read={
            "cursor": cursor,
            "limit": limit,
            "projection": ["identity", "hierarchy"],
            "budget_ms": 1000,
            "expected_collection_token": expected_collection_token,
        },
    )


def _extract_tempo(reply: dict[str, Any]) -> float:
    candidate: Any = reply.get("tempo")
    if candidate is None and isinstance(reply.get("result"), dict):
        candidate = reply["result"].get("tempo", reply["result"].get("value"))
    if isinstance(candidate, bool) or not isinstance(candidate, (int, float)):
        raise AlsHubVerificationError("Hub tempo reply did not contain a numeric tempo")
    return float(candidate)


def _extract_locators(reply: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: Any = reply.get("before")
    if candidates is None:
        candidates = reply.get("locators", reply.get("items"))
    if not isinstance(candidates, list):
        raise AlsHubVerificationError("Hub locator reply did not contain a locator list")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            raise AlsHubVerificationError(f"Hub locator item {index} is not an object")
        beat = item.get("beat", item.get("time"))
        if isinstance(beat, bool) or not isinstance(beat, (int, float)):
            raise AlsHubVerificationError(f"Hub locator item {index} has no numeric beat")
        result.append({"name": str(item.get("name", "")), "beat": float(beat)})
    return result


def collect_hub_track_pages(
    *,
    page_reader: Callable[[int, int, str | None, float], dict[str, Any]] = _hub_track_page_reader,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_items: int = DEFAULT_MAX_ITEMS,
    page_timeout: float = DEFAULT_PAGE_TIMEOUT,
    total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
) -> dict[str, Any]:
    if page_size < 1 or page_size > 64:
        raise AlsHubVerificationError("page_size must be 1..64")
    if max_pages < 1 or max_items < 1 or page_timeout <= 0 or total_timeout <= 0:
        raise AlsHubVerificationError("page and timeout safety limits must be positive")

    started = time.perf_counter()
    cursor = 0
    collection_token: str | None = None
    items: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []

    for page_number in range(max_pages):
        remaining = total_timeout - (time.perf_counter() - started)
        if remaining <= 0:
            raise AlsHubVerificationError(
                f"Hub track paging exceeded total timeout at cursor {cursor}"
            )
        reply = page_reader(cursor, page_size, collection_token, min(page_timeout, remaining))
        if not isinstance(reply, dict) or reply.get("ok") is not True:
            raise AlsHubVerificationError(
                f"Hub track page {page_number + 1} failed at cursor {cursor}: {reply!r}"
            )
        read = reply.get("read")
        page_items = reply.get("items")
        if not isinstance(read, dict) or not isinstance(page_items, list):
            raise AlsHubVerificationError(
                f"Hub track page {page_number + 1} lacks bounded read metadata or items"
            )
        warnings = read.get("warnings", [])
        if warnings:
            raise AlsHubVerificationError(
                f"Hub track page {page_number + 1} returned warnings: {warnings!r}"
            )
        token = read.get("collection_token")
        if not isinstance(token, str) or not token:
            raise AlsHubVerificationError("Hub track page did not return a collection token")
        if collection_token is None:
            collection_token = token
        elif token != collection_token:
            raise AlsHubVerificationError(
                "Hub track collection changed while pages were being collected"
            )
        if int(read.get("cursor", -1)) != cursor:
            raise AlsHubVerificationError("Hub track page cursor did not match the request")

        items.extend(dict(item) for item in page_items if isinstance(item, dict))
        if len(items) > max_items:
            raise AlsHubVerificationError(
                f"Hub track paging exceeded the safety limit of {max_items} items"
            )
        next_cursor = int(read.get("next_cursor", cursor))
        has_more = bool(read.get("has_more", False))
        pages.append(
            {
                "page": page_number + 1,
                "cursor": cursor,
                "next_cursor": next_cursor,
                "returned_count": len(page_items),
                "elapsed_ms": read.get("elapsed_ms"),
            }
        )
        if not has_more:
            return {
                "items": items,
                "pages": pages,
                "page_count": len(pages),
                "item_count": len(items),
                "collection_token": collection_token,
                "elapsed_ms": _elapsed_ms(started),
            }
        if next_cursor <= cursor:
            raise AlsHubVerificationError("Hub track page did not advance its cursor")
        cursor = next_cursor

    raise AlsHubVerificationError(
        f"Hub track paging exceeded the safety limit of {max_pages} pages at cursor {cursor}"
    )


def read_hub_verification_snapshot(
    *,
    tempo_reader: Callable[[float], dict[str, Any]] = _hub_tempo_reader,
    locator_reader: Callable[[float], dict[str, Any]] = _hub_locator_reader,
    track_page_reader: Callable[[int, int, str | None, float], dict[str, Any]] = _hub_track_page_reader,
    page_size: int = DEFAULT_PAGE_SIZE,
    page_timeout: float = DEFAULT_PAGE_TIMEOUT,
    total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
) -> dict[str, Any]:
    result: dict[str, Any] = {"errors": {}, "timing_ms": {}}

    started = time.perf_counter()
    try:
        result["tempo"] = _extract_tempo(tempo_reader(page_timeout))
    except Exception as error:
        result["errors"]["tempo"] = f"{type(error).__name__}: {error}"
    result["timing_ms"]["tempo"] = _elapsed_ms(started)

    started = time.perf_counter()
    try:
        result["locators"] = _extract_locators(locator_reader(page_timeout))
    except Exception as error:
        result["errors"]["locators"] = f"{type(error).__name__}: {error}"
    result["timing_ms"]["locators"] = _elapsed_ms(started)

    started = time.perf_counter()
    try:
        tracks = collect_hub_track_pages(
            page_reader=track_page_reader,
            page_size=page_size,
            page_timeout=page_timeout,
            total_timeout=total_timeout,
        )
        result["tracks"] = tracks["items"]
        result["track_read"] = {key: value for key, value in tracks.items() if key != "items"}
    except Exception as error:
        result["errors"]["tracks"] = f"{type(error).__name__}: {error}"
    result["timing_ms"]["tracks"] = _elapsed_ms(started)
    return result


def _canonical_als_tracks(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    section_indexes = {"track": 0, "return": 0}
    result: list[dict[str, Any]] = []
    for track in snapshot.get("tracks", []):
        section = "return" if track.get("is_return") else "track"
        record = {
            "section": section,
            "track_index": section_indexes[section],
            "track_name": str(track.get("name", "")),
            "track_type": ALS_TRACK_TYPES.get(str(track.get("type", "")), "unknown"),
            "group_path_names": list(track.get("group_path", [])) if section == "track" else [],
        }
        section_indexes[section] += 1
        result.append(record)
    main = snapshot.get("main_track", {})
    if main.get("present"):
        result.append(
            {
                "section": "main",
                "track_index": 0,
                "track_name": str(main.get("name", "Main")),
                "track_type": "main",
                "group_path_names": [],
            }
        )
    return result


def _canonical_hub_tracks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordinary = {
        int(item["track_id"]): item
        for item in items
        if item.get("section") == "track" and isinstance(item.get("track_id"), int)
    }
    result: list[dict[str, Any]] = []
    for item in items:
        section = str(item.get("section", ""))
        path: list[str] = []
        if section == "track":
            cursor = item
            seen: set[int] = set()
            while True:
                parent_id = cursor.get("parent_group_id")
                if not isinstance(parent_id, int) or parent_id == 0 or parent_id in seen:
                    break
                parent = ordinary.get(parent_id)
                if parent is None:
                    break
                seen.add(parent_id)
                path.insert(0, str(parent.get("track_name", "")))
                cursor = parent
        result.append(
            {
                "section": section,
                "track_index": int(item.get("track_index", 0)),
                "track_name": str(item.get("track_name", "")),
                "track_type": str(item.get("track_type", "")),
                "group_path_names": path,
            }
        )
    return result


def _canonical_als_locators(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"name": str(item.get("name", "")), "beat": float(item.get("beat", 0.0))}
        for item in snapshot.get("locators", [])
    ]


def _sequence_differences(
    saved: list[dict[str, Any]],
    live: list[dict[str, Any]],
    *,
    maximum: int = 20,
) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    for index in range(max(len(saved), len(live))):
        saved_item = saved[index] if index < len(saved) else None
        live_item = live[index] if index < len(live) else None
        if saved_item != live_item:
            differences.append({"index": index, "als": saved_item, "hub": live_item})
            if len(differences) >= maximum:
                break
    return differences


def compare_als_snapshot_to_hub(
    als_snapshot: dict[str, Any],
    hub_snapshot: dict[str, Any],
) -> dict[str, Any]:
    comparisons: dict[str, dict[str, Any]] = {}
    errors = hub_snapshot.get("errors", {})

    als_tempo = als_snapshot.get("main_track", {}).get("tempo", {}).get("manual_bpm")
    if "tempo" in errors or als_tempo is None or "tempo" not in hub_snapshot:
        comparisons["tempo"] = {
            "status": "inconclusive",
            "als": als_tempo,
            "hub": hub_snapshot.get("tempo"),
            "error": errors.get("tempo", "ALS did not contain a saved manual tempo"),
        }
    else:
        hub_tempo = float(hub_snapshot["tempo"])
        matched = abs(float(als_tempo) - hub_tempo) <= 0.000001
        comparisons["tempo"] = {
            "status": "verified" if matched else "mismatch",
            "als": float(als_tempo),
            "hub": hub_tempo,
        }

    saved_locators = _canonical_als_locators(als_snapshot)
    if "locators" in errors or "locators" not in hub_snapshot:
        comparisons["locators"] = {
            "status": "inconclusive",
            "als_count": len(saved_locators),
            "hub_count": None,
            "error": errors.get("locators", "Hub locator data is unavailable"),
        }
    else:
        live_locators = list(hub_snapshot["locators"])
        differences = _sequence_differences(saved_locators, live_locators)
        comparisons["locators"] = {
            "status": "verified" if not differences else "mismatch",
            "als_count": len(saved_locators),
            "hub_count": len(live_locators),
            "differences": differences,
        }

    saved_tracks = _canonical_als_tracks(als_snapshot)
    if "tracks" in errors or "tracks" not in hub_snapshot:
        comparisons["tracks"] = {
            "status": "inconclusive",
            "als_count": len(saved_tracks),
            "hub_count": None,
            "error": errors.get("tracks", "Hub track data is unavailable"),
        }
    else:
        live_tracks = _canonical_hub_tracks(list(hub_snapshot["tracks"]))
        differences = _sequence_differences(saved_tracks, live_tracks)
        comparisons["tracks"] = {
            "status": "verified" if not differences else "mismatch",
            "als_count": len(saved_tracks),
            "hub_count": len(live_tracks),
            "differences": differences,
        }

    statuses = [item["status"] for item in comparisons.values()]
    if "mismatch" in statuses:
        overall = "mismatch"
    elif "inconclusive" in statuses:
        overall = "partial"
    else:
        overall = "verified"

    return {
        "ok": overall == "verified",
        "read_only": True,
        "overall_status": overall,
        "verified_scope": [
            name for name, comparison in comparisons.items() if comparison["status"] == "verified"
        ],
        "comparisons": comparisons,
        "freshness": {
            "status": "unknown",
            "message": (
                "ALS values are the last saved disk state. Exact matches verify only the compared "
                "fields; Hub does not prove that unrelated unsaved Live state is absent."
            ),
        },
    }


def verify_als_against_hub(
    path: str | Path,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    page_timeout: float = DEFAULT_PAGE_TIMEOUT,
    total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
    tempo_reader: Callable[[float], dict[str, Any]] = _hub_tempo_reader,
    locator_reader: Callable[[float], dict[str, Any]] = _hub_locator_reader,
    track_page_reader: Callable[[int, int, str | None, float], dict[str, Any]] = _hub_track_page_reader,
) -> dict[str, Any]:
    started = time.perf_counter()
    als_started = time.perf_counter()
    als_snapshot = read_als_snapshot(path)
    als_elapsed = _elapsed_ms(als_started)
    hub_snapshot = read_hub_verification_snapshot(
        tempo_reader=tempo_reader,
        locator_reader=locator_reader,
        track_page_reader=track_page_reader,
        page_size=page_size,
        page_timeout=page_timeout,
        total_timeout=total_timeout,
    )
    result = compare_als_snapshot_to_hub(als_snapshot, hub_snapshot)
    result.update(
        {
            "source": als_snapshot["source"],
            "format": als_snapshot["format"],
            "timing_ms": {
                "als_read": als_elapsed,
                "hub": hub_snapshot.get("timing_ms", {}),
                "total": _elapsed_ms(started),
            },
            "hub_track_read": hub_snapshot.get("track_read"),
            "warnings": list(als_snapshot.get("warnings", [])),
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare a saved read-only ALS snapshot with narrow current Hub reads"
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--page-timeout", type=float, default=DEFAULT_PAGE_TIMEOUT)
    parser.add_argument("--total-timeout", type=float, default=DEFAULT_TOTAL_TIMEOUT)
    args = parser.parse_args()
    try:
        result = verify_als_against_hub(
            args.path,
            page_size=args.page_size,
            page_timeout=args.page_timeout,
            total_timeout=args.total_timeout,
        )
    except (AlsSnapshotError, AlsHubVerificationError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    return 0 if result["overall_status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())

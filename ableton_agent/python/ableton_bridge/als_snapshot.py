from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from .als_loader import (
    DEFAULT_MAX_UNCOMPRESSED_BYTES as LOADER_MAX_UNCOMPRESSED_BYTES,
    AlsDocumentError,
    load_als_document,
)


DEFAULT_MAX_UNCOMPRESSED_BYTES = LOADER_MAX_UNCOMPRESSED_BYTES
DEFAULT_MAX_FILE_REFERENCES = 512
TRACK_TAGS = {"MidiTrack", "AudioTrack", "GroupTrack", "ReturnTrack"}


class AlsSnapshotError(RuntimeError):
    pass


def _value(element: ET.Element | None, path: str, default: str = "") -> str:
    if element is None:
        return default
    node = element.find(path)
    if node is None:
        return default
    return str(node.attrib.get("Value", default))


def _int_value(value: str, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_value(value: str, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _decompress_als(raw: bytes, maximum: int) -> bytes:
    if raw[:2] != b"\x1f\x8b":
        raise AlsSnapshotError("ALS file does not have the expected Gzip header")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as stream:
            data = stream.read(maximum + 1)
    except (OSError, EOFError) as error:
        raise AlsSnapshotError(f"Cannot decompress ALS Gzip data: {error}") from error
    if len(data) > maximum:
        raise AlsSnapshotError(
            f"Decompressed ALS exceeds the configured safety limit of {maximum} bytes"
        )
    return data


def _track_name(track: ET.Element) -> tuple[str, str, str]:
    user_name = _value(track, ".//Name/UserName")
    effective_name = _value(track, ".//Name/EffectiveName")
    return effective_name or user_name, user_name, effective_name


def _group_path(
    track_id: int | None,
    by_id: dict[int, dict[str, Any]],
) -> tuple[list[str], int]:
    names: list[str] = []
    visited: set[int] = set()
    current = by_id.get(track_id) if track_id is not None else None
    while current and current["parent_group_id"] is not None:
        parent_id = current["parent_group_id"]
        if parent_id in visited:
            break
        visited.add(parent_id)
        parent = by_id.get(parent_id)
        if parent is None:
            break
        names.append(parent["name"])
        current = parent
    names.reverse()
    return names, len(names)


def _read_tracks(live_set: ET.Element) -> tuple[list[dict[str, Any]], dict[str, int]]:
    tracks_node = live_set.find("Tracks")
    tracks: list[dict[str, Any]] = []
    if tracks_node is None:
        return tracks, {}

    for order, track in enumerate(list(tracks_node)):
        if track.tag not in TRACK_TAGS:
            continue
        name, user_name, effective_name = _track_name(track)
        parent_id = _int_value(_value(track, ".//TrackGroupId"))
        if parent_id is not None and parent_id < 0:
            parent_id = None
        tracks.append(
            {
                "order": order,
                "type": track.tag,
                "file_id": _int_value(track.attrib.get("Id", "")),
                "name": name,
                "user_name": user_name,
                "effective_name": effective_name,
                "parent_group_id": parent_id,
                "is_group": track.tag == "GroupTrack",
                "is_return": track.tag == "ReturnTrack",
            }
        )

    by_id = {track["file_id"]: track for track in tracks if track["file_id"] is not None}
    for track in tracks:
        path, depth = _group_path(track["file_id"], by_id)
        track["group_path"] = path
        track["depth"] = depth

    counts = Counter(track["type"] for track in tracks)
    counts["total"] = len(tracks)
    counts["ordinary"] = sum(not track["is_return"] for track in tracks)
    return tracks, dict(counts)


def _read_main_track(live_set: ET.Element) -> dict[str, Any]:
    main = live_set.find("MainTrack")
    if main is None:
        return {"present": False}
    name, user_name, effective_name = _track_name(main)
    tempo = main.find(".//Tempo")
    return {
        "present": True,
        "name": name or "Main",
        "user_name": user_name,
        "effective_name": effective_name,
        "tempo": {
            "manual_bpm": _float_value(_value(tempo, "Manual")),
            "automation_target_id": _int_value(
                tempo.find("AutomationTarget").attrib.get("Id", "")
                if tempo is not None and tempo.find("AutomationTarget") is not None
                else ""
            ),
        },
    }


def _read_locators(live_set: ET.Element) -> list[dict[str, Any]]:
    locators: list[dict[str, Any]] = []
    node = live_set.find("Locators")
    if node is None:
        return locators
    for locator in node.findall(".//Locator"):
        locators.append(
            {
                "file_id": _int_value(locator.attrib.get("Id", "")),
                "lom_id": _int_value(_value(locator, "LomId")),
                "beat": _float_value(_value(locator, "Time")),
                "name": _value(locator, "Name"),
                "is_song_start": _value(locator, "IsSongStart").lower() == "true",
            }
        )
    return locators


def _normalized_windows_path(value: str) -> Path | None:
    if not value:
        return None
    return Path(value.replace("/", "\\"))


def _read_file_references(
    root: ET.Element,
    maximum: int,
) -> dict[str, Any]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    total = 0
    for reference in root.findall(".//FileRef"):
        total += 1
        absolute = _value(reference, "Path")
        relative = _value(reference, "RelativePath")
        if not absolute and not relative:
            continue
        key = (absolute, relative)
        if key in unique:
            continue
        path = _normalized_windows_path(absolute)
        unique[key] = {
            "path": absolute,
            "relative_path": relative,
            "exists": path.exists() if path is not None and path.is_absolute() else None,
            "type": _int_value(_value(reference, "Type")),
            "original_file_size": _int_value(_value(reference, "OriginalFileSize"), 0),
        }

    items = list(unique.values())
    returned = items[:maximum]
    return {
        "xml_reference_count": total,
        "unique_nonempty_count": len(items),
        "returned_count": len(returned),
        "has_more": len(returned) < len(items),
        "missing_absolute_count": sum(item["exists"] is False for item in items),
        "items": returned,
    }


def read_als_snapshot(
    path: str | Path,
    *,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
    max_file_references: int = DEFAULT_MAX_FILE_REFERENCES,
) -> dict[str, Any]:
    if max_file_references < 0:
        raise AlsSnapshotError("max_file_references cannot be negative")

    try:
        document = load_als_document(
            path, max_uncompressed_bytes=max_uncompressed_bytes
        )
    except AlsDocumentError as error:
        raise AlsSnapshotError(str(error)) from error
    source = document.path
    raw = document.raw
    xml = document.xml
    root = document.root
    live_set = document.live_set

    tracks, track_counts = _read_tracks(live_set)
    locators = _read_locators(live_set)
    warnings = list(document.warnings)

    return {
        "ok": True,
        "read_only": True,
        "source": {
            "path": str(source),
            "compressed_bytes": len(raw),
            "uncompressed_bytes": len(xml),
            "modified_utc": document.source_info["modified_utc"],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "changed_during_read": document.source_info["changed_during_read"],
            "file_token": document.source_info["file_token"],
            "cache_hit": document.cache_hit,
        },
        "format": {
            "container": "gzip",
            "document": "xml",
            "root": root.tag,
            "major_version": root.attrib.get("MajorVersion", ""),
            "minor_version": root.attrib.get("MinorVersion", ""),
            "creator": root.attrib.get("Creator", ""),
            "revision": root.attrib.get("Revision", ""),
        },
        "track_counts": track_counts,
        "tracks": tracks,
        "main_track": _read_main_track(live_set),
        "locator_count": len(locators),
        "locators": locators,
        "file_references": _read_file_references(root, max_file_references),
        "unsupported": {
            "tempo_automation_breakpoints": (
                "use ableton_bridge.als_project or the combined saved-set reader for "
                "target-linked envelope events"
            ),
            "writes": "intentionally unsupported",
        },
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read a saved Ableton .als file as a bounded, read-only XML snapshot"
    )
    parser.add_argument("path", type=Path)
    parser.add_argument("--max-uncompressed-mb", type=int, default=128)
    parser.add_argument("--max-file-references", type=int, default=512)
    args = parser.parse_args()
    try:
        result = read_als_snapshot(
            args.path,
            max_uncompressed_bytes=args.max_uncompressed_mb * 1024 * 1024,
            max_file_references=args.max_file_references,
        )
    except (AlsSnapshotError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

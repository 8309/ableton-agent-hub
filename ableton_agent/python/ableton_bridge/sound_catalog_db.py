from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import sqlite3
from typing import Any, Iterable
import xml.etree.ElementTree as ET

from .sound_catalog_analysis import (
    AUDIO_ANALYSIS_VERSION,
    PRESET_PARSER_VERSION,
    analyze_audio_resource,
    parse_ableton_preset,
)


ABLETON_AGENT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ABLETON_AGENT_ROOT / "sound_catalog"
LOCAL_DATABASE = CATALOG_DIR / "local_sound_catalog.sqlite3"
ABLETON_ROAMING = Path.home() / "AppData" / "Roaming" / "Ableton"

XMP_NAMESPACES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "ablFR": "https://ns.ableton.com/xmp/fs-resources/1.0/",
}

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE scan_runs (
    id INTEGER PRIMARY KEY,
    generated_at TEXT NOT NULL,
    catalog_schema_version INTEGER NOT NULL,
    source_json TEXT,
    pack_count INTEGER NOT NULL,
    resource_count INTEGER NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE packs (
    id TEXT PRIMARY KEY,
    ableton_unique_id TEXT,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE,
    pack_version TEXT,
    xmp_platform TEXT,
    registered INTEGER NOT NULL,
    disk_size_bytes INTEGER NOT NULL,
    disk_file_count INTEGER NOT NULL,
    resource_count INTEGER NOT NULL,
    last_scanned_at TEXT NOT NULL
);

CREATE TABLE resources (
    id TEXT PRIMARY KEY,
    stable_key TEXT NOT NULL UNIQUE,
    pack_id TEXT REFERENCES packs(id),
    name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    absolute_path TEXT NOT NULL UNIQUE,
    extension TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    exists_flag INTEGER NOT NULL,
    load_mode TEXT NOT NULL,
    agent_control TEXT NOT NULL,
    auto_insert INTEGER NOT NULL
);

CREATE INDEX resources_pack_kind ON resources(pack_id, kind);
CREATE INDEX resources_kind ON resources(kind);
CREATE INDEX resources_name ON resources(name COLLATE NOCASE);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    namespace TEXT NOT NULL,
    group_name TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    UNIQUE(namespace, canonical_name)
);

CREATE TABLE resource_tags (
    resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    method_version TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY(resource_id, tag_id, source)
);

CREATE INDEX resource_tags_tag ON resource_tags(tag_id, resource_id);

CREATE TABLE audio_features (
    resource_id TEXT PRIMARY KEY REFERENCES resources(id) ON DELETE CASCADE,
    duration_seconds REAL,
    sample_rate INTEGER,
    channels INTEGER,
    bit_depth INTEGER,
    encoding TEXT,
    estimated_bpm REAL,
    bpm_confidence REAL,
    estimated_key TEXT,
    key_confidence REAL,
    root_note TEXT,
    root_note_confidence REAL,
    is_loop INTEGER,
    loop_confidence REAL,
    lufs REAL,
    peak_dbfs REAL,
    spectral_centroid REAL,
    spectral_rolloff REAL,
    transient_density REAL,
    attack_ms REAL,
    decay_ms REAL,
    pitch_mean REAL,
    pitch_confidence REAL,
    analysis_status TEXT NOT NULL,
    analysis_error TEXT,
    header_method TEXT,
    metadata_json TEXT NOT NULL,
    analysis_version TEXT NOT NULL
);

CREATE TABLE preset_details (
    resource_id TEXT PRIMARY KEY REFERENCES resources(id) ON DELETE CASCADE,
    rack_type TEXT,
    primary_device TEXT,
    device_chain_json TEXT,
    macro_names_json TEXT,
    referenced_sample_count INTEGER,
    references_json TEXT NOT NULL,
    preview_audio_path TEXT,
    parse_status TEXT NOT NULL,
    parse_error TEXT,
    parser_version TEXT NOT NULL
);

CREATE TABLE resource_links (
    source_resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    target_resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    detail_json TEXT,
    PRIMARY KEY(source_resource_id, target_resource_id, relationship)
);

CREATE TABLE usage_feedback (
    id INTEGER PRIMARY KEY,
    resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    project TEXT,
    track_role TEXT,
    section TEXT,
    rating REAL,
    decision TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE embeddings (
    resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    embedding_type TEXT NOT NULL,
    model TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    vector_row INTEGER NOT NULL,
    segment TEXT NOT NULL,
    PRIMARY KEY(resource_id, embedding_type, model, model_version, segment)
);

CREATE VIRTUAL TABLE resource_fts USING fts5(
    resource_id UNINDEXED,
    name,
    pack_name,
    relative_path,
    tags,
    roles,
    tokenize='unicode61 remove_diacritics 2'
);
"""


def find_latest_library_config(root: str | Path = ABLETON_ROAMING) -> Path | None:
    base = Path(root)
    if not base.exists():
        return None
    candidates = list(base.glob("Live */Preferences/Library.cfg"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def parse_library_config(path: str | Path | None) -> dict[str, Any]:
    if path is None or not Path(path).exists():
        return {
            "path": None,
            "creator": None,
            "packs": {},
            "preferred_factory_packs_path": None,
        }
    source = Path(path)
    root = ET.parse(source).getroot()
    packs: dict[str, dict[str, Any]] = {}
    for item in root.findall(".//LibrarySliceInfo"):
        pack_path = item.attrib.get("Path", "")
        record = {
            "name": item.attrib.get("DisplayName", ""),
            "path": pack_path,
            "unique_id": item.attrib.get("UniqueId", ""),
            "library_id": item.attrib.get("Id", ""),
        }
        packs[_normal_path(pack_path)] = record
    preferred = root.find(".//PreferredFactoryPacksInstallationPath")
    return {
        "path": str(source),
        "creator": root.attrib.get("Creator"),
        "packs": packs,
        "preferred_factory_packs_path": (
            preferred.attrib.get("Value") if preferred is not None else None
        ),
    }


def parse_pack_xmp(pack_path: str | Path) -> dict[str, Any]:
    pack_root = Path(pack_path)
    result: dict[str, Any] = {
        "unique_id": None,
        "pack_version": None,
        "platform": None,
        "items": {},
        "files": [],
        "warnings": [],
    }
    info_dir = pack_root / "Ableton Folder Info"
    if not info_dir.exists():
        return result
    for xmp_path in sorted(info_dir.rglob("*.xmp")):
        result["files"].append(str(xmp_path))
        try:
            root = ET.parse(xmp_path).getroot()
        except (ET.ParseError, OSError) as exc:
            result["warnings"].append(f"{xmp_path}: {exc}")
            continue
        unique_id = root.findtext(".//ablFR:packUniqueId", namespaces=XMP_NAMESPACES)
        version = root.findtext(".//ablFR:packVersion", namespaces=XMP_NAMESPACES)
        platform = root.findtext(".//ablFR:platform", namespaces=XMP_NAMESPACES)
        result["unique_id"] = result["unique_id"] or unique_id
        result["pack_version"] = result["pack_version"] or version
        result["platform"] = result["platform"] or platform
        for item in root.findall(".//ablFR:items/rdf:Bag/rdf:li", XMP_NAMESPACES):
            file_path = item.findtext("ablFR:filePath", namespaces=XMP_NAMESPACES)
            if not file_path:
                continue
            keywords = [
                str(node.text).strip()
                for node in item.findall("ablFR:keywords/rdf:Bag/rdf:li", XMP_NAMESPACES)
                if node.text and str(node.text).strip()
            ]
            key = _normal_relative_path(file_path)
            current = result["items"].setdefault(key, [])
            current.extend(keyword for keyword in keywords if keyword not in current)
    return result


def build_catalog_database(
    catalog: dict[str, Any],
    *,
    database_path: str | Path = LOCAL_DATABASE,
    library_config_path: str | Path | None = None,
    source_json: str | Path | None = None,
) -> dict[str, Any]:
    destination = Path(database_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    previous = _load_previous_analysis(destination)

    config_path = Path(library_config_path) if library_config_path else find_latest_library_config()
    registry = parse_library_config(config_path)
    generated_at = str(catalog.get("generated_at") or datetime.now().isoformat(timespec="seconds"))
    pack_metadata: dict[str, dict[str, Any]] = {}
    pack_ids_by_name: dict[str, str] = {}
    pack_ids_by_path: dict[str, str] = {}
    pack_ids_by_unique: dict[str, str] = {}
    official_item_count = 0
    official_tagged_resources = 0
    unmatched_xmp_items = 0

    connection = sqlite3.connect(temporary)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO metadata(key, value) VALUES (?, ?)", ("schema_version", "2"))
        connection.execute("INSERT INTO metadata(key, value) VALUES (?, ?)", ("generated_at", generated_at))
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            ("library_config", str(config_path) if config_path else ""),
        )

        for pack in catalog.get("packs", []):
            root_path = str(pack.get("path", ""))
            registry_record = registry["packs"].get(_normal_path(root_path), {})
            xmp = parse_pack_xmp(root_path)
            unique_id = str(registry_record.get("unique_id") or xmp.get("unique_id") or "")
            stable_pack_key = unique_id or f"path:{_normal_path(root_path)}"
            pack_id = _stable_id("pack", stable_pack_key)
            pack_ids_by_name[str(pack.get("name", ""))] = pack_id
            pack_ids_by_path[_normal_path(root_path)] = pack_id
            if unique_id:
                pack_ids_by_unique[unique_id.casefold()] = pack_id
            pack_metadata[pack_id] = {
                "root_path": root_path,
                "xmp": xmp,
                "unique_id": unique_id,
            }
            official_item_count += len(xmp.get("items", {}))
            connection.execute(
                """
                INSERT INTO packs(
                    id, ableton_unique_id, name, root_path, pack_version,
                    xmp_platform, registered, disk_size_bytes, disk_file_count,
                    resource_count, last_scanned_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pack_id, unique_id or None, pack.get("name", ""), root_path,
                    xmp.get("pack_version"), xmp.get("platform"),
                    1 if registry_record else 0, int(pack.get("disk_size_bytes", 0)),
                    int(pack.get("disk_file_count", 0)), int(pack.get("resource_count", 0)),
                    generated_at,
                ),
            )

        matched_xmp_paths: dict[str, set[str]] = {pack_id: set() for pack_id in pack_metadata}
        fts_rows: list[tuple[str, str, str, str, str, str]] = []
        tag_assignments = 0
        tag_cache: dict[tuple[str, str], int] = {}
        resource_records: dict[str, dict[str, Any]] = {}
        resource_lookup: dict[tuple[str | None, str], str] = {}

        for item in catalog.get("resources", []):
            pack_name = str(item.get("pack") or "")
            pack_id = pack_ids_by_name.get(pack_name)
            absolute_path = str(item.get("path", ""))
            relative_path = _relative_resource_path(absolute_path, pack_metadata.get(pack_id))
            stable_scope = (
                pack_metadata[pack_id]["unique_id"] or f"pack-path:{_normal_path(pack_metadata[pack_id]['root_path'])}"
                if pack_id else str(item.get("source") or "local")
            )
            stable_key = f"{stable_scope}/{_normal_relative_path(relative_path)}"
            resource_id = _stable_id("resource", stable_key)
            fingerprint = _fingerprint(item)
            connection.execute(
                """
                INSERT INTO resources(
                    id, stable_key, pack_id, name, relative_path, absolute_path,
                    extension, kind, source, size_bytes, mtime_ns, fingerprint,
                    exists_flag, load_mode, agent_control, auto_insert
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resource_id, stable_key, pack_id, item.get("name", ""), relative_path,
                    absolute_path, item.get("extension", ""), item.get("kind", ""),
                    item.get("source", ""), int(item.get("size_bytes", 0)),
                    int(item.get("mtime_ns", 0)), fingerprint, 1 if item.get("exists") else 0,
                    item.get("load_mode", "manual_load"), item.get("agent_control", ""),
                    1 if item.get("auto_insert") else 0,
                ),
            )
            resource_records[resource_id] = {
                "item": item,
                "pack_id": pack_id,
                "relative_path": relative_path,
                "fingerprint": fingerprint,
            }
            resource_lookup[(pack_id, _normal_relative_path(relative_path))] = resource_id

            resource_tags: list[str] = []
            roles = [str(role) for role in item.get("roles", [])]
            for role in roles:
                tag_id = _ensure_tag(
                    connection, tag_cache, "filename_inferred", "role", role, role,
                )
                _assign_tag(
                    connection, resource_id, tag_id, "filename_path_regex", 0.55,
                    "role_patterns_v1", generated_at,
                )
                tag_assignments += 1
                resource_tags.append(role)

            official_tags: dict[str, str] = {}
            if pack_id:
                relative_key = _normal_relative_path(relative_path)
                xmp_items = pack_metadata[pack_id]["xmp"].get("items", {})
                for keyword in xmp_items.get(relative_key, []):
                    official_tags[keyword] = "pack_xmp"
                relative_parts = relative_key.split("/")
                for index in range(1, len(relative_parts)):
                    parent_key = "/".join(relative_parts[:index])
                    parent_tags = xmp_items.get(parent_key, [])
                    if parent_tags:
                        matched_xmp_paths[pack_id].add(parent_key)
                    for keyword in parent_tags:
                        official_tags.setdefault(keyword, "pack_xmp_folder")
                if official_tags:
                    official_tagged_resources += 1
                    matched_xmp_paths[pack_id].add(relative_key)
            for keyword, tag_source in official_tags.items():
                parts = [part.strip() for part in keyword.split("|") if part.strip()]
                group = parts[0] if parts else "Ableton"
                display = parts[-1] if parts else keyword
                tag_id = _ensure_tag(
                    connection, tag_cache, "ableton_factory", group, keyword, display,
                )
                _assign_tag(
                    connection, resource_id, tag_id, tag_source, 1.0,
                    "ableton_xmp_v1", generated_at,
                )
                tag_assignments += 1
                resource_tags.append(keyword)

            fts_rows.append((
                resource_id,
                str(item.get("name", "")),
                pack_name,
                relative_path,
                " ".join(resource_tags),
                " ".join(roles),
            ))

        audio_stats = _populate_audio_features(
            connection, resource_records, previous["audio"]
        )
        preset_stats, preset_references = _populate_preset_details(
            connection,
            resource_records,
            pack_metadata,
            previous["presets"],
        )
        link_stats = _populate_resource_links(
            connection,
            resource_records,
            resource_lookup,
            pack_ids_by_unique,
            preset_references,
        )

        for pack_id, metadata in pack_metadata.items():
            xmp_paths = set(metadata["xmp"].get("items", {}))
            unmatched_xmp_items += len(xmp_paths - matched_xmp_paths[pack_id])

        for key, value in (
            ("library_creator", registry.get("creator") or ""),
            ("official_xmp_items", official_item_count),
            ("official_tagged_resources", official_tagged_resources),
            ("unmatched_xmp_items", unmatched_xmp_items),
            ("tag_assignments", tag_assignments),
            ("audio_analyzed", audio_stats["analyzed"]),
            ("audio_reused", audio_stats["reused"]),
            ("audio_errors", audio_stats["errors"]),
            ("presets_parsed", preset_stats["parsed"]),
            ("presets_reused", preset_stats["reused"]),
            ("preset_errors", preset_stats["errors"]),
            ("resource_links_resolved", link_stats["resolved"]),
            ("resource_links_unresolved", link_stats["unresolved"]),
        ):
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                (key, str(value)),
            )

        connection.executemany(
            "INSERT INTO resource_fts(resource_id, name, pack_name, relative_path, tags, roles) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            fts_rows,
        )
        summary = catalog.get("summary", {})
        connection.execute(
            """
            INSERT INTO scan_runs(
                generated_at, catalog_schema_version, source_json,
                pack_count, resource_count, status
            ) VALUES (?, ?, ?, ?, ?, 'complete')
            """,
            (
                generated_at, int(catalog.get("schema_version", 0)),
                str(source_json) if source_json else None,
                int(summary.get("pack_count", 0)), int(summary.get("resource_count", 0)),
            ),
        )
        from .audio_similarity import preserve_cache
        preserve_cache(connection, destination)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    os.replace(temporary, destination)
    stats = database_stats(destination)
    stats.update({
        "ok": True,
        "database_path": str(destination),
        "library_config": str(config_path) if config_path else None,
        "library_creator": registry.get("creator"),
        "official_xmp_items": official_item_count,
        "official_tagged_resources": official_tagged_resources,
        "unmatched_xmp_items": unmatched_xmp_items,
        "tag_assignments": tag_assignments,
        "analysis": {
            "audio": audio_stats,
            "presets": preset_stats,
            "links": link_stats,
        },
    })
    return stats


def _load_previous_analysis(database_path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {"audio": {}, "presets": {}}
    if not database_path.exists():
        return result
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        audio_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(audio_features)")
        }
        if {"analysis_status", "metadata_json"}.issubset(audio_columns):
            for row in connection.execute(
                "SELECT af.*, r.fingerprint FROM audio_features af "
                "JOIN resources r ON r.id = af.resource_id"
            ):
                result["audio"][row["resource_id"]] = dict(row)
        preset_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(preset_details)")
        }
        if {"parser_version", "references_json"}.issubset(preset_columns):
            for row in connection.execute(
                "SELECT pd.*, r.fingerprint FROM preset_details pd "
                "JOIN resources r ON r.id = pd.resource_id"
            ):
                result["presets"][row["resource_id"]] = dict(row)
    except sqlite3.DatabaseError:
        return {"audio": {}, "presets": {}}
    finally:
        connection.close()
    return result


def _populate_audio_features(
    connection: sqlite3.Connection,
    resource_records: dict[str, dict[str, Any]],
    previous: dict[str, dict[str, Any]],
) -> dict[str, int]:
    stats = {"analyzed": 0, "reused": 0, "errors": 0}
    for resource_id, record in resource_records.items():
        item = record["item"]
        if item.get("kind") != "audio_sample":
            continue
        cached = previous.get(resource_id)
        if (
            cached
            and cached.get("fingerprint") == record["fingerprint"]
            and cached.get("analysis_version") == AUDIO_ANALYSIS_VERSION
        ):
            values = cached
            stats["reused"] += 1
        else:
            values = analyze_audio_resource(
                item.get("path", ""), item.get("name", ""), record["relative_path"]
            )
            stats["analyzed"] += 1
        if values.get("analysis_status") != "ok":
            stats["errors"] += 1
        _insert_audio_features(connection, resource_id, values)
    return stats


def _insert_audio_features(
    connection: sqlite3.Connection, resource_id: str, values: dict[str, Any]
) -> None:
    columns = (
        "duration_seconds", "sample_rate", "channels", "bit_depth", "encoding",
        "estimated_bpm", "bpm_confidence", "estimated_key", "key_confidence",
        "root_note", "root_note_confidence", "is_loop", "loop_confidence",
        "lufs", "peak_dbfs", "spectral_centroid", "spectral_rolloff",
        "transient_density", "attack_ms", "decay_ms", "pitch_mean",
        "pitch_confidence", "analysis_status", "analysis_error", "header_method",
        "metadata_json", "analysis_version",
    )
    payload = []
    for column in columns:
        value = values.get(column)
        if column == "is_loop" and value is not None:
            value = 1 if value else 0
        payload.append(value)
    connection.execute(
        f"INSERT INTO audio_features(resource_id, {', '.join(columns)}) "
        f"VALUES ({', '.join('?' for _ in range(len(columns) + 1))})",
        (resource_id, *payload),
    )


def _populate_preset_details(
    connection: sqlite3.Connection,
    resource_records: dict[str, dict[str, Any]],
    pack_metadata: dict[str, dict[str, Any]],
    previous: dict[str, dict[str, Any]],
) -> tuple[dict[str, int], dict[str, list[dict[str, Any]]]]:
    stats = {"parsed": 0, "reused": 0, "errors": 0}
    references_by_resource: dict[str, list[dict[str, Any]]] = {}
    for resource_id, record in resource_records.items():
        item = record["item"]
        if str(item.get("extension", "")).casefold() not in {".adg", ".adv"}:
            continue
        cached = previous.get(resource_id)
        if (
            cached
            and cached.get("fingerprint") == record["fingerprint"]
            and cached.get("parser_version") == PRESET_PARSER_VERSION
        ):
            values = cached
            stats["reused"] += 1
            references = json.loads(values.get("references_json") or "[]")
        else:
            parsed = parse_ableton_preset(item.get("path", ""))
            references = parsed.get("references", [])
            preview = _preset_preview_path(record, pack_metadata)
            values = {
                "rack_type": parsed.get("rack_type"),
                "primary_device": parsed.get("primary_device"),
                "device_chain_json": json.dumps(
                    {
                        "devices": parsed.get("devices", []),
                        "macro_groups": parsed.get("macro_groups", []),
                        "creator": parsed.get("creator"),
                    },
                    ensure_ascii=False,
                ),
                "macro_names_json": json.dumps(parsed.get("macro_names", []), ensure_ascii=False),
                "referenced_sample_count": sum(
                    1 for reference in references if _reference_kind(reference) == "audio_sample"
                ),
                "references_json": json.dumps(references, ensure_ascii=False),
                "preview_audio_path": preview,
                "parse_status": parsed.get("parse_status", "error"),
                "parse_error": parsed.get("parse_error"),
                "parser_version": parsed.get("parser_version", PRESET_PARSER_VERSION),
            }
            stats["parsed"] += 1
        if values.get("parse_status") != "ok":
            stats["errors"] += 1
        _insert_preset_details(connection, resource_id, values)
        references_by_resource[resource_id] = references
    return stats, references_by_resource


def _insert_preset_details(
    connection: sqlite3.Connection, resource_id: str, values: dict[str, Any]
) -> None:
    columns = (
        "rack_type", "primary_device", "device_chain_json", "macro_names_json",
        "referenced_sample_count", "references_json", "preview_audio_path",
        "parse_status", "parse_error", "parser_version",
    )
    connection.execute(
        f"INSERT INTO preset_details(resource_id, {', '.join(columns)}) "
        f"VALUES ({', '.join('?' for _ in range(len(columns) + 1))})",
        (resource_id, *(values.get(column) for column in columns)),
    )


def _populate_resource_links(
    connection: sqlite3.Connection,
    resource_records: dict[str, dict[str, Any]],
    resource_lookup: dict[tuple[str | None, str], str],
    pack_ids_by_unique: dict[str, str],
    preset_references: dict[str, list[dict[str, Any]]],
) -> dict[str, int]:
    stats = {"resolved": 0, "unresolved": 0}
    supported = {
        ".aif", ".aiff", ".wav", ".flac", ".mp3", ".adg", ".adv",
        ".amxd", ".alc", ".mid", ".midi",
    }
    for source_id, references in preset_references.items():
        source = resource_records[source_id]
        source_pack = source["pack_id"]
        source_dir = posixpath.dirname(_normal_relative_path(source["relative_path"]))
        for reference in references:
            relative = str(reference.get("relative_path") or "").replace("\\", "/")
            if not relative or Path(relative).suffix.casefold() not in supported:
                continue
            live_pack_id = str(reference.get("live_pack_id") or "").casefold()
            target_pack = (
                pack_ids_by_unique.get(live_pack_id) if live_pack_id else source_pack
            )
            if live_pack_id and target_pack is None:
                stats["unresolved"] += 1
                continue
            direct = _normal_relative_path(posixpath.normpath(relative))
            candidates = [direct]
            joined = _normal_relative_path(posixpath.normpath(posixpath.join(source_dir, relative)))
            if joined not in candidates:
                candidates.append(joined)
            target_id = next(
                (resource_lookup.get((target_pack, candidate)) for candidate in candidates
                 if resource_lookup.get((target_pack, candidate))),
                None,
            )
            if not target_id or target_id == source_id:
                if target_id != source_id:
                    stats["unresolved"] += 1
                continue
            target_kind = resource_records[target_id]["item"].get("kind")
            relationship = (
                "preset_uses_sample" if target_kind == "audio_sample"
                else "preset_uses_preset" if target_kind in {"ableton_preset", "max_for_live_device"}
                else "preset_references_resource"
            )
            before = connection.total_changes
            connection.execute(
                "INSERT OR IGNORE INTO resource_links("
                "source_resource_id, target_resource_id, relationship, detail_json) "
                "VALUES (?, ?, ?, ?)",
                (
                    source_id, target_id, relationship,
                    json.dumps({"source": "ableton_file_ref_v1", "reference": reference}, ensure_ascii=False),
                ),
            )
            if connection.total_changes > before:
                stats["resolved"] += 1
    return stats


def _preset_preview_path(
    record: dict[str, Any], pack_metadata: dict[str, dict[str, Any]]
) -> str | None:
    pack_id = record.get("pack_id")
    if not pack_id or pack_id not in pack_metadata:
        return None
    candidate = (
        Path(pack_metadata[pack_id]["root_path"])
        / "Ableton Folder Info" / "Previews"
        / f"{record['relative_path']}.ogg"
    )
    return str(candidate) if candidate.exists() else None


def _reference_kind(reference: dict[str, Any]) -> str | None:
    suffix = Path(str(reference.get("relative_path") or "")).suffix.casefold()
    if suffix in {".aif", ".aiff", ".wav", ".flac", ".mp3"}:
        return "audio_sample"
    if suffix in {".adg", ".adv", ".amxd"}:
        return "preset"
    return None


def database_stats(database_path: str | Path = LOCAL_DATABASE) -> dict[str, Any]:
    connection = sqlite3.connect(database_path)
    try:
        counts = {}
        for table in (
            "packs", "resources", "tags", "resource_tags", "audio_features",
            "preset_details", "resource_links", "usage_feedback", "embeddings",
        ):
            counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        namespace_counts = dict(connection.execute(
            "SELECT namespace, COUNT(*) FROM tags GROUP BY namespace ORDER BY namespace"
        ).fetchall())
        registered_packs = connection.execute(
            "SELECT COUNT(*) FROM packs WHERE registered = 1"
        ).fetchone()[0]
        metadata = dict(connection.execute("SELECT key, value FROM metadata").fetchall())
        result = {
            "database_path": str(Path(database_path)),
            "counts": counts,
            "tag_namespaces": namespace_counts,
            "registered_packs": registered_packs,
        }
        for key in (
            "official_xmp_items", "official_tagged_resources",
            "unmatched_xmp_items", "tag_assignments", "audio_analyzed",
            "audio_reused", "audio_errors", "presets_parsed", "presets_reused",
            "preset_errors", "resource_links_resolved", "resource_links_unresolved",
        ):
            if key in metadata:
                result[key] = int(metadata[key])
        result["library_creator"] = metadata.get("library_creator") or None
        return result
    finally:
        connection.close()


def search_database(
    database_path: str | Path = LOCAL_DATABASE,
    *,
    query: str | None = None,
    role: str | None = None,
    kind: str | None = None,
    pack: str | None = None,
    official_tag: str | None = None,
    bpm_min: float | None = None,
    bpm_max: float | None = None,
    key: str | None = None,
    root_note: str | None = None,
    duration_min: float | None = None,
    duration_max: float | None = None,
    is_loop: bool | None = None,
    device: str | None = None,
    rack_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        parameters: list[Any] = []
        conditions = ["r.exists_flag = 1"]
        joins = [
            "LEFT JOIN packs p ON p.id = r.pack_id",
            "LEFT JOIN audio_features af ON af.resource_id = r.id",
            "LEFT JOIN preset_details pd ON pd.resource_id = r.id",
        ]
        fts_query = _fts_query(query)
        if fts_query:
            joins.append("JOIN resource_fts f ON f.resource_id = r.id")
            conditions.append("resource_fts MATCH ?")
            parameters.append(fts_query)
        if kind:
            conditions.append("LOWER(r.kind) = LOWER(?)")
            parameters.append(kind)
        if pack:
            conditions.append("LOWER(COALESCE(p.name, '')) LIKE LOWER(?)")
            parameters.append(f"%{pack}%")
        if role:
            conditions.append(
                "EXISTS (SELECT 1 FROM resource_tags rt JOIN tags t ON t.id = rt.tag_id "
                "WHERE rt.resource_id = r.id AND t.namespace = 'filename_inferred' "
                "AND t.group_name = 'role' AND LOWER(t.canonical_name) = LOWER(?))"
            )
            parameters.append(role)
        if official_tag:
            if "|" in official_tag:
                tag_condition = "LOWER(t.canonical_name) = LOWER(?)"
                parameters.append(official_tag)
            else:
                tag_condition = (
                    "(LOWER(t.canonical_name) = LOWER(?) "
                    "OR LOWER(t.canonical_name) LIKE LOWER(?))"
                )
                parameters.extend((official_tag, f"%|{official_tag}"))
            conditions.append(
                "EXISTS (SELECT 1 FROM resource_tags rt JOIN tags t ON t.id = rt.tag_id "
                "WHERE rt.resource_id = r.id AND t.namespace = 'ableton_factory' "
                f"AND {tag_condition})"
            )
        for value, operator, column in (
            (bpm_min, ">=", "af.estimated_bpm"),
            (bpm_max, "<=", "af.estimated_bpm"),
            (duration_min, ">=", "af.duration_seconds"),
            (duration_max, "<=", "af.duration_seconds"),
        ):
            if value is not None:
                conditions.append(f"{column} {operator} ?")
                parameters.append(float(value))
        if key:
            conditions.append("LOWER(COALESCE(af.estimated_key, '')) = LOWER(?)")
            parameters.append(key)
        if root_note:
            conditions.append("LOWER(COALESCE(af.root_note, '')) = LOWER(?)")
            parameters.append(root_note)
        if is_loop is not None:
            conditions.append("af.is_loop = ?")
            parameters.append(1 if is_loop else 0)
        if device:
            conditions.append("LOWER(COALESCE(pd.device_chain_json, '')) LIKE LOWER(?)")
            parameters.append(f"%{device}%")
        if rack_type:
            conditions.append("LOWER(COALESCE(pd.rack_type, '')) LIKE LOWER(?)")
            parameters.append(f"%{rack_type}%")
        parameters.append(max(1, int(limit)))
        rows = connection.execute(
            f"""
            SELECT
                r.id, r.name, r.kind, r.extension, r.relative_path,
                r.absolute_path AS path, r.size_bytes, r.load_mode,
                r.agent_control, r.auto_insert, p.name AS pack,
                af.duration_seconds, af.sample_rate, af.channels, af.bit_depth,
                af.encoding, af.estimated_bpm, af.bpm_confidence,
                af.estimated_key, af.key_confidence, af.root_note,
                af.root_note_confidence, af.is_loop, af.loop_confidence,
                af.analysis_status, af.analysis_error,
                pd.rack_type, pd.primary_device, pd.device_chain_json,
                pd.macro_names_json, pd.referenced_sample_count,
                pd.preview_audio_path, pd.parse_status, pd.parse_error,
                COALESCE((
                    SELECT GROUP_CONCAT(t.namespace || ':' || t.canonical_name, ' | ')
                    FROM resource_tags rt JOIN tags t ON t.id = rt.tag_id
                    WHERE rt.resource_id = r.id
                ), '') AS tags
            FROM resources r
            {' '.join(joins)}
            WHERE {' AND '.join(conditions)}
            ORDER BY COALESCE(p.name, ''), r.name COLLATE NOCASE
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _ensure_tag(
    connection: sqlite3.Connection,
    cache: dict[tuple[str, str], int],
    namespace: str,
    group_name: str,
    canonical_name: str,
    display_name: str,
) -> int:
    key = (namespace, canonical_name)
    if key in cache:
        return cache[key]
    connection.execute(
        "INSERT OR IGNORE INTO tags(namespace, group_name, canonical_name, display_name) "
        "VALUES (?, ?, ?, ?)",
        (namespace, group_name, canonical_name, display_name),
    )
    tag_id = connection.execute(
        "SELECT id FROM tags WHERE namespace = ? AND canonical_name = ?",
        key,
    ).fetchone()[0]
    cache[key] = int(tag_id)
    return int(tag_id)


def _assign_tag(
    connection: sqlite3.Connection,
    resource_id: str,
    tag_id: int,
    source: str,
    confidence: float,
    method_version: str,
    observed_at: str,
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO resource_tags(
            resource_id, tag_id, source, confidence, method_version, observed_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (resource_id, tag_id, source, confidence, method_version, observed_at),
    )


def _relative_resource_path(absolute_path: str, pack_metadata: dict[str, Any] | None) -> str:
    if not pack_metadata:
        return Path(absolute_path).name
    try:
        return Path(absolute_path).relative_to(pack_metadata["root_path"]).as_posix()
    except ValueError:
        return Path(absolute_path).name


def _fingerprint(item: dict[str, Any]) -> str:
    raw = f"{item.get('size_bytes', 0)}:{item.get('mtime_ns', 0)}:{item.get('extension', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _stable_id(kind: str, key: str) -> str:
    digest = hashlib.sha256(f"{kind}:{key.casefold()}".encode("utf-8")).hexdigest()
    return digest[:32]


def _normal_path(value: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(value))).replace("\\", "/").casefold()


def _normal_relative_path(value: str | Path) -> str:
    return str(value).replace("\\", "/").strip("/").casefold()


def _fts_query(query: str | None) -> str | None:
    terms = re.findall(r"[^\W_]+", str(query or ""), flags=re.UNICODE)
    if not terms:
        return None
    return " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"*' for term in terms)

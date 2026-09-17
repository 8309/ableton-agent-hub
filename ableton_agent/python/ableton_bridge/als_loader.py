"""Shared, bounded loader for read-only Ableton Live Set documents."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import io
from pathlib import Path
import threading
from typing import Any
import xml.etree.ElementTree as ET


DEFAULT_MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
DEFAULT_MAX_COMPRESSED_BYTES = 32 * 1024 * 1024
_CACHE_SIZE = 4


class AlsDocumentError(RuntimeError):
    """Raised when a saved ALS document cannot be read safely."""


@dataclass(frozen=True)
class AlsDocument:
    path: Path
    raw: bytes
    xml: bytes
    root: ET.Element
    live_set: ET.Element
    source_info: dict[str, Any]
    warnings: list[str]
    cache_hit: bool = False


_cache: OrderedDict[tuple[str, int, int], AlsDocument] = OrderedDict()
_lock = threading.RLock()


def _decompress(raw: bytes, maximum: int) -> bytes:
    if raw[:2] != b"\x1f\x8b":
        raise AlsDocumentError("ALS file does not have the expected Gzip header")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as stream:
            data = stream.read(maximum + 1)
    except (OSError, EOFError) as error:
        raise AlsDocumentError(f"Cannot decompress ALS Gzip data: {error}") from error
    if len(data) > maximum:
        raise AlsDocumentError(
            f"Decompressed ALS exceeds the configured safety limit of {maximum} bytes"
        )
    return data


def _parse(xml: bytes) -> tuple[ET.Element, ET.Element]:
    # ElementTree does not resolve external entities here, but rejecting DTDs
    # also makes the input contract explicit and keeps this parser conservative.
    if b"\x00" in xml or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise AlsDocumentError("Unsupported XML encoding or DTD/entity declaration")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise AlsDocumentError(f"Decompressed ALS is not valid XML: {error}") from error
    if root.tag != "Ableton":
        raise AlsDocumentError(f"Unexpected ALS XML root: {root.tag}")
    live_set = root.find("LiveSet")
    if live_set is None:
        raise AlsDocumentError("ALS XML does not contain LiveSet")
    return root, live_set


def _source_info(path: Path, raw: bytes, xml: bytes, stat_result) -> dict[str, Any]:
    token = hashlib.sha256(raw).hexdigest()
    return {
        "kind": "saved_als",
        "path": str(path),
        "compressed_bytes": len(raw),
        "uncompressed_bytes": len(xml),
        "size_bytes": stat_result.st_size,
        "modified_ns": stat_result.st_mtime_ns,
        "modified_utc": datetime.fromtimestamp(
            stat_result.st_mtime, tz=timezone.utc
        ).isoformat(),
        "sha256": token,
        "file_token": token,
        "live_verified": False,
        "unsaved_changes_included": False,
        "changed_during_read": False,
    }


def load_als_document(
    path: str | Path,
    *,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
    max_compressed_bytes: int = DEFAULT_MAX_COMPRESSED_BYTES,
) -> AlsDocument:
    """Load and cache one immutable-in-practice XML tree keyed by file stat.

    Consumers only read the returned ElementTree. A changed file is rejected
    instead of allowing a page or a combined snapshot to mix two saved states.
    """
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise AlsDocumentError(f"ALS file does not exist: {source}")
    if max_uncompressed_bytes < 1:
        raise AlsDocumentError("max_uncompressed_bytes must be positive")
    if max_compressed_bytes < 1:
        raise AlsDocumentError("max_compressed_bytes must be positive")

    before = source.stat()
    key = (str(source), before.st_size, before.st_mtime_ns)
    with _lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            return AlsDocument(
                path=cached.path,
                raw=cached.raw,
                xml=cached.xml,
                root=cached.root,
                live_set=cached.live_set,
                source_info=dict(cached.source_info),
                warnings=list(cached.warnings),
                cache_hit=True,
            )

    if before.st_size > max_compressed_bytes:
        raise AlsDocumentError(
            f"Compressed ALS exceeds the configured safety limit of {max_compressed_bytes} bytes"
        )
    raw = source.read_bytes()
    after_read = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after_read.st_size, after_read.st_mtime_ns):
        raise AlsDocumentError("ALS changed while reading; retry after saving finishes")
    xml = _decompress(raw, max_uncompressed_bytes)
    root, live_set = _parse(xml)
    after_parse = source.stat()
    if (after_read.st_size, after_read.st_mtime_ns) != (
        after_parse.st_size,
        after_parse.st_mtime_ns,
    ):
        raise AlsDocumentError("ALS changed while reading; retry after saving finishes")

    source_info = _source_info(source, raw, xml, after_parse)
    warnings = [
        "Saved ALS data is the last saved disk state, not necessarily current Live memory state.",
        "ALS XML file IDs are not Live runtime IDs and cannot authorize Hub writes.",
    ]
    document = AlsDocument(
        path=source,
        raw=raw,
        xml=xml,
        root=root,
        live_set=live_set,
        source_info=source_info,
        warnings=warnings,
    )
    final_key = (str(source), after_parse.st_size, after_parse.st_mtime_ns)
    with _lock:
        _cache[final_key] = document
        _cache.move_to_end(final_key)
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return document


def clear_als_document_cache() -> None:
    with _lock:
        _cache.clear()

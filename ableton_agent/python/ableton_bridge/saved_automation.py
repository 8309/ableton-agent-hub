"""Read saved Arrangement automation, never Live state or writable runtime IDs."""
from __future__ import annotations

import gzip
import hashlib
import io
import math
from pathlib import Path
import time
from threading import Lock
import xml.etree.ElementTree as ET

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SavedAutomationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    als_path: str = Field(min_length=1)
    envelope_key: str | None = None
    query: str | None = None
    start_beat: float = Field(default=0, ge=0)
    end_beat: float | None = Field(default=None, ge=0)
    cursor: int = Field(default=0, strict=True, ge=0)
    limit: int = Field(default=32, strict=True, ge=1, le=128)
    expected_file_token: str | None = None
    beats_per_bar: float = Field(default=4, gt=0, le=64)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_beat is not None and self.end_beat < self.start_beat:
            raise ValueError("end_beat must be >= start_beat")
        if self.cursor and not self.expected_file_token:
            raise ValueError("Continuation requires expected_file_token")
        return self


def value(node, path, default=None):
    child = node.find(path)
    return child.get("Value", default) if child is not None else default


def scalar(raw):
    if raw in ("true", "false"):
        return raw == "true"
    try:
        number = float(raw)
        return number if math.isfinite(number) else raw
    except (ValueError, TypeError):
        return raw


def parse_saved_curves(xml):
    # Live saves UTF-8 XML; reject DTD/entities instead of accepting arbitrary XML.
    if b"\x00" in xml or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("Unsupported XML encoding or DTD/entity declaration")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise ValueError("Invalid saved Live Set XML: " + str(error)) from error
    live_set = root.find("LiveSet")
    if root.tag != "Ableton" or live_set is None:
        raise ValueError("Not an Ableton Live Set document")
    tracks = list(live_set.find("Tracks")) if live_set.find("Tracks") is not None else []
    tracks += [node for tag in ("MainTrack", "MasterTrack") for node in live_set.findall(tag)]
    curves = []
    for track_index, track in enumerate(tracks):
        section = "main" if track.tag in ("MainTrack", "MasterTrack") else "return" if track.tag == "ReturnTrack" else "track"
        track_name = value(track, "Name/EffectiveName", value(track, "Name/UserName", track.tag))
        targets = {}

        def walk(node, path, devices):
            if node.tag in ("AudioClip", "MidiClip"):
                return
            target = node.find("AutomationTarget")
            if target is not None:
                descriptor = dict(parameter_xml_path="/".join(path), parameter_xml_name=node.tag,
                                  device_path=devices, manual_saved_value=scalar(value(node, "Manual")))
                targets.setdefault(target.get("Id"), []).append(descriptor)
            for child in node:
                next_devices = devices
                if node.tag == "Devices":
                    next_devices = devices + [dict(type=child.tag, device_file_id=child.get("Id"),
                                                   name=value(child, "UserName", child.tag))]
                walk(child, path + [child.tag + ("[" + child.get("Id") + "]" if child.get("Id") is not None else "")], next_devices)

        walk(track, [track.tag], [])
        for index, envelope in enumerate(track.findall("AutomationEnvelopes/Envelopes/AutomationEnvelope")):
            target_id = value(envelope, "EnvelopeTarget/PointeeId")
            candidates = targets.get(target_id, [])
            points, warnings = [], []
            for event in envelope.findall("Automation/Events/*"):
                if event.tag not in ("FloatEvent", "BoolEvent", "EnumEvent"):
                    warnings.append("Unknown event type: " + event.tag)
                try:
                    beat = float(event.get("Time", "nan"))
                    if not math.isfinite(beat) or event.get("Value") is None:
                        raise ValueError()
                except ValueError:
                    warnings.append("Unrecognized event retained only as an incomplete-curve warning")
                    continue
                points.append(dict(beat=beat, value=scalar(event.get("Value")), event_type=event.tag,
                                   raw_attributes=dict(event.attrib)))
            points.sort(key=lambda p: p["beat"])
            if len(candidates) != 1:
                warnings.append("Automation target missing or ambiguous; no runtime parameter mapping")
            curves.append(dict(envelope_key=f"{track_index}:{index}", envelope_file_id=envelope.get("Id"),
                track_file_id=track.get("Id"), track_name=track_name, section=section,
                target_file_id=target_id, target=candidates[0] if len(candidates) == 1 else None,
                points=points, warnings=warnings))
    return curves, root.get("Creator")


class SavedAutomationReader:
    """One-file cache to avoid decompressing/parsing again for each requested page."""
    MAX_XML = 64 * 1024 * 1024

    def __init__(self):
        self.cached = None
        self.lock = Lock()

    def read(self, fields):
        with self.lock:
            return self._read(fields)

    def _read(self, fields):
        started = time.monotonic()
        request = SavedAutomationRequest.model_validate(fields)
        path = Path(request.als_path).expanduser()
        if not path.is_absolute() or path.suffix.lower() != ".als":
            raise ValueError("An explicit absolute .als file path is required")
        path = path.resolve(strict=True)
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        hit = self.cached is not None and self.cached[0] == key
        if not hit:
            if stat.st_size > 32 * 1024 * 1024:
                raise ValueError("Compressed ALS exceeds 32 MiB read bound")
            raw = path.read_bytes()
            token = hashlib.sha256(raw).hexdigest()
            with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as stream:
                xml = stream.read(self.MAX_XML + 1)
            if len(xml) > self.MAX_XML:
                raise ValueError("Expanded XML exceeds 64 MiB read bound")
            curves, creator = parse_saved_curves(xml)
            after = path.stat()
            if (after.st_size, after.st_mtime_ns) != key[1:]:
                raise ValueError("ALS changed while reading; retry after saving finishes")
            self.cached = (key, token, curves, creator)
        _, token, curves, creator = self.cached
        if request.expected_file_token and request.expected_file_token != token:
            raise ValueError("stale_file: ALS changed; restart at cursor 0")

        def point(p):
            if p is None:
                return None
            return {**p, "bar_reference": 1 + p["beat"] / request.beats_per_bar if p["beat"] >= 0 else None,
                    "bar_number": 1 + math.floor(p["beat"] / request.beats_per_bar) if p["beat"] >= 0 else None,
                    "beat_offset_in_bar": p["beat"] % request.beats_per_bar if p["beat"] >= 0 else None}

        source = dict(kind="saved_als", path=str(path), file_token=token, modified_ns=stat.st_mtime_ns,
                      size_bytes=stat.st_size, creator=creator, live_verified=False, unsaved_changes_included=False)
        result = dict(ok=True, read_only=True, source=source, cache_hit=hit,
                      bar_basis=dict(beats_per_bar=request.beats_per_bar, origin_bar=1,
                                     assumption="constant caller meter, default 4/4; not the saved signature map"),
                      warnings=["Saved file only, not the current Live Set. File IDs are not Live IDs.",
                                "First/last nodes are not activation/end times. Values retain file units; no UI conversion or curve interpolation."])
        if request.envelope_key is None:
            rows = []
            for curve in curves:
                summary = {k: v for k, v in curve.items() if k != "points"}
                search = str(summary).casefold()
                if request.query and request.query.casefold() not in search:
                    continue
                finite = [p for p in curve["points"] if p["beat"] >= 0]
                summary.update(node_count=len(finite), first_node=point(finite[0]) if finite else None,
                               last_node=point(finite[-1]) if finite else None)
                rows.append(summary)
        else:
            curve = next((c for c in curves if c["envelope_key"] == request.envelope_key), None)
            if curve is None:
                raise ValueError("Unknown saved envelope_key; list curves first")
            nodes = [p for p in curve["points"] if p["beat"] >= 0]
            end = request.end_beat if request.end_beat is not None else math.inf
            rows = []
            for i, p in enumerate(nodes):
                if request.start_beat <= p["beat"] <= end:
                    row = point(p)
                    following = nodes[i+1] if i+1 < len(nodes) else None
                    row["next_node"] = point(following)
                    row["value_changes_to_next"] = following is not None and p["value"] != following["value"]
                    row["interpolation"] = "not_evaluated; raw curve attributes preserved"
                    rows.append(row)
            before = [p for p in curve["points"] if p["beat"] < request.start_beat]
            after = next((p for p in nodes if p["beat"] > end), None)
            result.update(envelope={k:v for k,v in curve.items() if k != "points"},
                          range=dict(start_beat=request.start_beat, end_beat=request.end_beat),
                          preceding_node=point(before[-1]) if before else None, following_node=point(after),
                          first_node=point(nodes[0]) if nodes else None, last_node=point(nodes[-1]) if nodes else None,
                          curve_end_beat=None, curve_parse_complete=not curve["warnings"])
        if request.cursor > len(rows):
            raise ValueError("cursor outside selected saved data")
        page = rows[request.cursor:request.cursor+request.limit]
        next_cursor = request.cursor+len(page)
        result.update(items=page, total_items=len(rows), complete=next_cursor == len(rows),
                      continuation=None if next_cursor == len(rows) else dict(cursor=next_cursor, expected_file_token=token),
                      elapsed_ms=round((time.monotonic()-started)*1000, 3))
        return result

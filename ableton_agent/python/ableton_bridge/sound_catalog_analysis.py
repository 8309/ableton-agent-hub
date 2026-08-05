from __future__ import annotations

from collections import Counter
import gzip
import json
import math
from pathlib import Path
import re
import struct
from typing import Any
import wave
import xml.etree.ElementTree as ET


AUDIO_ANALYSIS_VERSION = "audio_header_filename_v1"
PRESET_PARSER_VERSION = "ableton_preset_xml_v2"

_BPM_PATTERN = re.compile(
    r"(?<!\d)(?P<bpm>\d{2,3}(?:\.\d+)?)\s*[-_ ]?\s*bpm\b",
    re.IGNORECASE,
)
_KEY_PATTERN = re.compile(
    r"(?<![A-Za-z])(?P<note>[A-Ga-g](?:#|b|♯|♭)?)"
    r"(?P<quality>maj(?:or)?|min(?:or)?|m)(?P<extension>\d{0,2})\b",
    re.IGNORECASE,
)
_ROOT_NOTE_PATTERN = re.compile(
    r"(?P<note>[A-Ga-g](?:#|b|♯|♭)?)(?P<octave>-?\d)(?!\d)",
)


def analyze_audio_resource(path: str | Path, name: str, relative_path: str) -> dict[str, Any]:
    source = Path(path)
    header: dict[str, Any]
    try:
        header = read_audio_header(source)
        status = "ok"
        error = None
    except Exception as exc:
        header = {}
        status = "error"
        error = f"{type(exc).__name__}: {exc}"
    inferred = infer_filename_metadata(name, relative_path)
    return {
        "duration_seconds": header.get("duration_seconds"),
        "sample_rate": header.get("sample_rate"),
        "channels": header.get("channels"),
        "bit_depth": header.get("bit_depth"),
        "encoding": header.get("encoding"),
        "estimated_bpm": inferred.get("estimated_bpm"),
        "bpm_confidence": inferred.get("bpm_confidence"),
        "estimated_key": inferred.get("estimated_key"),
        "key_confidence": inferred.get("key_confidence"),
        "root_note": inferred.get("root_note"),
        "root_note_confidence": inferred.get("root_note_confidence"),
        "is_loop": inferred.get("is_loop"),
        "loop_confidence": inferred.get("loop_confidence"),
        "analysis_status": status,
        "analysis_error": error,
        "header_method": header.get("header_method"),
        "metadata_json": json.dumps(inferred.get("provenance", {}), ensure_ascii=False),
        "analysis_version": AUDIO_ANALYSIS_VERSION,
    }


def read_audio_header(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    suffix = source.suffix.casefold()
    if suffix in {".aif", ".aiff", ".aifc"}:
        return _read_aiff_header(source)
    if suffix == ".wav":
        with wave.open(str(source), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            return {
                "duration_seconds": frames / rate if rate else None,
                "sample_rate": rate,
                "channels": handle.getnchannels(),
                "bit_depth": handle.getsampwidth() * 8,
                "encoding": "PCM",
                "header_method": "wave_stdlib_v1",
            }
    try:
        import soundfile as sf
    except ImportError as exc:
        raise ValueError(f"unsupported audio extension without soundfile: {suffix}") from exc
    info = sf.info(str(source))
    bit_depth = _bit_depth_from_subtype(info.subtype)
    return {
        "duration_seconds": info.frames / info.samplerate if info.samplerate else None,
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "bit_depth": bit_depth,
        "encoding": info.subtype or info.format,
        "header_method": "soundfile_info_v1",
    }


def infer_filename_metadata(name: str, relative_path: str) -> dict[str, Any]:
    text = f"{name} {relative_path}"
    normalized_path = relative_path.replace("\\", "/").casefold()
    provenance: dict[str, Any] = {}

    bpm = bpm_confidence = None
    bpm_match = _BPM_PATTERN.search(text)
    if bpm_match:
        candidate = float(bpm_match.group("bpm"))
        if 20 <= candidate <= 400:
            bpm = candidate
            bpm_confidence = 0.95
            provenance["bpm"] = "filename_bpm_token"

    estimated_key = key_confidence = None
    key_match = _KEY_PATTERN.search(name)
    if key_match:
        note = _normalize_note(key_match.group("note"))
        quality = key_match.group("quality").casefold()
        estimated_key = f"{note} {'major' if quality.startswith('maj') else 'minor'}"
        extension = key_match.group("extension")
        key_confidence = 0.6 if extension else 0.78
        provenance["key"] = "filename_key_or_chord_token"

    root_note = root_note_confidence = None
    root_match = _ROOT_NOTE_PATTERN.search(name)
    if root_match:
        root_note = f"{_normalize_note(root_match.group('note'))}{root_match.group('octave')}"
        root_note_confidence = 0.72
        provenance["root_note"] = "filename_note_octave_token"

    is_loop = loop_confidence = None
    path_parts = {part.strip() for part in normalized_path.split("/")}
    if path_parts.intersection({"one shots", "one shot", "one-shots", "one-shot"}):
        is_loop = False
        loop_confidence = 0.98
        provenance["loop"] = "path_one_shot_folder"
    elif path_parts.intersection({"loops", "loop", "drum loops", "music loops"}):
        is_loop = True
        loop_confidence = 0.98
        provenance["loop"] = "path_loop_folder"
    elif re.search(r"\bloop\b", name, re.IGNORECASE):
        is_loop = True
        loop_confidence = 0.82
        provenance["loop"] = "filename_loop_token"
    elif bpm is not None:
        is_loop = True
        loop_confidence = 0.68
        provenance["loop"] = "filename_bpm_proxy"

    return {
        "estimated_bpm": bpm,
        "bpm_confidence": bpm_confidence,
        "estimated_key": estimated_key,
        "key_confidence": key_confidence,
        "root_note": root_note,
        "root_note_confidence": root_note_confidence,
        "is_loop": is_loop,
        "loop_confidence": loop_confidence,
        "provenance": provenance,
    }


def parse_ableton_preset(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        data = source.read_bytes()
        xml_data = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
        root = ET.fromstring(xml_data)
    except Exception as exc:
        return {
            "rack_type": None,
            "primary_device": None,
            "devices": [],
            "macro_names": [],
            "references": [],
            "creator": None,
            "parse_status": "error",
            "parse_error": f"{type(exc).__name__}: {exc}",
            "parser_version": PRESET_PARSER_VERSION,
        }

    devices: list[str] = []
    device_elements: list[ET.Element] = []
    for element in root.iter():
        tag = _local_tag(element.tag)
        child_tags = {_local_tag(child.tag) for child in list(element)}
        if (
            "LomId" in child_tags
            and ("On" in child_tags or tag.startswith("MxDevice"))
            and tag not in devices
        ):
            devices.append(tag)
            device_elements.append(element)

    parent_by_element = {child: parent for parent in root.iter() for child in parent}
    macro_groups_by_owner: dict[ET.Element, list[dict[str, Any]]] = {}
    for element in root.iter():
        tag = _local_tag(element.tag)
        match = re.fullmatch(r"MacroDisplayNames\.(\d+)", tag)
        if not match:
            continue
        value = element.attrib.get("Value", "").strip()
        if value:
            owner = parent_by_element.get(element)
            if owner is None:
                continue
            macro_groups_by_owner.setdefault(owner, []).append({
                "index": int(match.group(1)),
                "name": value,
                "is_default": bool(re.fullmatch(r"Macro \d+", value)),
            })
    macro_groups = []
    for owner, names in macro_groups_by_owner.items():
        names.sort(key=lambda item: item["index"])
        macro_groups.append({"owner": _local_tag(owner.tag), "names": names})
    top_device = device_elements[0] if device_elements else None
    macro_names = list(macro_groups_by_owner.get(top_device, []))

    references: list[dict[str, str | None]] = []
    seen_references: set[tuple[str, str, str]] = set()
    for element in root.iter():
        if _local_tag(element.tag) != "FileRef":
            continue
        values: dict[str, str] = {}
        for child in element.iter():
            tag = _local_tag(child.tag)
            if tag in {"RelativePath", "Path", "LivePackId", "LivePackName"}:
                value = child.attrib.get("Value")
                if value:
                    values[tag] = value
        relative = values.get("RelativePath", "")
        absolute = values.get("Path", "")
        pack_id = values.get("LivePackId", "")
        if not relative and not absolute:
            continue
        key = (relative.casefold(), absolute.casefold(), pack_id.casefold())
        if key in seen_references:
            continue
        seen_references.add(key)
        references.append({
            "relative_path": relative or None,
            "absolute_path": absolute or None,
            "live_pack_id": pack_id or None,
            "live_pack_name": values.get("LivePackName") or None,
        })

    group_devices = {
        "InstrumentGroupDevice", "AudioEffectGroupDevice", "MidiEffectGroupDevice",
        "DrumGroupDevice", "AudioBranchMixerDevice",
    }
    primary_device = next((device for device in devices if device not in group_devices), None)
    return {
        "rack_type": devices[0] if devices else _local_tag(list(root)[0].tag) if list(root) else None,
        "primary_device": primary_device or (devices[0] if devices else None),
        "devices": devices,
        "macro_names": macro_names,
        "macro_groups": macro_groups,
        "references": references,
        "creator": root.attrib.get("Creator"),
        "parse_status": "ok",
        "parse_error": None,
        "parser_version": PRESET_PARSER_VERSION,
    }


def _read_aiff_header(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        if handle.read(4) != b"FORM":
            raise ValueError("not an AIFF FORM file")
        form_size_data = handle.read(4)
        form_type = handle.read(4)
        if len(form_size_data) != 4 or form_type not in {b"AIFF", b"AIFC"}:
            raise ValueError("unsupported AIFF form")
        while True:
            header = handle.read(8)
            if not header:
                break
            if len(header) != 8:
                raise ValueError("truncated AIFF chunk header")
            chunk_id, chunk_size = struct.unpack(">4sI", header)
            if chunk_id != b"COMM":
                handle.seek(chunk_size + (chunk_size % 2), 1)
                continue
            data = handle.read(chunk_size)
            if len(data) != chunk_size:
                raise ValueError("truncated AIFF chunk")
            if chunk_size % 2:
                handle.read(1)
            if len(data) < 18:
                raise ValueError("truncated AIFF COMM chunk")
            channels, frames, bit_depth = struct.unpack(">hIh", data[:8])
            sample_rate = _decode_extended_80(data[8:18])
            encoding = "PCM"
            if form_type == b"AIFC" and len(data) >= 22:
                encoding = data[18:22].decode("ascii", "replace")
            return {
                "duration_seconds": frames / sample_rate if sample_rate else None,
                "sample_rate": int(round(sample_rate)) if sample_rate else None,
                "channels": channels,
                "bit_depth": bit_depth,
                "encoding": encoding,
                "header_method": "aiff_comm_chunk_v1",
            }
    raise ValueError("AIFF COMM chunk not found")


def _decode_extended_80(data: bytes) -> float:
    if len(data) != 10:
        raise ValueError("invalid 80-bit extended float")
    exponent = struct.unpack(">H", data[:2])[0]
    sign = -1 if exponent & 0x8000 else 1
    exponent &= 0x7FFF
    mantissa = int.from_bytes(data[2:], "big")
    if exponent == 0 and mantissa == 0:
        return 0.0
    if exponent == 0x7FFF:
        return math.inf
    return sign * math.ldexp(mantissa, exponent - 16383 - 63)


def _bit_depth_from_subtype(subtype: str | None) -> int | None:
    match = re.search(r"(\d+)", str(subtype or ""))
    return int(match.group(1)) if match else None


def _normalize_note(value: str) -> str:
    note = value[0].upper() + value[1:]
    return note.replace("♯", "#").replace("♭", "b")


def _local_tag(value: str) -> str:
    return value.rsplit("}", 1)[-1]

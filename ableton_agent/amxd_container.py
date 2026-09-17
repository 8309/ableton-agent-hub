"""Minimal AMXD container helpers; no legacy device builder dependency."""
import json
from pathlib import Path

FALLBACK_TEMPLATE = Path(__file__).resolve().parent / "dist" / "Ableton Agent Hub.amxd"


def _template_prefix(path: Path) -> bytes:
    data = path.read_bytes()
    marker = data.find(b"ptch")
    if not data.startswith(b"ampf") or marker < 0:
        raise ValueError(f"Unsupported AMXD template: {path}")
    return data[:marker]


def extract_patch_json(path: Path) -> dict:
    data = path.read_bytes()
    marker = len(_template_prefix(path))
    size = int.from_bytes(data[marker + 4:marker + 8], "little")
    return json.loads(data[marker + 8:marker + 8 + size].rstrip(b"\x00"))

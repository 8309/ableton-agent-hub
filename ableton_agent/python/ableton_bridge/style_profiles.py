from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StyleProfileError(RuntimeError):
    pass


STYLE_ROOT = Path(__file__).resolve().parents[2] / "styles"


def load_style_profile(style: str, *, style_root: Path = STYLE_ROOT) -> dict[str, Any]:
    slug = _normalize_style_slug(style)
    path = style_root / f"{slug}.json"
    if not path.exists():
        available = ", ".join(available_styles(style_root)) or "none"
        raise StyleProfileError(f"Unknown style {style!r}. Available styles: {available}")
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise StyleProfileError(f"Invalid style profile JSON: {path}") from error
    _validate_profile(profile, slug)
    return profile


def available_styles(style_root: Path = STYLE_ROOT) -> list[str]:
    if not style_root.exists():
        return []
    return sorted(path.stem for path in style_root.glob("*.json") if path.is_file())


def _normalize_style_slug(style: str) -> str:
    slug = str(style or "").strip().lower().replace("-", "_").replace(" ", "_")
    return "".join(character for character in slug if character.isalnum() or character == "_")


def _validate_profile(profile: dict[str, Any], expected_slug: str) -> None:
    if not isinstance(profile, dict):
        raise StyleProfileError("Style profile must be a JSON object")
    slug = profile.get("slug")
    if slug != expected_slug:
        raise StyleProfileError(f"Style profile slug must be {expected_slug!r}")
    if not isinstance(profile.get("role_keywords"), list):
        raise StyleProfileError("Style profile must contain role_keywords")
    roles = profile.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise StyleProfileError("Style profile must contain roles")

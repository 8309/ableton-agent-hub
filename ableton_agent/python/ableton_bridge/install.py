from __future__ import annotations

import hashlib
from importlib import resources
import os
from pathlib import Path
import tempfile
from typing import Any


HUB_FILE_NAMES = (
    "Ableton Agent Hub.amxd",
    "ableton_agent_read_core.js",
    "ableton_agent_snapshot.js",
    "ableton_agent_parameter_summary.js",
    "ableton_agent_mixer_control.js",
    "ableton_agent_inserter.js",
    "ableton_agent_sample_loader.js",
    "ableton_agent_multi_parameter_control.js",
    "ableton_agent_clip_writer.js",
    "ableton_agent_detail_clip_writer.js",
    "ableton_agent_clip_note_tools.js",
    "ableton_agent_clip_variation.js",
    "ableton_agent_arrangement_tools.js",
    "ableton_agent_track_management.js",
    "ableton_agent_routing.js",
    "ableton_agent_scene.js",
    "ableton_agent_device_chain.js",
    "ableton_agent_device_tree.js",
    "ableton_agent_macro_parameters.js",
    "ableton_agent_meter_monitor.js",
    "ableton_agent_sample_confirm.js",
    "ableton_agent_eq_tools.js",
    "ableton_agent_value_display.js",
    "ableton_agent_parameter_diagnostics.js",
    "ableton_agent_tempo.js",
    "ableton_agent_transport.js",
    "ableton_agent_locator.js",
)


def default_user_library() -> Path:
    candidates = (
        Path.home() / "Documents" / "Ableton" / "User Library",
        Path.home() / "Music" / "Ableton" / "User Library",
    )
    return next((path for path in candidates if path.exists()), candidates[0])


def default_hub_destination() -> Path:
    return (
        default_user_library()
        / "Presets"
        / "MIDI Effects"
        / "Max MIDI Effect"
        / "Ableton Agent Hub"
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _packaged_assets() -> dict[str, bytes]:
    root = resources.files("ableton_bridge.resources.hub")
    assets: dict[str, bytes] = {}
    for name in HUB_FILE_NAMES:
        asset = root.joinpath(name)
        if not asset.is_file():
            raise FileNotFoundError(f"Packaged Hub asset is missing: {name}")
        assets[name] = asset.read_bytes()
    return assets


def plan_hub_install(destination: str | Path | None = None) -> dict[str, Any]:
    target = Path(destination) if destination is not None else default_hub_destination()
    target = target.expanduser().resolve()
    assets = _packaged_assets()
    files = []
    for name, data in assets.items():
        destination_path = target / name
        expected_hash = _sha256_bytes(data)
        if not destination_path.exists():
            action = "create"
            current_hash = None
        else:
            current_hash = _sha256_file(destination_path)
            action = "unchanged" if current_hash == expected_hash else "update"
        files.append(
            {
                "name": name,
                "action": action,
                "sha256": expected_hash,
                "current_sha256": current_hash,
            }
        )
    return {
        "ok": True,
        "dry_run": True,
        "destination": str(target),
        "file_count": len(files),
        "changed_file_count": sum(item["action"] != "unchanged" for item in files),
        "files": files,
    }


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def install_hub(
    destination: str | Path | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    plan = plan_hub_install(destination)
    if dry_run:
        return plan

    target = Path(plan["destination"])
    assets = _packaged_assets()
    for item in plan["files"]:
        if item["action"] == "unchanged":
            continue
        _atomic_write(target / item["name"], assets[item["name"]])

    verification = []
    for name, data in assets.items():
        path = target / name
        expected_hash = _sha256_bytes(data)
        actual_hash = _sha256_file(path)
        verification.append(
            {
                "name": name,
                "sha256": actual_hash,
                "verified": actual_hash == expected_hash,
            }
        )
    ok = all(item["verified"] for item in verification)
    return {
        "ok": ok,
        "dry_run": False,
        "destination": str(target),
        "file_count": len(verification),
        "changed_file_count": plan["changed_file_count"],
        "files": verification,
    }

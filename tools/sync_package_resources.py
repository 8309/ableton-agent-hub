from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ableton_agent" / "dist"
DESTINATION = (
    ROOT
    / "ableton_agent"
    / "python"
    / "ableton_bridge"
    / "resources"
    / "hub"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync() -> dict:
    from sys import path as sys_path

    sys_path.insert(0, str(ROOT / "ableton_agent"))
    from build_hub_device import JAVASCRIPT_SOURCES

    names = ["Ableton Agent Hub.amxd", "hub_build_manifest.json", *(source.name for source in JAVASCRIPT_SOURCES)]
    DESTINATION.mkdir(parents=True, exist_ok=True)
    files = []
    for name in names:
        source = SOURCE / name
        if not source.is_file():
            raise FileNotFoundError(f"Built Hub asset is missing: {source}")
        destination = DESTINATION / name
        shutil.copy2(source, destination)
        files.append({"name": name, "sha256": sha256(destination)})
    return {"ok": True, "file_count": len(files), "files": files}


def main() -> int:
    print(json.dumps(sync(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

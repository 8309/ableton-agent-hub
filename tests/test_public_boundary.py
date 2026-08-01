from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ableton_agent"))


class PublicBoundaryTest(unittest.TestCase):
    def test_private_workspace_content_is_absent(self) -> None:
        forbidden = (
            "AGENTS.md",
            "SESSION_HANDOFF.md",
            "projects",
            "experiments",
            "ableton_agent/legacy",
            "ableton_agent/disabled_backup",
            "ableton_agent/sample_index/local_sample_index.json",
            "ableton_agent/sound_catalog/local_sound_catalog.json",
            "ableton_agent/sound_catalog/local_sound_catalog_summary.md",
        )
        self.assertEqual([], [path for path in forbidden if (ROOT / path).exists()])

    def test_public_text_has_no_named_user_profile_or_private_workspace(self) -> None:
        patterns = (
            re.compile(
                r"[A-Za-z]:[\\/]+Users[\\/]+(?!example(?:[\\/]|$)|username(?:[\\/]|$)|path(?:[\\/]|$))[^\\/\s]+",
                re.IGNORECASE,
            ),
            re.compile(
                r"[A-Za-z]:[\\/]+Documents[\\/]+codex[_-]f(?:[\\/]|$)",
                re.IGNORECASE,
            ),
            re.compile("ableton_agent_" + "workspace", re.IGNORECASE),
        )
        violations = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            if path.suffix.lower() not in {".py", ".js", ".json", ".md", ".txt"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(pattern.search(text) for pattern in patterns):
                violations.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], violations)

    def test_export_refuses_destination_inside_private_source(self) -> None:
        from tools.export_from_workspace import export

        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "private"
            source.mkdir()
            destination = source / "public"
            with self.assertRaisesRegex(ValueError, "outside the private workspace"):
                export(source, destination, dry_run=True)
            self.assertFalse(destination.exists())

    def test_hub_source_and_dist_javascript_match(self) -> None:
        from build_hub_device import JAVASCRIPT_SOURCES

        mismatches = []
        for source in JAVASCRIPT_SOURCES:
            built = ROOT / "ableton_agent" / "dist" / source.name
            if not built.exists() or source.read_bytes() != built.read_bytes():
                mismatches.append(source.name)
        self.assertEqual([], mismatches)

    def test_export_manifest_matches_exported_snapshot(self) -> None:
        manifest = json.loads((ROOT / "PUBLIC_EXPORT_MANIFEST.json").read_text())
        self.assertEqual(manifest["exported_file_count"], len(manifest["files"]))
        mismatches = []
        for relative, expected in manifest["files"].items():
            path = ROOT / relative
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                mismatches.append(relative)
        self.assertEqual([], mismatches)

    def test_public_product_files_are_not_overwritten_by_export(self) -> None:
        from tools.export_from_workspace import PUBLIC_OWNED_PATHS

        manifest = json.loads((ROOT / "PUBLIC_EXPORT_MANIFEST.json").read_text())
        exported = {Path(relative) for relative in manifest["files"]}
        self.assertTrue(PUBLIC_OWNED_PATHS.isdisjoint(exported))

    def test_public_product_name_replaces_legacy_device_name(self) -> None:
        searchable = (
            ROOT / "ableton_agent" / "python" / "ableton_bridge" / "client.py",
            ROOT / "ableton_agent" / "python" / "ableton_bridge" / "server.py",
        )
        combined = "\n".join(path.read_text(encoding="utf-8") for path in searchable)
        self.assertNotIn("Ableton Agent Bridge.amxd", combined)
        self.assertNotIn("Ableton Agent Bridge listening at", combined)


if __name__ == "__main__":
    unittest.main()

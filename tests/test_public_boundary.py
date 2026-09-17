from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ableton_agent"))


class PublicBoundaryTest(unittest.TestCase):
    def test_repository_fixes_text_line_endings_for_stable_hashes(self) -> None:
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("* text=auto eol=lf", attributes)
        self.assertIn("*.amxd binary", attributes)

    def test_private_workspace_content_is_absent(self) -> None:
        forbidden = (
            "SESSION_HANDOFF.md",
            "projects",
            "experiments",
            "ableton_agent/legacy",
            "ableton_agent/disabled_backup",
            "ableton_agent/sample_index/local_sample_index.json",
            "ableton_agent/sound_catalog/local_sound_catalog.json",
            "ableton_agent/sound_catalog/local_sound_catalog_summary.md",
            "ableton_agent/sound_catalog/local_sound_catalog.sqlite3",
            "ableton_agent/runtime",
        )
        self.assertEqual([], [path for path in forbidden if (ROOT / path).exists()])

    def test_public_agents_file_contains_safe_workflow_contract(self) -> None:
        from tools.export_from_workspace import PUBLIC_OWNED_PATHS

        path = ROOT / "AGENTS.md"
        text = path.read_text(encoding="utf-8")
        required = (
            "scripts/read_current_set.ps1",
            "UDP 7401",
            "--commit",
            "git diff --check",
            "test_*.py",
            "docs/safety_model.md",
            "ableton_agent/max/",
        )

        self.assertIn(Path("AGENTS.md"), PUBLIC_OWNED_PATHS)
        self.assertLessEqual(len(text.splitlines()), 100)
        self.assertEqual([], [item for item in required if item not in text])

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
        paths = []
        for directory, children, files in os.walk(ROOT):
            children[:] = [name for name in children if name not in {".git", ".venv", "build", "release", "__pycache__"}]
            paths.extend(Path(directory) / name for name in files)
        for path in paths:
            if path.suffix.lower() not in {".py", ".js", ".json", ".md", ".txt", ".ps1", ".amxd"}:
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

    def test_export_normalizes_text_before_manifest_hashing(self) -> None:
        from tools import export_from_workspace as exporter

        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "private"
            destination = Path(root) / "public"
            source.mkdir()
            (source / "module.js").write_bytes(b"first\r\nsecond\rthird\n")
            binary_payload = b"binary\r\ncontent\r"
            (source / "device.amxd").write_bytes(binary_payload)

            with (
                patch.object(exporter, "STATIC_FILES", ("module.js", "device.amxd")),
                patch.object(exporter, "HUB_JAVASCRIPT", ()),
                patch.object(exporter, "GLOB_RULES", ()),
                patch.object(exporter, "PUBLIC_OWNED_PATHS", set()),
            ):
                exporter.export(source, destination)

            normalized = b"first\nsecond\nthird\n"
            manifest = json.loads(
                (destination / "PUBLIC_EXPORT_MANIFEST.json").read_text()
            )
            self.assertEqual(normalized, (destination / "module.js").read_bytes())
            self.assertEqual(binary_payload, (destination / "device.amxd").read_bytes())
            self.assertEqual(
                hashlib.sha256(normalized).hexdigest(),
                manifest["files"]["module.js"],
            )

    def test_exporter_hub_javascript_matches_public_builder(self) -> None:
        from build_hub_device import JAVASCRIPT_SOURCES
        from tools.export_from_workspace import HUB_JAVASCRIPT

        self.assertEqual(
            set(source.name for source in JAVASCRIPT_SOURCES),
            set(HUB_JAVASCRIPT),
        )

    def test_legacy_test_filter_allows_methods_already_removed_upstream(self) -> None:
        from tools.export_from_workspace import export_public_tests

        source = """\
class DevicePackageTest:
    def test_builds_amxd_with_required_bridge_objects(self):
        pass

    def test_current_hub_behavior(self):
        pass
"""
        with tempfile.TemporaryDirectory() as root:
            source_path = Path(root) / "source.py"
            destination_path = Path(root) / "destination.py"
            source_path.write_text(source, encoding="utf-8")
            export_public_tests(source_path, destination_path)
            exported = destination_path.read_text(encoding="utf-8")

        self.assertNotIn("test_builds_amxd_with_required_bridge_objects", exported)
        self.assertIn("test_current_hub_behavior", exported)

    def test_hub_source_and_dist_javascript_match(self) -> None:
        from build_hub_device import JAVASCRIPT_SOURCES

        mismatches = []
        version = json.loads((ROOT / "ableton_agent/dist/hub_build_manifest.json").read_text())["build_id"]
        for source in JAVASCRIPT_SOURCES:
            built = ROOT / "ableton_agent" / "dist" / source.name
            expected = source.read_text().replace("__HUB_BUILD_ID__", version)
            if not built.exists() or expected != built.read_text():
                mismatches.append(source.name)
        self.assertEqual([], mismatches)

    def test_export_never_copies_local_build_and_portable_patch_has_no_absolute_js(self):
        from tools.export_from_workspace import STATIC_FILES
        from amxd_container import extract_patch_json
        self.assertFalse(any(path.startswith("ableton_agent/dist/") for path in STATIC_FILES))
        patch_data = extract_patch_json(ROOT / "ableton_agent/dist/Ableton Agent Hub.amxd")
        for item in patch_data["patcher"]["boxes"]:
            box = item["box"]
            if box.get("maxclass") == "jsui":
                self.assertNotRegex(box["filename"], r"[:/\\]")
            if box.get("text", "").startswith("js "):
                self.assertNotRegex(box["text"], r"[:/\\]")
        manifest = json.loads((ROOT / "ableton_agent/dist/hub_build_manifest.json").read_text())
        self.assertEqual("portable", manifest["mode"])

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

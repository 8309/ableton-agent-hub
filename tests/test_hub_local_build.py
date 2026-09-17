import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ableton_agent"))
from amxd_container import extract_patch_json
from build_hub_device import build_hub_amxd, hub_build_version, JAVASCRIPT_SOURCES


class LocalHubBuildTests(unittest.TestCase):
    def test_local_build_pins_entries_and_includes(self):
        with tempfile.TemporaryDirectory(prefix="hub space ") as folder:
            target = Path(folder)
            output = build_hub_amxd(target / "Hub.amxd", dependency_dir=target)
            patch = extract_patch_json(output)["patcher"]
            for item in patch["boxes"]:
                box = item["box"]
                if box.get("maxclass") == "jsui":
                    self.assertEqual(Path(box["filename"]).parent, target)
                    self.assertTrue(Path(box["filename"]).is_file())
                if box.get("maxclass") == "newobj" and box.get("text", "").startswith("js "):
                    script = Path(json.loads(box["text"][3:]))
                    self.assertEqual(script.parent, target)
                    self.assertTrue(script.is_file())
            self.assertEqual({entry["name"] for entry in patch["dependency_cache"]},
                             {source.name for source in JAVASCRIPT_SOURCES})
            for source in JAVASCRIPT_SOURCES:
                original = source.read_text(encoding="utf-8")
                installed = (target / source.name).read_text(encoding="utf-8")
                for dependency in JAVASCRIPT_SOURCES:
                    include = 'include("' + dependency.name + '")'
                    self.assertNotIn(include, installed)
                    if include in original:
                        self.assertIn("include(" + json.dumps((target / dependency.name).as_posix()) + ")", installed)
            version = next(x["box"]["text"] for x in patch["boxes"] if x["box"]["id"] == "obj-version")
            self.assertTrue(version.endswith("-local"))
            manifest = json.loads((target / "hub_build_manifest.json").read_text())
            self.assertEqual(version, "Version: " + manifest["build_id"])
            for name, digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256((target / name).read_bytes()).hexdigest(), digest)
            self.assertIn(manifest["build_id"], (target / "ableton_agent_health.js").read_text())
            self.assertIn(manifest["build_id"], (target / "ableton_agent_dashboard.js").read_text())
            self.assertNotEqual(hub_build_version(dependency_dir=target),
                                hub_build_version(dependency_dir=target / "other"))
            self.assertNotEqual(hub_build_version(dependency_dir=target), hub_build_version())

    def test_relative_install_path_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                build_hub_amxd(Path(folder) / "Hub.amxd", dependency_dir=Path("relative"))

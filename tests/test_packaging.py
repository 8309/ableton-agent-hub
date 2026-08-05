from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ableton_agent" / "python"))


class PackagingTest(unittest.TestCase):
    def test_public_release_documents_are_present(self) -> None:
        expected = (
            "README.md",
            "LICENSE",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "docs/getting_started.md",
            "docs/safety_model.md",
            "docs/live_api_limits.md",
            "docs/release_validation_v0.1.0-alpha.md",
            "docs/release_validation_v0.2.0-alpha.md",
            "docs/agent_setup.md",
            "docs/current_set_bootstrap.md",
            "docs/api_capability_matrix.md",
        )
        self.assertEqual([], [relative for relative in expected if not (ROOT / relative).is_file()])

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("ableton-agent.exe install --dry-run", readme)
        self.assertIn("docs/safety_model.md", readme)
        self.assertNotIn("Installation and packaging are not yet finalized", readme)

    def test_pyproject_declares_console_script_and_package_data(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(
            metadata["project"]["scripts"]["ableton-agent"],
            "ableton_bridge.cli:main",
        )
        self.assertEqual(
            metadata["tool"]["setuptools"]["package-data"]["ableton_bridge.resources.hub"],
            ["*.amxd", "*.js"],
        )
        self.assertEqual("0.2.0a0", metadata["project"]["version"])

    def test_packaged_hub_contains_all_declared_assets(self) -> None:
        from ableton_bridge.install import HUB_FILE_NAMES, _packaged_assets

        assets = _packaged_assets()
        self.assertEqual(set(HUB_FILE_NAMES), set(assets))
        self.assertEqual(24, len(HUB_FILE_NAMES))
        for name, data in assets.items():
            self.assertEqual((ROOT / "ableton_agent" / "dist" / name).read_bytes(), data)

    def test_install_dry_run_does_not_create_destination(self) -> None:
        from ableton_bridge.install import install_hub

        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "not-created"
            result = install_hub(destination, dry_run=True)
            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])
            self.assertEqual(24, result["changed_file_count"])
            self.assertFalse(destination.exists())

    def test_install_writes_verifies_and_is_idempotent(self) -> None:
        from ableton_bridge.install import HUB_FILE_NAMES, install_hub

        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "Hub"
            first = install_hub(destination)
            second = install_hub(destination)
            self.assertTrue(first["ok"])
            self.assertEqual(24, first["changed_file_count"])
            self.assertEqual(0, second["changed_file_count"])
            self.assertEqual(set(HUB_FILE_NAMES), {path.name for path in destination.iterdir()})

    def test_cli_install_reports_json(self) -> None:
        from ableton_bridge.cli import main

        with tempfile.TemporaryDirectory() as root:
            output = io.StringIO()
            with redirect_stdout(output):
                status = main(["install", "--destination", root, "--dry-run"])
            result = json.loads(output.getvalue())
            self.assertEqual(0, status)
            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])

    def test_cli_ping_uses_hub_client(self) -> None:
        from ableton_bridge.cli import main

        output = io.StringIO()
        with patch("ableton_bridge.cli.ping", return_value={"request_id": "r1"}):
            with redirect_stdout(output):
                status = main(["ping"])
        self.assertEqual(0, status)
        self.assertEqual("r1", json.loads(output.getvalue())["result"]["request_id"])

    def test_cli_progressive_initial_read_writes_quick_and_full_caches(self) -> None:
        from ableton_bridge.cli import main

        quick = {
            "status": "complete",
            "depth": "quick",
            "summary": {"depth": "quick", "track_count": 2},
        }
        full = {
            "status": "complete",
            "depth": "full",
            "summary": {"depth": "full", "midi_note_count": 12},
        }

        def fake_initial_read(**kwargs):
            self.assertEqual("full", kwargs["depth"])
            kwargs["on_quick_ready"](quick)
            return full

        with tempfile.TemporaryDirectory() as root:
            output_path = Path(root) / "set.json"
            output = io.StringIO()
            with patch("ableton_bridge.cli.initial_read", side_effect=fake_initial_read):
                with redirect_stdout(output):
                    status = main(["initial-read", "--output", str(output_path)])
            result = json.loads(output.getvalue())
            quick_path = Path(result["quick_output"])

            self.assertEqual(0, status)
            self.assertEqual(quick, json.loads(quick_path.read_text(encoding="utf-8")))
            self.assertEqual(full, json.loads(output_path.read_text(encoding="utf-8")))

    def test_cli_initial_read_failure_invalidates_old_caches(self) -> None:
        from ableton_bridge.cli import main
        from ableton_bridge.initial_read import InitialReadError

        with tempfile.TemporaryDirectory() as root:
            output_path = Path(root) / "set.json"
            quick_path = Path(root) / "set.quick.json"
            output_path.write_text("old full", encoding="utf-8")
            quick_path.write_text("old quick", encoding="utf-8")
            errors = io.StringIO()
            with patch(
                "ableton_bridge.cli.initial_read",
                side_effect=InitialReadError("Hub did not respond"),
            ):
                with redirect_stderr(errors):
                    status = main(["initial-read", "--output", str(output_path)])

            payload = json.loads(errors.getvalue())
            self.assertEqual(1, status)
            self.assertEqual("preflight", payload["stage"])
            self.assertFalse(output_path.exists())
            self.assertFalse(quick_path.exists())


if __name__ == "__main__":
    unittest.main()

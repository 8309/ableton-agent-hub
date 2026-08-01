from __future__ import annotations

from contextlib import redirect_stdout
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

    def test_packaged_hub_contains_all_declared_assets(self) -> None:
        from ableton_bridge.install import HUB_FILE_NAMES, _packaged_assets

        self.assertEqual(set(HUB_FILE_NAMES), set(_packaged_assets()))
        self.assertEqual(24, len(HUB_FILE_NAMES))

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


if __name__ == "__main__":
    unittest.main()

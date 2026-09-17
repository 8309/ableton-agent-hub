from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(os.name == "nt", "Windows project launchers")
class PythonEnvironmentTests(unittest.TestCase):
    def run_ps(self, command, override=None):
        env = dict(os.environ)
        env.pop("ABLETON_AGENT_PYTHON", None)
        if override is not None:
            env["ABLETON_AGENT_PYTHON"] = override
        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        return subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-EncodedCommand", encoded],
            env=env, cwd=tempfile.gettempdir(), capture_output=True, text=True,
            timeout=20,
        )

    def resolve(self, root, override=None):
        return self.run_ps(
            "$ErrorActionPreference = 'Stop'\n"
            f". {ps_quote(SCRIPTS / 'agent_python.ps1')}\n"
            f"Resolve-AgentPython -RepoRoot {ps_quote(root)}", override,
        )

    def test_default_is_project_venv_not_old_mcp_or_system(self):
        with tempfile.TemporaryDirectory() as directory:
            python = Path(directory) / ".venv/Scripts/python.exe"
            python.parent.mkdir(parents=True)
            python.touch()
            result = self.resolve(directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()), python)

    def test_explicit_absolute_override_supports_rollback(self):
        result = self.resolve(ROOT, sys.executable)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), sys.executable)

    def test_missing_env_does_not_try_available_system_python(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.resolve(directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No fallback was attempted", result.stderr)

    def test_invalid_override_does_not_silently_use_project_env(self):
        for override in ("python.exe", str(ROOT / "missing/python.exe"), str(ROOT)):
            with self.subTest(override=override):
                result = self.resolve(ROOT, override)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("No fallback was attempted", result.stderr)

    def test_wrapper_forwards_arguments_exit_and_bridge_import_from_other_cwd(self):
        with tempfile.TemporaryDirectory(prefix="agent python ") as directory:
            probe = Path(directory) / "probe.py"
            probe.write_text(
                "import json, os, sys, ableton_bridge\n"
                "print(json.dumps({'argv': sys.argv[1:], 'exe': sys.executable, "
                "'path': os.environ['PYTHONPATH']}))\n"
                "sys.exit(7)\n", encoding="utf-8",
            )
            result = self.run_ps(
                f"& {ps_quote(SCRIPTS / 'python.ps1')} {ps_quote(probe)} "
                "'two words' '--limit' '4'\nexit $LASTEXITCODE", sys.executable,
            )
            self.assertEqual(result.returncode, 7, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["argv"], ["two words", "--limit", "4"])
            self.assertEqual(payload["exe"], sys.executable)
            self.assertTrue(payload["path"].startswith(str(ROOT / "ableton_agent/python")))

    def test_launcher_restores_pythonpath(self):
        result = self.run_ps(
            "$env:PYTHONPATH = 'sentinel'\n"
            f"& {ps_quote(SCRIPTS / 'python.ps1')} --version\n"
            "Write-Output $env:PYTHONPATH", sys.executable,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], "sentinel")

    def test_all_launchers_share_resolution_and_installer_is_pinned(self):
        self.assertIn("python.ps1", (SCRIPTS / "start_ableton_mcp.ps1").read_text())
        bootstrap = (SCRIPTS / "read_current_set.ps1").read_text()
        self.assertIn("agent_python.ps1", bootstrap)
        self.assertNotIn("function Resolve-AgentPython", bootstrap)
        for name in ("agent_python.ps1", "install_ableton_mcp.ps1", "read_current_set.ps1"):
            content = (SCRIPTS / name).read_text()
            self.assertNotIn("codex-runtimes", content)
            self.assertNotIn("Get-Command python", content)
        installer = (SCRIPTS / "install_ableton_mcp.ps1").read_text()
        self.assertIn(".python-version", installer)
        self.assertIn("requirements-mcp.lock.txt", installer)
        self.assertIn("--managed-python", installer)
        direct = (ROOT / "ableton_agent/requirements-mcp.txt").read_text().splitlines()
        locked = (ROOT / "ableton_agent/requirements-mcp.lock.txt").read_text().splitlines()
        for requirement in direct:
            if requirement.strip() and not requirement.startswith("#"):
                self.assertIn(requirement, locked)

    def test_fresh_stdio_launcher_lists_tools_without_live_calls(self):
        try:
            from mcp import Client
            from mcp.client.stdio import StdioServerParameters, stdio_client
        except ImportError:
            self.skipTest("optional MCP dependency missing")

        async def exercise():
            env = dict(os.environ, ABLETON_AGENT_PYTHON=sys.executable)
            params = StdioServerParameters(
                command="powershell",
                args=["-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                      str(SCRIPTS / "start_ableton_mcp.ps1")], env=env,
            )
            async with Client(stdio_client(params), raise_exceptions=True) as client:
                result = await client.list_tools()
                return [tool.name for tool in result.tools]

        names = asyncio.run(asyncio.wait_for(exercise(), timeout=15))
        self.assertEqual(len(names), 27)
        self.assertIn("ableton_status", names)


if __name__ == "__main__":
    unittest.main()

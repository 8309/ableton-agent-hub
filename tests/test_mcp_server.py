from __future__ import annotations

import asyncio
from pathlib import Path
import tomllib
import unittest

try:
    from mcp import Client
except ImportError:  # The core bridge does not require the optional MCP environment.
    Client = None


@unittest.skipIf(Client is None, "optional mcp dependency is not installed")
class McpServerTests(unittest.TestCase):
    def test_server_exposes_supported_tools_and_correlates_call(self) -> None:
        import ableton_bridge.mcp_server as module

        original_service = module.service

        class FakeService:
            def status(self, **kwargs):
                return {"ok": True, "timeout": kwargs["timeout"]}

        async def exercise():
            module.service = FakeService()
            try:
                async with Client(module.mcp, raise_exceptions=True) as client:
                    listed = await client.list_tools()
                    names = [tool.name for tool in listed.tools]
                    result = await client.call_tool("ableton_status", {"timeout": 1.25})
                    return names, result.structured_content
            finally:
                module.service = original_service

        names, result = asyncio.run(exercise())

        self.assertEqual(
            names,
            [
                "ableton_status",
                "ableton_read_set",
                "ableton_find_target",
                "ableton_read_parameters",
                "ableton_set_mix",
                "ableton_set_parameters",
                "ableton_diagnose_parameters",
                "ableton_apply_batch",
                "ableton_transport",
                "ableton_tempo",
                "ableton_list_locators",
                "ableton_scan_clips",
                "ableton_read_clip_notes",
                "ableton_read_meters",
                "ableton_write_midi_clip",
                "ableton_edit_midi_notes",
                "ableton_vary_midi_clip",
                "ableton_search_sounds",
                "ableton_confirm_sample",
                "ableton_insert_device",
                "ableton_eq",
                "ableton_manage_tracks",
                "ableton_manage_scenes",
                "ableton_scan_automation",
                "ableton_edit_arrangement",
                "ableton_read_saved_automation",
                "ableton_read_saved_set",
            ],
        )
        self.assertEqual(result, {"ok": True, "timeout": 1.25})
        config_path = Path(__file__).resolve().parents[1] / "examples" / "mcp.toml"
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        enabled = config["mcp_servers"]["ableton_agent"]["enabled_tools"]
        self.assertCountEqual(enabled, names, "Project allowlist must match the supported MCP inventory")

    def test_read_tools_advertise_read_only_and_writes_do_not(self) -> None:
        import ableton_bridge.mcp_server as module

        async def exercise():
            async with Client(module.mcp, raise_exceptions=True) as client:
                listed = await client.list_tools()
                return {tool.name: tool.annotations for tool in listed.tools}

        annotations = asyncio.run(exercise())

        self.assertTrue(annotations["ableton_status"].read_only_hint)
        self.assertTrue(annotations["ableton_read_parameters"].read_only_hint)
        self.assertTrue(annotations["ableton_scan_automation"].read_only_hint)
        self.assertTrue(annotations["ableton_read_saved_automation"].read_only_hint)
        self.assertTrue(annotations["ableton_read_saved_set"].read_only_hint)
        self.assertFalse(annotations["ableton_edit_arrangement"].read_only_hint)
        self.assertFalse(annotations["ableton_set_mix"].read_only_hint)
        self.assertFalse(annotations["ableton_set_parameters"].destructive_hint)
        for name in ("ableton_list_locators", "ableton_scan_clips",
                     "ableton_read_clip_notes", "ableton_read_meters"):
            self.assertTrue(annotations[name].read_only_hint)
        for name in ("ableton_transport", "ableton_tempo"):
            self.assertFalse(annotations[name].read_only_hint)

    def test_common_tools_protocol_arguments_and_validation(self) -> None:
        import ableton_bridge.mcp_server as module
        from unittest.mock import Mock, patch

        fake = Mock()
        cases = [
            ("ableton_transport", {"action": "play", "beat": 128, "execution": "inspect"}, "control_transport"),
            ("ableton_tempo", {"bpm": 132.25}, "read_or_set_tempo"),
            ("ableton_list_locators", {}, "list_locators"),
            ("ableton_scan_clips", {"target": "session", "cursor": 4, "collection_token": "clips"}, "scan_clips"),
            ("ableton_read_clip_notes", {"clip_id": 77, "beat_window": 2}, "read_clip_notes"),
            ("ableton_read_meters", {"track_id": 88, "section": "return"}, "read_meters"),
            ("ableton_diagnose_parameters", {"track_id": 1, "device_id": 2}, "diagnose_parameters"),
            ("ableton_apply_batch", {"mix_changes": [], "parameter_changes": [], "execution": "inspect"}, "apply_batch"),
        ]
        for _, _, method in cases:
            getattr(fake, method).return_value = {"ok": True, "method": method}

        async def exercise():
            with patch.object(module, "service", fake):
                async with Client(module.mcp, raise_exceptions=True) as client:
                    for tool, args, method in cases:
                        result = await client.call_tool(tool, args)
                        self.assertEqual(result.structured_content, {"ok": True, "method": method})
                        for key, value in args.items():
                            self.assertEqual(getattr(fake, method).call_args.kwargs[key], value)
                    self.assertEqual(fake.read_or_set_tempo.call_args.kwargs["execution"], "inspect")
                    self.assertEqual(fake.scan_clips.call_args.kwargs["limit"], 4)
                    before = len(fake.mock_calls)
                    for tool, args in [("ableton_transport", {"action": "delete"}),
                                       ("ableton_tempo", {"bpm": 2}),
                                       ("ableton_scan_clips", {"limit": 65}),
                                       ("ableton_read_clip_notes", {"clip_id": -1}),
                                       ("ableton_diagnose_parameters", {"track_id": 1, "device_id": 2, "limit": 5}),
                                       ("ableton_apply_batch", {"mix_changes": [{"track_id": -1, "field": "volume", "value": 0.5}], "parameter_changes": []})]:
                        result = await client.call_tool(tool, args)
                        self.assertTrue(result.is_error, tool)
                    self.assertEqual(len(fake.mock_calls), before)

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()

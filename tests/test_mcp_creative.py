from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from ableton_bridge.mcp_creative import prepare_request, search_sounds
from ableton_bridge.mcp_tools import AbletonMcpService, McpOperations


class CreativeTests(unittest.TestCase):
    def test_inspect_default_and_private_legacy_safe_envelope(self):
        route, wire, apply = prepare_request("write_midi_clip", {
            "track_id": 11, "scene_id": 21, "notes": [], "execution": "inspect"})
        self.assertEqual(route, "/write_clip")
        self.assertFalse(apply)
        self.assertEqual(wire["action"], "mcp_creative_v1")
        self.assertNotIn("track_id", wire)
        self.assertEqual(wire["creative"]["track_id"], 11)

    def test_direct_apply_and_optional_token_same_route(self):
        fields = {"track_id": 11, "location": "arrangement", "start": 32, "notes": [], "execution": "apply"}
        self.assertTrue(prepare_request("write_midi_clip", fields)[1]["creative"]["direct_apply"])
        route, wire, apply = prepare_request("write_midi_clip", {**fields, "plan_token": "abc"})
        self.assertTrue(apply)
        self.assertEqual(route, "/write_arrangement_clip")
        self.assertEqual(wire["creative"]["plan_token"], "abc")

    def test_bad_inputs_never_dispatch(self):
        request = Mock()
        service = AbletonMcpService(operations=McpOperations(creative_request=request))
        for tool, args in [
            ("edit_midi_notes", {"track_id": True, "clip_id": 3, "action": "shift_notes"}),
            ("edit_midi_notes", {"track_id": 1, "clip_id": 3, "action": "shift_notes", "beats": float("nan")}),
            ("manage_tracks", {"action": "delete_track", "track_id": 1, "section": "return"}),
            ("manage_tracks", {"action": "delete_track"}),
            ("manage_tracks", {"action": "delete_track", "track_id": 1, "name": "X"}),
            ("manage_tracks", {"action": "rename_track", "name": "X"}),
            ("manage_scenes", {"action": "fire"}),
            ("confirm_sample", {"track_id": 1, "device_id": 2, "target": "drum_rack_pad"}),
            ("write_midi_clip", {"track_id": 1, "scene_id": 2, "notes": [{"pitch": 60, "start_time": 15, "duration": 2}]}),
        ]:
            self.assertFalse(service.creative(tool, args)["ok"], (tool,args))
        request.assert_not_called()

    def test_track_delete_uses_existing_tool_private_route_and_guard(self):
        from ableton_bridge.mcp_creative import ManageTracks
        fields = {"action": "delete_track", "track_id": 117}
        route, wire, apply = prepare_request("manage_tracks", fields)
        self.assertEqual(route, "/track_management")
        self.assertTrue(apply)
        self.assertEqual(wire["action"], "mcp_creative_v1")
        self.assertEqual(wire["creative"]["action"], "delete_track")
        self.assertEqual(wire["creative"]["track_id"], 117)
        self.assertNotIn("track_id", wire)
        self.assertIn("delete_track", ManageTracks.model_json_schema()["properties"]["action"]["enum"])
        self.assertTrue(prepare_request("manage_tracks", {**fields, "execution": "apply"})[2])
        self.assertTrue(prepare_request("manage_tracks", {**fields, "execution": "apply", "plan_token": "abc"})[2])
        for extra in ({"section": "main"}, {"color": 0}, {"track_id": True}, {"track_index": 10}):
            with self.assertRaises(ValueError):
                prepare_request("manage_tracks", {**fields, **extra})

    def test_service_serialization_and_protocol_marker(self):
        request = Mock(return_value={"ok": True, "mcp_protocol": 1, "plan_token": "abc"})
        service = AbletonMcpService(operations=McpOperations(creative_request=request))
        result = service.creative("manage_tracks", {"action": "create_audio_track", "name": "Texture"})
        self.assertTrue(result["mcp"]["serialized"])
        self.assertTrue(request.call_args.kwargs["commit"])
        service._track_cache = {"old": True}
        result = service.creative("manage_tracks", {"action": "create_audio_track", "name": "Texture", "execution": "apply", "plan_token": "abc"})
        self.assertTrue(request.call_args.kwargs["commit"])
        self.assertIsNone(service._track_cache)
        request.return_value = {"ok": True}
        self.assertEqual(service.creative("manage_scenes", {})["error_code"], "creative_protocol_unavailable")

    def test_hub_failure_is_not_claimed_success(self):
        request = Mock(return_value={"ok": False, "mcp_protocol": 1, "error": "stale_plan"})
        result = AbletonMcpService(operations=McpOperations(creative_request=request)).creative("manage_scenes", {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "stale_plan")

    def test_arrangement_uses_existing_route_and_stable_ids(self):
        fields = dict(action="move_audio_clip", track_id=11, clip_id=41, target_start=16)
        route, wire, apply = prepare_request("edit_arrangement", fields)
        self.assertEqual(route, "/arrangement_tools")
        self.assertEqual(wire["creative"]["clip_id"], 41)
        self.assertTrue(apply)
        for extra in ({"target_start": -1}, {"clip_id": True}, {"name": "rename"}):
            with self.assertRaises(ValueError):
                prepare_request("edit_arrangement", {**fields, **extra})
        self.assertTrue(prepare_request("edit_arrangement", {**fields, "execution": "apply", "plan_token": "p"})[2])

    def test_timeout_apply_has_unknown_state_and_no_retry(self):
        from ableton_bridge.inserter import InserterTimeoutError
        request = Mock(side_effect=InserterTimeoutError("old message"))
        service = AbletonMcpService(operations=McpOperations(creative_request=request))
        result = service.creative("manage_tracks", {"action": "create_audio_track", "execution": "apply", "plan_token": "abc"})
        self.assertEqual(result["error_code"], "creative_reply_timeout")
        self.assertIsNone(result["applied"])
        self.assertTrue(result["mutation_attempted"])
        request.assert_called_once()

    def test_packet_cap_and_hub_build_inputs(self):
        with self.assertRaisesRegex(ValueError, "48000"):
            prepare_request("write_midi_clip", {"track_id": 1, "scene_id": 2,
                "notes": [{"pitch": 60, "start_time": 0, "duration": 1}] * 512})
        root = Path(__file__).resolve().parents[1]
        builder = (root / "ableton_agent/build_hub_device.py").read_text()
        self.assertIn('ROOT / "max" / "ableton_agent_creative_control.js"', builder)
        import json
        patcher = json.loads((root / "ableton_agent/max/agent_hub.maxpat.json").read_text())["patcher"]
        self.assertTrue(any(b["box"].get("text") == "loadmess maxpacketsize 32768" for b in patcher["boxes"]))
        self.assertTrue(any(l["patchline"]["source"][0] == "obj-creative-packet-size" and
                            l["patchline"]["destination"][0] == "obj-udp-send" for l in patcher["lines"]))

    def test_catalog_checks_real_paths_without_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "catalog.sqlite3"
            db.touch()
            present = root / "hit.wav"
            present.touch()
            missing = root / "missing.wav"
            with patch("ableton_bridge.sound_catalog_db.search_database", return_value=[
                {"path": str(present), "name": "Hit"}, {"path": str(missing), "name": "Missing"}]) as query:
                result = search_sounds({"role": "fx", "limit": 4}, database_path=db)
                self.assertEqual(len(result["resources"]), 1)
                self.assertEqual(result["missing_paths"], [str(missing)])
                self.assertEqual(query.call_args.kwargs["limit"], 4)
            self.assertFalse(search_sounds({}, database_path=root / "absent.sqlite3")["ok"])

    def test_all_tool_schemas_and_runtime_dispatch(self):
        from mcp import Client
        import ableton_bridge.mcp_server as module
        fake = Mock()
        fake.creative.return_value = {"ok": True}
        cases = [
            ("write_midi_clip", {"track_id": 1, "scene_id": 2, "notes": []}),
            ("edit_midi_notes", {"track_id": 1, "clip_id": 2, "action": "shift_notes"}),
            ("vary_midi_clip", {"track_id": 1, "clip_id": 2, "target_start": 32}),
            ("confirm_sample", {"track_id": 1, "device_id": 2}),
            ("insert_device", {"track_id": 1, "kind": "effect", "device": "Utility"}),
            ("eq", {}), ("manage_tracks", {"action": "create_audio_track"}), ("manage_scenes", {}),
            ("manage_tracks", {"action": "delete_track", "track_id": 117}),
            ("edit_arrangement", {"action": "copy_midi_clip", "track_id": 11, "clip_id": 41, "target_start": 16}),
        ]
        async def exercise():
            with patch.object(module, "service", fake):
                async with Client(module.mcp, raise_exceptions=True) as client:
                    for name, fields in cases:
                        result = await client.call_tool("ableton_" + name, {"request": fields})
                        self.assertFalse(result.is_error, (name,result))
                        self.assertEqual(fake.creative.call_args.args[0], name)
                    fake.scan_automation.return_value = {"ok": True, "complete": True}
                    result = await client.call_tool("ableton_scan_automation", {"request": {}})
                    self.assertFalse(result.is_error)
                    self.assertEqual(fake.scan_automation.call_args.args[0]["limit"], 4)
        asyncio.run(exercise())

    @unittest.skipUnless(shutil.which("node"), "Node required for Max mock runtime")
    def test_max_creative_runtime(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([shutil.which("node"), str(root / "tests" / "fixtures" / "creative_runtime.cjs")],
                                cwd=root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

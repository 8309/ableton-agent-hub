from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from ableton_bridge.mcp_tools import AbletonMcpService, McpOperations
from ableton_bridge.parameter_summary import (
    ParameterSummaryError, _inspection_payload, read_device_parameter_page,
)
from ableton_bridge.bounded_read import collect_pages

ROOT = Path(__file__).resolve().parents[1]


class DiscoveryTests(unittest.TestCase):
    def test_special_sections_and_children_controls(self):
        calls = []
        def devices(action, **kw):
            calls.append((action, kw))
            return {"ok": True, "tree": {"devices": [], "read": {
                "has_more": True, "next_cursor": 8, "collection_token": "d1"}}}
        service = AbletonMcpService(operations=McpOperations(device_chain=devices))
        for section in ("track", "return", "main", "master"):
            result = service.find_target(target_type="device", query="Verb", section=section,
                track_id=3, root_device_id=5, cursor=4, page_limit=4, collection_token="d1")
            self.assertEqual(calls[-1][0], "scan_children")
            self.assertEqual(calls[-1][1]["section"], section)
            self.assertEqual(result["continuation"], {"cursor": 8, "collection_token": "d1", "match_offset": 0})
            self.assertFalse(result["source_complete"])

    def test_recursive_limits_are_explicit(self):
        calls = []
        def devices(action, **kw):
            calls.append(kw)
            return {"ok": True, "tree": {"devices": []}}
        service = AbletonMcpService(operations=McpOperations(device_chain=devices))
        service.find_target(target_type="device", query="x", track_id=1,
            scan_mode="recursive", max_depth=9, max_devices=256, budget_ms=55)
        self.assertEqual(calls[0]["max_depth"], 9)
        self.assertEqual(calls[0]["max_devices"], 256)

    def test_parameter_search_continues_beyond_128_without_loss(self):
        calls = []
        def parameters(**kw):
            calls.append(kw)
            start = kw["offset"]
            def fetch(payload, timeout):
                cursor = payload["read"]["cursor"]
                end = min(cursor + payload["read"]["limit"], 150)
                return {"ok": True, "items": [{"index": i, "id": 1000+i, "name": "needle"}
                    for i in range(cursor, end)], "read": {
                    "cursor": cursor, "next_cursor": end if end < 150 else None,
                    "has_more": end < 150, "collection_token": "params", "partial": False}}
            return collect_pages(fetch, {"read": {"cursor": start, "limit": kw["limit"],
                "expected_collection_token": kw["expected_collection_token"]}}, max_pages=kw["max_pages"])
        service = AbletonMcpService(operations=McpOperations(inspect_device_parameters=parameters))
        arguments = dict(target_type="parameter", query="needle", track_id=1, device_id=2, limit=32)
        indices = []
        for _ in range(10):
            result = service.find_target(**arguments)
            self.assertTrue(result["ok"])
            indices.extend(item["index"] for item in result["matches"])
            if result["continuation"] is None:
                break
            arguments.update(result["continuation"])
        self.assertEqual(indices, list(range(150)))
        self.assertEqual(calls[0]["limit"], 4)
        self.assertEqual(calls[-1]["offset"], 128)
        self.assertEqual(calls[-1]["expected_collection_token"], "params")

    def test_track_cache_revision_expiry_refresh_error_and_write(self):
        state = {"revision": "set-a", "scans": 0, "fail": False}
        def tracks(action, **kw):
            if state["fail"]: return {"ok": False, "error": "disconnected"}
            if action == "lookup_revision": return {"ok": True, "revision": state["revision"]}
            state["scans"] += 1
            return {"ok": True, "complete": True, "items": [{"track_id": 1, "section": "track", "track_name": "Kick"}]}
        service = AbletonMcpService(operations=McpOperations(track_management=tracks,
            set_mix=lambda *a, **k: {"ok": True}))
        args = dict(target_type="track", query="Kick")
        self.assertFalse(service.find_target(**args)["cache"]["hit"])
        self.assertTrue(service.find_target(**args)["cache"]["hit"])
        self.assertEqual(state["scans"], 1)
        state["revision"] = "set-b"
        self.assertFalse(service.find_target(**args)["cache"]["hit"])
        self.assertEqual(state["scans"], 2)
        service.find_target(**args, refresh=True)
        service._track_cache["created"] -= 6
        service.find_target(**args)
        self.assertEqual(state["scans"], 4)
        service.apply_mix([{"track_id": 1, "field": "volume", "value": .5}])
        self.assertIsNone(service._track_cache)
        service.find_target(**args)
        state["fail"] = True
        self.assertFalse(service.find_target(**args)["ok"])
        self.assertIsNone(service._track_cache)

    def test_incomplete_track_result_is_not_cached(self):
        def tracks(action, **kw):
            if action == "lookup_revision": return {"ok": True, "revision": "r"}
            return {"ok": True, "complete": False, "items": []}
        service = AbletonMcpService(operations=McpOperations(track_management=tracks))
        service.find_target(target_type="track", query="x")
        self.assertIsNone(service._track_cache)

    def test_trace_levels_wire_options_and_default(self):
        for level in ("none", "page", "parameter", "field"):
            with patch("ableton_bridge.parameter_summary.request_page", return_value={"ok": True}) as request:
                read_device_parameter_page(track_id=1, device_id=2, trace_level=level)
            payload = request.call_args.args[1]
            self.assertEqual(payload["read"]["limit"], 4)
            self.assertEqual(payload["read"]["cursor"], 0)
            self.assertEqual("progress_route" in request.call_args.kwargs, level != "none")
            self.assertEqual(payload.get("trace_level", "none"), level)
        with self.assertRaises(ParameterSummaryError):
            _inspection_payload(track_id=1, trace_level="all")

    def test_journal_does_not_reuse_previous_page_checkpoint(self):
        from ableton_bridge.runtime_diagnostics import begin_request, checkpoint_request, request_journal_entry
        begin_request("page-reset-test", "/parameter_summary", {"read": {"cursor": 0}})
        checkpoint_request("page-reset-test", "page_completed", layer="hub")
        begin_request("page-reset-test", "/parameter_summary", {"read": {"cursor": 4}})
        current = request_journal_entry("page-reset-test")
        self.assertNotIn("last_hub_checkpoint", current)
        self.assertEqual(current["payload"]["read"]["cursor"], 4)


@unittest.skipUnless(shutil.which("node"), "Node required for executing Max JS mocks")
class MaxDiscoveryProgressTests(unittest.TestCase):
    def test_liveapi_mocks(self):
        result = subprocess.run(["node", str(ROOT / "tests/fixtures/mcp_discovery_progress.cjs")],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_progress_wiring_has_no_defer_and_keeps_final_outlet(self):
        patcher = json.loads((ROOT / "ableton_agent/max/agent_hub.maxpat.json").read_text())["patcher"]
        lines = [(tuple(x["patchline"]["source"]), tuple(x["patchline"]["destination"])) for x in patcher["lines"]]
        self.assertIn((("obj-summary-js", 1), ("obj-summary-progress", 0)), lines)
        self.assertIn((("obj-summary-progress", 0), ("obj-udp-send", 0)), lines)
        self.assertIn((("obj-summary-js", 0), ("obj-prepend-summary", 0)), lines)


if __name__ == "__main__":
    unittest.main()

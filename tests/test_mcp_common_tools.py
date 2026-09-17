from __future__ import annotations

from dataclasses import fields
import threading
import time
import unittest
from unittest.mock import Mock, patch

from ableton_bridge.bounded_read import BoundedReadTimeoutError
from ableton_bridge.mcp_tools import AbletonMcpService, McpOperations
from ableton_bridge.transport import transport, TransportTimeoutError


class CommonToolTests(unittest.TestCase):
    def service(self, **overrides):
        # Every unexpected operation fails locally; tests can never fall through to Live.
        operations = {field.name: Mock(side_effect=AssertionError(field.name))
                      for field in fields(McpOperations)}
        operations.update(overrides)
        return AbletonMcpService(operations=McpOperations(**operations))

    def test_transport_modes_and_action_validation(self):
        call = Mock(return_value={"ok": True, "request_id": "transport"})
        service = self.service(transport=call)
        for action, execution, commit in [("status", "auto", False),
                                           ("stop", "auto", True),
                                           ("play", "inspect", False),
                                           ("continue", "apply", True)]:
            result = service.control_transport(action=action, execution=execution)
            self.assertTrue(result["mcp"]["serialized"])
            self.assertEqual(call.call_args.kwargs["commit"], commit)
        service.control_transport(action="play", beat=128.25)
        self.assertEqual(call.call_args.kwargs["beat"], 128.25)
        for kwargs in ({"action": "delete"}, {"action": "jump"},
                       {"action": "stop", "beat": 1}, {"action": "jump", "beat": float("nan")},
                       {"action": "jump", "beat": -1}, {"execution": "unsafe"}):
            call.reset_mock()
            with self.assertRaises(ValueError):
                service.control_transport(**kwargs)
            call.assert_not_called()

    def test_tempo_read_inspect_apply_and_automation_boundary(self):
        call = Mock(return_value={"ok": True, "tempo": 132, "tempo_before": 120})
        service = self.service(tempo=call)
        for bpm, execution, commit in [(None, "inspect", False), (None, "apply", False),
                                       (132.25, "inspect", False), (132.25, "apply", True)]:
            result = service.read_or_set_tempo(bpm=bpm, execution=execution)
            self.assertEqual(call.call_args.args, (bpm,))
            self.assertEqual(call.call_args.kwargs["commit"], commit)
            self.assertFalse(result["automation_managed"])
            self.assertEqual(result["tempo_before"], 120)
        for bpm in (19, 1000, float("inf"), float("nan"), True):
            call.reset_mock()
            with self.assertRaises(ValueError):
                service.read_or_set_tempo(bpm=bpm)
            call.assert_not_called()

    def test_locators_and_meters_are_narrow_read_only(self):
        call = Mock(return_value={"ok": True, "request_id": "read-1"})
        service = self.service(locator=call, meter_monitor=call)
        service.list_locators()
        self.assertEqual(call.call_args.args, ("list",))
        self.assertFalse(call.call_args.kwargs["commit"])
        for section in ("track", "return", "main"):
            result = service.read_meters(track_id=9, section=section)
            self.assertEqual(call.call_args.args, ("read_meters",))
            self.assertEqual(call.call_args.kwargs["track_id"], 9)
            self.assertEqual(call.call_args.kwargs["section"], section)
            self.assertEqual(result["measurement_scope"], "single_instant")
        with self.assertRaises(ValueError):
            service.read_meters(track_id=0)

    def test_clip_pages_preserve_token_cursor_partial_and_content(self):
        raw = {"ok": True, "request_id": "clip-page", "items": [{"clip_id": 44}],
               "read": {"has_more": True, "partial": True, "next_cursor": 2,
                        "collection_token": "clips-1", "warnings": []}}
        call = Mock(return_value=raw)
        service = self.service(request_page=call)
        result = service.scan_clips(track_index=3)
        payload = call.call_args.args[1]
        self.assertEqual(call.call_args.args[0], "/clip_note_tools")
        self.assertEqual(payload["action"], "scan_clips_metadata")
        self.assertEqual(payload["track_index"], 3)
        self.assertEqual(payload["read"]["cursor"], 0)
        self.assertEqual(payload["read"]["limit"], 4)
        self.assertEqual(call.call_args.kwargs["mode"], "dry_run")
        self.assertEqual(result["read"], raw["read"])
        service.scan_clips(track_index=3, limit=7, **result["continuation"])
        self.assertEqual(call.call_args.args[1]["read"]["expected_collection_token"], "clips-1")
        self.assertEqual(call.call_args.args[1]["read"]["cursor"], 2)
        self.assertEqual(call.call_args.args[1]["read"]["limit"], 7)

    def test_note_windows_are_beats_not_item_limits(self):
        raw = {"ok": True, "notes": [{"pitch": 60}], "window_start": 4, "window_end": 8,
               "read": {"has_more": False, "next_cursor": 8, "collection_token": "clip-length"}}
        call = Mock(return_value=raw)
        result = self.service(request_page=call).read_clip_notes(
            clip_id=44, cursor=4, beat_window=4, collection_token="clip-length")
        payload = call.call_args.args[1]
        self.assertEqual(payload["clip_id"], 44)
        self.assertEqual(payload["read"]["projection"], ["notes"])
        self.assertEqual(payload["read"]["limit"], 4)
        self.assertEqual(result["notes"], raw["notes"])
        self.assertIsNone(result["continuation"])

    def test_errors_warnings_and_scope_cap_do_not_offer_blind_continuation(self):
        for raw in [
            {"ok": False, "error": "stale_collection", "request_id": "bad-page"},
            {"ok": True, "read": {"has_more": True, "next_cursor": 4, "warnings": ["unsupported"]}},
            {"ok": True, "total_item_count": 512, "read": {"has_more": True, "next_cursor": 4}},
        ]:
            result = self.service(request_page=Mock(return_value=raw)).scan_clips()
            self.assertIsNone(result["continuation"])
            for key in ("ok", "error", "request_id", "read"):
                if key in raw:
                    self.assertEqual(result[key], raw[key])
        error = BoundedReadTimeoutError("timeout", error_code="udp_reply_timeout",
                                        error_layer="udp_client", stage="udp_sent", request_id="notes-1")
        call = Mock(side_effect=error)
        result = self.service(request_page=call).read_clip_notes(clip_id=1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["request_id"], "notes-1")
        self.assertEqual(call.call_count, 1)

    def test_bad_page_input_never_calls_hub(self):
        call = Mock()
        service = self.service(request_page=call)
        for kwargs in ({"limit": 0}, {"limit": 65}, {"cursor": -1}, {"cursor": 513},
                       {"limit": True}, {"budget_ms": 0}, {"collection_token": ""}):
            with self.assertRaises(ValueError):
                service.scan_clips(**kwargs)
        with self.assertRaises(ValueError):
            service.read_clip_notes(clip_id=1, beat_window=0)
        call.assert_not_called()

    def test_new_tools_share_existing_serialization(self):
        state = {"active": 0, "maximum": 0}
        def operation(*args, **kwargs):
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
            time.sleep(0.01)
            state["active"] -= 1
            return {"ok": True}
        service = self.service(tempo=operation, locator=operation, ping=operation)
        threads = [threading.Thread(target=method) for method in
                   (service.read_or_set_tempo, service.list_locators, service.status)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(state["maximum"], 1)

    def test_transport_stops_on_failed_apply_and_preserves_readback_failure(self):
        with patch("ableton_bridge.transport._request_transport", return_value={"ok": False}) as call:
            transport("play", commit=True)
            self.assertEqual(call.call_count, 1)
        for failure in ({"ok": False, "error": "unavailable"}, TransportTimeoutError("no status")):
            with patch("ableton_bridge.transport.time.sleep"), patch(
                "ableton_bridge.transport._request_transport",
                side_effect=[{"ok": True, "changed": True, "request_id": "applied"}, failure],
            ):
                result = transport("play", commit=True)
            self.assertFalse(result["ok"])
            self.assertTrue(result["changed"])
            self.assertEqual(result["request_id"], "applied")
            self.assertEqual(result["error_code"], "transport_readback_failed")
            self.assertFalse(result["readback"]["ok"])


if __name__ == "__main__":
    unittest.main()

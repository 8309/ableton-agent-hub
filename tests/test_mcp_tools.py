from __future__ import annotations

import threading
import time
import unittest

from ableton_bridge.bounded_read import BoundedReadTimeoutError, BoundedReadAutoCollectError

from ableton_bridge.mcp_tools import (
    AbletonMcpService,
    McpConnectionSettings,
    McpOperations,
)


def _unused(*_args, **_kwargs):
    raise AssertionError("unexpected operation")


class McpToolsTests(unittest.TestCase):
    def service(self, **overrides):
        operations = {
            "ping": _unused,
            "initial_read": _unused,
            "track_management": _unused,
            "device_chain": _unused,
            "inspect_device_parameters": _unused,
            "set_mix": _unused,
            "set_parameters": _unused,
        }
        operations.update(overrides)
        return AbletonMcpService(
            settings=McpConnectionSettings(timeout=3.0),
            operations=McpOperations(**operations),
        )

    def test_status_reports_transport_and_serial_metadata(self) -> None:
        captured = {}

        def fake_ping(**kwargs):
            captured.update(kwargs)
            return {"request_id": "ping-1"}

        result = self.service(ping=fake_ping).status(timeout=1.25)

        self.assertTrue(result["ok"])
        self.assertEqual(result["hub"]["request_id"], "ping-1")
        self.assertEqual(captured["reply_port"], 7401)
        self.assertEqual(captured["timeout"], 1.25)
        self.assertTrue(result["mcp"]["serialized"])

    def test_all_hub_operations_are_serialized(self) -> None:
        state = {"active": 0, "maximum": 0}
        state_lock = threading.Lock()
        started = threading.Barrier(3)

        def fake_ping(**_kwargs):
            with state_lock:
                state["active"] += 1
                state["maximum"] = max(state["maximum"], state["active"])
            time.sleep(0.04)
            with state_lock:
                state["active"] -= 1
            return {"request_id": "ok"}

        service = self.service(ping=fake_ping)
        results = []

        def worker():
            started.wait()
            results.append(service.status())

        threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
        for thread in threads:
            thread.start()
        started.wait()
        for thread in threads:
            thread.join()

        self.assertEqual(state["maximum"], 1)
        self.assertEqual(
            sorted(item["mcp"]["request_sequence"] for item in results), [1, 2]
        )
        self.assertGreater(max(item["mcp"]["queue_wait_ms"] for item in results), 20)

    def test_read_set_defaults_to_compact_quick_summary(self) -> None:
        captured = {}

        def fake_initial_read(**kwargs):
            captured.update(kwargs)
            return {
                "status": "complete",
                "summary": {"tempo": 132.0},
                "tracks": [{"track_id": 1}],
            }

        result = self.service(initial_read=fake_initial_read).read_set()

        self.assertEqual(result["summary"]["tempo"], 132.0)
        self.assertNotIn("tracks", result)
        self.assertEqual(captured["depth"], "quick")
        self.assertEqual(captured["max_note_clips"], 64)

    def test_find_track_prefers_exact_match_and_returns_stable_id(self) -> None:
        def fake_tracks(*_args, **_kwargs):
            return {
                "ok": True,
                "items": [
                    {"section": "track", "track_id": 11, "track_name": "Bass Layer"},
                    {"section": "track", "track_id": 12, "track_name": "Bass"},
                ],
                "complete": True,
            }

        result = self.service(track_management=fake_tracks).find_target(
            target_type="track", query="Bass"
        )

        self.assertEqual([item["track_id"] for item in result["matches"]], [12, 11])

    def test_find_device_flattens_nested_tree(self) -> None:
        def fake_devices(*_args, **_kwargs):
            return {
                "ok": True,
                "tree": {
                    "devices": [
                        {
                            "device_id": 20,
                            "device_name": "Instrument Rack",
                            "chains": [
                                {"devices": [{"device_id": 21, "device_name": "Wavetable"}]}
                            ],
                        }
                    ]
                },
            }

        result = self.service(device_chain=fake_devices).find_target(
            target_type="device", query="wave", track_id=10
        )

        self.assertEqual(result["matches"][0]["device_id"], 21)

    def test_read_parameters_defaults_to_one_four_item_page(self) -> None:
        captured = {}

        def fake_parameters(**kwargs):
            captured.update(kwargs)
            return {"ok": True, "items": [], "read": {"has_more": True}}

        result = self.service(inspect_device_parameters=fake_parameters).read_parameters(
            track_id=10, device_id=20
        )

        self.assertTrue(result["ok"])
        self.assertEqual(captured["offset"], 0)
        self.assertEqual(captured["limit"], 4)
        self.assertFalse(captured["auto_collect"])
        self.assertEqual(
            captured["projection"], ["identity", "internal_value", "display_value"]
        )

    def test_read_parameters_forwards_cursor_token_and_explicit_limit(self) -> None:
        captured = {}

        def fake_parameters(**kwargs):
            captured.update(kwargs)
            return {"ok": True, "items": []}

        self.service(inspect_device_parameters=fake_parameters).read_parameters(
            track_id=10,
            device_id=20,
            cursor=4,
            limit=7,
            collection_token="token-1",
        )

        self.assertEqual(captured["offset"], 4)
        self.assertEqual(captured["limit"], 7)
        self.assertEqual(captured["expected_collection_token"], "token-1")

    def test_scalar_writes_require_stable_ids_and_preserve_ui_default(self) -> None:
        captured = {}

        def fake_set_mix(changes, **kwargs):
            captured["changes"] = changes
            captured.update(kwargs)
            return {"ok": True, "applied": True}

        service = self.service(set_mix=fake_set_mix)
        result = service.apply_mix(
            [{"section": "track", "track_id": 10, "field": "volume", "value": 0.5}]
        )

        self.assertTrue(result["ok"])
        self.assertEqual(captured["execution"], "auto")
        self.assertEqual(captured["value_display"], "ui")
        with self.assertRaisesRegex(ValueError, "stable track_id"):
            service.apply_mix([{"track": "Bass", "field": "volume", "value": 0.5}])

    def test_parameter_writes_require_all_stable_ids(self) -> None:
        captured = {}

        def fake_set_parameters(changes, **kwargs):
            captured["changes"] = changes
            captured.update(kwargs)
            return {"ok": True, "applied": True}

        service = self.service(set_parameters=fake_set_parameters)
        result = service.apply_parameters(
            [
                {
                    "track_id": 10,
                    "device_id": 20,
                    "parameter_id": 30,
                    "value": 0.25,
                }
            ]
        )

        self.assertTrue(result["ok"])
        self.assertEqual(captured["changes"][0]["parameter_id"], 30)
        with self.assertRaisesRegex(ValueError, "stable parameter_id"):
            service.apply_parameters([{"track_id": 10, "device_id": 20, "value": 0.25}])

    def test_operation_exception_becomes_structured_tool_result(self) -> None:
        def fake_ping(**_kwargs):
            raise TimeoutError("no reply")

        result = self.service(ping=fake_ping).status()

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_layer"], "mcp_service")
        self.assertEqual(result["error_type"], "TimeoutError")
        self.assertEqual(result["mcp"]["operation"], "ableton_status")

    def test_lookup_preserves_nested_tree_truncation_and_continuation(self) -> None:
        def scan(*args, **kwargs):
            return {"ok": True, "request_id": "tree-1", "tree": {
                "truncated": True, "truncation_reasons": ["budget_ms"],
                "selectable_child_rack_ids": [99], "devices": [],
            }}
        result = self.service(device_chain=scan).find_target(
            target_type="device", query="Reverb", track_id=1)
        self.assertTrue(result["ok"])
        self.assertFalse(result["source_complete"])
        self.assertEqual(result["truncation_reasons"], ["budget_ms"])
        self.assertEqual(result["selectable_child_rack_ids"], [99])
        self.assertEqual(result["request_id"], "tree-1")

    def test_lookup_preserves_error_and_bounded_incomplete_states(self) -> None:
        for source in [
            {"ok": False, "error": "missing target", "error_code": "target_not_found"},
            {"ok": True, "read": {"has_more": True, "next_cursor": 4}},
            {"ok": True, "complete": False, "stop_reason": "max_pages"},
            {"ok": True, "warnings": ["unsupported property"]},
            {"ok": True, "truncated": True},
        ]:
            with self.subTest(source=source):
                result = self.service(device_chain=lambda *a, **k: source).find_target(
                    target_type="device", query="Reverb", track_id=1)
                self.assertFalse(result["source_complete"])
                for key in ("error", "error_code", "read", "stop_reason", "warnings"):
                    if key in source:
                        self.assertEqual(result[key], source[key])

    def test_structured_timeout_and_auto_collector_cause_survive_mcp(self) -> None:
        timeout = BoundedReadTimeoutError(
            "no final reply", error_code="udp_reply_timeout", error_layer="udp_client",
            stage="udp_sent", request_id="page-2", details={"cursor": 4})
        for error in [timeout, BoundedReadAutoCollectError(
                "collector failed", page=2, cursor=4, cause=timeout)]:
            def fail(**kwargs):
                raise error
            result = self.service(inspect_device_parameters=fail).read_parameters(
                track_id=1, device_id=2)
            for key, value in error.to_dict().items():
                self.assertEqual(result[key], value)
            self.assertEqual(result["mcp"]["operation"], "ableton_read_parameters")


if __name__ == "__main__":
    unittest.main()

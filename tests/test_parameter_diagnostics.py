import unittest
from unittest.mock import Mock, patch

from ableton_bridge.parameter_diagnostics import diagnose_parameters
from ableton_bridge.bounded_read import BoundedReadTimeoutError
from ableton_bridge.mcp_tools import AbletonMcpService, McpOperations


class ParameterDiagnosticsTests(unittest.TestCase):
    def run_probe(self, read, ping=None, **kwargs):
        return diagnose_parameters(read=read, ping=ping or Mock(return_value={"ok": True}),
            target={"track_id": 1, "device_id": 2}, connection={"timeout": 1.0}, **kwargs)

    def test_fields_and_continuation(self):
        reader = Mock(return_value={"ok": True, "read": {
            "collection_token": "a", "has_more": True, "next_cursor": 4}})
        result = self.run_probe(reader)
        self.assertTrue(result["ok"])
        self.assertEqual(reader.call_count, 6)
        self.assertEqual(reader.call_args_list[0].kwargs["projection"], ["identity"])
        self.assertEqual(reader.call_args.kwargs["offset"], 4)
        self.assertEqual(reader.call_args.kwargs["expected_collection_token"], "a")
        self.assertTrue(all(call.kwargs["auto_collect"] is False for call in reader.call_args_list))

    def test_timeout_health_failure_stops_reads(self):
        reader = Mock(side_effect=BoundedReadTimeoutError("timeout", details={"last_checkpoint": "metadata"}))
        pinger = Mock(side_effect=[{"ok": True}, {"ok": False}, {"ok": False}])
        result = self.run_probe(reader, pinger)
        self.assertFalse(result["ok"])
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(result["steps"][1]["result"]["details"]["last_checkpoint"], "metadata")

    def test_timeout_healthy_narrows(self):
        reader = Mock(side_effect=[BoundedReadTimeoutError("timeout"), {"ok": False, "error_code": "lom_property_read_failed"}])
        result = self.run_probe(reader)
        self.assertFalse(result["ok"])
        self.assertEqual(reader.call_args.kwargs["limit"], 1)

    def test_stale_stops_without_isolation(self):
        reader = Mock(side_effect=[{"ok": True, "read": {"collection_token": "a"}},
                                  {"ok": True, "read": {"collection_token": "b"}}])
        result = self.run_probe(reader)
        self.assertFalse(result["ok"])
        self.assertEqual(reader.call_count, 2)

    def test_partial_not_timeout(self):
        reader = Mock(return_value={"ok": True, "read": {"partial": True}})
        result = self.run_probe(reader)
        self.assertEqual(result["failure_probe"], "page_partial")
        self.assertEqual(reader.call_count, 1)

    def test_validation_before_network(self):
        reader, pinger = Mock(), Mock()
        with self.assertRaises(ValueError):
            self.run_probe(reader, pinger, limit=0)
        pinger.assert_not_called()

    def test_unhealthy_initial_ping_sends_no_reads(self):
        reader = Mock()
        result = self.run_probe(reader, Mock(return_value={"ok": False}))
        self.assertEqual(result["failure_probe"], "initial_ping_failed")
        reader.assert_not_called()

    def test_warning_stops_without_isolation(self):
        reader = Mock(return_value={"ok": True, "read": {"warnings": ["unsupported"]}})
        self.assertFalse(self.run_probe(reader)["ok"])
        self.assertEqual(reader.call_count, 1)

    def test_exhausted_deadline_sends_nothing(self):
        reader, pinger = Mock(), Mock()
        with patch("ableton_bridge.parameter_diagnostics.time.monotonic", side_effect=[0, 31, 32]):
            result = self.run_probe(reader, pinger)
        self.assertEqual(result["stop_reason"], "diagnostic_budget_exceeded")
        pinger.assert_not_called()
        reader.assert_not_called()


class BatchTests(unittest.TestCase):
    mix = [{"track_id": 1, "field": "volume", "value": 0.5}]
    parameters = [{"track_id": 1, "device_id": 2, "parameter_id": 3, "value": 0.5}]

    def test_one_native_request_per_group(self):
        mixer = Mock(return_value={"ok": True, "undo_receipt": {"before": 0.6}})
        parameters = Mock(return_value={"ok": True})
        service = AbletonMcpService(operations=McpOperations(set_mix=mixer, set_parameters=parameters))
        result = service.apply_batch(mix_changes=self.mix, parameter_changes=self.parameters)
        self.assertTrue(result["ok"])
        self.assertEqual(mixer.call_count, 1)
        self.assertEqual(parameters.call_count, 1)
        self.assertEqual(result["steps"][0]["result"]["undo_receipt"]["before"], 0.6)

    def test_unknown_write_never_retried(self):
        mixer, parameters = Mock(side_effect=TimeoutError("lost")), Mock()
        service = AbletonMcpService(operations=McpOperations(set_mix=mixer, set_parameters=parameters))
        result = service.apply_batch(mix_changes=self.mix, parameter_changes=self.parameters)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["steps"][0]["result"]["applied"])
        self.assertEqual(result["remaining_not_sent"], ["parameters"])
        parameters.assert_not_called()

    def test_second_group_failure_retains_first_receipt(self):
        first = {"ok": True, "applied": True, "undo_receipt": {"restore_changes": self.mix}}
        mixer = Mock(return_value=first)
        parameters = Mock(side_effect=TimeoutError("reply lost"))
        service = AbletonMcpService(operations=McpOperations(set_mix=mixer, set_parameters=parameters))
        result = service.apply_batch(mix_changes=self.mix, parameter_changes=self.parameters)
        self.assertFalse(result["ok"])
        self.assertFalse(result["atomic"])
        self.assertEqual(result["stopped_at"], "parameters")
        self.assertEqual(result["steps"][0]["result"], first)
        self.assertIsNone(result["steps"][1]["result"]["applied"])
        self.assertEqual(result["remaining_not_sent"], [])
        self.assertEqual(mixer.call_count, 1)
        self.assertEqual(parameters.call_count, 1)

    def test_batch_limits_reject_before_sending(self):
        mixer, parameters = Mock(), Mock()
        service = AbletonMcpService(operations=McpOperations(set_mix=mixer, set_parameters=parameters))
        for mix, params in ((self.mix * 33, self.parameters), (self.mix, self.parameters * 17)):
            with self.assertRaises(ValueError):
                service.apply_batch(mix_changes=mix, parameter_changes=params)
        mixer.assert_not_called()
        parameters.assert_not_called()

    def test_validate_both_groups_before_any_write(self):
        mixer = Mock()
        service = AbletonMcpService(operations=McpOperations(set_mix=mixer))
        with self.assertRaises(ValueError):
            service.apply_batch(mix_changes=self.mix, parameter_changes=[{"track_id": 1}])
        mixer.assert_not_called()

    def test_inspect_and_business_failure(self):
        mixer = Mock(return_value={"ok": False, "error_code": "target_not_found"})
        parameters = Mock()
        service = AbletonMcpService(operations=McpOperations(set_mix=mixer, set_parameters=parameters))
        result = service.apply_batch(mix_changes=self.mix, parameter_changes=self.parameters, execution="inspect")
        self.assertFalse(result["ok"])
        self.assertEqual(mixer.call_args.kwargs["execution"], "inspect")
        parameters.assert_not_called()

    def test_recent_operation_ring_is_bounded(self):
        service = AbletonMcpService(operations=McpOperations(ping=Mock(return_value={"request_id": "p"})))
        for _ in range(35):
            result = service.status()
        self.assertEqual(len(result["recent_operations"]), 32)
        self.assertNotIn("recent_operations", result["recent_operations"][0])

    def test_invalid_second_group_value_sends_nothing(self):
        mixer = Mock()
        service = AbletonMcpService(operations=McpOperations(set_mix=mixer))
        bad = [{**self.parameters[0], "value": float("nan")}]
        with self.assertRaises(ValueError):
            service.apply_batch(mix_changes=self.mix, parameter_changes=bad)
        mixer.assert_not_called()

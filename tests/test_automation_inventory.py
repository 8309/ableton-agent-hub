from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ableton_bridge.automation_inventory import AutomationInventory, AutomationScan
from ableton_bridge.mcp_tools import AbletonMcpService, McpOperations


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.tracks = [dict(track_id=1, section="track", track_name="Lead"),
                       dict(track_id=2, section="return", track_name="Reverb"),
                       dict(track_id=3, section="main", track_name="Main")]
        self.devices = {(1, None): [dict(device_id=11, name="Rack", can_have_chains=True)],
                        (1, 11): [dict(device_id=12, name="Synth", can_have_chains=False)],
                        (2, None): [dict(device_id=21, name="FX", can_have_chains=False)],
                        (3, None): []}
        self.parameters = {11: self.params(5), 12: self.params(3), 21: self.params(1)}
        self.ops = SimpleNamespace(track_management=self.track, device_chain=self.device,
                                   inspect_device_parameters=self.parameter)
        self.reader = AutomationInventory(self.ops, lambda timeout: dict(timeout=timeout))

    def params(self, count):
        return [dict(id=100+i, index=i, name=f"P{i}", automation_state=i % 3, is_enabled=True)
                for i in range(count)]

    def page(self, rows, key, kwargs):
        cursor = kwargs.get("cursor", kwargs.get("offset", 0))
        limit = kwargs["limit"]
        token = "collection:" + str(len(rows))
        if kwargs.get("expected_collection_token") not in (None, token):
            return dict(ok=False, error="stale_collection")
        items = rows[cursor:cursor+limit]
        end = cursor+len(items)
        return dict(ok=True, request_id=f"r{len(self.calls)}", **{key: items},
                    read=dict(cursor=cursor, next_cursor=end, has_more=end < len(rows),
                              complete=end == len(rows), collection_token=token, warnings=[], elapsed_ms=1))

    def track(self, action, **kwargs):
        self.calls.append((action, kwargs))
        self.assertFalse(kwargs["commit"])
        if action == "lookup_revision":
            return dict(ok=True, revision="set-1")
        return self.page(self.tracks, "items", kwargs)

    def device(self, action, **kwargs):
        self.calls.append((action, kwargs))
        self.assertFalse(kwargs["commit"])
        page = self.page(self.devices[(kwargs["track_id"], kwargs.get("root_device_id"))], "devices", kwargs)
        return dict(ok=page.pop("ok"), request_id=page.pop("request_id", None), tree=page)

    def parameter(self, **kwargs):
        self.calls.append(("parameters", kwargs))
        self.assertEqual(kwargs["projection"], ["identity", "automation_state"])
        self.assertEqual(kwargs["action"], "list_parameters")
        self.assertFalse(kwargs["auto_collect"])
        return self.page(self.parameters[kwargs["device_id"]], "items", kwargs)

    def test_full_inventory_nested_special_tracks_and_default_small_pages(self):
        result = self.reader.scan({})
        self.assertTrue(result["complete"], result)
        self.assertEqual(result["parameters_scanned"], 9)
        self.assertEqual(result["state_counts"], {"none": 4, "active": 3, "overridden": 2})
        self.assertEqual(len(result["items"]), 5)
        self.assertEqual(result["devices_completed"], 3)
        self.assertEqual(result["tracks_scanned"], 3)
        for action, fields in self.calls:
            if action != "lookup_revision":
                self.assertEqual(fields["limit"], 4)
        reads = [k for a, k in self.calls if a == "parameters" and k["device_id"] == 11]
        self.assertEqual([r["offset"] for r in reads], [0, 4])
        self.assertEqual(reads[1]["expected_collection_token"], "collection:5")

    def test_resume_is_delta_with_cumulative_counts_no_duplicates(self):
        fields = dict(max_pages=2, limit=1, states=["none", "active", "overridden"])
        rows, scan_id = [], None
        for _ in range(40):
            result = self.reader.scan(fields)
            self.assertTrue(result["ok"], result)
            scan_id = scan_id or result["scan_id"]
            self.assertEqual(scan_id, result["scan_id"])
            rows.extend(result["items"])
            if result["complete"]:
                break
            self.assertEqual(result["stop_reason"], "max_pages")
            fields["continuation"] = result["continuation"]
        self.assertTrue(result["complete"])
        self.assertEqual(len(rows), 9)
        self.assertEqual(len({(r["device_id"], r["parameter_id"]) for r in rows}), 9)
        self.assertEqual(result["parameters_scanned"], 9)

    def test_selected_track_no_nested(self):
        result = self.reader.scan(dict(track_ids=[1], include_nested=False))
        self.assertTrue(result["complete"], result)
        self.assertEqual(result["parameters_scanned"], 5)
        self.assertEqual(result["devices_completed"], 1)

    def test_missing_track_is_not_empty_success(self):
        result = self.reader.scan(dict(track_ids=[99]))
        self.assertFalse(result["ok"])
        self.assertIn("absent", result["failure"]["error"])

    def test_warning_missing_field_and_malformed_page_stop(self):
        original = self.ops.inspect_device_parameters
        for change in (lambda r: r["read"].update(warnings=["LOM failed"]),
                       lambda r: r.pop("items"),
                       lambda r: r["read"].update(has_more=True, next_cursor=0),
                       lambda r: r["items"][0].pop("automation_state")):
            with self.subTest(change=change):
                def changed(**kw):
                    import copy
                    response = copy.deepcopy(original(**kw))
                    change(response)
                    return response
                self.ops.inspect_device_parameters = changed
                result = self.reader.scan({})
                self.assertFalse(result["ok"])
                self.assertFalse(result["complete"])
                self.assertIsNone(result["continuation"])
                self.assertEqual(result["failed_target"]["kind"], "parameters")

    def test_token_change_stops_before_mixing_page(self):
        def changed(**kw):
            response = self.parameter(**kw)
            if kw["offset"]:
                response["read"]["collection_token"] = "changed"
            return response
        self.ops.inspect_device_parameters = changed
        result = self.reader.scan({})
        self.assertFalse(result["ok"])
        self.assertEqual(result["parameters_scanned"], 4)
        self.assertIn("stale_collection", result["failure"]["error"])

    def test_timeout_no_retry_and_resume_revision_guard(self):
        self.ops.inspect_device_parameters = Mock(side_effect=TimeoutError("udp_sent; no final"))
        result = self.reader.scan({})
        self.ops.inspect_device_parameters.assert_called_once()
        self.assertFalse(result["ok"])
        self.assertIn("udp_sent", result["failure"]["error"])
        first = self.reader.scan(dict(max_pages=1))
        self.ops.track_management = Mock(return_value=dict(ok=True, revision="another-set"))
        result = self.reader.scan(dict(max_pages=1, continuation=first["continuation"]))
        self.assertFalse(result["ok"])
        self.assertIn("stale_scan", result["failure"]["error"])

    def test_continuation_one_use_scope_and_ttl(self):
        for change in ({"limit": 8}, {}):
            first = self.reader.scan(dict(max_pages=1))
            token = first["continuation"]
            if not change:
                self.reader.sessions[token]["started"] -= 301
            with self.assertRaisesRegex(ValueError, "stale_scan"):
                self.reader.scan(dict(continuation=token, **change))
            with self.assertRaises(ValueError):
                self.reader.scan(dict(continuation=token))

    def test_validation_before_io_and_service_serializes(self):
        for fields in ({"limit": 0}, {"limit": 33}, {"limit": True}, {"track_ids": []}, {"max_pages": 65}):
            with self.assertRaises(ValueError):
                self.reader.scan(fields)
        self.assertEqual(self.calls, [])
        svc = AbletonMcpService(operations=McpOperations())
        with patch.object(svc._automation_inventory, "scan", return_value=dict(ok=True)) as scan:
            result = svc.scan_automation({})
            scan.assert_called_once_with({})
            self.assertTrue(result["mcp"]["serialized"])

    def test_real_client_builders_dispatch_only_bounded_reads(self):
        from ableton_bridge import track_management, device_chain, parameter_summary
        def transport(route, payload, **kwargs):
            self.assertFalse(kwargs.get("commit", False))
            if payload["action"] == "lookup_revision":
                return dict(ok=True, revision="set-1")
            if route == "/track_management":
                return self.track(payload["action"], commit=False, **payload["read"])
            if route == "/device_chain":
                return self.device(payload["action"], commit=False, **{k:v for k,v in payload.items() if k != "action"})
            self.assertEqual(route, "/parameter_summary")
            self.assertEqual(payload["read"]["projection"], ["identity", "automation_state"])
            return self.page(self.parameters[payload["device_id"]], "items", payload["read"])
        ops = SimpleNamespace(track_management=track_management.track_management,
                              device_chain=device_chain.device_chain,
                              inspect_device_parameters=parameter_summary.inspect_device_parameters)
        with patch.object(track_management, "request_page", side_effect=transport), \
             patch.object(track_management, "_request_track_management", side_effect=lambda p, **k: transport("/track_management", p, **k)), \
             patch.object(device_chain, "_request", side_effect=lambda p, **k: transport("/device_chain", p, **k)), \
             patch.object(parameter_summary, "request_page", side_effect=transport):
            result = AutomationInventory(ops, lambda timeout: dict(timeout=timeout)).scan({})
        self.assertTrue(result["complete"], result)
        self.assertEqual(result["parameters_scanned"], 9)

    def test_clean_budget_partial_continues(self):
        original = self.ops.inspect_device_parameters
        def short(**kwargs):
            return original(**{**kwargs, "limit": 1})
        self.ops.inspect_device_parameters = short
        result = self.reader.scan({})
        self.assertTrue(result["complete"], result)
        self.assertEqual(result["parameters_scanned"], 9)

    def test_time_budget_pauses_and_memory_is_bounded(self):
        now = [0.0]
        self.reader.clock = lambda: now[0]
        original = self.ops.device_chain
        def slow(*args, **kwargs):
            page = original(*args, **kwargs)
            now[0] += 0.95
            return page
        self.ops.device_chain = slow
        result = self.reader.scan(dict(total_timeout=1))
        self.assertTrue(result["partial"], result)
        self.assertEqual(result["stop_reason"], "time_budget")
        self.assertIsNotNone(result["continuation"])
        for _ in range(10):
            self.reader.scan(dict(max_pages=1))
        self.assertEqual(len(self.reader.sessions), 8)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest


class AlsSnapshotValidationTest(unittest.TestCase):
    def _als_snapshot(self):
        return {
            "tracks": [
                {
                    "type": "GroupTrack",
                    "name": "DRUMS",
                    "is_return": False,
                    "group_path": [],
                },
                {
                    "type": "MidiTrack",
                    "name": "Kick",
                    "is_return": False,
                    "group_path": ["DRUMS"],
                },
                {
                    "type": "ReturnTrack",
                    "name": "A-Room",
                    "is_return": True,
                    "group_path": [],
                },
            ],
            "main_track": {
                "present": True,
                "name": "Main",
                "tempo": {"manual_bpm": 132.0},
            },
            "locators": [{"name": "Drop", "beat": 16.0}],
        }

    def _hub_snapshot(self):
        return {
            "tempo": 132.0,
            "locators": [{"name": "Drop", "beat": 16.0}],
            "tracks": [
                {
                    "section": "track",
                    "track_index": 0,
                    "track_id": 100,
                    "track_name": "DRUMS",
                    "track_type": "group",
                    "parent_group_id": 0,
                },
                {
                    "section": "track",
                    "track_index": 1,
                    "track_id": 101,
                    "track_name": "Kick",
                    "track_type": "midi",
                    "parent_group_id": 100,
                },
                {
                    "section": "return",
                    "track_index": 0,
                    "track_id": 200,
                    "track_name": "A-Room",
                    "track_type": "return",
                    "parent_group_id": 0,
                },
                {
                    "section": "main",
                    "track_index": 0,
                    "track_id": 300,
                    "track_name": "Main",
                    "track_type": "main",
                    "parent_group_id": 0,
                },
            ],
            "errors": {},
        }

    def test_exact_supported_fields_are_verified(self):
        from ableton_bridge.als_verify import compare_als_snapshot_to_hub

        result = compare_als_snapshot_to_hub(self._als_snapshot(), self._hub_snapshot())

        self.assertTrue(result["ok"])
        self.assertEqual(result["overall_status"], "verified")
        self.assertEqual(result["verified_scope"], ["tempo", "locators", "tracks"])
        self.assertEqual(result["freshness"]["status"], "unknown")

    def test_mismatch_reports_field_and_first_difference(self):
        from ableton_bridge.als_verify import compare_als_snapshot_to_hub

        hub = self._hub_snapshot()
        hub["tempo"] = 120.0
        hub["tracks"][1]["track_name"] = "Wrong Kick"
        result = compare_als_snapshot_to_hub(self._als_snapshot(), hub)

        self.assertFalse(result["ok"])
        self.assertEqual(result["overall_status"], "mismatch")
        self.assertEqual(result["comparisons"]["tempo"]["status"], "mismatch")
        self.assertEqual(result["comparisons"]["tracks"]["differences"][0]["index"], 1)

    def test_route_error_is_partial_not_a_false_mismatch(self):
        from ableton_bridge.als_verify import compare_als_snapshot_to_hub

        hub = self._hub_snapshot()
        del hub["tracks"]
        hub["errors"]["tracks"] = "timeout"
        result = compare_als_snapshot_to_hub(self._als_snapshot(), hub)

        self.assertFalse(result["ok"])
        self.assertEqual(result["overall_status"], "partial")
        self.assertEqual(result["comparisons"]["tracks"]["status"], "inconclusive")

    def test_bounded_track_pages_require_a_stable_token(self):
        from ableton_bridge.als_verify import collect_hub_track_pages

        requests = []

        def page_reader(cursor, limit, expected_token, timeout):
            requests.append((cursor, limit, expected_token, timeout))
            end = min(cursor + 2, 3)
            return {
                "ok": True,
                "read": {
                    "cursor": cursor,
                    "next_cursor": end,
                    "has_more": end < 3,
                    "collection_token": "stable-token",
                    "warnings": [],
                    "elapsed_ms": 1,
                },
                "items": [{"track_index": index} for index in range(cursor, end)],
            }

        result = collect_hub_track_pages(page_reader=page_reader, page_size=2)

        self.assertEqual(result["item_count"], 3)
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(requests[0][2], None)
        self.assertEqual(requests[1][2], "stable-token")

    def test_changed_collection_token_is_rejected(self):
        from ableton_bridge.als_verify import AlsHubVerificationError, collect_hub_track_pages

        def page_reader(cursor, limit, expected_token, timeout):
            return {
                "ok": True,
                "read": {
                    "cursor": cursor,
                    "next_cursor": cursor + 1,
                    "has_more": cursor == 0,
                    "collection_token": "first" if cursor == 0 else "second",
                    "warnings": [],
                },
                "items": [{"track_index": cursor}],
            }

        with self.assertRaisesRegex(AlsHubVerificationError, "collection changed"):
            collect_hub_track_pages(page_reader=page_reader, page_size=1)


if __name__ == "__main__":
    unittest.main()

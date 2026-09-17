from __future__ import annotations

import unittest


class AlsMidiVerificationTest(unittest.TestCase):
    def _als_clip(self):
        return {
            "stored_note_count": 2,
            "returned_note_count": 2,
            "notes_has_more": False,
            "notes": [
                {"pitch": 60, "start_time": 0.0, "duration": 0.5, "velocity": 100.0, "mute": 0},
                {"pitch": 64, "start_time": 1.0, "duration": 0.25, "velocity": 90.0, "mute": 1},
            ],
        }

    def _hub_reply(self):
        return {
            "ok": True,
            "note_count": 2,
            "selected_count": 2,
            "notes": [
                {"pitch": 60, "start_time": 0.0, "duration": 0.5, "velocity": 100, "mute": 0},
                {"pitch": 64, "start_time": 1.0, "duration": 0.25, "velocity": 90, "mute": 1},
            ],
        }

    def test_exact_note_fields_are_verified(self):
        from ableton_bridge.als_midi_verify import compare_als_clip_to_hub

        result = compare_als_clip_to_hub(self._als_clip(), self._hub_reply())

        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["difference_count"], 0)

    def test_note_difference_is_reported(self):
        from ableton_bridge.als_midi_verify import compare_als_clip_to_hub

        hub = self._hub_reply()
        hub["notes"][1]["velocity"] = 80
        result = compare_als_clip_to_hub(self._als_clip(), hub)

        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["differences"][0]["fields"], ["velocity"])

    def test_truncated_matching_notes_are_partial(self):
        from ableton_bridge.als_midi_verify import compare_als_clip_to_hub

        als = self._als_clip()
        als["stored_note_count"] = 3
        als["notes_has_more"] = True
        hub = self._hub_reply()
        hub["note_count"] = 3
        result = compare_als_clip_to_hub(als, hub)

        self.assertEqual(result["status"], "partial")


if __name__ == "__main__":
    unittest.main()

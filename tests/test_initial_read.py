from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BRIDGE_ROOT = ROOT / "ableton_agent" / "python"
if str(BRIDGE_ROOT) not in sys.path:
    sys.path.insert(0, str(BRIDGE_ROOT))

initial_read_module = importlib.import_module("ableton_bridge.initial_read")
BoundedReadTimeoutError = importlib.import_module("ableton_bridge.bounded_read").BoundedReadTimeoutError
PingTimeoutError = importlib.import_module("ableton_bridge.ping").PingTimeoutError


def hierarchy_result() -> dict:
    ordinary = [
        {
            "section": "track",
            "track_id": 2,
            "track_index": 0,
            "track_name": "Keys",
            "track_type": "midi",
        }
    ]
    returns = [
        {
            "section": "return",
            "track_id": 3,
            "track_index": 0,
            "track_name": "A-Reverb",
            "track_type": "return",
        }
    ]
    return {
        "tracks": ordinary + returns,
        "return_tracks": returns,
        "main_track": {
            "section": "main",
            "track_id": 4,
            "track_index": 0,
            "track_name": "Main",
            "track_type": "main",
        },
        "hierarchy": [{"track_id": 2, "track_name": "Keys", "children": []}],
        "warnings": [],
    }


def clip_metadata_result() -> dict:
    return {
        "items": [
            {
                "clip_id": 10,
                "track_id": 2,
                "track_index": 0,
                "track_name": "Keys",
                "clip_name": "Verse",
                "clip_type": "midi",
                "is_midi_clip": True,
                "is_audio_clip": False,
                "start_time": 0.0,
                "end_time": 16.0,
                "length": 16.0,
            },
            {
                "clip_id": 11,
                "track_id": 5,
                "track_index": 1,
                "track_name": "Texture",
                "clip_name": "Noise",
                "clip_type": "audio",
                "is_midi_clip": False,
                "is_audio_clip": True,
                "start_time": 8.0,
                "end_time": 20.0,
                "length": 12.0,
            },
        ],
        "warnings": [],
    }


class InitialReadTest(unittest.TestCase):
    def common_patches(self):
        return (
            patch.object(initial_read_module, "ping", return_value={"ok": True}),
            patch.object(initial_read_module, "tempo", return_value={"tempo": 120.0}),
            patch.object(
                initial_read_module,
                "transport",
                return_value={"before": {"current_song_time": 4.0, "is_playing": False}},
            ),
            patch.object(initial_read_module, "locator", return_value={"before": []}),
            patch.object(initial_read_module, "track_management", return_value=hierarchy_result()),
        )

    def test_quick_reads_map_once_and_skips_notes_and_mixer(self) -> None:
        patches = self.common_patches()
        with patches[0] as ping_mock, patches[1], patches[2], patches[3], patches[4] as tracks_mock, patch.object(
            initial_read_module, "clip_note_tools_bounded", return_value=clip_metadata_result()
        ) as clips_mock, patch.object(initial_read_module, "set_mix") as mixer_mock:
            result = initial_read_module.initial_read(depth="quick")

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["summary"]["arrangement_clip_count"], 2)
        self.assertEqual(result["summary"]["midi_note_count"], 0)
        self.assertEqual(tracks_mock.call_count, 1)
        self.assertEqual(clips_mock.call_count, 1)
        self.assertEqual(ping_mock.call_count, 2)
        mixer_mock.assert_not_called()

    def test_preflight_ping_failure_stops_before_scanning(self) -> None:
        with patch.object(initial_read_module, "ping", side_effect=PingTimeoutError("Hub missing")) as ping_mock, patch.object(
            initial_read_module, "track_management"
        ) as tracks_mock, patch.object(initial_read_module, "clip_note_tools_bounded") as clips_mock:
            with self.assertRaisesRegex(initial_read_module.InitialReadError, "PingTimeoutError"):
                initial_read_module.initial_read(depth="quick", ping_timeout=0.25)

        self.assertEqual(ping_mock.call_args.kwargs["timeout"], 0.25)
        tracks_mock.assert_not_called()
        clips_mock.assert_not_called()

    def test_full_reuses_metadata_and_reads_only_midi_notes(self) -> None:
        patches = self.common_patches()
        quick_snapshots = []

        def clip_read(action: str, **_kwargs):
            if action == "scan_clips_metadata":
                return clip_metadata_result()
            self.assertEqual(action, "read_notes_by_clip_id")
            return {
                "notes": [
                    {"pitch": 60, "start_time": 0.0, "duration": 1.0},
                    {"pitch": 67, "start_time": 2.0, "duration": 0.5},
                ],
                "complete": True,
                "warnings": [],
            }

        mixer_reply = {
            "results": [
                {
                    "section": "track",
                    "track_id": 2,
                    "track_name": "Keys",
                    "field": "volume",
                    "before": {"value": 0.85, "display_value": "0.0 dB"},
                },
                {
                    "section": "track",
                    "track_id": 2,
                    "track_name": "Keys",
                    "field": "mute",
                    "before": False,
                },
            ]
        }
        with patches[0], patches[1], patches[2], patches[3], patches[4] as tracks_mock, patch.object(
            initial_read_module, "clip_note_tools_bounded", side_effect=clip_read
        ) as clips_mock, patch.object(initial_read_module, "set_mix", return_value=mixer_reply) as mixer_mock:
            result = initial_read_module.initial_read(depth="full", on_quick_ready=quick_snapshots.append)

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["summary"]["midi_note_clip_count"], 1)
        self.assertEqual(result["summary"]["midi_note_count"], 2)
        self.assertNotIn("notes", result["midi_notes"]["10"])
        self.assertEqual(tracks_mock.call_count, 1)
        self.assertEqual(clips_mock.call_count, 2)
        self.assertGreaterEqual(mixer_mock.call_count, 1)
        self.assertEqual(len(quick_snapshots), 1)
        self.assertEqual(quick_snapshots[0]["depth"], "quick")
        self.assertEqual(quick_snapshots[0]["summary"]["midi_note_count"], 0)

    def test_full_can_filter_note_tracks_and_keep_raw_notes(self) -> None:
        patches = self.common_patches()

        def clip_read(action: str, **kwargs):
            if action == "scan_clips_metadata":
                return clip_metadata_result()
            self.assertEqual(kwargs["clip_id"], 10)
            return {
                "notes": [{"pitch": 64, "start_time": 0.0, "duration": 1.0}],
                "complete": True,
                "warnings": [],
            }

        with patches[0], patches[1], patches[2], patches[3], patches[4], patch.object(
            initial_read_module, "clip_note_tools_bounded", side_effect=clip_read
        ), patch.object(initial_read_module, "set_mix", return_value={"results": []}):
            result = initial_read_module.initial_read(
                depth="full",
                note_tracks=["Keys"],
                include_raw_notes=True,
            )

        self.assertEqual(result["midi_notes"]["10"]["notes"][0]["pitch"], 64)

    def test_full_retries_dense_clip_with_smaller_note_window(self) -> None:
        patches = self.common_patches()
        attempted_limits = []
        metadata = clip_metadata_result()
        second_midi_clip = dict(metadata["items"][0])
        second_midi_clip.update({"clip_id": 12, "clip_name": "Chorus", "start_time": 16.0, "end_time": 32.0})
        metadata["items"].append(second_midi_clip)

        def clip_read(action: str, **kwargs):
            if action == "scan_clips_metadata":
                return metadata
            attempted_limits.append(kwargs["limit"])
            if kwargs["limit"] == 16:
                raise BoundedReadTimeoutError("dense page timed out")
            return {
                "notes": [{"pitch": 60, "start_time": 0.0, "duration": 0.25}],
                "complete": True,
                "warnings": [],
            }

        with patches[0], patches[1], patches[2], patches[3], patches[4], patch.object(
            initial_read_module, "clip_note_tools_bounded", side_effect=clip_read
        ), patch.object(initial_read_module, "set_mix", return_value={"results": []}):
            result = initial_read_module.initial_read(depth="full")

        self.assertEqual(result["status"], "complete")
        self.assertEqual(attempted_limits, [16, 4, 4])
        self.assertEqual(result["midi_notes"]["10"]["window_beats"], 4)
        self.assertEqual(result["midi_notes"]["10"]["window_source"], "adaptive_retry")
        self.assertEqual(result["midi_notes"]["12"]["window_source"], "inherited_track_fallback")
        self.assertEqual(result["warnings"][0]["type"], "adaptive_note_window")
        self.assertEqual(len(result["warnings"]), 1)


if __name__ == "__main__":
    unittest.main()

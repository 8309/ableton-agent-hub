from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "ableton_agent" / "python"
sys.path.insert(0, str(PYTHON_ROOT))


class OscCodecTest(unittest.TestCase):
    def test_round_trips_supported_message_types(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message

        packet = encode_message("/agent", ["request-1", "set_tempo", '{"tempo":128}', 1, 0.5])

        self.assertEqual(
            decode_message(packet),
            ("/agent", ["request-1", "set_tempo", '{"tempo":128}', 1, 0.5]),
        )


class BridgeClientTest(unittest.TestCase):
    def test_correlates_request_and_reply(self) -> None:
        from ableton_bridge.client import AbletonBridgeClient
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/agent" or args[1] != "ping" or json.loads(args[2]) != {}:
                    raise AssertionError((path, args))
                FakeSocket.reply = encode_message(
                    "/ableton/reply",
                    [args[0], 1, json.dumps({"ready": True})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        client = AbletonBridgeClient(timeout=1.0)
        with patch("ableton_bridge.client.socket.socket", side_effect=lambda *_args: FakeSocket()):
            self.assertEqual(client.request("ping"), {"ready": True})

    def test_times_out_when_device_is_not_loaded(self) -> None:
        from ableton_bridge.client import AbletonBridgeClient, BridgeTimeoutError

        class TimeoutSocket:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, *_args):
                return None

            def recvfrom(self, _size):
                raise socket.timeout()

        client = AbletonBridgeClient(timeout=0.001)
        with patch("ableton_bridge.client.socket.socket", side_effect=lambda *_args: TimeoutSocket()):
            with self.assertRaises(BridgeTimeoutError):
                client.request("ping")


class PingClientTest(unittest.TestCase):
    def test_ping_correlates_pong_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.ping import ping

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/ping" or len(args) != 1:
                    raise AssertionError((path, args))
                FakeSocket.reply = encode_message("/pong", [args[0]])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.ping.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = ping(timeout=1.0)

        self.assertEqual(result["from"], "127.0.0.1")
        self.assertEqual(result["port"], 7400)


class NotesClientTest(unittest.TestCase):
    def test_send_note_correlates_note_ack(self) -> None:
        from ableton_bridge.notes import send_note
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/note" or args != [64, 90]:
                    raise AssertionError((path, args))
                FakeSocket.reply = encode_message("/note_ack", args)

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.notes.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = send_note(64, 90, timeout=1.0)

        self.assertEqual(result["pitch"], 64)
        self.assertEqual(result["velocity"], 90)
        self.assertEqual(result["from"], "127.0.0.1")
        self.assertEqual(result["port"], 7400)


class TempoClientTest(unittest.TestCase):
    def test_get_tempo_correlates_tempo_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.tempo import get_tempo

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/tempo" or len(args) != 3:
                    raise AssertionError((path, args))
                if json.loads(args[1]) != {} or args[2] != "dry_run":
                    raise AssertionError(args)
                FakeSocket.reply = encode_message("/tempo", [args[0], json.dumps({"ok": True, "tempo": 120.0})])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.tempo.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = get_tempo(timeout=1.0)

        self.assertEqual(result["tempo"], 120.0)
        self.assertEqual(result["from"], "127.0.0.1")
        self.assertEqual(result["port"], 7400)

    def test_set_tempo_dry_run_correlates_tempo_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.tempo import tempo

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/tempo" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"tempo": 132.0}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/tempo",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "tempo": 120.0, "target_tempo": 132.0})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.tempo.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = tempo(132, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["target_tempo"], 132.0)


class TransportClientTest(unittest.TestCase):
    def test_transport_jump_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.transport import transport

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/transport" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "jump", "beat": 128.0}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/transport",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "jump", "target_beat": 128.0})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.transport.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = transport("jump", beat=128, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["target_beat"], 128.0)


class LocatorClientTest(unittest.TestCase):
    def test_locator_create_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.locator import locator
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/locator" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "create", "name": "Drop 1", "beat": 128.0}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/locator",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "create"})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.locator.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = locator("create", name="Drop 1", beat=128, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["action"], "create")


class ClipNoteToolsClientTest(unittest.TestCase):
    def test_clip_note_tools_quantize_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.clip_note_tools import clip_note_tools
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/clip_note_tools" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "quantize_notes", "grid": 0.25, "start": 0.0, "end": 4.0, "candidate_index": 1}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/clip_note_tools",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "quantize_notes", "changed_count": 3})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.clip_note_tools.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = clip_note_tools("quantize_notes", grid=0.25, start=0.0, end=4.0, candidate_index=1, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["changed_count"], 3)

    def test_clip_note_tools_scan_is_default_flow(self) -> None:
        from ableton_bridge.clip_note_tools import clip_note_tools
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/clip_note_tools" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "scan_clips", "candidate_limit": 8}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/clip_note_tools",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "scan_clips", "candidate_count": 2})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.clip_note_tools.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = clip_note_tools("scan_clips", candidate_limit=8, timeout=1.0)

        self.assertEqual(result["action"], "scan_clips")
        self.assertEqual(result["candidate_count"], 2)


class ClipVariationClientTest(unittest.TestCase):
    def test_clip_variation_scan_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.clip_variation import clip_variation
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/clip_variation" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "scan_clips", "candidate_limit": 4}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/clip_variation",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "scan_clips", "candidate_count": 4})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.clip_variation.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = clip_variation("scan_clips", candidate_limit=4, timeout=1.0)

        self.assertEqual(result["action"], "scan_clips")
        self.assertEqual(result["candidate_count"], 4)

    def test_clip_variation_make_fill_requires_candidate(self) -> None:
        from ableton_bridge.clip_variation import clip_variation
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/clip_variation" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "make_fill", "candidate_index": 1, "target_start": 256.0, "fill_length": 4.0}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/clip_variation",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "make_fill", "changed_count": 6})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.clip_variation.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = clip_variation("make_fill", candidate_index=1, target_start=256, fill_length=4, timeout=1.0)

        self.assertEqual(result["changed_count"], 6)


class ArrangementToolsClientTest(unittest.TestCase):
    def test_arrangement_tools_scan_region_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.arrangement_tools import arrangement_tools
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/arrangement_tools" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "scan_region", "start": 224.0, "length": 32.0, "limit": 12}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/arrangement_tools",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "scan_region", "clip_count": 3})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.arrangement_tools.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = arrangement_tools("scan_region", start=224, length=32, limit=12, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["clip_count"], 3)

    def test_arrangement_tools_duplicate_region_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.arrangement_tools import arrangement_tools
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/arrangement_tools" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                expected = {
                    "action": "duplicate_region",
                    "start": 128.0,
                    "length": 32.0,
                    "target_start": 256.0,
                    "name_suffix": " Copy",
                }
                if payload != expected:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/arrangement_tools",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "duplicate_region", "plan": {"copied_count": 2}})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.arrangement_tools.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = arrangement_tools(
                "duplicate_region",
                start=128,
                length=32,
                target_start=256,
                name_suffix=" Copy",
                timeout=1.0,
            )

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["action"], "duplicate_region")


class TrackManagementClientTest(unittest.TestCase):
    def test_track_management_scan_tracks_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.track_management import track_management

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/track_management" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "scan_tracks", "include_returns": False}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/track_management",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "scan_tracks", "track_count": 9})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.track_management.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = track_management("scan_tracks", include_returns=False, bounded=False, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["track_count"], 9)

    def test_bounded_hierarchy_aggregates_flat_pages(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.track_management import track_management

        records = [
            {"section": "track", "track_index": 0, "track_id": 10, "track_name": "DRUMS", "track_type": "group", "parent_group_id": 0},
            {"section": "track", "track_index": 1, "track_id": 11, "track_name": "Kick", "track_type": "midi", "parent_group_id": 10},
            {"section": "return", "track_index": 0, "track_id": 20, "track_name": "Reverb", "track_type": "return", "parent_group_id": 0},
            {"section": "main", "track_index": 0, "track_id": 30, "track_name": "Main", "track_type": "main", "parent_group_id": 0},
        ]

        class FakeSocket:
            reply = None
            requests = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                payload = json.loads(args[1])
                read = payload["read"]
                FakeSocket.requests.append(read.copy())
                cursor = read["cursor"]
                items = records[cursor:cursor + read["limit"]]
                next_cursor = cursor + len(items)
                reply = {
                    "ok": True,
                    "dry_run": True,
                    "action": "scan_hierarchy",
                    "ordinary_track_count": 2,
                    "return_track_count": 1,
                    "main_track_count": 1,
                    "read": {
                        "complete": next_cursor == len(records),
                        "partial": False,
                        "cursor": cursor,
                        "next_cursor": next_cursor,
                        "limit": read["limit"],
                        "scanned_count": len(items),
                        "returned_count": len(items),
                        "has_more": next_cursor < len(records),
                        "collection_token": "fnv1a-track-set-4",
                        "elapsed_ms": 2,
                        "warnings": [],
                    },
                    "items": items,
                    "tracks": items,
                }
                FakeSocket.reply = encode_message(path, [args[0], json.dumps(reply)])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                reply = FakeSocket.reply
                FakeSocket.reply = None
                return reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.bounded_read.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = track_management("scan_hierarchy", include_returns=True, limit=2, timeout=1.0)

        self.assertTrue(result["complete"])
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["track_count"], 3)
        self.assertEqual(result["return_tracks"][0]["track_id"], 20)
        self.assertEqual(result["main_track"]["track_id"], 30)
        self.assertEqual(result["root_track_ids"], [10])
        self.assertEqual(result["hierarchy"][0]["child_track_ids"], [11])
        self.assertEqual(result["tracks"][1]["group_path_ids"], [10])
        self.assertIsNone(FakeSocket.requests[0]["expected_collection_token"])
        self.assertEqual(FakeSocket.requests[1]["expected_collection_token"], "fnv1a-track-set-4")

    def test_track_management_rename_track_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.track_management import track_management

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/track_management" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "rename_track", "track_index": 8, "name": "9-Sub Layer"}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/track_management",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "rename_track"})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.track_management.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = track_management("rename_track", track_index=8, name="9-Sub Layer", timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["action"], "rename_track")

    def test_track_management_delete_empty_track_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.track_management import track_management

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/track_management" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "delete_empty_track", "track_index": 14}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/track_management",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "delete_empty_track", "plan": {"empty": True}})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.track_management.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = track_management("delete_empty_track", track_index=14, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["action"], "delete_empty_track")

    def test_track_management_color_track_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.track_management import track_management

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/track_management" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "color_track", "track_index": 9, "color": "#FFAA33"}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/track_management",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "color_track"})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.track_management.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = track_management("color_track", track_index=9, color="#FFAA33", timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["action"], "color_track")

    def test_track_management_create_return_track_commit_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.track_management import track_management

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/track_management" or args[2] != "commit":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {
                    "action": "create_return_track",
                    "name": "C Parallel Verb",
                    "color": "#88AAFF",
                    "expected_return_ids": [401, 402],
                }:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/track_management",
                    [args[0], json.dumps({"ok": True, "dry_run": False, "action": "create_return_track", "applied": True})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.track_management.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = track_management(
                "create_return_track",
                name="C Parallel Verb",
                color="#88AAFF",
                expected_return_ids=[401, 402],
                commit=True,
                timeout=1.0,
            )

        self.assertFalse(result["dry_run"])
        self.assertEqual(result["action"], "create_return_track")

    def test_track_management_scan_hierarchy_uses_dry_run(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.track_management import track_management

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/track_management" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                if json.loads(args[1]) != {"action": "scan_hierarchy", "include_returns": True}:
                    raise AssertionError(args[1])
                FakeSocket.reply = encode_message(
                    "/track_management",
                    [args[0], json.dumps({
                        "ok": True,
                        "dry_run": True,
                        "action": "scan_hierarchy",
                        "ordinary_track_count": 14,
                        "return_track_count": 2,
                        "group_track_count": 0,
                    })],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.track_management.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = track_management("scan_hierarchy", include_returns=True, bounded=False, timeout=1.0)

        self.assertEqual(result["ordinary_track_count"], 14)
        self.assertEqual(result["return_track_count"], 2)

    def test_track_management_group_properties_commit_sends_stable_id_and_plan_token(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.track_management import track_management

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                payload = json.loads(args[1])
                expected = {
                    "action": "set_group_properties",
                    "group_track_id": 501,
                    "name": "DRUMS",
                    "color": "#D35F5F",
                    "fold_state": 1,
                    "plan_token": "abc12345",
                }
                if path != "/track_management" or args[2] != "commit" or payload != expected:
                    raise AssertionError((path, args, payload))
                FakeSocket.reply = encode_message(
                    "/track_management",
                    [args[0], json.dumps({
                        "ok": True,
                        "dry_run": False,
                        "applied": True,
                        "action": "set_group_properties",
                        "plan": {"verified": True},
                    })],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.track_management.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = track_management(
                "set_group_properties",
                group_track_id=501,
                name="DRUMS",
                color="#D35F5F",
                fold_state=1,
                plan_token="abc12345",
                commit=True,
                timeout=1.0,
            )

        self.assertTrue(result["plan"]["verified"])

    def test_track_management_group_plan_keeps_member_ids_in_payload(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.track_management import track_management

        groups = [
            {"name": "DRUMS", "member_track_ids": [101, 102, 108]},
            {"name": "BASS", "member_track_ids": [103, 109]},
        ]

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                payload = json.loads(args[1])
                if path != "/track_management" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                if payload != {"action": "plan_groups", "groups": groups}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/track_management",
                    [args[0], json.dumps({
                        "ok": True,
                        "dry_run": True,
                        "action": "plan_groups",
                        "blocked_by_live_api": True,
                        "plan": {"member_track_ids": [101, 102, 108, 103, 109]},
                    })],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.track_management.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = track_management("plan_groups", groups=groups, timeout=1.0)

        self.assertTrue(result["blocked_by_live_api"])
        self.assertEqual(result["plan"]["member_track_ids"], [101, 102, 108, 103, 109])


class RoutingClientTest(unittest.TestCase):
    def test_routing_scan_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.routing import routing

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/routing" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "scan_routing", "include_returns": False}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/routing",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "scan_routing", "track_count": 9})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.routing.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = routing("scan_routing", include_returns=False, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["track_count"], 9)

    def test_routing_set_output_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.routing import routing

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/routing" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "set_output_routing", "track_index": 0, "output_routing_type": "Master"}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/routing",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "set_output_routing"})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.routing.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = routing("set_output_routing", track_index=0, output_routing_type="Master", timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["action"], "set_output_routing")

    def test_routing_set_input_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.routing import routing

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/routing" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {
                    "action": "set_input_routing",
                    "track_index": 0,
                    "input_routing_type": "All Ins",
                    "include_input": True,
                    "include_available": True,
                }:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/routing",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "set_input_routing"})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.routing.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = routing(
                "set_input_routing",
                track_index=0,
                input_routing_type="All Ins",
                include_input=True,
                include_available=True,
                timeout=1.0,
            )

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["action"], "set_input_routing")


class SceneClientTest(unittest.TestCase):
    def test_scene_list_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.scene import scene

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/scene" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "list"}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/scene",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "list", "scene_count": 2})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.scene.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = scene("list", timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["scene_count"], 2)

    def test_scene_create_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.scene import scene

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/scene" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "create", "name": "Sketch Scene"}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/scene",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "create"})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.scene.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = scene("create", name="Sketch Scene", timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["action"], "create")

    def test_scene_duplicate_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.scene import scene

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/scene" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "duplicate", "scene_index": 1, "name": "Drop 1 Copy"}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/scene",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "duplicate"})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.scene.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = scene("duplicate", scene_index=1, name="Drop 1 Copy", timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["action"], "duplicate")

    def test_scene_capture_midi_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.scene import scene

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/scene" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "capture_midi", "name": "Captured Idea"}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/scene",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "capture_midi"})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.scene.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = scene("capture_midi", name="Captured Idea", timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["action"], "capture_midi")


class DeviceChainClientTest(unittest.TestCase):
    def test_device_chain_list_templates_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.device_chain import device_chain
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/device_chain" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "list_templates"}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/device_chain",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "templates": {"utility_gain_stage": ["Utility"]}})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.device_chain.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = device_chain("list_templates", timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertIn("utility_gain_stage", result["templates"])

    def test_device_chain_apply_template_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.device_chain import device_chain
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/device_chain" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "apply_template", "template": "utility_gain_stage", "track_index": 0}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/device_chain",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "apply_template", "inserted_devices": ["Utility"]})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.device_chain.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = device_chain("apply_template", template="utility_gain_stage", track_index=0, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["inserted_devices"], ["Utility"])

    def test_device_chain_apply_parameter_preset_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.device_chain import device_chain
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/device_chain" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "apply_parameter_preset", "preset": "lead_light_space", "track_index": 4}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/device_chain",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "apply_parameter_preset", "plan": {"changed_count": 1}})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.device_chain.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = device_chain("apply_parameter_preset", preset="lead_light_space", track_index=4, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["action"], "apply_parameter_preset")


class EqToolsClientTest(unittest.TestCase):
    def test_eq_tools_list_presets_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.eq_tools import eq_tools
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/eq_tools" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "list_presets"}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/eq_tools",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "presets": [{"name": "gentle_cleanup"}]})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.eq_tools.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = eq_tools("list_presets", timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["presets"][0]["name"], "gentle_cleanup")

    def test_eq_tools_apply_preset_formats_ui_values(self) -> None:
        from ableton_bridge.eq_tools import eq_tools
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/eq_tools" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "apply_preset", "preset": "lead_presence_soft", "track_index": 4}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/eq_tools",
                    [
                        args[0],
                        json.dumps({
                            "ok": True,
                            "dry_run": True,
                            "action": "apply_preset",
                            "result": {
                                "changed_count": 1,
                                "changes": [
                                    {
                                        "after": {"value": 1.0, "display_value": "1.00 dB"},
                                        "before": {"value": 0.0, "display_value": "0.00 dB"},
                                    }
                                ],
                            },
                        }),
                    ],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.eq_tools.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = eq_tools("apply_preset", preset="lead_presence_soft", track_index=4, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["result"]["changes"][0]["after"]["value"], "1.00 dB")
        self.assertEqual(result["result"]["changes"][0]["after"]["internal_value"], 1.0)


class MacroParametersClientTest(unittest.TestCase):
    def test_macro_parameters_scan_snapshot_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.macro_parameters import macro_parameters
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/macro_parameters" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "scan_snapshot", "track_index": 0, "device_index": 0, "limit": 8}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/macro_parameters",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "snapshot": {"parameter_count": 8}})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.macro_parameters.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = macro_parameters("scan_snapshot", track_index=0, device_index=0, limit=8, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["snapshot"]["parameter_count"], 8)

    def test_macro_parameters_apply_snapshot_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.macro_parameters import macro_parameters
        from ableton_bridge.osc import decode_message, encode_message

        snapshot = {"parameters": [{"parameter_index": 1, "name": "Dry/Wet", "value": 0.05}]}

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/macro_parameters" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "apply_snapshot", "track_index": 4, "device": "Reverb", "snapshot": snapshot}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/macro_parameters",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "apply_snapshot", "plan": {"changed_count": 1}})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.macro_parameters.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = macro_parameters("apply_snapshot", track_index=4, device="Reverb", snapshot=snapshot, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["action"], "apply_snapshot")


class MeterMonitorClientTest(unittest.TestCase):
    def test_meter_monitor_read_meters_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.meter_monitor import meter_monitor
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/meter_monitor" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "read_meters", "limit": 9}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/meter_monitor",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "track_count": 9, "silent_count": 2})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.meter_monitor.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = meter_monitor("read_meters", limit=9, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["track_count"], 9)
        self.assertEqual(result["silent_count"], 2)

    def test_meter_monitor_balance_report_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.meter_monitor import meter_monitor
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/meter_monitor" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "balance_report", "limit": 12}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/meter_monitor",
                    [args[0], json.dumps({"ok": True, "dry_run": True, "action": "balance_report", "active_count": 4})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.meter_monitor.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = meter_monitor("balance_report", limit=12, timeout=1.0)

        self.assertEqual(result["action"], "balance_report")
        self.assertEqual(result["active_count"], 4)


class ClipClientTest(unittest.TestCase):
    def test_read_clip_correlates_clip_reply(self) -> None:
        from ableton_bridge.clip import read_clip
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/clip" or len(args) != 1:
                    raise AssertionError((path, args))
                FakeSocket.reply = encode_message("/clip", [args[0], 1, 1, "Test Clip", 4.0])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.clip.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = read_clip(timeout=1.0)

        self.assertTrue(result["has_clip"])
        self.assertTrue(result["is_midi"])
        self.assertEqual(result["name"], "Test Clip")
        self.assertEqual(result["length"], 4.0)


class NoteReaderClientTest(unittest.TestCase):
    def test_read_notes_correlates_notes_reply(self) -> None:
        from ableton_bridge.note_reader import read_notes
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/notes" or len(args) != 1:
                    raise AssertionError((path, args))
                payload = json.dumps({
                    "ok": True,
                    "has_clip": True,
                    "is_midi": True,
                    "count": 1,
                    "notes": [{"pitch": 60, "start_time": 0.0, "bar": 1, "beat": 1.0}],
                })
                FakeSocket.reply = encode_message("/notes", [args[0], payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.note_reader.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = read_notes(timeout=1.0)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["notes"][0]["pitch"], 60)
        self.assertEqual(result["notes"][0]["bar"], 1)


class ClipWriterClientTest(unittest.TestCase):
    def test_write_clip_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.clip_writer import write_clip
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/write_clip" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload["track"] != "3-Operator" or payload["scene_index"] != 0:
                    raise AssertionError(payload)
                if payload["notes"] != [{"pitch": 41, "start_time": 0.0, "duration": 0.5, "velocity": 100}]:
                    raise AssertionError(payload)
                reply_payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "applied": False,
                    "track_name": "3-Operator",
                    "scene_index": 0,
                    "length": 4,
                    "note_count": 1,
                })
                FakeSocket.reply = encode_message("/write_clip", [args[0], reply_payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.clip_writer.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = write_clip(
                track="3-Operator",
                scene_index=0,
                length=4,
                notes=[{"pitch": 41, "start_time": 0.0, "duration": 0.5, "velocity": 100}],
                timeout=1.0,
            )

        self.assertTrue(result["dry_run"])
        self.assertFalse(result["applied"])
        self.assertEqual(result["track_name"], "3-Operator")
        self.assertEqual(result["note_count"], 1)

    def test_write_arrangement_clip_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.clip_writer import write_arrangement_clip
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/write_arrangement_clip" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload["track"] != "3-Operator" or payload["start"] != 16.0:
                    raise AssertionError(payload)
                reply_payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "applied": False,
                    "track_name": "3-Operator",
                    "start_time": 16.0,
                    "length": 4,
                    "note_count": 1,
                })
                FakeSocket.reply = encode_message("/write_arrangement_clip", [args[0], reply_payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.clip_writer.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = write_arrangement_clip(
                track="3-Operator",
                start=16.0,
                length=4,
                notes=[{"pitch": 41, "start_time": 0.0, "duration": 0.5, "velocity": 100}],
                timeout=1.0,
            )

        self.assertTrue(result["dry_run"])
        self.assertFalse(result["applied"])
        self.assertEqual(result["track_name"], "3-Operator")
        self.assertEqual(result["start_time"], 16.0)
        self.assertEqual(result["note_count"], 1)

    def test_note_from_text_parses_velocity_optional(self) -> None:
        from ableton_bridge.clip_writer import note_from_text

        self.assertEqual(
            note_from_text("41,0,0.5"),
            {"pitch": 41, "start_time": 0.0, "duration": 0.5, "velocity": 100},
        )
        self.assertEqual(
            note_from_text("41,0.5,0.25,88"),
            {"pitch": 41, "start_time": 0.5, "duration": 0.25, "velocity": 88},
        )


class DetailClipWriterClientTest(unittest.TestCase):
    def test_transpose_detail_note_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.detail_clip_writer import transpose_detail_note
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/transpose_detail_note" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"note_index": 0, "semitones": 12, "selector": "first_musical"}:
                    raise AssertionError(payload)
                reply_payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "applied": False,
                    "clip_name": "Bass - Bouncy Sub",
                    "note_count": 128,
                    "before": {"pitch": 41, "start_time": 0.0, "bar": 1, "beat": 1},
                    "after": {"pitch": 53, "start_time": 0.0, "bar": 1, "beat": 1},
                })
                FakeSocket.reply = encode_message("/transpose_detail_note", [args[0], reply_payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.detail_clip_writer.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = transpose_detail_note(note_index=0, semitones=12, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertFalse(result["applied"])
        self.assertEqual(result["clip_name"], "Bass - Bouncy Sub")
        self.assertEqual(result["before"]["pitch"], 41)
        self.assertEqual(result["after"]["pitch"], 53)

    def test_rejects_zero_transpose(self) -> None:
        from ableton_bridge.detail_clip_writer import DetailClipWriteError, transpose_detail_note

        with self.assertRaises(DetailClipWriteError):
            transpose_detail_note(semitones=0)


class TracksClientTest(unittest.TestCase):
    def test_read_tracks_correlates_tracks_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.tracks import read_tracks

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/tracks" or len(args) != 1:
                    raise AssertionError((path, args))
                payload = json.dumps({
                    "ok": True,
                    "count": 1,
                    "tracks": [{"index": 0, "name": "1-MIDI", "device_count": 2}],
                })
                FakeSocket.reply = encode_message("/tracks", [args[0], payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.tracks.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = read_tracks(timeout=1.0)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["tracks"][0]["name"], "1-MIDI")
        self.assertEqual(result["tracks"][0]["device_count"], 2)


class SnapshotClientTest(unittest.TestCase):
    def test_read_snapshot_correlates_snapshot_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.snapshot import read_snapshot

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/snapshot" or len(args) != 1:
                    raise AssertionError((path, args))
                payload = json.dumps({
                    "ok": True,
                    "tempo": 132,
                    "track_count": 2,
                    "return_track_count": 1,
                    "tracks": [
                        {
                            "index": 0,
                            "name": "Drums",
                            "kind": "midi",
                            "device_count": 1,
                            "devices": [{"name": "Garage Kit", "type_name": "instrument"}],
                        },
                        {
                            "index": 1,
                            "name": "Bass",
                            "kind": "midi",
                            "device_count": 1,
                            "mix": {
                                "volume": {"value": 0.85, "display_value": "-3.0 dB"},
                                "pan": {"value": 0.0, "display_value": "C"},
                                "sends": [{"index": 0, "label": "A", "value": 0.25}],
                                "output_meter_left": 0.1,
                                "crossfade_assign": 1,
                            },
                            "devices": [{"name": "Operator", "type_name": "instrument"}],
                        },
                    ],
                    "return_tracks": [{"index": 0, "name": "A-Reverb", "devices": []}],
                    "master_track": {"name": "Master", "devices": []},
                })
                FakeSocket.reply = encode_message("/snapshot", [args[0], payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.snapshot.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = read_snapshot(timeout=1.0)

        self.assertEqual(result["tempo"], 132)
        self.assertEqual(result["track_count"], 2)
        self.assertEqual(result["tracks"][0]["devices"][0]["name"], "Garage Kit")
        self.assertEqual(result["tracks"][1]["devices"][0]["name"], "Operator")
        self.assertEqual(result["tracks"][1]["mix"]["volume"]["value"], 0.85)
        self.assertEqual(result["tracks"][1]["mix"]["sends"][0]["label"], "A")


class DevicesClientTest(unittest.TestCase):
    def test_read_devices_correlates_devices_reply(self) -> None:
        from ableton_bridge.devices import read_devices
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/devices" or len(args) != 1:
                    raise AssertionError((path, args))
                payload = json.dumps({
                    "ok": True,
                    "has_track": True,
                    "track_name": "1-MIDI",
                    "count": 1,
                    "devices": [{"index": 0, "name": "Drift", "parameter_count": 12}],
                })
                FakeSocket.reply = encode_message("/devices", [args[0], payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.devices.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = read_devices(timeout=1.0)

        self.assertEqual(result["track_name"], "1-MIDI")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["devices"][0]["name"], "Drift")


class InserterClientTest(unittest.TestCase):
    def test_insert_device_dry_run_correlates_insert_reply(self) -> None:
        from ableton_bridge.inserter import insert_device
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/insert_device" or args[1:] != ["Operator", "dry_run"]:
                    raise AssertionError((path, args))
                payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "inserted": False,
                    "track_name": "Bass",
                    "resolved_device": "Operator",
                })
                FakeSocket.reply = encode_message("/insert_device", [args[0], payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.inserter.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = insert_device("bass", timeout=1.0)

        self.assertEqual(result["track_name"], "Bass")
        self.assertEqual(result["resolved_device"], "Operator")
        self.assertFalse(result["inserted"])

    def test_insert_device_rejects_non_whitelisted_devices(self) -> None:
        from ableton_bridge.inserter import InserterError, insert_device

        with self.assertRaises(InserterError):
            insert_device("Some Random Plugin")

    def test_insert_device_resolves_expanded_roles_and_aliases(self) -> None:
        from ableton_bridge.inserter import resolve_device

        self.assertEqual(resolve_device("pad"), "Wavetable")
        self.assertEqual(resolve_device("lead"), "Drift")
        self.assertEqual(resolve_device("mallet"), "Collision")
        self.assertEqual(resolve_device("drumrack"), "Drum Rack")
        self.assertEqual(resolve_device("operator"), "Operator")
        self.assertEqual(resolve_device("Drum Sampler"), "Drum Sampler")

    def test_insert_devices_dry_run_correlates_batch_reply(self) -> None:
        from ableton_bridge.inserter import insert_devices
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/insert_devices" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload["targets"] != [
                    {"track": "3-Operator", "role": "bass"},
                    {"track": "4-E-Piano Basic", "role": "chords"},
                ]:
                    raise AssertionError(payload)
                reply_payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "inserted": 0,
                    "insertable_count": 2,
                    "skipped_count": 0,
                    "plans": [
                        {"track_name": "3-Operator", "resolved_device": "Operator"},
                        {"track_name": "4-E-Piano Basic", "resolved_device": "Electric"},
                    ],
                })
                FakeSocket.reply = encode_message("/insert_devices", [args[0], reply_payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        targets = [
            {"track": "3-Operator", "role": "bass"},
            {"track": "4-E-Piano Basic", "role": "chords"},
        ]
        with patch("ableton_bridge.inserter.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = insert_devices(targets, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["insertable_count"], 2)
        self.assertEqual(result["plans"][0]["resolved_device"], "Operator")
        self.assertEqual(result["plans"][1]["resolved_device"], "Electric")

    def test_create_midi_track_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.inserter import create_midi_track
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/create_midi_track" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"name": "7-Chord Stabs", "select": True, "device": "Electric"}:
                    raise AssertionError(payload)
                reply_payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "created": False,
                    "index": 6,
                    "name": "7-Chord Stabs",
                    "resolved_device": "Electric",
                })
                FakeSocket.reply = encode_message("/create_midi_track", [args[0], reply_payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.inserter.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = create_midi_track(name="7-Chord Stabs", role_or_device="chords", select=True, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertFalse(result["created"])
        self.assertEqual(result["resolved_device"], "Electric")

    def test_load_sample_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.sample_loader import load_sample

        sample_path = r"C:\ProgramData\Ableton\Live 12 Trial\Resources\Core Library\Samples\One Shots\Drums\Hihat\Hihat Closed Sharp Garage.aif"

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/load_sample" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {
                    "sample_path": sample_path,
                    "track": "8-Top Percussion",
                    "target": "drum_rack_pad",
                    "scan_browser": False,
                    "scan_limit": 1500,
                }:
                    raise AssertionError(payload)
                reply_payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "loaded": False,
                    "track_name": "8-Top Percussion",
                    "found": True,
                    "browser_item": {"name": "Hihat Closed Sharp Garage.aif"},
                })
                FakeSocket.reply = encode_message("/load_sample", [args[0], reply_payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.sample_loader.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = load_sample(
                sample_path=sample_path,
                track="8-Top Percussion",
                target="drum_rack_pad",
                check_index=False,
                timeout=1.0,
            )

        self.assertTrue(result["dry_run"])
        self.assertTrue(result["found"])
        self.assertEqual(result["browser_item"]["name"], "Hihat Closed Sharp Garage.aif")

    def test_sample_index_confirms_existing_path_without_rescan(self) -> None:
        from ableton_bridge.sample_index import ensure_sample_available, save_index

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sample = root / "Loops" / "Drums" / "Top" / "Hihat Closed Sharp Garage.aif"
            sample.parent.mkdir(parents=True)
            sample.write_bytes(b"sample")
            index_path = root / "sample_index.json"
            save_index({"samples": []}, index_path)

            result = ensure_sample_available(sample, index_path=index_path, preferred_category="hat")

        self.assertTrue(result["ok"])
        self.assertTrue(result["exists"])
        self.assertFalse(result["rescanned"])
        self.assertEqual(Path(result["path"]).name, "Hihat Closed Sharp Garage.aif")

    def test_sample_index_rescans_nearby_folder_for_missing_path(self) -> None:
        from ableton_bridge.sample_index import ensure_sample_available, load_index, save_index

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            top = root / "Samples" / "Loops" / "Drums" / "Top"
            top.mkdir(parents=True)
            missing = top / "Old Hat.aif"
            replacement = top / "Old Hat.wav"
            replacement.write_bytes(b"sample")
            index_path = root / "sample_index.json"
            save_index({"samples": []}, index_path)

            result = ensure_sample_available(
                missing,
                index_path=index_path,
                preferred_category="hat",
                allow_replacement=True,
            )
            updated_index = load_index(index_path)

        self.assertTrue(result["ok"])
        self.assertTrue(result["replacement_used"])
        self.assertEqual(Path(result["path"]).name, "Old Hat.wav")
        self.assertEqual(updated_index["total_matches"], 1)
        self.assertEqual(updated_index["samples"][0]["name"], "Old Hat.wav")

    def test_sample_picker_returns_existing_ranked_candidates(self) -> None:
        from ableton_bridge.sample_index import save_index
        from ableton_bridge.sample_picker import pick_samples

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            garage_hat = root / "Samples" / "One Shots" / "Drums" / "Hihat Closed Sharp Garage.aif"
            generic_hat = root / "Samples" / "Loops" / "Drums" / "Hihat Wide 128 bpm.wav"
            missing_hat = root / "Samples" / "One Shots" / "Drums" / "Missing Hat.aif"
            garage_hat.parent.mkdir(parents=True)
            generic_hat.parent.mkdir(parents=True, exist_ok=True)
            garage_hat.write_bytes(b"sample")
            generic_hat.write_bytes(b"sample")
            index_path = root / "sample_index.json"
            save_index(
                {
                    "samples": [
                        {
                            "name": garage_hat.name,
                            "path": str(garage_hat),
                            "extension": ".aif",
                            "kind": "audio_sample",
                            "categories": ["hat"],
                            "size_bytes": 6,
                        },
                        {
                            "name": generic_hat.name,
                            "path": str(generic_hat),
                            "extension": ".wav",
                            "kind": "audio_sample",
                            "categories": ["hat", "perc"],
                            "size_bytes": 6,
                        },
                        {
                            "name": missing_hat.name,
                            "path": str(missing_hat),
                            "extension": ".aif",
                            "kind": "audio_sample",
                            "categories": ["hat"],
                            "size_bytes": 6,
                        },
                    ]
                },
                index_path,
            )

            result = pick_samples(category="hat", style="garage", limit=2, index_path=index_path, refresh_missing=False)

        self.assertTrue(result["ok"])
        self.assertEqual(result["picked_count"], 2)
        self.assertTrue(all(candidate["exists"] for candidate in result["candidates"]))
        self.assertEqual(result["candidates"][0]["name"], "Hihat Closed Sharp Garage.aif")
        self.assertIsInstance(result["candidates"][0]["rank_score"], int)
        self.assertIn("category match: hat", result["candidates"][0]["rank_reasons"])
        self.assertIn("garage/UKG text match", result["candidates"][0]["rank_reasons"])

    def test_sample_confirm_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.sample_confirm import sample_confirm

        intended_path = r"C:\Samples\Hihat Closed Sharp Garage.aif"

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/sample_confirm" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {
                    "action": "confirm_loaded_sample",
                    "track_index": 7,
                    "target": "drum_rack_pad",
                    "pad_index": 4,
                    "intended_path": intended_path,
                }:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/sample_confirm",
                    [
                        args[0],
                        json.dumps({
                            "ok": True,
                            "dry_run": True,
                            "action": "confirm_loaded_sample",
                            "result": {"loaded": True},
                        }),
                    ],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.sample_confirm.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = sample_confirm(
                track_index=7,
                target="drum_rack_pad",
                pad_index=4,
                intended_path=intended_path,
                timeout=1.0,
            )

        self.assertTrue(result["dry_run"])
        self.assertTrue(result["result"]["loaded"])

    def test_sample_confirm_scan_loaded_samples_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.sample_confirm import sample_confirm

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/sample_confirm" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"action": "scan_loaded_samples", "track_index": 7, "limit": 12}:
                    raise AssertionError(payload)
                FakeSocket.reply = encode_message(
                    "/sample_confirm",
                    [
                        args[0],
                        json.dumps({
                            "ok": True,
                            "dry_run": True,
                            "action": "scan_loaded_samples",
                            "result": {"loaded_count": 1, "candidates": [{"candidate_index": 0}]},
                        }),
                    ],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.sample_confirm.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = sample_confirm("scan_loaded_samples", track_index=7, limit=12, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["result"]["loaded_count"], 1)

    def test_parse_target_supports_track_and_role(self) -> None:
        from ableton_bridge.inserter import parse_target

        self.assertEqual(parse_target("3-Operator|bass"), {"track": "3-Operator", "role": "bass"})
        self.assertEqual(parse_target("2|drums"), {"track": 2, "role": "drums"})

    def test_insert_effect_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.inserter import insert_effect
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/insert_effect" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {"track": "3-Operator", "effect": "filter", "allow_duplicate": False}:
                    raise AssertionError(payload)
                reply_payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "inserted": False,
                    "plan": {"track_name": "3-Operator", "resolved_effect": "Auto Filter"},
                })
                FakeSocket.reply = encode_message("/insert_effect", [args[0], reply_payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.inserter.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = insert_effect("filter", track="3-Operator", timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["plan"]["resolved_effect"], "Auto Filter")

    def test_insert_effects_dry_run_correlates_batch_reply(self) -> None:
        from ableton_bridge.inserter import insert_effects
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/insert_effects" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload["targets"] != [{"track": "3-Operator", "effect": "compressor"}]:
                    raise AssertionError(payload)
                reply_payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "insertable_count": 1,
                    "plans": [{"track_name": "3-Operator", "resolved_effect": "Compressor"}],
                })
                FakeSocket.reply = encode_message("/insert_effects", [args[0], reply_payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.inserter.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = insert_effects([{"track": "3-Operator", "effect": "compressor"}], timeout=1.0)

        self.assertEqual(result["insertable_count"], 1)
        self.assertEqual(result["plans"][0]["resolved_effect"], "Compressor")

    def test_parse_effect_target_and_resolve_effect(self) -> None:
        from ableton_bridge.inserter import parse_effect_target, resolve_effect

        self.assertEqual(resolve_effect("filter"), "Auto Filter")
        self.assertEqual(resolve_effect("eq"), "EQ Eight")
        self.assertEqual(parse_effect_target("master|limiter"), {"track": "master", "effect": "limiter"})


class ParametersClientTest(unittest.TestCase):
    def test_read_parameters_correlates_parameters_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.parameters import read_parameters

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/parameters" or len(args) != 1:
                    raise AssertionError((path, args))
                payload = json.dumps({
                    "ok": True,
                    "track_name": "1-MIDI",
                    "device_name": "E-Piano Detuned",
                    "count": 1,
                    "parameters": [{"index": 0, "name": "Device On", "value": 1, "min": 0, "max": 1}],
                })
                FakeSocket.reply = encode_message("/parameters", [args[0], payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.parameters.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = read_parameters(timeout=1.0)

        self.assertEqual(result["device_name"], "E-Piano Detuned")
        self.assertEqual(result["parameters"][0]["name"], "Device On")


class ParameterSummaryClientTest(unittest.TestCase):
    def test_read_parameter_summary_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.parameter_summary import read_parameter_summary

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/parameter_summary" or len(args) != 2:
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {
                    "max_devices_per_track": 2,
                    "max_parameters_per_device": 8,
                    "include_display_values": False,
                }:
                    raise AssertionError(payload)
                reply_payload = json.dumps({
                    "ok": True,
                    "track_count": 1,
                    "max_devices_per_track": 2,
                    "max_parameters_per_device": 8,
                    "tracks": [
                        {
                            "name": "3-Operator",
                            "target_device": "Operator",
                            "devices": [
                                {
                                    "name": "Operator",
                                    "parameter_count": 195,
                                    "summarized_parameter_count": 8,
                                    "parameters": [{"index": 0, "name": "Device On", "value": 1}],
                                }
                            ],
                        }
                    ],
                })
                FakeSocket.reply = encode_message("/parameter_summary", [args[0], reply_payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.parameter_summary.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = read_parameter_summary(max_parameters_per_device=8, timeout=1.0)

        self.assertEqual(result["track_count"], 1)
        self.assertEqual(result["tracks"][0]["target_device"], "Operator")
        self.assertEqual(result["tracks"][0]["devices"][0]["summarized_parameter_count"], 8)


class ParameterSummaryInspectionClientTest(unittest.TestCase):
    def test_search_parameters_uses_bounded_read_only_payload(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.parameter_summary import inspect_device_parameters

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/parameter_summary" or len(args) != 3 or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload != {
                    "action": "search_parameters",
                    "section": "track",
                    "offset": 0,
                    "limit": 8,
                    "include_display_values": True,
                    "include_enum_values": True,
                    "read": {
                        "cursor": 0,
                        "limit": 8,
                        "projection": ["identity", "metadata", "internal_value", "display_value", "enum_values"],
                        "budget_ms": 1000,
                        "expected_collection_token": None,
                    },
                    "track_id": 101,
                    "device_id": 202,
                    "query": "unison",
                }:
                    raise AssertionError(payload)
                reply = {
                    "ok": True,
                    "dry_run": True,
                    "action": "search_parameters",
                    "target": {"track_id": 101, "device_id": 202},
                    "matched_parameter_count": 1,
                    "read": {
                        "complete": True,
                        "partial": False,
                        "cursor": 0,
                        "next_cursor": 8,
                        "limit": 8,
                        "scanned_count": 8,
                        "returned_count": 1,
                        "has_more": False,
                        "collection_token": "fnv1a-test-8",
                        "elapsed_ms": 4,
                        "warnings": [],
                    },
                    "items": [
                        {
                            "index": 14,
                            "name": "Unison Mode",
                            "value": 1,
                            "display_value": "Classic",
                            "is_quantized": True,
                        }
                    ],
                    "parameters": [
                        {
                            "index": 14,
                            "name": "Unison Mode",
                            "value": 1,
                            "display_value": "Classic",
                            "is_quantized": True,
                        }
                    ],
                }
                FakeSocket.reply = encode_message("/parameter_summary", [args[0], json.dumps(reply)])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.bounded_read.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = inspect_device_parameters(
                action="search_parameters",
                track_id=101,
                device_id=202,
                query="unison",
                limit=8,
                include_display_values=True,
                include_enum_values=True,
                auto_collect=False,
                timeout=1.0,
            )

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["parameters"][0]["name"], "Unison Mode")

    def test_rejects_unbounded_or_ambiguous_requests(self) -> None:
        from ableton_bridge.parameter_summary import ParameterSummaryError, inspect_device_parameters

        with self.assertRaises(ParameterSummaryError):
            inspect_device_parameters(track_name="Wide Chords", limit=33)
        with self.assertRaises(ParameterSummaryError):
            inspect_device_parameters(action="search_parameters", track_name="Wide Chords", query="")
        with self.assertRaises(ParameterSummaryError):
            inspect_device_parameters(action="list_parameters")

    def test_auto_collects_pages_and_carries_collection_token(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.parameter_summary import inspect_device_parameters

        class FakeSocket:
            reply = None
            requests = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                payload = json.loads(args[1])
                read = payload["read"]
                FakeSocket.requests.append(read.copy())
                cursor = read["cursor"]
                names = ["Device On", "Unison Mode"] if cursor == 0 else ["Unison Amount"]
                items = [{"index": cursor + index, "name": name, "value": index} for index, name in enumerate(names)]
                reply = {
                    "ok": True,
                    "dry_run": True,
                    "action": "list_parameters",
                    "target": {"track_id": 101, "device_id": 202},
                    "parameter_count": 3,
                    "read": {
                        "complete": cursor == 2,
                        "partial": False,
                        "cursor": cursor,
                        "next_cursor": 2 if cursor == 0 else 3,
                        "limit": 2,
                        "scanned_count": 2 if cursor == 0 else 1,
                        "returned_count": len(items),
                        "has_more": cursor == 0,
                        "collection_token": "fnv1a-stable-3",
                        "elapsed_ms": 3,
                        "warnings": [],
                    },
                    "items": items,
                    "parameters": items,
                }
                FakeSocket.reply = encode_message(path, [args[0], json.dumps(reply)])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                reply = FakeSocket.reply
                FakeSocket.reply = None
                return reply, ("127.0.0.1", 7400)

        progress = []
        with patch("ableton_bridge.bounded_read.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = inspect_device_parameters(
                track_id=101,
                device_id=202,
                limit=2,
                timeout=1.0,
                on_page=lambda page, _result: progress.append(page),
            )

        self.assertTrue(result["complete"])
        self.assertEqual(result["page_count"], 2)
        self.assertEqual([item["name"] for item in result["parameters"]], ["Device On", "Unison Mode", "Unison Amount"])
        self.assertIsNone(FakeSocket.requests[0]["expected_collection_token"])
        self.assertEqual(FakeSocket.requests[1]["expected_collection_token"], "fnv1a-stable-3")
        self.assertEqual(progress, [1, 2])


class BoundedReadCoordinatorTest(unittest.TestCase):
    @staticmethod
    def page(*, cursor: int, next_cursor: int, token: str = "stable", has_more: bool = False, warnings=None, ok: bool = True):
        return {
            "ok": ok,
            "error": None if ok else "business failure",
            "read": {
                "cursor": cursor,
                "next_cursor": next_cursor,
                "has_more": has_more,
                "partial": False,
                "collection_token": token,
                "elapsed_ms": 1,
                "scanned_count": next_cursor - cursor,
                "returned_count": next_cursor - cursor,
                "warnings": warnings or [],
            },
            "items": [{"index": index} for index in range(cursor, next_cursor)],
        }

    def test_warning_stops_a_clean_continuation(self) -> None:
        from ableton_bridge.bounded_read import collect_pages

        result = collect_pages(
            lambda _payload, _timeout: self.page(cursor=0, next_cursor=2, has_more=True, warnings=["unsafe field skipped"]),
            {"read": {"cursor": 0, "limit": 2}},
        )
        self.assertFalse(result["complete"])
        self.assertEqual(result["stop_reason"], "warning")
        self.assertEqual(result["page_count"], 1)

    def test_collection_change_is_rejected(self) -> None:
        from ableton_bridge.bounded_read import BoundedReadError, collect_pages

        calls = 0

        def fetch(_payload, _timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                return self.page(cursor=0, next_cursor=1, token="first", has_more=True)
            return self.page(cursor=1, next_cursor=2, token="changed", has_more=False)

        with self.assertRaisesRegex(BoundedReadError, "Collection token changed"):
            collect_pages(fetch, {"read": {"cursor": 0, "limit": 1}})

    def test_business_error_and_page_limit_are_distinct(self) -> None:
        from ableton_bridge.bounded_read import BoundedReadBusinessError, collect_pages

        with self.assertRaises(BoundedReadBusinessError):
            collect_pages(
                lambda _payload, _timeout: self.page(cursor=0, next_cursor=0, ok=False),
                {"read": {"cursor": 0, "limit": 1}},
            )

        limited = collect_pages(
            lambda payload, _timeout: self.page(
                cursor=payload["read"]["cursor"],
                next_cursor=payload["read"]["cursor"] + 1,
                has_more=True,
            ),
            {"read": {"cursor": 0, "limit": 1}},
            max_pages=2,
        )
        self.assertEqual(limited["stop_reason"], "max_pages")
        self.assertFalse(limited["complete"])

    def test_item_limit_stops_without_claiming_completion(self) -> None:
        from ableton_bridge.bounded_read import collect_pages

        result = collect_pages(
            lambda _payload, _timeout: self.page(cursor=0, next_cursor=3, has_more=True),
            {"read": {"cursor": 0, "limit": 3}},
            max_items=2,
        )
        self.assertEqual(result["stop_reason"], "max_items")
        self.assertEqual(len(result["items"]), 2)
        self.assertFalse(result["complete"])


class RecommenderTest(unittest.TestCase):
    def test_loads_external_uk_garage_style_profile(self) -> None:
        from ableton_bridge.style_profiles import available_styles, load_style_profile

        self.assertIn("uk_garage", available_styles())
        profile = load_style_profile("uk-garage")

        self.assertEqual(profile["slug"], "uk_garage")
        self.assertEqual(profile["roles"]["bass"]["instrument"], "Operator")

    def test_loads_supported_external_style_profiles(self) -> None:
        from ableton_bridge.recommender import recommend
        from ableton_bridge.style_profiles import available_styles, load_style_profile

        expected = {
            "ambient",
            "bossa_nova",
            "dnb",
            "future_bass",
            "hiphop",
            "house",
            "lofi",
            "techno",
            "techno_acid",
            "techno_detroit",
            "techno_dub",
            "techno_hardgroove",
            "techno_industrial",
            "techno_melodic",
            "techno_minimal",
            "techno_peak_time",
            "trap",
            "uk_garage",
        }
        self.assertTrue(expected.issubset(set(available_styles())))

        summary = {
            "ok": True,
            "tracks": [
                {"name": "Drums", "target_device": "Drum Rack", "devices": [{"name": "Drum Rack", "parameters": []}]},
                {"name": "Bass", "target_device": "Operator", "devices": [{"name": "Operator", "parameters": []}]},
            ],
        }
        for style in sorted(expected):
            with self.subTest(style=style):
                profile = load_style_profile(style)
                result = recommend(summary, style=style)
                self.assertEqual(profile["slug"], style)
                self.assertEqual(result["style"], style)
                self.assertGreater(result["action_count"], 0)

    def test_recommends_uk_garage_actions_from_parameter_summary(self) -> None:
        from ableton_bridge.recommender import recommend

        summary = {
            "ok": True,
            "track_count": 4,
            "tracks": [
                {
                    "name": "1-Garage Kit",
                    "target_device": "Garage Kit",
                    "devices": [
                        {
                            "name": "Garage Kit",
                            "parameters": [
                                {"name": "Device On", "value": 1},
                                {"name": "DrBuss Amount", "value": 0},
                            ],
                        }
                    ],
                },
                {
                    "name": "3-Operator",
                    "target_device": "Operator",
                    "devices": [{"name": "Operator", "parameters": [{"name": "Algorithm", "value": 0}]}],
                },
                {
                    "name": "4-E-Piano Basic",
                    "target_device": "E-Piano Basic",
                    "devices": [
                        {
                            "name": "E-Piano Basic",
                            "parameters": [{"name": "Reverb Amount", "value": 0.12}],
                        },
                        {"name": "Echo", "parameters": []},
                    ],
                },
                {"name": "Mystery", "target_device": "", "devices": []},
            ],
        }

        result = recommend(summary)

        self.assertTrue(result["ok"])
        self.assertEqual(result["style"], "uk_garage")
        self.assertEqual(result["mode"], "recommend_only")
        roles = {track["track"]: track["role"] for track in result["tracks"]}
        self.assertEqual(roles["1-Garage Kit"], "drums")
        self.assertEqual(roles["3-Operator"], "bass")
        self.assertEqual(roles["4-E-Piano Basic"], "chords")
        self.assertIsNone(roles["Mystery"])
        self.assertIn(
            {
                "type": "insert_effect",
                "track": "3-Operator",
                "role": "bass",
                "effect": "filter",
                "resolved_effect": "Auto Filter",
                "reason": "bass needs a basic Auto Filter stage",
            },
            result["actions"],
        )
        self.assertFalse(
            any(
                action.get("type") == "insert_device" and action.get("track") == "4-E-Piano Basic"
                for action in result["actions"]
            )
        )
        self.assertNotIn(
            {
                "type": "insert_effect",
                "track": "4-E-Piano Basic",
                "role": "chords",
                "effect": "echo",
                "resolved_effect": "Echo",
                "reason": "chords needs a basic Echo stage",
            },
            result["actions"],
        )
        self.assertIn(
            {
                "type": "set_mix",
                "track": "3-Operator",
                "role": "bass",
                "field": "send",
                "send": "A",
                "value": 0.0,
                "reason": "bass send balance for UK Garage space",
            },
            result["actions"],
        )
        self.assertIn(
            {
                "type": "set_parameter",
                "track": "1-Garage Kit",
                "role": "drums",
                "device": "Garage Kit",
                "parameter": "DrBuss Amount",
                "value": 12.0,
                "reason": "drums preset-style parameter starting point",
            },
            result["actions"],
        )
        self.assertEqual(result["execution_plan"]["batch_count"], 4)
        self.assertGreater(result["execution_plan"]["executable_action_count"], 0)

    def test_recommender_rejects_unknown_style(self) -> None:
        from ableton_bridge.recommender import RecommenderError, recommend

        with self.assertRaises(RecommenderError):
            recommend({"tracks": []}, style="not_a_real_style")

    def test_build_execution_plan_groups_actions_for_existing_clients(self) -> None:
        from ableton_bridge.recommender import build_execution_plan

        actions = [
            {"type": "insert_device", "track": "Empty Bass", "device": "Operator"},
            {"type": "insert_effect", "track": "3-Operator", "effect": "filter"},
            {"type": "set_mix", "track": "3-Operator", "field": "send", "send": "A", "value": 0.0},
            {
                "type": "set_parameter",
                "track": "1-Garage Kit",
                "device": "Garage Kit",
                "parameter": "DrBuss Amount",
                "value": 12.0,
            },
            {"type": "note", "track": "Mystery", "reason": "not executable"},
        ]

        plan = build_execution_plan(actions)

        self.assertEqual(plan["batch_count"], 4)
        self.assertEqual(plan["executable_action_count"], 4)
        self.assertEqual(plan["skipped_count"], 1)
        self.assertEqual([batch["batch_number"] for batch in plan["batches"]], [1, 2, 3, 4])
        self.assertEqual(plan["batches"][0]["type"], "insert_devices")
        self.assertEqual(plan["batches"][1]["type"], "insert_effects")
        self.assertEqual(plan["batches"][2]["type"], "set_mix")
        self.assertEqual(plan["batches"][3]["type"], "set_parameters")
        self.assertEqual(plan["batches"][2]["changes"][0], {"track": "3-Operator", "field": "send", "value": 0.0, "send": "A"})

    def test_execute_recommendations_dry_runs_grouped_clients(self) -> None:
        from ableton_bridge.recommender import execute_recommendations

        calls = []

        def fake_runner(name):
            def run(payload, *, commit, timeout):
                calls.append((name, payload, commit, timeout))
                return {"ok": True, "dry_run": not commit, "count": len(payload)}

            return run

        recommendation = {
            "actions": [
                {"type": "insert_effect", "track": "3-Operator", "effect": "filter"},
                {"type": "set_mix", "track": "3-Operator", "field": "volume", "value": 0.78},
                {
                    "type": "set_parameter",
                    "track": "1-Garage Kit",
                    "device": "Garage Kit",
                    "parameter": "DrBuss Amount",
                    "value": 12.0,
                },
            ]
        }

        result = execute_recommendations(
            recommendation,
            timeout=9,
            runners={
                "insert_devices": fake_runner("insert_devices"),
                "insert_effects": fake_runner("insert_effects"),
                "set_mix": fake_runner("set_mix"),
                "set_parameters": fake_runner("set_parameters"),
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "dry_run")
        self.assertEqual([call[0] for call in calls], ["insert_effects", "set_mix", "set_parameters"])
        self.assertTrue(all(call[2] is False for call in calls))
        self.assertTrue(all(call[3] == 9 for call in calls))

    def test_execute_recommendations_can_filter_action_types(self) -> None:
        from ableton_bridge.recommender import execute_recommendations

        calls = []

        def fake_set_mix(payload, *, commit, timeout):
            calls.append((payload, commit, timeout))
            return {"ok": True}

        result = execute_recommendations(
            {
                "actions": [
                    {"type": "insert_effect", "track": "3-Operator", "effect": "filter"},
                    {"type": "set_mix", "track": "3-Operator", "field": "volume", "value": 0.78},
                ]
            },
            action_types={"set_mix"},
            commit=True,
            runners={
                "insert_devices": lambda *_args, **_kwargs: {},
                "insert_effects": lambda *_args, **_kwargs: {},
                "set_mix": fake_set_mix,
                "set_parameters": lambda *_args, **_kwargs: {},
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "commit")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][1])

    def test_execute_recommendations_can_select_one_batch(self) -> None:
        from ableton_bridge.recommender import execute_recommendations

        calls = []

        def fake_set_mix(payload, *, commit, timeout):
            calls.append(payload)
            return {"ok": True, "count": len(payload)}

        actions = [
            {"type": "set_mix", "track": "1-Garage Kit", "field": "volume", "value": 0.82}
            for _index in range(10)
        ]

        result = execute_recommendations(
            {"actions": actions},
            action_types={"set_mix"},
            batch_numbers={2},
            runners={
                "insert_devices": lambda *_args, **_kwargs: {},
                "insert_effects": lambda *_args, **_kwargs: {},
                "set_mix": fake_set_mix,
                "set_parameters": lambda *_args, **_kwargs: {},
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["selected_batch_numbers"], [2])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), 2)
        self.assertEqual(result["summary"]["successful_batch_count"], 1)

    def test_summarize_execution_plan_lists_batch_tracks(self) -> None:
        from ableton_bridge.recommender import build_execution_plan, summarize_execution_plan

        plan = build_execution_plan(
            [
                {"type": "set_mix", "track": "1-Garage Kit", "field": "volume", "value": 0.82},
                {"type": "set_mix", "track": "2-Garage Kit", "field": "volume", "value": 0.82},
            ]
        )

        summary = summarize_execution_plan(plan)

        self.assertEqual(summary["by_type"], {"set_mix": 2})
        self.assertEqual(summary["batches"][0]["tracks"], ["1-Garage Kit", "2-Garage Kit"])

    def test_build_execution_plan_chunks_large_mix_batches(self) -> None:
        from ableton_bridge.recommender import build_execution_plan

        actions = [
            {"type": "set_mix", "track": "3-Operator", "field": "volume", "value": 0.5}
            for _index in range(17)
        ]

        plan = build_execution_plan(actions)

        self.assertEqual(plan["batch_count"], 3)
        self.assertEqual([batch["count"] for batch in plan["batches"]], [8, 8, 1])

    def test_loads_saved_recommendation_shape(self) -> None:
        from ableton_bridge.recommender import _load_recommendation

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "recommendation.json"
            path.write_text(json.dumps({"ok": True, "result": {"actions": []}}), encoding="utf-8")

            result = _load_recommendation(str(path))

        self.assertEqual(result, {"actions": []})


class MixerControlClientTest(unittest.TestCase):
    def test_formats_value_display_modes(self) -> None:
        from ableton_bridge.value_display import format_value_display

        payload = {
            "before": {"value": 0.04, "display_value": "-65.0 dB"},
            "after": {"value": 0.18, "display_value": "-42.9 dB"},
        }

        ui_result = format_value_display(payload, "ui")
        self.assertEqual(ui_result["before"]["value"], "-65.0 dB")
        self.assertEqual(ui_result["before"]["internal_value"], 0.04)
        self.assertNotIn("display_value", ui_result["before"])

        internal_result = format_value_display(payload, "internal")
        self.assertEqual(internal_result["after"]["value"], 0.18)
        self.assertNotIn("display_value", internal_result["after"])

        both_result = format_value_display(payload, "both")
        self.assertEqual(both_result["after"]["value"], 0.18)
        self.assertEqual(both_result["after"]["ui_value"], "-42.9 dB")

    def test_set_mix_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.mixer_control import set_mix
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/set_mix" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                if payload["changes"] != [
                    {"track": "Bass", "field": "volume", "value": 0.8},
                    {"track": "Bass", "field": "send", "send": "A", "value": 0.25},
                ]:
                    raise AssertionError(payload)
                reply_payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "applied": False,
                    "change_count": 2,
                    "results": [
                        {"track_name": "Bass", "field": "volume", "requested_value": 0.8},
                        {"track_name": "Bass", "field": "send", "send": "A", "requested_value": 0.25},
                    ],
                })
                FakeSocket.reply = encode_message("/set_mix", [args[0], reply_payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        changes = [
            {"track": "Bass", "field": "volume", "value": 0.8},
            {"track": "Bass", "field": "send", "send": "A", "value": 0.25},
        ]
        with patch("ableton_bridge.mixer_control.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = set_mix(changes, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertFalse(result["applied"])
        self.assertEqual(result["change_count"], 2)
        self.assertEqual(result["value_display"], "ui")

    def test_set_mix_can_return_ui_values(self) -> None:
        from ableton_bridge.mixer_control import set_mix
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/set_mix":
                    raise AssertionError((path, args))
                reply_payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "applied": False,
                    "change_count": 1,
                    "results": [
                        {
                            "track_name": "5-Sax Lead",
                            "field": "send",
                            "send": "A",
                            "before": {"value": 0, "display_value": "-inf dB"},
                            "after": {"value": 0.04, "display_value": "-65.0 dB"},
                        }
                    ],
                })
                FakeSocket.reply = encode_message("/set_mix", [args[0], reply_payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.mixer_control.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = set_mix(
                [{"track": "5-Sax Lead", "field": "send", "send": "A", "value": 0.04}],
                value_display="ui",
                timeout=1.0,
            )

        self.assertEqual(result["value_display"], "ui")
        self.assertEqual(result["results"][0]["after"]["value"], "-65.0 dB")
        self.assertEqual(result["results"][0]["after"]["internal_value"], 0.04)

    def test_parse_mix_change_supports_send_and_booleans(self) -> None:
        from ableton_bridge.mixer_control import parse_change

        self.assertEqual(parse_change("Bass|volume|0.8"), {"track": "Bass", "field": "volume", "value": 0.8})
        self.assertEqual(parse_change("Bass|send|A|0.25"), {"track": "Bass", "field": "send", "send": "A", "value": 0.25})
        self.assertEqual(parse_change("Bass|mute|on"), {"track": "Bass", "field": "mute", "value": 1})


class ParameterControlClientTest(unittest.TestCase):
    def test_set_parameter_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.parameter_control import set_parameter

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/set_parameter" or args[1:] != ["DrBuss Amount", 12.0, "dry_run"]:
                    raise AssertionError((path, args))
                payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "applied": False,
                    "track_name": "1-Garage Kit",
                    "device_name": "Garage Kit",
                    "parameter": {"index": 1, "name": "DrBuss Amount", "min": 0, "max": 127},
                    "before": {"value": 0, "display_value": "0.0 %"},
                    "requested_value": 12,
                    "after": {"value": 0, "display_value": "0.0 %"},
                })
                FakeSocket.reply = encode_message("/set_parameter", [args[0], payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.parameter_control.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = set_parameter("DrBuss Amount", 12, timeout=1.0)

        self.assertEqual(result["track_name"], "1-Garage Kit")
        self.assertEqual(result["parameter"]["name"], "DrBuss Amount")
        self.assertEqual(result["before"]["value"], "0.0 %")
        self.assertEqual(result["before"]["internal_value"], 0)
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["applied"])

    def test_set_parameter_commit_sends_commit_mode(self) -> None:
        from ableton_bridge.osc import decode_message, encode_message
        from ableton_bridge.parameter_control import set_parameter

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/set_parameter" or args[1:] != ["1", 8.0, "commit"]:
                    raise AssertionError((path, args))
                payload = json.dumps({
                    "ok": True,
                    "dry_run": False,
                    "applied": True,
                    "parameter": {"index": 1, "name": "DrBuss Amount"},
                })
                FakeSocket.reply = encode_message("/set_parameter", [args[0], payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.parameter_control.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = set_parameter(1, 8, commit=True, timeout=1.0)

        self.assertTrue(result["applied"])


class MultiParameterControlClientTest(unittest.TestCase):
    def test_set_parameters_dry_run_correlates_reply(self) -> None:
        from ableton_bridge.multi_parameter_control import set_parameters
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/set_parameters" or args[2] != "dry_run":
                    raise AssertionError((path, args))
                payload = json.loads(args[1])
                self_changes = payload["changes"]
                if self_changes != [
                    {"track": "1-Garage Kit", "parameter": "DrBuss Amount", "value": 12},
                    {"track": "2-Garage Kit", "parameter": "DrBuss Amount", "value": 12},
                ]:
                    raise AssertionError(self_changes)
                reply_payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "applied": False,
                    "change_count": 2,
                    "results": [
                        {"track_name": "1-Garage Kit", "parameter": {"name": "DrBuss Amount"}},
                        {"track_name": "2-Garage Kit", "parameter": {"name": "DrBuss Amount"}},
                    ],
                })
                FakeSocket.reply = encode_message("/set_parameters", [args[0], reply_payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        changes = [
            {"track": "1-Garage Kit", "parameter": "DrBuss Amount", "value": 12},
            {"track": "2-Garage Kit", "parameter": "DrBuss Amount", "value": 12},
        ]
        with patch("ableton_bridge.multi_parameter_control.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = set_parameters(changes, timeout=1.0)

        self.assertTrue(result["dry_run"])
        self.assertFalse(result["applied"])
        self.assertEqual(result["change_count"], 2)

    def test_set_parameters_can_return_internal_values_only(self) -> None:
        from ableton_bridge.multi_parameter_control import set_parameters
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                if path != "/set_parameters":
                    raise AssertionError((path, args))
                reply_payload = json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "applied": False,
                    "change_count": 1,
                    "results": [
                        {
                            "track_name": "5-Sax Lead",
                            "device_name": "Reverb",
                            "parameter": {"name": "Dry/Wet"},
                            "before": {"value": 0, "display_value": "0.0 %"},
                            "after": {"value": 0.08, "display_value": "8.0 %"},
                        }
                    ],
                })
                FakeSocket.reply = encode_message("/set_parameters", [args[0], reply_payload])

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch("ableton_bridge.multi_parameter_control.socket.socket", side_effect=lambda *_args: FakeSocket()):
            result = set_parameters(
                [{"track": "5-Sax Lead", "device": "Reverb", "parameter": "Dry/Wet", "value": 0.08}],
                value_display="internal",
                timeout=1.0,
            )

        self.assertEqual(result["value_display"], "internal")
        self.assertEqual(result["results"][0]["after"]["value"], 0.08)
        self.assertNotIn("display_value", result["results"][0]["after"])

    def test_parse_change_supports_track_parameter_value(self) -> None:
        from ableton_bridge.multi_parameter_control import parse_change

        self.assertEqual(
            parse_change("1-Garage Kit|DrBuss Amount|12"),
            {"track": "1-Garage Kit", "parameter": "DrBuss Amount", "value": 12.0},
        )

    def test_parse_change_supports_track_device_parameter_value(self) -> None:
        from ableton_bridge.multi_parameter_control import parse_change

        self.assertEqual(
            parse_change("1-Garage Kit|Garage Kit|DrBuss Amount|12"),
            {"track": "1-Garage Kit", "device": "Garage Kit", "parameter": "DrBuss Amount", "value": 12.0},
        )


class SpecialTrackClientPayloadTest(unittest.TestCase):
    def _run(self, patch_target, expected_path, expected_payload, call, *, mode="dry_run"):
        from ableton_bridge.osc import decode_message, encode_message

        class FakeSocket:
            reply = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def setsockopt(self, *_args):
                return None

            def bind(self, *_args):
                return None

            def settimeout(self, *_args):
                return None

            def sendto(self, packet, _address):
                path, args = decode_message(packet)
                payload = json.loads(args[1])
                if path != expected_path or args[2] != mode or payload != expected_payload:
                    raise AssertionError((path, args[2], payload))
                FakeSocket.reply = encode_message(
                    expected_path,
                    [args[0], json.dumps({"ok": True, "dry_run": mode != "commit", "applied": mode == "commit"})],
                )

            def recvfrom(self, _size):
                if FakeSocket.reply is None:
                    raise socket.timeout()
                return FakeSocket.reply, ("127.0.0.1", 7400)

        with patch(patch_target, side_effect=lambda *_args: FakeSocket()):
            return call()

    def test_scan_special_tracks_uses_lightweight_track_management_action(self) -> None:
        from ableton_bridge.track_management import track_management

        result = self._run(
            "ableton_bridge.track_management.socket.socket",
            "/track_management",
            {"action": "scan_special_tracks"},
            lambda: track_management("scan_special_tracks", timeout=1.0),
        )
        self.assertTrue(result["dry_run"])

    def test_delete_return_commit_sends_stable_identity_and_plan_token(self) -> None:
        from ableton_bridge.track_management import track_management

        result = self._run(
            "ableton_bridge.track_management.socket.socket",
            "/track_management",
            {
                "action": "delete_return_track",
                "track_id": 364,
                "expected_track_name": "E-Agent Validation",
                "plan_token": "delete123",
                "allow_nonempty": True,
            },
            lambda: track_management(
                "delete_return_track",
                track_id=364,
                expected_track_name="E-Agent Validation",
                plan_token="delete123",
                allow_nonempty=True,
                commit=True,
                timeout=1.0,
            ),
            mode="commit",
        )
        self.assertTrue(result["applied"])

    def test_return_effect_commit_sends_stable_identity(self) -> None:
        from ableton_bridge.inserter import insert_effect

        result = self._run(
            "ableton_bridge.inserter.socket.socket",
            "/insert_effect",
            {"track": "selected", "effect": "reverb", "allow_duplicate": False, "section": "return", "track_id": 501},
            lambda: insert_effect("reverb", section="return", track_id=501, commit=True, timeout=1.0),
            mode="commit",
        )
        self.assertTrue(result["applied"])

    def test_return_mixer_commit_keeps_stable_identity(self) -> None:
        from ableton_bridge.mixer_control import set_mix

        result = self._run(
            "ableton_bridge.mixer_control.socket.socket",
            "/set_mix",
            {"changes": [{"section": "return", "track_id": 501, "track": 0, "field": "volume", "value": 0.8}]},
            lambda: set_mix(
                [{"section": "return", "track_id": 501, "track": 0, "field": "volume", "value": 0.8}],
                commit=True,
                timeout=1.0,
            ),
            mode="commit",
        )
        self.assertTrue(result["applied"])

    def test_main_parameter_commit_keeps_stable_identity(self) -> None:
        from ableton_bridge.multi_parameter_control import set_parameters

        result = self._run(
            "ableton_bridge.multi_parameter_control.socket.socket",
            "/set_parameters",
            {"changes": [{"section": "main", "track_id": 601, "track": "main", "device": "Limiter", "parameter": "Gain", "value": 0.5}]},
            lambda: set_parameters(
                [{"section": "main", "track_id": 601, "track": "main", "device": "Limiter", "parameter": "Gain", "value": 0.5}],
                commit=True,
                timeout=1.0,
            ),
            mode="commit",
        )
        self.assertTrue(result["applied"])

    def test_return_meter_read_uses_explicit_stable_identity(self) -> None:
        from ableton_bridge.meter_monitor import meter_monitor

        result = self._run(
            "ableton_bridge.meter_monitor.socket.socket",
            "/meter_monitor",
            {"action": "read_meters", "section": "return", "track_id": 501},
            lambda: meter_monitor("read_meters", section="return", track_id=501, timeout=1.0),
        )
        self.assertTrue(result["dry_run"])


class DevicePackageTest(unittest.TestCase):









    def test_builds_hub_amxd_with_common_agent_modules(self) -> None:
        sys.path.insert(0, str(ROOT / "ableton_agent"))
        from build_hub_device import extract_patch_json
        from build_hub_device import build_hub_amxd

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "Ableton Agent Hub.amxd"
            build_hub_amxd(output)
            patch = extract_patch_json(output)
            copied_read_core = (Path(temp_dir) / "ableton_agent_read_core.js").exists()

        self.assertEqual(output.name, "Ableton Agent Hub.amxd")
        texts = {
            box["box"].get("text", "")
            for box in patch["patcher"]["boxes"]
        }
        self.assertIn("udpreceive 7400 @defer 1", texts)
        self.assertIn(
            "route ping /ping snapshot /snapshot parameter_summary /parameter_summary set_mix /set_mix insert_device /insert_device insert_devices /insert_devices insert_effect /insert_effect insert_effects /insert_effects create_midi_track /create_midi_track load_sample /load_sample set_parameters /set_parameters write_clip /write_clip write_arrangement_clip /write_arrangement_clip transpose_detail_note /transpose_detail_note clip_note_tools /clip_note_tools clip_variation /clip_variation arrangement_tools /arrangement_tools track_management /track_management routing /routing scene /scene device_chain /device_chain macro_parameters /macro_parameters meter_monitor /meter_monitor sample_confirm /sample_confirm eq_tools /eq_tools tempo /tempo transport /transport locator /locator",
            texts,
        )
        self.assertIn("js ableton_agent_snapshot.js", texts)
        self.assertIn("js ableton_agent_parameter_summary.js", texts)
        self.assertTrue(copied_read_core)
        self.assertIn(
            "ableton_agent_read_core.js",
            {item["name"] for item in patch["patcher"]["dependency_cache"]},
        )
        parameter_source = (ROOT / "ableton_agent" / "max" / "ableton_agent_parameter_summary.js").read_text(encoding="utf-8")
        self.assertIn('include("ableton_agent_read_core.js")', parameter_source)
        self.assertIn("scanned < read.limit", parameter_source)
        self.assertIn("readDeviceParameterPageBounded", parameter_source)
        self.assertIn('safeGet(parameter, "automation_state", 0)', parameter_source)
        self.assertIn("automation_state_name", parameter_source)
        track_source = (ROOT / "ableton_agent" / "max" / "ableton_agent_track_management.js").read_text(encoding="utf-8")
        self.assertIn('include("ableton_agent_read_core.js")', track_source)
        self.assertIn("scanTracksBounded", track_source)
        self.assertIn("scanned < read.limit", track_source)
        self.assertIn("js ableton_agent_mixer_control.js", texts)
        self.assertIn("js ableton_agent_inserter.js", texts)
        self.assertIn("js ableton_agent_sample_loader.js", texts)
        self.assertIn("js ableton_agent_multi_parameter_control.js", texts)
        multi_parameter_source = (ROOT / "ableton_agent" / "max" / "ableton_agent_multi_parameter_control.js").read_text(encoding="utf-8")
        self.assertIn('parameter.get("automation_state")', multi_parameter_source)
        self.assertIn("automation_state_name", multi_parameter_source)
        self.assertIn("js ableton_agent_clip_writer.js", texts)
        self.assertIn("js ableton_agent_detail_clip_writer.js", texts)
        self.assertIn("js ableton_agent_clip_note_tools.js", texts)
        self.assertIn("js ableton_agent_clip_variation.js", texts)
        self.assertIn("js ableton_agent_arrangement_tools.js", texts)
        self.assertIn("js ableton_agent_track_management.js", texts)
        self.assertIn("js ableton_agent_routing.js", texts)
        self.assertIn("js ableton_agent_scene.js", texts)
        self.assertIn("js ableton_agent_device_chain.js", texts)
        self.assertIn("js ableton_agent_macro_parameters.js", texts)
        self.assertIn("js ableton_agent_meter_monitor.js", texts)
        self.assertIn("js ableton_agent_sample_confirm.js", texts)
        self.assertIn("js ableton_agent_eq_tools.js", texts)
        self.assertIn("js ableton_agent_tempo.js", texts)
        self.assertIn("js ableton_agent_transport.js", texts)
        self.assertIn("js ableton_agent_locator.js", texts)
        self.assertIn("prepend create_midi_track", texts)
        self.assertIn("prepend write_arrangement_clip", texts)
        self.assertIn("prepend clip_note_tools", texts)
        self.assertIn("prepend clip_variation", texts)
        self.assertIn("prepend arrangement_tools", texts)
        self.assertIn("prepend track_management", texts)
        self.assertIn("prepend routing", texts)
        self.assertIn("prepend scene", texts)
        self.assertIn("prepend device_chain", texts)
        self.assertIn("prepend macro_parameters", texts)
        self.assertIn("prepend meter_monitor", texts)
        self.assertIn("prepend sample_confirm", texts)
        self.assertIn("prepend eq_tools", texts)
        self.assertIn("prepend tempo", texts)
        self.assertIn("prepend transport", texts)
        self.assertIn("prepend locator", texts)
        self.assertIn("udpsend 127.0.0.1 7401", texts)
        self.assertNotIn("oscparse", texts)
        self.assertNotIn("oscformat ableton reply", texts)

    def test_transport_uses_absolute_position_and_current_playback(self) -> None:
        source = (ROOT / "ableton_agent" / "max" / "ableton_agent_transport.js").read_text()

        self.assertIn('song.set("current_song_time", Number(beat));', source)
        self.assertIn('song.call("start_playing");', source)
        self.assertIn('song.call("continue_playing");', source)
        self.assertNotIn('song.call("jump_by"', source)

    def test_clip_note_tools_scans_before_targeting_a_midi_clip(self) -> None:
        source = (ROOT / "ableton_agent" / "max" / "ableton_agent_clip_note_tools.js").read_text()

        self.assertIn('var allowed = ["scan_clips", "read_notes"', source)
        self.assertIn("function scanMidiClips(payload)", source)
        self.assertIn("function resolveTargetClip(payload)", source)
        self.assertIn("collectArrangementMidiClips(song, targetTrack, candidates, limit)", source)
        self.assertIn("collectSessionMidiClips(song, targetTrack, candidates, limit)", source)
        self.assertIn("Run scan_clips first, then pass candidate_index", source)
        self.assertIn("var detail = resolveTargetClip(payload);", source)

    def test_clip_variation_preserves_source_by_default(self) -> None:
        source = (ROOT / "ableton_agent" / "max" / "ableton_agent_clip_variation.js").read_text()

        self.assertIn('var allowed = ["scan_clips", "duplicate_clip", "make_fill", "thin_notes", "mute_notes_in_range"];', source)
        self.assertIn("Run scan_clips first, then pass candidate_index", source)
        self.assertIn("source_preserved: !Boolean(payload.replace)", source)
        self.assertIn("target_start === undefined ? candidate.start_time + candidate.length", source)

    def test_arrangement_tools_scans_and_edits_regions(self) -> None:
        source = (ROOT / "ableton_agent" / "max" / "ableton_agent_arrangement_tools.js").read_text()

        self.assertIn('var allowed = ["scan_region", "clear_region", "copy_region", "duplicate_region", "rename_region_clip"];', source)
        self.assertIn("function scanRegion(payload)", source)
        self.assertIn("function clearRegion(payload, dryRun)", source)
        self.assertIn("function copyRegion(payload, dryRun)", source)
        self.assertIn("function renameRegionClip(payload, dryRun)", source)
        self.assertIn("arrangement_clips", source)
        self.assertIn('track.call("delete_clip", "id " + clipInfo.clip_id);', source)
        self.assertIn('track.call("create_midi_clip", destinationStart, clipInfo.length);', source)
        self.assertIn("only MIDI Arrangement clips are copied safely", source)

    def test_track_management_supports_hierarchy_and_blocks_unsupported_group_writes(self) -> None:
        source = (ROOT / "ableton_agent" / "max" / "ableton_agent_track_management.js").read_text()

        self.assertIn('"scan_hierarchy"', source)
        self.assertIn('"set_group_properties"', source)
        self.assertIn('"plan_groups"', source)
        self.assertIn("function scanTracks(payload)", source)
        self.assertIn("function hierarchySnapshot(payload)", source)
        self.assertIn("function setGroupProperties(payload, dryRun)", source)
        self.assertIn("function structuralPlan(action, payload)", source)
        self.assertIn("parent_group_id", source)
        self.assertIn("plan_token", source)
        self.assertIn("blocked_by_live_api", source)
        self.assertIn('song.call("create_midi_track", index);', source)
        self.assertIn('song.call("create_audio_track", index);', source)
        self.assertIn('song.call("create_return_track");', source)
        self.assertNotIn('song.call("create_return_track", index);', source)
        self.assertIn('"scan_special_tracks"', source)
        self.assertIn("expected_return_ids", source)
        self.assertIn("exactly one new stable track_id", source)
        self.assertIn("hasReturnPrefix", source)
        self.assertIn('"delete_return_track"', source)
        self.assertIn('song.call("delete_return_track", index);', source)
        self.assertIn("deleteReturnPlanToken", source)
        self.assertIn("requires allow_nonempty=true", source)
        self.assertIn("Unexpected Return Track identity/order change after deletion", source)
        self.assertIn('track.set("name", newName);', source)
        self.assertIn('track.set("color", color);', source)
        self.assertIn('song.call("delete_track", target.track_index);', source)
        self.assertIn("Refusing to delete non-empty track", source)
        self.assertNotIn('song.call("create_group_track"', source)
        self.assertNotIn('song.call("move_track"', source)

    def test_routing_scans_before_setting_output_routing(self) -> None:
        source = (ROOT / "ableton_agent" / "max" / "ableton_agent_routing.js").read_text()

        self.assertIn('var allowed = ["scan_routing", "set_input_routing", "set_output_routing"];', source)
        self.assertIn("function scanRouting(payload)", source)
        self.assertIn("input_routing_type", source)
        self.assertIn("available_output_routing_types", source)
        self.assertIn("findRoutingRaw(list, value)", source)
        self.assertIn("looksLikeRawRoutingValue(requested, direction, field)", source)
        self.assertIn("routingSetValue(coercedType, direction, \"type\")", source)
        self.assertIn('safeSet(track, direction + "_routing_type", routingSetValue(coercedType, direction, "type"))', source)

    def test_scene_lists_and_edits_scenes(self) -> None:
        source = (ROOT / "ableton_agent" / "max" / "ableton_agent_scene.js").read_text()

        self.assertIn('var allowed = ["list", "create", "duplicate", "rename", "capture_midi", "fire"];', source)
        self.assertIn("function listScenes()", source)
        self.assertIn('song.call("create_scene", index);', source)
        self.assertIn('song.call("duplicate_scene", target.scene_index);', source)
        self.assertIn('song.call("capture_midi");', source)
        self.assertIn('scene.set("name", newName);', source)
        self.assertIn('scene.call("fire");', source)

    def test_device_chain_uses_safe_templates_and_insert_device(self) -> None:
        source = (ROOT / "ableton_agent" / "max" / "ableton_agent_device_chain.js").read_text()

        self.assertIn('var allowed = ["list_templates", "apply_template", "apply_parameter_preset"];', source)
        self.assertIn("lead_light_space", source)
        self.assertIn("utility_gain_stage", source)
        self.assertIn("CHAIN_PARAMETER_PRESETS", source)
        self.assertIn("function applyParameterPreset(payload, dryRun)", source)
        self.assertIn('track.api.call("insert_device", effect);', source)
        self.assertIn("skipped_existing_devices", source)

    def test_macro_parameters_scans_applies_and_morphs_snapshots(self) -> None:
        source = (ROOT / "ableton_agent" / "max" / "ableton_agent_macro_parameters.js").read_text()

        self.assertIn('var allowed = ["scan_snapshot", "apply_snapshot", "morph_snapshots"];', source)
        self.assertIn("function scanSnapshot(payload)", source)
        self.assertIn("function applySnapshot(payload, dryRun)", source)
        self.assertIn("function morphSnapshots(payload, dryRun)", source)
        self.assertIn("snapshot_name", source)
        self.assertIn("display_value", source)
        self.assertIn("Parameter snapshot scanned", source)

    def test_meter_monitor_reads_track_meters_without_polling(self) -> None:
        source = (ROOT / "ableton_agent" / "max" / "ableton_agent_meter_monitor.js").read_text()

        self.assertIn('var allowed = ["read_meters", "detect_silent", "detect_clipping", "balance_report"];', source)
        self.assertIn("output_meter_left", source)
        self.assertIn("output_meter_right", source)
        self.assertIn("clipping_risk_count", source)
        self.assertIn("balance_notes", source)
        self.assertIn("active_peak_spread", source)
        self.assertIn("payload.track_id", source)
        self.assertIn('section === "return"', source)
        self.assertIn("Return/Main meter reads require an explicit track_id", source)
        self.assertIn("no continuous polling was started", source)

    def test_special_track_writes_use_stable_ids_and_readback(self) -> None:
        inserter = (ROOT / "ableton_agent" / "max" / "ableton_agent_inserter.js").read_text()
        mixer = (ROOT / "ableton_agent" / "max" / "ableton_agent_mixer_control.js").read_text()
        parameters = (ROOT / "ableton_agent" / "max" / "ableton_agent_multi_parameter_control.js").read_text()

        self.assertIn("function requireStableSpecialTarget", inserter)
        self.assertIn("function commitEffectPlan", inserter)
        self.assertIn("created_device_id", inserter)
        self.assertIn("verified_inserted", inserter)
        self.assertNotIn("resolveEffectTrack(plans[index].track_index)", inserter)
        self.assertIn("Commit to Return/Main requires track_id", mixer)
        self.assertIn("track_id: resolved.track.id", mixer)
        self.assertIn("Commit to Return/Main requires track_id", parameters)
        self.assertIn("track_id: resolved.track.id", parameters)

    def test_sample_confirm_reads_simpler_and_reports_drum_rack_limits(self) -> None:
        source = (ROOT / "ableton_agent" / "max" / "ableton_agent_sample_confirm.js").read_text()

        self.assertIn('action !== "confirm_loaded_sample" && action !== "scan_loaded_samples"', source)
        self.assertIn("function scanLoadedSamples(payload)", source)
        self.assertIn("candidate_index", source)
        self.assertIn('safeGet(device.api, "sample", [])', source)
        self.assertIn('"file_path"', source)
        self.assertIn("drum_pads", source)
        self.assertIn("Drum Rack pad traversal is not exposed here", source)
        self.assertIn("basename_match", source)

    def test_eq_tools_lists_reads_and_applies_safe_eq_presets(self) -> None:
        source = (ROOT / "ableton_agent" / "max" / "ableton_agent_eq_tools.js").read_text()

        self.assertIn('var EQ_PRESETS = {', source)
        self.assertIn("lead_presence_soft", source)
        self.assertIn("chord_stab_cleanup", source)
        self.assertIn("function readEq(payload)", source)
        self.assertIn("function applyPreset(payload, dryRun)", source)
        self.assertIn("function setBand(payload, dryRun)", source)
        self.assertIn('var allowed = ["list_presets", "read_eq", "apply_preset", "set_band"];', source)
        self.assertIn('parameter.api.set("value", afterValue);', source)
        self.assertIn("skipped_count", source)













class SoundCatalogTest(unittest.TestCase):
    def test_scans_packs_plugins_and_searches_roles(self) -> None:
        from ableton_bridge.sound_catalog import scan_sound_catalog, search_catalog

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packs = root / "Factory Packs"
            lost = packs / "Lost and Found"
            plugins = root / "VST3"
            lost.mkdir(parents=True)
            plugins.mkdir()
            (lost / "Deep Bass.adg").write_bytes(b"preset")
            (lost / "Air Texture.wav").write_bytes(b"audio")
            (plugins / "Serum.vst3").write_bytes(b"plugin")

            catalog = scan_sound_catalog([packs, plugins], output_path=None, summary_path=None)

        self.assertEqual(catalog["summary"]["pack_count"], 1)
        self.assertEqual(catalog["summary"]["kind_counts"]["plugin"], 1)
        self.assertEqual(catalog["summary"]["kind_counts"]["ableton_preset"], 1)
        bass = search_catalog(catalog, role="bass", pack="Lost and Found")
        self.assertEqual(bass[0]["name"], "Deep Bass")
        self.assertFalse(bass[0]["auto_insert"])
        plugins_found = search_catalog(catalog, kind="plugin")
        self.assertEqual(plugins_found[0]["name"], "Serum")
        self.assertEqual(plugins_found[0]["agent_control"], "control_after_load")

    def test_summary_is_compact_and_lists_packs_and_plugins(self) -> None:
        from ableton_bridge.sound_catalog import render_summary

        summary = render_summary({
            "generated_at": "2026-07-21T00:00:00",
            "summary": {"pack_count": 1, "resource_count": 2, "kind_counts": {"plugin": 1}, "role_counts": {}},
            "packs": [{"name": "Lost and Found", "resource_count": 1, "roles": ["pad"]}],
            "resources": [{"name": "Serum", "kind": "plugin", "load_mode": "manual_load", "agent_control": "control_after_load"}],
        })
        self.assertIn("Lost and Found", summary)
        self.assertIn("Serum", summary)
        self.assertIn("Discovery does not grant automatic insertion", summary)


class HttpProtocolTest(unittest.TestCase):
    def test_processes_json_command_body(self) -> None:
        from ableton_bridge.server import process_command_body

        class FakeClient:
            def request(self, command, payload):
                return {"command": command, "payload": payload}

        result = process_command_body(
            FakeClient(),
            b'{"command":"set_tempo","payload":{"tempo":132}}',
        )

        self.assertEqual(
            result,
            {"command": "set_tempo", "payload": {"tempo": 132}},
        )

    def test_rejects_body_without_command(self) -> None:
        from ableton_bridge.server import RequestValidationError, process_command_body

        with self.assertRaises(RequestValidationError):
            process_command_body(object(), b'{"payload":{}}')


if __name__ == "__main__":
    unittest.main()


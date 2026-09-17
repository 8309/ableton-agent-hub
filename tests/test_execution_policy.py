from __future__ import annotations

import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "ableton_agent" / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


class ExecutionPolicyTest(unittest.TestCase):
    def test_low_risk_auto_applies_and_legacy_false_inspects(self) -> None:
        from ableton_bridge.execution_policy import resolve_execution

        automatic = resolve_execution("set_mix")
        self.assertEqual(automatic.effective, "apply")
        self.assertEqual(automatic.wire_mode, "commit")
        legacy = resolve_execution("set_mix", commit=False)
        self.assertEqual(legacy.effective, "inspect")
        self.assertEqual(legacy.wire_mode, "dry_run")

    def test_auto_is_direct_independent_of_legacy_risk(self) -> None:
        from ableton_bridge.execution_policy import resolve_execution

        decision = resolve_execution("delete_empty_track")
        self.assertEqual(decision.risk, "high")
        self.assertEqual(decision.effective, "apply")
        self.assertFalse(decision.requires_inspection)

    def test_explicit_apply_and_inspect_override_auto(self) -> None:
        from ableton_bridge.execution_policy import resolve_execution

        self.assertEqual(resolve_execution("set_parameters", execution="inspect").wire_mode, "dry_run")
        self.assertEqual(resolve_execution("delete_empty_track", execution="apply").wire_mode, "commit")


class OperationJournalTest(unittest.TestCase):
    def test_journal_is_bounded_and_loads_latest_receipt(self) -> None:
        from ableton_bridge.operation_journal import append_receipt, load_receipt

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "journal.json"
            for index in range(5):
                append_receipt(
                    {"operation_id": f"op-{index}", "route": "/set_mix", "restore_changes": []},
                    path=path,
                    limit=3,
                )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual([item["operation_id"] for item in payload["receipts"]], ["op-2", "op-3", "op-4"])
            self.assertEqual(load_receipt("op-4", path=path)["route"], "/set_mix")


class _FakeSocket:
    reply = None
    expected_path = ""
    expected_mode = ""
    expected_payload = None
    reply_payload = None

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
        from ableton_bridge.osc import decode_message, encode_message

        path, arguments = decode_message(packet)
        if path != self.expected_path or arguments[2] != self.expected_mode:
            raise AssertionError((path, arguments))
        payload = json.loads(arguments[1])
        if self.expected_payload is not None and payload != self.expected_payload:
            raise AssertionError(payload)
        _FakeSocket.reply = encode_message(path, [arguments[0], json.dumps(self.reply_payload or {"ok": True})])

    def recvfrom(self, _size):
        if _FakeSocket.reply is None:
            raise socket.timeout()
        return _FakeSocket.reply, ("127.0.0.1", 7400)


class DirectApplyClientTest(unittest.TestCase):
    def setUp(self) -> None:
        _FakeSocket.reply = None

    def test_set_mix_defaults_to_one_apply_request(self) -> None:
        from ableton_bridge.mixer_control import set_mix

        _FakeSocket.expected_path = "/set_mix"
        _FakeSocket.expected_mode = "commit"
        _FakeSocket.expected_payload = {"changes": [{"track": 0, "field": "volume", "value": 0.8}]}
        _FakeSocket.reply_payload = {"ok": True, "applied": True, "dry_run": False}
        with patch("ableton_bridge.mixer_control.socket.socket", side_effect=lambda *_args: _FakeSocket()):
            result = set_mix(_FakeSocket.expected_payload["changes"], timeout=1.0)
        self.assertTrue(result["applied"])
        self.assertEqual(result["execution"]["effective"], "apply")

    def test_explicit_inspect_preserves_old_wire_mode(self) -> None:
        from ableton_bridge.multi_parameter_control import set_parameters

        change = {"track": 0, "parameter": "Gain", "value": 0.5}
        _FakeSocket.expected_path = "/set_parameters"
        _FakeSocket.expected_mode = "dry_run"
        _FakeSocket.expected_payload = {"changes": [change]}
        _FakeSocket.reply_payload = {"ok": True, "applied": False, "dry_run": True}
        with patch("ableton_bridge.multi_parameter_control.socket.socket", side_effect=lambda *_args: _FakeSocket()):
            result = set_parameters([change], execution="inspect", timeout=1.0)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["execution"]["effective"], "inspect")

    def test_restore_uses_exact_values_and_expected_after_guard(self) -> None:
        from ableton_bridge.mixer_control import restore_mix
        from ableton_bridge.operation_journal import append_receipt

        restore_changes = [{
            "section": "track",
            "track_id": 101,
            "field": "volume",
            "value": 0.6,
            "expected_before": 0.8,
        }]
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "journal.json"
            append_receipt(
                {"operation_id": "op-restore", "route": "/set_mix", "restore_changes": restore_changes},
                path=journal,
            )
            _FakeSocket.expected_path = "/set_mix"
            _FakeSocket.expected_mode = "commit"
            _FakeSocket.expected_payload = {"changes": restore_changes}
            _FakeSocket.reply_payload = {"ok": True, "applied": True, "dry_run": False}
            with patch("ableton_bridge.mixer_control.socket.socket", side_effect=lambda *_args: _FakeSocket()):
                result = restore_mix("op-restore", journal_path=journal, timeout=1.0)
        self.assertTrue(result["applied"])


class GuardedHubStaticTest(unittest.TestCase):
    def test_mix_and_parameter_modules_include_guard_rollback_and_receipt(self) -> None:
        for name in ("ableton_agent_mixer_control.js", "ableton_agent_multi_parameter_control.js"):
            source = (ROOT / "ableton_agent" / "max" / name).read_text(encoding="utf-8")
            self.assertIn("expected_before", source)
            self.assertIn("undo_receipt", source)
            self.assertIn("rolled_back", source)
            self.assertIn("resolve_ms", source)
            self.assertIn('operation: dryRun ? "inspect" : "apply"', source)


if __name__ == "__main__":
    unittest.main()

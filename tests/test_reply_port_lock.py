from __future__ import annotations

import ast
import multiprocessing
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from ableton_bridge.reply_port_lock import ReplyPortBusyError, reply_port_lock


def hold_port(port, ready, release):
    with reply_port_lock(port, timeout=3):
        ready.set()
        release.wait(10)


def wait_for_port(port, attempting, acquired):
    attempting.set()
    with reply_port_lock(port, timeout=3):
        acquired.set()


class ReplyPortLockTests(unittest.TestCase):
    def test_waiting_process_acquires_only_after_owner_releases(self):
        ctx = multiprocessing.get_context("spawn")
        attempting, acquired = ctx.Event(), ctx.Event()
        process = ctx.Process(target=wait_for_port, args=(57405, attempting, acquired))
        try:
            with reply_port_lock(57405, timeout=1):
                process.start()
                self.assertTrue(attempting.wait(5))
                self.assertFalse(acquired.wait(0.1))
            self.assertTrue(acquired.wait(3))
            process.join(3)
            self.assertEqual(process.exitcode, 0)
        finally:
            if process.is_alive():
                process.terminate()
            process.join(3)

    def test_process_contention_timeout_and_crash_release(self):
        ctx = multiprocessing.get_context("spawn")
        ready, release = ctx.Event(), ctx.Event()
        process = ctx.Process(target=hold_port, args=(57401, ready, release))
        process.start()
        try:
            self.assertTrue(ready.wait(5))
            with self.assertRaises(ReplyPortBusyError) as caught:
                with reply_port_lock(57401, timeout=0.05):
                    self.fail("second process acquired an owned port")
            self.assertFalse(caught.exception.to_dict()["details"]["request_sent"])
            with reply_port_lock(57402, timeout=0.1):
                pass
            process.terminate()
            process.join(5)
            self.assertFalse(process.is_alive())
            with reply_port_lock(57401, timeout=1):
                pass
        finally:
            if process.is_alive():
                process.terminate()
            process.join(5)

    def test_cli_does_not_open_socket_while_other_thread_owns_port(self):
        from ableton_bridge.ping import ping
        ready, release = threading.Event(), threading.Event()
        thread = threading.Thread(target=hold_port, args=(57403, ready, release))
        thread.start()
        try:
            self.assertTrue(ready.wait(2))
            with patch("ableton_bridge.ping.socket.socket") as socket_factory:
                with self.assertRaises(ReplyPortBusyError):
                    ping(reply_port=57403, timeout=0.05)
                socket_factory.assert_not_called()
        finally:
            release.set()
            thread.join(2)

    def test_exception_releases_lock(self):
        with self.assertRaisesRegex(RuntimeError, "probe"):
            with reply_port_lock(57404, timeout=0.1):
                raise RuntimeError("probe")
        with reply_port_lock(57404, timeout=0.1):
            pass

    def test_every_reply_socket_is_guarded_before_open(self):
        root = Path(__file__).resolve().parents[1] / "ableton_agent/python/ableton_bridge"
        count = 0
        for path in root.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.With) and any(
                    isinstance(item.optional_vars, ast.Name) and item.optional_vars.id == "reply_socket"
                    for item in node.items
                ):
                    count += 1
                    first = node.items[0].context_expr
                    self.assertIsInstance(first, ast.Call, str(path))
                    self.assertIsInstance(first.func, ast.Name, str(path))
                    self.assertEqual(first.func.id, "reply_port_lock", str(path))
        self.assertGreater(count, 25)


if __name__ == "__main__":
    unittest.main()

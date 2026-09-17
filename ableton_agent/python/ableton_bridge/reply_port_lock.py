"""Cooperative, cross-process ownership of a local Hub reply port."""
from __future__ import annotations

import errno
import math
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class ReplyPortBusyError(TimeoutError):
    def __init__(self, port: int, elapsed_ms: float) -> None:
        super().__init__(f"UDP reply port {port} is busy; no request was sent")
        self.port = port
        self.elapsed_ms = elapsed_ms

    def to_dict(self) -> dict:
        return {
            "ok": False,
            "error": str(self),
            "error_code": "reply_port_busy",
            "error_layer": "udp_client",
            "stage": "reply_port_lock",
            "details": {"reply_port": self.port, "queue_wait_ms": self.elapsed_ms,
                        "request_sent": False},
        }


_registry_guard = threading.Lock()
_thread_locks: dict[int, threading.Lock] = {}


@contextmanager
def reply_port_lock(port: int, *, timeout: float):
    """Hold through socket close. Queue deadline is separate from reply timeout.

    The persistent lock file must never be deleted: unlinking it could give two
    processes different lock objects for the same port. OS locks survive neither
    descriptor close nor process termination, so there is no stale owner to clear.
    """
    port = int(port)
    if not 1 <= port <= 65535 or not math.isfinite(timeout) or timeout < 0:
        raise ValueError("reply port must be 1..65535 and timeout finite and nonnegative")
    started = time.monotonic()
    with _registry_guard:
        local_lock = _thread_locks.setdefault(port, threading.Lock())
    if not local_lock.acquire(timeout=timeout):
        raise ReplyPortBusyError(port, (time.monotonic() - started) * 1000)
    try:
        directory = Path(tempfile.gettempdir()) / "ableton-agent-reply-locks"
        directory.mkdir(exist_ok=True)
        with (directory / f"udp-{port}.lock").open("a+b") as handle:
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"0")
                handle.flush()
            while True:
                handle.seek(0)
                try:
                    if os.name == "nt":
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as error:
                    if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        raise ReplyPortBusyError(port, (time.monotonic() - started) * 1000) from error
                    time.sleep(min(0.01, remaining))
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        local_lock.release()

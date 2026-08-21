from __future__ import annotations

import copy
import threading
import time
from collections import deque
from typing import Any


REQUEST_JOURNAL_LIMIT = 64
_REQUEST_JOURNAL: deque[dict[str, Any]] = deque(maxlen=REQUEST_JOURNAL_LIMIT)
_JOURNAL_LOCK = threading.Lock()


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    read = payload.get("read") if isinstance(payload.get("read"), dict) else {}
    target_keys = (
        "section",
        "track_id",
        "track_name",
        "track_index",
        "device_id",
        "device_name",
        "device_index",
    )
    return {
        "action": payload.get("action"),
        "target": {key: payload[key] for key in target_keys if key in payload},
        "read": {
            key: read.get(key)
            for key in ("cursor", "limit", "projection", "budget_ms", "expected_collection_token")
            if key in read
        },
    }


def begin_request(request_id: str, route: str, payload: dict[str, Any]) -> None:
    with _JOURNAL_LOCK:
        for entry in reversed(_REQUEST_JOURNAL):
            if entry["request_id"] != request_id:
                continue
            entry["status"] = "active"
            entry["stage"] = "request_created"
            entry["page_requests"] = int(entry.get("page_requests", 1)) + 1
            entry["payload"] = summarize_payload(payload)
            entry["last_checkpoint"] = {"stage": "request_created", "layer": "python"}
            return
    entry = {
        "request_id": request_id,
        "route": route,
        "status": "active",
        "stage": "request_created",
        "created_monotonic": time.monotonic(),
        "elapsed_ms": 0.0,
        "payload": summarize_payload(payload),
        "last_checkpoint": {"stage": "request_created", "layer": "python"},
        "page_requests": 1,
    }
    with _JOURNAL_LOCK:
        _REQUEST_JOURNAL.append(entry)


def checkpoint_request(
    request_id: str,
    stage: str,
    *,
    status: str | None = None,
    layer: str = "python",
    details: dict[str, Any] | None = None,
) -> None:
    with _JOURNAL_LOCK:
        for entry in reversed(_REQUEST_JOURNAL):
            if entry["request_id"] != request_id:
                continue
            entry["stage"] = stage
            entry["elapsed_ms"] = round(
                (time.monotonic() - float(entry["created_monotonic"])) * 1000, 3
            )
            if status is not None:
                entry["status"] = status
            checkpoint = {"stage": stage, "layer": layer}
            if details:
                checkpoint.update(copy.deepcopy(details))
            entry["last_checkpoint"] = checkpoint
            if layer == "hub":
                entry["last_hub_checkpoint"] = copy.deepcopy(checkpoint)
            return


def request_journal(*, limit: int = REQUEST_JOURNAL_LIMIT) -> list[dict[str, Any]]:
    if limit < 1:
        return []
    with _JOURNAL_LOCK:
        rows = list(_REQUEST_JOURNAL)[-min(limit, REQUEST_JOURNAL_LIMIT) :]
        return [
            {key: copy.deepcopy(value) for key, value in row.items() if key != "created_monotonic"}
            for row in rows
        ]


def request_journal_entry(request_id: str) -> dict[str, Any] | None:
    rows = request_journal()
    for row in reversed(rows):
        if row["request_id"] == request_id:
            return row
    return None


def clear_request_journal() -> None:
    with _JOURNAL_LOCK:
        _REQUEST_JOURNAL.clear()

"""Bounded, sequential, read-only probes over the existing parameter client."""
from __future__ import annotations

import math
import time
from typing import Any, Callable


def diagnose_parameters(*, ping: Callable, read: Callable, target: dict[str, Any],
                        connection: dict[str, Any], cursor: int = 0, limit: int = 4,
                        total_timeout: float = 30.0) -> dict[str, Any]:
    if type(limit) is not int or not 1 <= limit <= 4:
        raise ValueError("diagnostic limit must be 1..4")
    if type(cursor) is not int or not 0 <= cursor <= 512:
        raise ValueError("cursor must be 0..512")
    if not math.isfinite(total_timeout) or not 0 < total_timeout <= 120:
        raise ValueError("total_timeout must be finite and 0..120")
    for key in ("track_id", "device_id"):
        if type(target.get(key)) is not int or target[key] <= 0:
            raise ValueError(f"positive stable {key} required")
    if target.get("section", "track") not in {"track", "return", "main", "master"}:
        raise ValueError("unsupported section")
    started = time.monotonic()
    steps: list[dict[str, Any]] = []
    token = None
    stop_reason = None

    def call(label: str, function: Callable, **kwargs) -> dict[str, Any]:
        nonlocal stop_reason
        remaining = total_timeout - (time.monotonic() - started)
        if remaining <= 0 or len(steps) >= 16:
            stop_reason = "diagnostic_budget_exceeded"
            return {"ok": False, "error_code": stop_reason}
        before = time.monotonic()
        try:
            reply = function(**{**connection, "timeout": min(connection["timeout"], remaining)}, **kwargs)
        except Exception as error:
            converter = getattr(error, "to_dict", None)
            reply = converter() if callable(converter) else {
                "ok": False, "error_code": type(error).__name__, "error": str(error)}
        steps.append({"probe": label, "elapsed_ms": round((time.monotonic() - before) * 1000, 3),
                      "result": reply})
        return reply

    def page(label: str, fields: list[str], offset: int, count: int) -> dict[str, Any]:
        nonlocal token
        reply = call(label, read, **target, auto_collect=False, offset=offset, limit=count,
                     projection=fields, expected_collection_token=token, trace_level="field")
        meta = reply.get("read", {})
        if reply.get("ok", True) and meta.get("collection_token"):
            if token is not None and meta["collection_token"] != token:
                reply.update(ok=False, error_code="stale_collection")
            else:
                token = meta["collection_token"]
        return reply

    def clean(reply: dict[str, Any]) -> bool:
        return reply.get("ok", True) and not reply.get("read", {}).get("warnings") and not reply.get("warnings")

    initial = call("initial_ping", ping)
    failure = None
    if not clean(initial):
        failure = "initial_ping_failed"
    else:
        identity = None
        fields = ["identity"]
        for field in ("identity", "internal_value", "metadata", "display_value", "enum_values"):
            if field != "identity":
                fields.append(field)
            reply = page(field, fields[:], cursor, limit)
            if field == "identity":
                identity = reply
            if not clean(reply):
                failure = field
                # Only retry narrower reads after health confirmation, never after
                # stale collections or warnings which require a fresh inventory.
                health = call("recovery_ping", ping)
                code = str(reply.get("error_code", ""))
                if clean(health) and code not in {"stale_collection", "cursor_out_of_range", "target_not_found"} and reply.get("ok") is False:
                    for index in range(cursor, min(cursor + limit, 513)):
                        narrow = page(f"isolate_{field}_{index}", ["identity"] if field == "identity" else ["identity", field], index, 1)
                        if not clean(narrow):
                            break
                break
            # A clean budget partial is evidence of budget exhaustion, not timeout.
            if reply.get("read", {}).get("partial"):
                failure = "page_partial"
                break
        if failure is None and identity:
            meta = identity.get("read", {})
            next_cursor = meta.get("next_cursor")
            if meta.get("has_more"):
                if type(next_cursor) is not int or not cursor < next_cursor <= 512:
                    failure = "invalid_next_cursor"
                elif not token:
                    failure = "missing_collection_token"
                else:
                    continuation = page("next_identity_page", ["identity"], next_cursor, limit)
                    if not clean(continuation):
                        failure = "continuation_failed"
                    elif continuation.get("read", {}).get("partial"):
                        failure = "page_partial"
        final = call("final_ping", ping)
        if not clean(final):
            failure = failure or "final_ping_failed"
    return {"ok": failure is None and stop_reason is None, "read_only": True,
            "scope": "one_parameter_window_plus_one_identity_continuation",
            "target": target, "cursor": cursor, "limit": limit,
            "failure_probe": failure, "stop_reason": stop_reason,
            "collection_token": token, "steps": steps,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3)}

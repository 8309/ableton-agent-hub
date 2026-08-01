from __future__ import annotations

import copy
import json
import socket
import time
import uuid
from collections.abc import Callable
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message


class BoundedReadError(RuntimeError):
    pass


class BoundedReadTimeoutError(BoundedReadError):
    pass


class BoundedReadBusinessError(BoundedReadError):
    def __init__(self, message: str, *, response: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.response = response


def request_page(
    route: str,
    payload: dict[str, Any],
    *,
    mode: str = "dry_run",
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 5.0,
) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    normalized_route = route if route.startswith("/") else f"/{route}"
    packet = encode_message(
        normalized_route,
        [request_id, json.dumps(payload, ensure_ascii=False), mode],
    )
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reply_socket:
        reply_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reply_socket.bind((host, reply_port))
        reply_socket.settimeout(min(timeout, 0.2))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as command_socket:
            command_socket.sendto(packet, (host, command_port))

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                cursor = payload.get("read", {}).get("cursor", 0)
                target = {
                    key: payload[key]
                    for key in ("section", "track_id", "track_name", "track_index", "device_id", "device_name", "device_index")
                    if key in payload
                }
                raise BoundedReadTimeoutError(
                    f"No {normalized_route} reply on UDP {reply_port}; "
                    f"target={target or 'unspecified'} failed page cursor={cursor}"
                )
            reply_socket.settimeout(min(remaining, 0.2))
            try:
                reply_packet, address = reply_socket.recvfrom(65535)
            except socket.timeout:
                continue
            try:
                path, arguments = decode_message(reply_packet)
            except OscDecodeError:
                continue
            if path not in {normalized_route, normalized_route.lstrip("/")} or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def collect_pages(
    fetch_page: Callable[[dict[str, Any], float], dict[str, Any]],
    payload: dict[str, Any],
    *,
    item_key: str = "items",
    max_pages: int = 32,
    max_items: int = 512,
    total_timeout: float = 30.0,
    page_timeout: float = 5.0,
    on_page: Callable[[int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if max_pages < 1 or max_pages > 32:
        raise BoundedReadError("max_pages must be 1..32")
    if max_items < 1 or max_items > 512:
        raise BoundedReadError("max_items must be 1..512")
    if total_timeout <= 0 or page_timeout <= 0:
        raise BoundedReadError("timeouts must be greater than zero")

    request = copy.deepcopy(payload)
    read_request = request.setdefault("read", {})
    cursor = int(read_request.get("cursor", 0))
    expected_token = read_request.get("expected_collection_token")
    started = time.monotonic()
    pages: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    first: dict[str, Any] | None = None
    final_read: dict[str, Any] | None = None
    stop_reason: str | None = None

    for page_number in range(1, max_pages + 1):
        remaining = total_timeout - (time.monotonic() - started)
        if remaining <= 0:
            stop_reason = "total_timeout"
            break
        read_request["cursor"] = cursor
        read_request["expected_collection_token"] = expected_token
        result = fetch_page(request, min(page_timeout, remaining))
        if not result.get("ok"):
            raise BoundedReadBusinessError(
                str(result.get("error", "Hub returned ok:false")), response=result
            )
        read = result.get("read")
        if not isinstance(read, dict):
            raise BoundedReadError("Bounded page reply is missing read metadata")
        if int(read.get("cursor", -1)) != cursor:
            raise BoundedReadError(
                f"Page cursor mismatch: requested {cursor}, received {read.get('cursor')}"
            )
        token = str(read.get("collection_token", ""))
        if not token:
            raise BoundedReadError("Bounded page reply is missing collection_token")
        if expected_token is not None and token != expected_token:
            raise BoundedReadError(
                f"Collection token changed: expected {expected_token}, received {token}"
            )
        expected_token = token
        page_items = result.get(item_key, [])
        if not isinstance(page_items, list):
            raise BoundedReadError(f"Bounded page field {item_key!r} must be a list")
        if len(items) + len(page_items) > max_items:
            allowed = max_items - len(items)
            items.extend(page_items[:allowed])
            stop_reason = "max_items"
        else:
            items.extend(page_items)
        page_record = {
            "page": page_number,
            "cursor": cursor,
            "next_cursor": read.get("next_cursor"),
            "elapsed_ms": read.get("elapsed_ms"),
            "scanned_count": read.get("scanned_count"),
            "returned_count": read.get("returned_count"),
            "partial": bool(read.get("partial")),
            "warnings": list(read.get("warnings") or []),
        }
        pages.append(page_record)
        if first is None:
            first = result
        final_read = read
        if on_page is not None:
            on_page(page_number, result)
        if page_record["warnings"]:
            stop_reason = "warning"
        if stop_reason is not None:
            break
        if not read.get("has_more"):
            break
        next_cursor = int(read.get("next_cursor", cursor))
        if next_cursor <= cursor:
            raise BoundedReadError(
                f"Bounded page made no progress at cursor {cursor}"
            )
        cursor = next_cursor
    else:
        stop_reason = "max_pages"

    if first is None:
        raise BoundedReadError("No bounded pages were read")
    complete = (
        stop_reason is None
        and final_read is not None
        and not bool(final_read.get("has_more"))
        and not bool(final_read.get("partial"))
    )

    aggregate = {key: value for key, value in first.items() if key not in {item_key, "parameters", "read"}}
    aggregate.update(
        {
            "ok": True,
            "complete": complete,
            "partial": not complete,
            "stop_reason": stop_reason,
            "collection_token": expected_token,
            "page_count": len(pages),
            "returned_count": len(items),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "warnings": [warning for page in pages for warning in page["warnings"]],
            "pages": pages,
            item_key: items,
        }
    )
    return aggregate

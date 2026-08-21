from __future__ import annotations

import copy
import json
import socket
import time
import uuid
from collections.abc import Callable
from typing import Any

from .osc import OscDecodeError, decode_message, encode_message
from .runtime_diagnostics import (
    begin_request,
    checkpoint_request,
    request_journal_entry,
    summarize_payload,
)


class BoundedReadError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "bounded_read_failed",
        error_layer: str = "python",
        stage: str | None = None,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.error_layer = error_layer
        self.stage = stage
        self.request_id = request_id
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": str(self),
            "error_code": self.error_code,
            "error_layer": self.error_layer,
            "stage": self.stage,
            "request_id": self.request_id,
            "details": self.details,
        }


class BoundedReadTimeoutError(BoundedReadError):
    pass


class BoundedReadAutoCollectError(BoundedReadError):
    def __init__(self, message: str, *, page: int, cursor: int, cause: BoundedReadError) -> None:
        super().__init__(
            message,
            error_code="auto_collect_failed",
            error_layer="python_auto_collector",
            stage="auto_collect_failed",
            request_id=cause.request_id,
            details={"page": page, "cursor": cursor, "cause": cause.to_dict()},
        )
        self.cause = cause


class BoundedReadBusinessError(BoundedReadError):
    def __init__(self, message: str, *, response: dict[str, Any] | None = None) -> None:
        response = response or {}
        diagnostics = response.get("diagnostics") if isinstance(response.get("diagnostics"), dict) else {}
        super().__init__(
            message,
            error_code=str(response.get("error_code", "hub_route_failed")),
            error_layer=str(response.get("error_layer", "hub")),
            stage=diagnostics.get("stage"),
            request_id=response.get("request_id"),
            details={"response": response},
        )
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
    request_id: str | None = None,
    progress_route: str | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    request_id = request_id or str(payload.get("request_id") or uuid.uuid4().hex)
    normalized_route = route if route.startswith("/") else f"/{route}"
    request_payload = copy.deepcopy(payload)
    request_payload["request_id"] = request_id
    begin_request(request_id, normalized_route, request_payload)
    started = time.monotonic()
    normalized_progress_route = None
    if progress_route is not None:
        normalized_progress_route = progress_route if progress_route.startswith("/") else f"/{progress_route}"
    try:
        packet = encode_message(
            normalized_route,
            [request_id, json.dumps(request_payload, ensure_ascii=False), mode],
        )
    except (TypeError, ValueError) as error:
        checkpoint_request(request_id, "client_validation_failed", status="failed")
        raise BoundedReadError(
            f"Could not encode {normalized_route} request: {error}",
            error_code="client_validation_failed",
            stage="request_created",
            request_id=request_id,
            details={"payload": summarize_payload(request_payload)},
        ) from error
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reply_socket:
        reply_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reply_socket.bind((host, reply_port))
        reply_socket.settimeout(min(timeout, 0.2))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as command_socket:
            try:
                command_socket.sendto(packet, (host, command_port))
            except OSError as error:
                checkpoint_request(request_id, "udp_send_failed", status="failed", layer="udp_client")
                raise BoundedReadError(
                    f"Could not send {normalized_route} request to UDP {command_port}: {error}",
                    error_code="udp_send_failed",
                    error_layer="udp_client",
                    stage="udp_send_failed",
                    request_id=request_id,
                    details={"payload": summarize_payload(request_payload)},
                ) from error
        checkpoint_request(request_id, "udp_sent", layer="udp_client")

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                last_available = request_journal_entry(request_id)
                checkpoint_request(request_id, "udp_reply_timeout", status="timed_out", layer="udp_client")
                cursor = payload.get("read", {}).get("cursor", 0)
                target = {
                    key: payload[key]
                    for key in ("section", "track_id", "track_name", "track_index", "device_id", "device_name", "device_index")
                    if key in payload
                }
                raise BoundedReadTimeoutError(
                    f"No {normalized_route} reply on UDP {reply_port}; "
                    f"request_id={request_id} target={target or 'unspecified'} failed page cursor={cursor}; "
                    f"last_checkpoint={last_available.get('last_checkpoint') if last_available else None}",
                    error_code="udp_reply_timeout",
                    error_layer="udp_client",
                    stage="udp_sent",
                    request_id=request_id,
                    details={
                        "payload": summarize_payload(request_payload),
                        "last_checkpoint": last_available,
                    },
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
            is_progress = normalized_progress_route is not None and path in {
                normalized_progress_route,
                normalized_progress_route.lstrip("/"),
            }
            is_final = path in {normalized_route, normalized_route.lstrip("/")}
            if (not is_progress and not is_final) or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            try:
                result = json.loads(str(arguments[1]))
            except (TypeError, ValueError) as error:
                checkpoint_request(request_id, "client_reply_decode_failed", status="failed", layer="udp_client")
                raise BoundedReadError(
                    f"Could not decode correlated {normalized_route} reply: {error}",
                    error_code="udp_reply_invalid",
                    error_layer="udp_client",
                    stage="client_received",
                    request_id=request_id,
                ) from error
            if is_progress:
                if result.get("kind") != "progress":
                    continue
                checkpoint = result.get("checkpoint") if isinstance(result.get("checkpoint"), dict) else {}
                checkpoint_request(
                    request_id,
                    str(checkpoint.get("stage", "hub_progress")),
                    layer="hub",
                    details={"progress": result},
                )
                if on_progress is not None:
                    on_progress(result)
                continue
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            result["client_elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
            diagnostics = result.setdefault("diagnostics", {})
            if isinstance(diagnostics, dict):
                diagnostics["client_stage"] = "client_received"
                diagnostics["client_elapsed_ms"] = result["client_elapsed_ms"]
            checkpoint_request(
                request_id,
                "client_received",
                status="completed" if result.get("ok") else "failed",
                layer="udp_client",
                details={"hub_stage": diagnostics.get("stage") if isinstance(diagnostics, dict) else None},
            )
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
        raise BoundedReadError("max_pages must be 1..32", error_code="client_validation_failed", stage="request_created")
    if max_items < 1 or max_items > 512:
        raise BoundedReadError("max_items must be 1..512", error_code="client_validation_failed", stage="request_created")
    if total_timeout <= 0 or page_timeout <= 0:
        raise BoundedReadError("timeouts must be greater than zero", error_code="client_validation_failed", stage="request_created")

    request = copy.deepcopy(payload)
    request["request_id"] = str(request.get("request_id") or uuid.uuid4().hex)
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
        try:
            result = fetch_page(request, min(page_timeout, remaining))
        except BoundedReadError as error:
            raise BoundedReadAutoCollectError(
                f"Auto-collector failed on page {page_number} at cursor {cursor}: {error}",
                page=page_number,
                cursor=cursor,
                cause=error,
            ) from error
        if not result.get("ok"):
            raise BoundedReadBusinessError(
                str(result.get("error", "Hub returned ok:false")), response=result
            )
        read = result.get("read")
        if not isinstance(read, dict):
            raise BoundedReadError("Bounded page reply is missing read metadata")
        if int(read.get("cursor", -1)) != cursor:
            raise BoundedReadError(
                f"Page cursor mismatch: requested {cursor}, received {read.get('cursor')}",
                error_code="auto_collect_failed",
                error_layer="python_auto_collector",
                stage="page_validation",
            )
        token = str(read.get("collection_token", ""))
        if not token:
            raise BoundedReadError(
                "Bounded page reply is missing collection_token",
                error_code="auto_collect_failed",
                error_layer="python_auto_collector",
                stage="page_validation",
            )
        if expected_token is not None and token != expected_token:
            raise BoundedReadError(
                f"Collection token changed: expected {expected_token}, received {token}",
                error_code="stale_collection",
                error_layer="python_auto_collector",
                stage="collection_token_verified",
            )
        expected_token = token
        page_items = result.get(item_key, [])
        if not isinstance(page_items, list):
            raise BoundedReadError(
                f"Bounded page field {item_key!r} must be a list",
                error_code="auto_collect_failed",
                error_layer="python_auto_collector",
                stage="page_validation",
            )
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
            "request_id": result.get("request_id"),
            "hub_elapsed_ms": (result.get("diagnostics") or {}).get("hub_elapsed_ms"),
            "client_elapsed_ms": result.get("client_elapsed_ms"),
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
                f"Bounded page made no progress at cursor {cursor}",
                error_code="auto_collect_failed",
                error_layer="python_auto_collector",
                stage="page_validation",
            )
        cursor = next_cursor
    else:
        stop_reason = "max_pages"

    if first is None:
        raise BoundedReadError(
            "No bounded pages were read",
            error_code="auto_collect_failed",
            error_layer="python_auto_collector",
            stage="auto_collect_failed",
        )
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
            "request_id": request["request_id"],
            "complete": complete,
            "partial": not complete,
            "stop_reason": stop_reason,
            "collection_token": expected_token,
            "page_count": len(pages),
            "returned_count": len(items),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "auto_collector_elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "warnings": [warning for page in pages for warning in page["warnings"]],
            "pages": pages,
            item_key: items,
        }
    )
    return aggregate

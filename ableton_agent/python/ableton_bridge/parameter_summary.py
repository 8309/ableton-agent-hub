from __future__ import annotations

import argparse
import json
from typing import Any

from .bounded_read import BoundedReadError, BoundedReadTimeoutError, collect_pages, request_page


DEFAULT_BOUNDED_PARAMETER_LIMIT = 4


class ParameterSummaryError(RuntimeError):
    error_code = "client_validation_failed"
    error_layer = "python"
    stage = "request_created"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": str(self),
            "error_code": self.error_code,
            "error_layer": self.error_layer,
            "stage": self.stage,
        }


class ParameterSummaryTimeoutError(BoundedReadTimeoutError, ParameterSummaryError):
    pass


def read_parameter_summary(
    *,
    max_devices_per_track: int = 2,
    max_parameters_per_device: int = 16,
    include_display_values: bool = False,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 4.0,
) -> dict[str, Any]:
    if max_devices_per_track < 1 or max_devices_per_track > 8:
        raise ParameterSummaryError("max_devices_per_track must be 1..8")
    if max_parameters_per_device < 1 or max_parameters_per_device > 32:
        raise ParameterSummaryError("max_parameters_per_device must be 1..32")

    try:
        return request_page(
            "/parameter_summary",
            {
                "action": "summary",
                "max_devices_per_track": max_devices_per_track,
                "max_parameters_per_device": max_parameters_per_device,
                "include_display_values": include_display_values,
            },
            host=host,
            command_port=command_port,
            reply_port=reply_port,
            timeout=timeout,
        )
    except BoundedReadTimeoutError as error:
        raise ParameterSummaryTimeoutError(
            str(error),
            error_code=error.error_code,
            error_layer=error.error_layer,
            stage=error.stage,
            request_id=error.request_id,
            details=error.details,
        ) from error


def _inspection_payload(
    *,
    action: str = "list_parameters",
    section: str = "track",
    track_id: int | None = None,
    track_name: str | None = None,
    track_index: int | None = None,
    device_id: int | None = None,
    device_name: str | None = None,
    device_index: int | None = None,
    query: str | None = None,
    offset: int = 0,
    limit: int = DEFAULT_BOUNDED_PARAMETER_LIMIT,
    include_display_values: bool = False,
    include_enum_values: bool = False,
    projection: list[str] | None = None,
    budget_ms: int = 1000,
    expected_collection_token: str | None = None,
) -> dict[str, Any]:
    if action not in {"list_parameters", "search_parameters"}:
        raise ParameterSummaryError("action must be list_parameters or search_parameters")
    if section not in {"track", "return", "main", "master"}:
        raise ParameterSummaryError("section must be track, return, or main")
    if action == "search_parameters" and not (query or "").strip():
        raise ParameterSummaryError("search_parameters requires a non-empty query")
    if offset < 0 or offset > 512:
        raise ParameterSummaryError("offset must be 0..512")
    if limit < 1 or limit > 32:
        raise ParameterSummaryError("limit must be 1..32")
    if budget_ms < 1 or budget_ms > 5000:
        raise ParameterSummaryError("budget_ms must be 1..5000")
    if track_id is None and track_name is None and track_index is None and section not in {"main", "master"}:
        raise ParameterSummaryError("track_id, track_name, or track_index is required")

    if projection is None:
        projection = ["identity", "metadata", "internal_value"]
        if include_display_values:
            projection.append("display_value")
        if include_enum_values:
            projection.append("enum_values")
    allowed = {"identity", "metadata", "internal_value", "display_value", "enum_values"}
    if not projection or any(field not in allowed for field in projection):
        raise ParameterSummaryError("projection contains an unsupported parameter field")

    payload: dict[str, Any] = {
        "action": action,
        "section": "main" if section == "master" else section,
        # Compatibility aliases for older Hub builds and direct callers.
        "offset": offset,
        "limit": limit,
        "include_display_values": include_display_values,
        "include_enum_values": include_enum_values,
        "read": {
            "cursor": offset,
            "limit": limit,
            "projection": projection,
            "budget_ms": budget_ms,
            "expected_collection_token": expected_collection_token,
        },
    }
    for key, value in {
        "track_id": track_id,
        "track_name": track_name,
        "track_index": track_index,
        "device_id": device_id,
        "device_name": device_name,
        "device_index": device_index,
        "query": query,
    }.items():
        if value is not None:
            payload[key] = value

    return payload


def read_device_parameter_page(
    *,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 5.0,
    **inspection: Any,
) -> dict[str, Any]:
    payload = _inspection_payload(**inspection)
    return request_page(
        "/parameter_summary",
        payload,
        host=host,
        command_port=command_port,
        reply_port=reply_port,
        timeout=timeout,
    )


def inspect_device_parameters(
    *,
    auto_collect: bool = True,
    max_pages: int = 32,
    max_items: int = 512,
    total_timeout: float = 30.0,
    page_timeout: float | None = None,
    on_page: Any = None,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 5.0,
    **inspection: Any,
) -> dict[str, Any]:
    payload = _inspection_payload(**inspection)
    if not auto_collect:
        return request_page(
            "/parameter_summary",
            payload,
            host=host,
            command_port=command_port,
            reply_port=reply_port,
            timeout=timeout,
        )

    def fetch(page_payload: dict[str, Any], current_timeout: float) -> dict[str, Any]:
        return request_page(
            "/parameter_summary",
            page_payload,
            host=host,
            command_port=command_port,
            reply_port=reply_port,
            timeout=current_timeout,
        )

    result = collect_pages(
        fetch,
        payload,
        item_key="items",
        max_pages=max_pages,
        max_items=max_items,
        total_timeout=total_timeout,
        page_timeout=page_timeout or timeout,
        on_page=on_page,
    )
    result["parameters"] = result["items"]
    result["returned_parameter_count"] = len(result["items"])
    if result.get("action") == "search_parameters" and result.get("complete"):
        result["matched_parameter_count"] = len(result["items"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read lightweight all-track parameter summary")
    parser.add_argument("--action", choices=["summary", "list_parameters", "search_parameters"], default="summary")
    parser.add_argument("--max-devices-per-track", type=int, default=2)
    parser.add_argument("--max-parameters-per-device", type=int, default=16)
    parser.add_argument("--section", choices=["track", "return", "main", "master"], default="track")
    parser.add_argument("--track-id", type=int)
    parser.add_argument("--track-name")
    parser.add_argument("--track-index", type=int)
    parser.add_argument("--device-id", type=int)
    parser.add_argument("--device-name")
    parser.add_argument("--device-index", type=int)
    parser.add_argument("--query")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_BOUNDED_PARAMETER_LIMIT,
        help="Parameters inspected per bounded page (default: 4)",
    )
    parser.add_argument("--include-display-values", action="store_true")
    parser.add_argument("--include-enum-values", action="store_true")
    parser.add_argument("--projection", action="append", choices=["identity", "metadata", "internal_value", "display_value", "enum_values"])
    parser.add_argument("--budget-ms", type=int, default=1000)
    parser.add_argument("--single-page", action="store_true")
    parser.add_argument("--max-pages", type=int, default=32)
    parser.add_argument("--max-items", type=int, default=512)
    parser.add_argument("--total-timeout", type=float, default=30.0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=4.0)
    args = parser.parse_args()

    try:
        if args.action == "summary":
            result = read_parameter_summary(
                max_devices_per_track=args.max_devices_per_track,
                max_parameters_per_device=args.max_parameters_per_device,
                include_display_values=args.include_display_values,
                host=args.host,
                command_port=args.command_port,
                reply_port=args.reply_port,
                timeout=args.timeout,
            )
        else:
            result = inspect_device_parameters(
                action=args.action,
                section=args.section,
                track_id=args.track_id,
                track_name=args.track_name,
                track_index=args.track_index,
                device_id=args.device_id,
                device_name=args.device_name,
                device_index=args.device_index,
                query=args.query,
                offset=args.offset,
                limit=args.limit,
                include_display_values=args.include_display_values,
                include_enum_values=args.include_enum_values,
                projection=args.projection,
                budget_ms=args.budget_ms,
                auto_collect=not args.single_page,
                max_pages=args.max_pages,
                max_items=args.max_items,
                total_timeout=args.total_timeout,
                host=args.host,
                command_port=args.command_port,
                reply_port=args.reply_port,
                timeout=args.timeout,
            )
    except (ParameterSummaryError, BoundedReadError, json.JSONDecodeError) as error:
        payload = error.to_dict() if hasattr(error, "to_dict") else {"ok": False, "error": str(error)}
        print(json.dumps(payload, indent=2, ensure_ascii=False), flush=True)
        return 1
    print(json.dumps({"ok": bool(result.get("ok")), "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

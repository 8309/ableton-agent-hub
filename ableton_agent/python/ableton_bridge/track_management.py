from __future__ import annotations

import argparse
import json
import socket
import time
import uuid
from pathlib import Path
from typing import Any

from .bounded_read import BoundedReadError, collect_pages, request_page
from .osc import OscDecodeError, decode_message, encode_message
from .reply_port_lock import reply_port_lock


class TrackManagementError(RuntimeError):
    pass


class TrackManagementTimeoutError(TrackManagementError):
    pass


def track_management(
    action: str = "scan_tracks",
    *,
    commit: bool = False,
    bounded: bool = True,
    auto_collect: bool = True,
    cursor: int = 0,
    limit: int = 16,
    projection: list[str] | None = None,
    budget_ms: int = 1000,
    expected_collection_token: str | None = None,
    include_main: bool = True,
    max_pages: int = 32,
    max_items: int = 512,
    total_timeout: float = 30.0,
    page_timeout: float | None = None,
    on_page: Any = None,
    host: str = "127.0.0.1",
    command_port: int = 7400,
    reply_port: int = 7401,
    timeout: float = 3.0,
    **payload_fields: Any,
) -> dict[str, Any]:
    payload = {"action": action}
    payload.update({key: value for key, value in payload_fields.items() if value is not None})
    if action in {"scan_tracks", "scan_hierarchy"} and bounded:
        if commit:
            raise TrackManagementError("bounded track scans are read-only")
        if cursor < 0 or cursor > 512:
            raise TrackManagementError("cursor must be 0..512")
        if limit < 1 or limit > 64:
            raise TrackManagementError("limit must be 1..64")
        if budget_ms < 1 or budget_ms > 5000:
            raise TrackManagementError("budget_ms must be 1..5000")
        allowed = {"identity", "hierarchy", "color", "fold", "device_count"}
        selected_projection = projection or ["identity", "hierarchy"]
        if any(field not in allowed for field in selected_projection):
            raise TrackManagementError("projection contains an unsupported track field")
        payload["include_main"] = include_main
        payload["read"] = {
            "cursor": cursor,
            "limit": limit,
            "projection": selected_projection,
            "budget_ms": budget_ms,
            "expected_collection_token": expected_collection_token,
        }

        def fetch(page_payload: dict[str, Any], current_timeout: float) -> dict[str, Any]:
            return request_page(
                "/track_management",
                page_payload,
                host=host,
                command_port=command_port,
                reply_port=reply_port,
                timeout=current_timeout,
            )

        if not auto_collect:
            return fetch(payload, page_timeout or timeout)
        aggregate = collect_pages(
            fetch,
            payload,
            item_key="items",
            max_pages=max_pages,
            max_items=max_items,
            total_timeout=total_timeout,
            page_timeout=page_timeout or timeout,
            on_page=on_page,
        )
        return _aggregate_track_pages(action, aggregate)
    return _request_track_management(
        payload,
        commit=commit,
        host=host,
        command_port=command_port,
        reply_port=reply_port,
        timeout=timeout,
    )


def _aggregate_track_pages(action: str, aggregate: dict[str, Any]) -> dict[str, Any]:
    ordinary = [dict(item) for item in aggregate["items"] if item.get("section") == "track"]
    returns = [dict(item) for item in aggregate["items"] if item.get("section") == "return"]
    mains = [dict(item) for item in aggregate["items"] if item.get("section") == "main"]
    by_id = {int(item["track_id"]): item for item in ordinary if "track_id" in item}

    for item in ordinary:
        item.setdefault("parent_group_id", 0)
        item["parent_group_name"] = ""
        item["depth"] = 0
        item["group_path_ids"] = []
        item["group_path_names"] = []
        item["child_track_ids"] = []
    for item in ordinary:
        parent = by_id.get(int(item.get("parent_group_id") or 0))
        if parent is not None:
            item["parent_group_name"] = parent.get("track_name", "")
            parent["child_track_ids"].append(item["track_id"])
        cursor_item = item
        seen: set[int] = set()
        while int(cursor_item.get("parent_group_id") or 0) in by_id:
            parent_id = int(cursor_item["parent_group_id"])
            if parent_id in seen:
                break
            seen.add(parent_id)
            cursor_item = by_id[parent_id]
            item["group_path_ids"].insert(0, cursor_item["track_id"])
            item["group_path_names"].insert(0, cursor_item.get("track_name", ""))
            item["depth"] += 1

    def tree_node(item: dict[str, Any]) -> dict[str, Any]:
        children = [tree_node(by_id[child_id]) for child_id in item["child_track_ids"] if child_id in by_id]
        return {
            "track_id": item["track_id"],
            "track_name": item.get("track_name", ""),
            "is_group": item.get("track_type") == "group",
            "fold_state": item.get("fold_state"),
            "child_track_ids": list(item["child_track_ids"]),
            "children": children,
        }

    roots = [item for item in ordinary if int(item.get("parent_group_id") or 0) not in by_id]
    aggregate["ordinary_track_count"] = len(ordinary)
    aggregate["return_track_count"] = len(returns)
    aggregate["main_track_count"] = len(mains)
    aggregate["group_track_count"] = sum(item.get("track_type") == "group" for item in ordinary)
    aggregate["track_count"] = len(ordinary) + len(returns)
    aggregate["tracks"] = ordinary + returns
    aggregate["return_tracks"] = returns
    aggregate["main_track"] = mains[0] if mains else None
    if action == "scan_hierarchy":
        aggregate["root_track_ids"] = [item["track_id"] for item in roots]
        aggregate["hierarchy"] = [tree_node(item) for item in roots]
    return aggregate


def _request_track_management(
    payload: dict[str, Any],
    *,
    commit: bool,
    host: str,
    command_port: int,
    reply_port: int,
    timeout: float,
) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    mode = "commit" if commit else "dry_run"
    packet = encode_message("/track_management", [request_id, json.dumps(payload, ensure_ascii=False), mode])

    with reply_port_lock(reply_port, timeout=timeout), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reply_socket:
        reply_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reply_socket.bind((host, reply_port))
        reply_socket.settimeout(min(timeout, 0.2))

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as command_socket:
            command_socket.sendto(packet, (host, command_port))

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TrackManagementTimeoutError(
                    f"No track_management reply from Ableton Agent Hub on UDP {reply_port}; reload Ableton Agent Hub.amxd"
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
            if path not in ["/track_management", "track_management"] or len(arguments) < 2:
                continue
            if arguments[0] != request_id:
                continue
            result = json.loads(str(arguments[1]))
            result["request_id"] = request_id
            result["from"] = address[0]
            result["port"] = address[1]
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan or safely manage Ableton tracks and existing Group Tracks through the unified Hub")
    parser.add_argument(
        "--action",
        default="scan_tracks",
        choices=[
            "scan_tracks",
            "scan_hierarchy",
            "scan_special_tracks",
            "create_midi_track",
            "create_audio_track",
            "create_return_track",
            "delete_return_track",
            "rename_track",
            "color_track",
            "delete_empty_track",
            "set_group_properties",
            "create_group",
            "move_track_to_group",
            "move_track_out_of_group",
            "reorder_track",
            "plan_groups",
        ],
    )
    parser.add_argument("--track", help="Track name or zero-based track index for rename_track")
    parser.add_argument("--track-index", type=int, dest="track_index", help="Track index for rename or insert position")
    parser.add_argument("--track-id", type=int, help="Session-stable Live track id for hierarchy-sensitive actions")
    parser.add_argument("--group-track-id", type=int, help="Session-stable Live track id of an existing Group Track")
    parser.add_argument("--member-track-ids", type=int, nargs="+", help="Existing ordinary track ids to include in a group plan")
    parser.add_argument(
        "--groups-json",
        help="JSON array of group plans, or @path to a JSON file; each item needs name and member_track_ids",
    )
    parser.add_argument("--section", choices=["track", "return"], help="Track section for rename lookup")
    parser.add_argument("--name", help="New or created track name")
    parser.add_argument("--color", help="Track color as integer, #RRGGBB, or 0xRRGGBB")
    parser.add_argument("--fold-state", type=int, choices=[0, 1], help="Existing Group Track fold state: 0 expanded, 1 folded")
    parser.add_argument("--index", type=int, help="Insert index for create actions")
    parser.add_argument("--target-index", type=int, help="Projected ordinary-track index for a manual move/reorder plan")
    parser.add_argument("--plan-token", help="Token returned by the immediately preceding dry-run")
    parser.add_argument("--expected-return-ids", type=int, nargs="*", help="Return track ids returned by create_return_track dry-run")
    parser.add_argument("--expected-track-name", help="Expected current name for stable-id Return deletion")
    parser.add_argument("--allow-nonempty", action="store_true", help="Allow deletion of a reviewed Return containing devices")
    parser.add_argument("--select", action="store_true", help="Select the created track after commit")
    parser.add_argument("--include-returns", action="store_true", help="Include return tracks in scan_tracks")
    parser.add_argument("--no-returns", action="store_true", help="Exclude return tracks in scan_tracks")
    parser.add_argument("--no-main", action="store_true", help="Exclude Main from bounded track scans")
    parser.add_argument("--legacy-scan", action="store_true", help="Use the pre-bounded one-shot scan response")
    parser.add_argument("--single-page", action="store_true", help="Return one bounded scan page")
    parser.add_argument("--cursor", type=int, default=0)
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--projection", action="append", choices=["identity", "hierarchy", "color", "fold", "device_count"])
    parser.add_argument("--budget-ms", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=32)
    parser.add_argument("--max-items", type=int, default=512)
    parser.add_argument("--total-timeout", type=float, default=30.0)
    parser.add_argument("--commit", action="store_true", help="Actually change Live. Without this, only dry-runs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=7400)
    parser.add_argument("--reply-port", type=int, default=7401)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    include_returns: bool | None = None
    if args.include_returns:
        include_returns = True
    if args.no_returns:
        include_returns = False

    try:
        groups: list[dict[str, Any]] | None = None
        if args.groups_json:
            raw_groups = args.groups_json
            if raw_groups.startswith("@"):
                raw_groups = Path(raw_groups[1:]).read_text(encoding="utf-8")
            decoded_groups = json.loads(raw_groups)
            if not isinstance(decoded_groups, list):
                raise ValueError("--groups-json must decode to a JSON array")
            groups = decoded_groups

        result = track_management(
            args.action,
            commit=args.commit,
            bounded=not args.legacy_scan,
            auto_collect=not args.single_page,
            cursor=args.cursor,
            limit=args.limit,
            projection=args.projection,
            budget_ms=args.budget_ms,
            include_main=not args.no_main,
            max_pages=args.max_pages,
            max_items=args.max_items,
            total_timeout=args.total_timeout,
            host=args.host,
            command_port=args.command_port,
            reply_port=args.reply_port,
            timeout=args.timeout,
            track=int(args.track) if args.track and args.track.isdigit() else args.track,
            track_index=args.track_index,
            track_id=args.track_id,
            group_track_id=args.group_track_id,
            member_track_ids=args.member_track_ids,
            groups=groups,
            section=args.section,
            name=args.name,
            color=args.color,
            fold_state=args.fold_state,
            index=args.index,
            target_index=args.target_index,
            plan_token=args.plan_token,
            expected_return_ids=args.expected_return_ids,
            expected_track_name=args.expected_track_name,
            allow_nonempty=args.allow_nonempty if args.allow_nonempty else None,
            select=args.select if args.select else None,
            include_returns=include_returns,
        )
    except (TrackManagementError, BoundedReadError, json.JSONDecodeError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps({"ok": bool(result.get("ok")), "result": result}, indent=2, ensure_ascii=False), flush=True)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

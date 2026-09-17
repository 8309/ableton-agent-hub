from __future__ import annotations

import os
import copy
import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from .device_chain import device_chain
from .initial_read import initial_read
from .mixer_control import set_mix
from .multi_parameter_control import set_parameters
from .parameter_summary import inspect_device_parameters
from .ping import ping
from .track_management import track_management
from .bounded_read import request_page
from .locator import locator
from .meter_monitor import meter_monitor
from .tempo import tempo
from .ui_input import validate_value_input
from .transport import transport
from .inserter import _request_json_command, InserterTimeoutError


ToolCallable = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class McpConnectionSettings:
    host: str = "127.0.0.1"
    command_port: int = 7400
    reply_port: int = 7401
    timeout: float = 5.0

    @classmethod
    def from_environment(cls) -> "McpConnectionSettings":
        return cls(
            host=os.environ.get("ABLETON_AGENT_HOST", "127.0.0.1"),
            command_port=int(os.environ.get("ABLETON_AGENT_COMMAND_PORT", "7400")),
            reply_port=int(os.environ.get("ABLETON_AGENT_REPLY_PORT", "7401")),
            timeout=float(os.environ.get("ABLETON_AGENT_TIMEOUT", "5.0")),
        )


@dataclass(frozen=True)
class McpOperations:
    creative_request: ToolCallable = _request_json_command
    ping: ToolCallable = ping
    initial_read: ToolCallable = initial_read
    track_management: ToolCallable = track_management
    device_chain: ToolCallable = device_chain
    inspect_device_parameters: ToolCallable = inspect_device_parameters
    set_mix: ToolCallable = set_mix
    set_parameters: ToolCallable = set_parameters
    transport: ToolCallable = transport
    tempo: ToolCallable = tempo
    locator: ToolCallable = locator
    meter_monitor: ToolCallable = meter_monitor
    request_page: ToolCallable = request_page


class AbletonMcpService:
    """Small, serialized MCP-facing facade over the existing Hub clients."""

    def __init__(
        self,
        *,
        settings: McpConnectionSettings | None = None,
        operations: McpOperations | None = None,
    ) -> None:
        self.settings = settings or McpConnectionSettings.from_environment()
        self.operations = operations or McpOperations()
        self._hub_lock = threading.Lock()
        self._sequence_lock = threading.Lock()
        self._request_sequence = 0
        self._started = time.monotonic()
        self._track_cache: dict[str, Any] | None = None
        self._recent_operations: deque[dict[str, Any]] = deque(maxlen=32)
        from .module_health import mcp_build_id
        self._mcp_build_id = mcp_build_id()
        from .automation_inventory import AutomationInventory
        self._automation_inventory = AutomationInventory(self.operations, self._connection)

    def scan_automation(self, fields: dict[str, Any]) -> dict[str, Any]:
        return self._serialized("ableton_scan_automation", lambda: self._automation_inventory.scan(fields))

    def diagnose_parameters(self, *, track_id: int, device_id: int, section: str = "track",
                            cursor: int = 0, limit: int = 4, total_timeout: float = 30.0) -> dict[str, Any]:
        from .parameter_diagnostics import diagnose_parameters
        return self._serialized("ableton_diagnose_parameters", lambda: diagnose_parameters(
            ping=self.operations.ping, read=self.operations.inspect_device_parameters,
            target={"track_id": track_id, "device_id": device_id, "section": section},
            connection=self._connection(self.settings.timeout), cursor=cursor, limit=limit,
            total_timeout=total_timeout))

    def apply_batch(self, *, mix_changes: list[dict[str, Any]],
                    parameter_changes: list[dict[str, Any]], execution: str = "auto",
                    value_display: str = "ui") -> dict[str, Any]:
        if execution not in {"auto", "inspect", "apply"}:
            raise ValueError("execution must be auto, inspect or apply")
        if value_display not in {"ui", "both", "internal"}:
            raise ValueError("unsupported value_display")
        if not mix_changes and not parameter_changes:
            raise ValueError("at least one change is required")
        if len(mix_changes) > 32 or len(parameter_changes) > 16:
            raise ValueError("batch exceeds 32 mixer or 16 parameter changes")
        for changes, device in ((mix_changes, False), (parameter_changes, True)):
            if changes:
                self._validate_stable_changes(changes, require_device=device)

        def operation():
            self._track_cache = None
            completed = []
            for name, changes, function in (("mix", mix_changes, self.operations.set_mix),
                                            ("parameters", parameter_changes, self.operations.set_parameters)):
                if not changes:
                    continue
                started = time.monotonic()
                try:
                    result = function(changes, execution=execution, value_display=value_display,
                                      **self._connection(self.settings.timeout))
                except Exception as error:
                    result = self._operation_error(error, name)
                    result["applied"] = None if execution != "inspect" else False
                completed.append({"operation": name, "result": result,
                                  "elapsed_ms": round((time.monotonic() - started) * 1000, 3)})
                if not result.get("ok", False):
                    return {"ok": False, "atomic": False, "steps": completed,
                            "stopped_at": name, "remaining_not_sent": ["parameters"] if name == "mix" and parameter_changes else [],
                            "message": "Stopped without retry or rollback; preserve confirmed results and inspect unknown writes."}
            return {"ok": True, "atomic": False, "steps": completed, "remaining_not_sent": []}
        return self._serialized("ableton_apply_batch", operation)

    def status(self, *, timeout: float = 2.0, probe_modules: bool = False) -> dict[str, Any]:
        from .module_health import module_status
        return self._serialized(
            "ableton_status",
            lambda: {
                "ok": True,
                "hub": self.operations.ping(**self._connection(timeout)),
                "health": module_status(self.operations.creative_request,
                                        self._connection(min(timeout, 2.0)), probe=probe_modules),
                "mcp_build": self._mcp_build_id,
                "transport": {
                    "mcp": "stdio",
                    "hub": "osc_udp",
                    "command_port": self.settings.command_port,
                    "reply_port": self.settings.reply_port,
                },
                "serialization": "process_lock_and_cross_process_reply_port_lock",
                "service_uptime_ms": round((time.monotonic() - self._started) * 1000.0, 1),
                "recent_operations": list(self._recent_operations),
            },
        )

    def creative(self, tool: str, fields: dict[str, Any]) -> dict[str, Any]:
        from .mcp_creative import prepare_request

        def operation():
            route, payload, apply = prepare_request(tool, fields)
            if apply:
                self._track_cache = None
            try:
                result = self.operations.creative_request(
                    route, payload, commit=apply, **self._connection(self.settings.timeout))
            except InserterTimeoutError:
                return {"ok": False, "error_code": "creative_reply_timeout", "route": route,
                        "mutation_attempted": apply, "applied": None if apply else False,
                        "error": "No final Hub reply. Stop; do not retry an apply. Inspect target state after Hub recovery."}
            if result.get("mcp_protocol") != 1:
                return {"ok": False, "error_code": "creative_protocol_unavailable",
                        "error": "Loaded Hub does not confirm creative protocol v1. Stop; request manual reload. Do not retry writes.",
                        "mutation_attempted": apply, "request_id": result.get("request_id")}
            return result

        return self._serialized("ableton_" + tool, operation)

    def read_set(
        self,
        *,
        depth: str = "quick",
        detail: str = "summary",
        include_raw_notes: bool = False,
        note_tracks: list[str] | None = None,
        max_note_clips: int = 64,
        total_timeout: float = 30.0,
        als_path: str | None = None,
        saved_sections: list[str] | None = None,
        include_saved_device_parameters: bool = False,
        include_saved_midi_notes: bool = False,
    ) -> dict[str, Any]:
        if depth not in {"quick", "full"}:
            raise ValueError("depth must be quick or full")
        if detail not in {"summary", "context"}:
            raise ValueError("detail must be summary or context")
        if depth == "quick" and include_raw_notes:
            raise ValueError("include_raw_notes is only meaningful for a full read")

        def operation() -> dict[str, Any]:
            self._track_cache = None
            context = self.operations.initial_read(
                depth=depth,
                include_raw_notes=include_raw_notes,
                note_tracks=note_tracks or [],
                max_note_clips=max_note_clips,
                total_timeout=total_timeout,
                als_path=als_path,
                saved_sections=set(saved_sections) if saved_sections is not None else None,
                include_saved_device_parameters=include_saved_device_parameters,
                include_saved_midi_notes=include_saved_midi_notes,
                **self._connection(self.settings.timeout),
            )
            if detail == "context":
                return context
            return {
                "ok": context.get("status") == "complete",
                "read_only": True,
                "status": context.get("status"),
                "summary": context.get("summary", {}),
            }

        return self._serialized("ableton_read_set", operation)

    def find_target(
        self,
        *,
        target_type: str,
        query: str,
        section: str = "track",
        track_id: int | None = None,
        device_id: int | None = None,
        root_device_id: int | None = None,
        limit: int = 12,
        cursor: int = 0,
        collection_token: str | None = None,
        page_limit: int = 4,
        max_pages: int = 32,
        scan_mode: str = "children",
        max_depth: int = 4,
        max_devices: int = 64,
        budget_ms: int = 1000,
        match_offset: int = 0,
        refresh: bool = False,
    ) -> dict[str, Any]:
        target_type = target_type.strip().lower()
        query = query.strip()
        if target_type not in {"track", "device", "parameter"}:
            raise ValueError("target_type must be track, device, or parameter")
        if not query:
            raise ValueError("query cannot be empty")
        if section not in {"track", "return", "main", "master"}:
            raise ValueError("section must be track, return, or main")
        if limit < 1 or limit > 32:
            raise ValueError("limit must be 1..32")
        if target_type in {"device", "parameter"} and not track_id:
            raise ValueError(f"track_id is required for {target_type} lookup")
        if target_type == "parameter" and not device_id:
            raise ValueError("device_id is required for parameter lookup")
        for name, value, low, high in (
            ("cursor", cursor, 0, 65536 if target_type == "device" else 512),
            ("page_limit", page_limit, 1, 32), ("max_pages", max_pages, 1, 32),
            ("max_depth", max_depth, 0, 12), ("max_devices", max_devices, 1, 512),
            ("budget_ms", budget_ms, 1, 5000), ("match_offset", match_offset, 0, 512),
        ):
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer from {low} to {high}")
        if scan_mode not in {"children", "recursive"}:
            raise ValueError("scan_mode must be children or recursive")
        if target_type == "device" and scan_mode == "recursive" and (cursor or collection_token):
            raise ValueError("cursor/token require children scan mode")

        def operation() -> dict[str, Any]:
            if target_type == "track":
                result = self._cached_tracks(refresh=refresh)
                records = [
                    item
                    for item in result.get("items", result.get("tracks", []))
                    if section in {"main", "master"}
                    and item.get("section") == "main"
                    or section not in {"main", "master"}
                    and item.get("section") == section
                ]
                matches = self._rank_matches(records, query, "track_name", 512)
            elif target_type == "device":
                options = {"max_depth": max_depth, "max_devices": max_devices} if scan_mode == "recursive" else {
                    "cursor": cursor, "limit": page_limit, "expected_collection_token": collection_token}
                result = self.operations.device_chain(
                    "scan_recursive" if scan_mode == "recursive" else "scan_children",
                    commit=False,
                    section=section,
                    track_id=track_id,
                    root_device_id=root_device_id,
                    budget_ms=budget_ms,
                    **options,
                    **self._connection(self.settings.timeout),
                )
                records = self._flatten_device_records(result.get("tree", result))
                matches = self._rank_matches(records, query, "device_name", 512)
            else:
                result = self.operations.inspect_device_parameters(
                    action="search_parameters",
                    section=section,
                    track_id=track_id,
                    device_id=device_id,
                    query=query,
                    projection=["identity"],
                    offset=cursor,
                    expected_collection_token=collection_token,
                    budget_ms=budget_ms,
                    limit=page_limit,
                    max_pages=min(max_pages, 512 // page_limit),
                    max_items=512,
                    total_timeout=15.0,
                    page_timeout=self.settings.timeout,
                    **self._connection(self.settings.timeout),
                )
                matches = list(result.get("items", result.get("parameters", [])))
            source = self._lookup_source(result)
            token = source.get("collection_token")
            if collection_token and token and collection_token != token:
                raise ValueError("stale_collection: lookup collection changed")
            selected = matches[match_offset:match_offset + limit]
            next_match = match_offset + len(selected)
            match_more = next_match < len(matches)
            continuation = None
            if result.get("ok", True) and not source.get("warnings"):
                if match_more:
                    continuation = {"cursor": cursor, "collection_token": token, "match_offset": next_match}
                elif source.get("next_cursor") is not None and not source["source_complete"]:
                    continuation = {"cursor": source["next_cursor"], "collection_token": token, "match_offset": 0}
            response = {
                **source,
                "ok": bool(result.get("ok", True)),
                "read_only": True,
                "target_type": target_type,
                "query": query,
                "match_count": len(selected),
                "page_match_count": len(matches),
                "matches": selected,
                "matches_complete": not match_more,
                "continuation": continuation,
                "cache": result.get("cache", {"hit": False}),
                "search_scope": "direct_children" if target_type == "device" and scan_mode == "children" else scan_mode if target_type == "device" else target_type,
            }
            return response

        return self._serialized("ableton_find_target", operation)

    def read_parameters(
        self,
        *,
        track_id: int,
        device_id: int,
        section: str = "track",
        query: str | None = None,
        cursor: int = 0,
        limit: int = 4,
        projection: list[str] | None = None,
        collection_token: str | None = None,
        collect_all: bool = False,
        total_timeout: float = 15.0,
        trace_level: str = "none",
    ) -> dict[str, Any]:
        if track_id <= 0 or device_id <= 0:
            raise ValueError("track_id and device_id must be positive stable IDs")
        if section not in {"track", "return", "main", "master"}:
            raise ValueError("section must be track, return, or main")
        if cursor < 0 or cursor > 512:
            raise ValueError("cursor must be 0..512")
        if limit < 1 or limit > 32:
            raise ValueError("limit must be 1..32")
        selected_projection = projection or ["identity", "internal_value", "display_value"]
        action = "search_parameters" if (query or "").strip() else "list_parameters"

        return self._serialized(
            "ableton_read_parameters",
            lambda: self.operations.inspect_device_parameters(
                action=action,
                section=section,
                track_id=track_id,
                device_id=device_id,
                query=query,
                offset=cursor,
                limit=limit,
                projection=selected_projection,
                trace_level=trace_level,
                expected_collection_token=collection_token,
                auto_collect=collect_all,
                max_pages=32,
                max_items=512,
                total_timeout=total_timeout,
                page_timeout=self.settings.timeout,
                **self._connection(self.settings.timeout),
            ),
        )

    def control_transport(
        self, *, action: str = "status", beat: float | None = None,
        execution: str = "auto",
    ) -> dict[str, Any]:
        if action not in {"status", "play", "stop", "continue", "jump", "set_position"}:
            raise ValueError("unsupported transport action")
        if execution not in {"auto", "inspect", "apply"}:
            raise ValueError("execution must be auto, inspect, or apply")
        if action in {"jump", "set_position"} and beat is None:
            raise ValueError("beat is required for jump/set_position")
        if beat is not None:
            self._finite_number("beat", beat, 0)
            if action not in {"jump", "set_position", "play"}:
                raise ValueError("beat is only used by play/jump/set_position")
        return self._serialized(
            "ableton_transport",
            lambda: self.operations.transport(
                action, beat=beat, commit=action != "status" and execution != "inspect",
                **self._connection(self.settings.timeout)),
        )

    def read_or_set_tempo(
        self, *, bpm: float | None = None, execution: str = "inspect",
    ) -> dict[str, Any]:
        if execution not in {"inspect", "apply"}:
            raise ValueError("tempo execution must be inspect or apply")
        if bpm is not None:
            self._finite_number("bpm", bpm, 20, 999)

        def operation() -> dict[str, Any]:
            result = self.operations.tempo(
                bpm, commit=bpm is not None and execution == "apply",
                **self._connection(self.settings.timeout))
            return {**result, "tempo_scope": "live_set.tempo", "automation_managed": False}

        return self._serialized("ableton_tempo", operation)

    def list_locators(self) -> dict[str, Any]:
        return self._serialized(
            "ableton_list_locators",
            lambda: self.operations.locator(
                "list", commit=False, **self._connection(self.settings.timeout)),
        )

    def scan_clips(
        self, *, target: str = "arrangement", track_index: int | None = None,
        cursor: int = 0, limit: int = 4, collection_token: str | None = None,
        budget_ms: int = 1000,
    ) -> dict[str, Any]:
        if target not in {"arrangement", "session"}:
            raise ValueError("target must be arrangement or session")
        if track_index is not None:
            self._integer_range("track_index", track_index, 0, 65536)
        self._integer_range("cursor", cursor, 0, 512)
        return self._clip_page(
            "ableton_scan_clips", {"action": "scan_clips_metadata", "target": target,
                                   **({"track_index": track_index} if track_index is not None else {})},
            cursor=cursor, limit=limit, collection_token=collection_token,
            budget_ms=budget_ms, projection=["identity", "timing", "type"],
        )

    def read_clip_notes(
        self, *, clip_id: int, cursor: int = 0, beat_window: int = 4,
        collection_token: str | None = None, budget_ms: int = 1000,
    ) -> dict[str, Any]:
        self._integer_range("clip_id", clip_id, 1, 2147483647)
        self._integer_range("cursor", cursor, 0, 1000000)
        return self._clip_page(
            "ableton_read_clip_notes", {"action": "read_notes_by_clip_id", "clip_id": clip_id},
            cursor=cursor, limit=beat_window, collection_token=collection_token,
            budget_ms=budget_ms, projection=["notes"],
        )

    def _clip_page(
        self, tool: str, payload: dict[str, Any], *, cursor: int, limit: int,
        collection_token: str | None, budget_ms: int, projection: list[str],
    ) -> dict[str, Any]:
        self._integer_range("limit", limit, 1, 64)
        self._integer_range("budget_ms", budget_ms, 1, 5000)
        if collection_token is not None and (not isinstance(collection_token, str) or not collection_token):
            raise ValueError("collection_token must be a nonempty string")
        payload["read"] = {"cursor": cursor, "limit": limit, "projection": projection,
                           "budget_ms": budget_ms, "expected_collection_token": collection_token}

        def operation() -> dict[str, Any]:
            result = self.operations.request_page(
                "/clip_note_tools", payload, mode="dry_run", **self._connection(self.settings.timeout))
            read = result.get("read", {})
            continuation = None
            if (result.get("ok") and read.get("has_more") and not read.get("warnings")
                    and not result.get("warnings") and read.get("next_cursor") is not None):
                continuation = {"cursor": read["next_cursor"],
                                "collection_token": read.get("collection_token")}
            response = {**result, "read_only": True, "continuation": continuation}
            if payload["action"] == "scan_clips_metadata" and result.get("total_item_count", 0) >= 512:
                response["scope_limit_reached"] = True
                response["warnings"] = [*result.get("warnings", []),
                                        "Hub metadata collection capped at 512; narrow by track_index."]
                response["continuation"] = None
            return response

        return self._serialized(tool, operation)

    def read_meters(self, *, track_id: int, section: str = "track") -> dict[str, Any]:
        self._integer_range("track_id", track_id, 1, 2147483647)
        if section not in {"track", "return", "main", "master"}:
            raise ValueError("section must be track, return, or main")

        def operation() -> dict[str, Any]:
            result = self.operations.meter_monitor(
                "read_meters", track_id=track_id, section=section,
                **self._connection(self.settings.timeout))
            return {**result, "measurement_scope": "single_instant",
                    "message_scope": "A silent instant is not proof of a silent track; playback is not started."}

        return self._serialized("ableton_read_meters", operation)

    @staticmethod
    def _integer_range(name: str, value: int, low: int, high: int) -> None:
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{name} must be an integer from {low} to {high}")

    @staticmethod
    def _finite_number(name: str, value: float, low: float, high: float = math.inf) -> None:
        if type(value) not in {int, float} or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{name} must be finite and between {low} and {high}")

    def apply_mix(
        self,
        changes: list[dict[str, Any]],
        *,
        execution: str = "auto",
        value_display: str = "ui",
    ) -> dict[str, Any]:
        self._validate_stable_changes(changes, require_device=False)
        return self._serialized(
            "ableton_set_mix",
            lambda: self.operations.set_mix(
                changes,
                execution=execution,
                value_display=value_display,
                **self._connection(self.settings.timeout),
            ),
        )

    def apply_parameters(
        self,
        changes: list[dict[str, Any]],
        *,
        execution: str = "auto",
        value_display: str = "ui",
    ) -> dict[str, Any]:
        self._validate_stable_changes(changes, require_device=True)
        return self._serialized(
            "ableton_set_parameters",
            lambda: self.operations.set_parameters(
                changes,
                execution=execution,
                value_display=value_display,
                **self._connection(self.settings.timeout),
            ),
        )

    def _serialized(self, operation_name: str, operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        queued = time.monotonic()
        with self._hub_lock:
            acquired = time.monotonic()
            sequence = self._next_sequence()
            if operation_name in {"ableton_set_mix", "ableton_set_parameters"}:
                self._track_cache = None
            try:
                raw_result = operation()
                if not isinstance(raw_result, dict):
                    raw_result = {"ok": True, "result": raw_result}
                result = dict(raw_result)
            except Exception as error:
                result = self._operation_error(error, operation_name)
            if not result.get("ok", True):
                from .module_health import error_category
                result.setdefault("error_category", error_category(result))
                self._track_cache = None
            completed = time.monotonic()
            result["mcp"] = {
                "operation": operation_name,
                "request_sequence": sequence,
                "serialized": True,
                "reply_port_coordination": "cross_process_lock",
                "queue_wait_ms": round((acquired - queued) * 1000.0, 3),
                "operation_elapsed_ms": round((completed - acquired) * 1000.0, 3),
            }
            self._recent_operations.append({
                **result["mcp"], "ok": result.get("ok", True),
                "error_code": result.get("error_code"), "stage": result.get("stage"),
                "request_id": result.get("request_id"),
            })
            return result

    def _cached_tracks(self, *, refresh: bool) -> dict[str, Any]:
        revision = self.operations.track_management(
            "lookup_revision", commit=False, **self._connection(self.settings.timeout))
        if not revision.get("ok"):
            self._track_cache = None
            return revision
        key = revision.get("revision")
        cached = self._track_cache
        if (not refresh and key and cached and cached["revision"] == key
                and time.monotonic() - cached["created"] < 5.0):
            result = copy.deepcopy(cached["result"])
            result["cache"] = {"hit": True, "age_ms": round((time.monotonic() - cached["created"]) * 1000),
                               "ttl_ms": 5000, "revision": key}
            return result
        self._track_cache = None
        result = self.operations.track_management(
            "scan_tracks", commit=False, projection=["identity", "hierarchy"],
            include_returns=True, include_main=True, limit=16, max_items=512,
            total_timeout=15.0, page_timeout=self.settings.timeout,
            **self._connection(self.settings.timeout))
        if key and self._lookup_source(result)["source_complete"]:
            after = self.operations.track_management(
                "lookup_revision", commit=False, **self._connection(self.settings.timeout))
            if after.get("ok") and after.get("revision") == key:
                self._track_cache = {"revision": key, "created": time.monotonic(), "result": copy.deepcopy(result)}
            else:
                result = {**result, "complete": False, "warnings": ["lookup revision changed during track scan"]}
        result["cache"] = {"hit": False, "ttl_ms": 5000, "revision": key}
        return result

    @staticmethod
    def _operation_error(error: Exception, operation: str) -> dict[str, Any]:
        converter = getattr(error, "to_dict", None)
        if callable(converter):
            result = dict(converter())
        elif isinstance(getattr(error, "response", None), dict):
            result = dict(error.response)
        else:
            result = {}
        result["ok"] = False
        result.setdefault("error", str(error))
        result.setdefault("error_code", "client_validation_failed" if isinstance(error, ValueError) else "mcp_ableton_operation_failed")
        result.setdefault("error_layer", "client" if isinstance(error, ValueError) else "mcp_service")
        result["operation"] = operation
        result["error_type"] = type(error).__name__
        return result

    @staticmethod
    def _lookup_source(result: dict[str, Any]) -> dict[str, Any]:
        # Legacy trees and bounded pages keep completeness in different places.
        sources = [result]
        sources.extend(result[key] for key in ("tree", "read") if isinstance(result.get(key), dict))
        if isinstance(result.get("tree"), dict) and isinstance(result["tree"].get("read"), dict):
            sources.append(result["tree"]["read"])
        source: dict[str, Any] = {}
        warnings: list[Any] = []
        complete = bool(result.get("ok", True))
        for item in sources:
            if (item.get("complete") is False or item.get("partial")
                    or item.get("truncated") or item.get("has_more")
                    or item.get("stop_reason") or item.get("truncation_reasons")):
                complete = False
            for warning in item.get("warnings") or []:
                if warning not in warnings:
                    warnings.append(warning)
            for key in (
                "request_id", "error", "error_code", "error_layer", "stage", "details",
                "diagnostics", "read", "partial", "truncated", "truncation_reasons",
                "selectable_child_rack_ids", "root_device_id", "collection_token",
                "next_cursor", "stop_reason", "page_count", "elapsed_ms",
            ):
                if key in item:
                    source[key] = item[key]
        source["warnings"] = warnings
        source["source_complete"] = complete and not warnings
        return source

    def _next_sequence(self) -> int:
        with self._sequence_lock:
            self._request_sequence += 1
            return self._request_sequence

    def _connection(self, timeout: float) -> dict[str, Any]:
        return {
            "host": self.settings.host,
            "command_port": self.settings.command_port,
            "reply_port": self.settings.reply_port,
            "timeout": timeout,
        }

    @staticmethod
    def _validate_stable_changes(changes: list[dict[str, Any]], *, require_device: bool) -> None:
        if not changes:
            raise ValueError("changes cannot be empty")
        for index, change in enumerate(changes):
            if not isinstance(change, dict):
                raise ValueError(f"change {index} must be an object")
            validate_value_input(change)
            if int(change.get("track_id") or 0) <= 0:
                raise ValueError(f"change {index} requires a positive stable track_id")
            if require_device:
                if int(change.get("device_id") or 0) <= 0:
                    raise ValueError(f"change {index} requires a positive stable device_id")
                if int(change.get("parameter_id") or 0) <= 0:
                    raise ValueError(f"change {index} requires a positive stable parameter_id")

    @staticmethod
    def _rank_matches(
        records: list[dict[str, Any]], query: str, name_key: str, limit: int
    ) -> list[dict[str, Any]]:
        needle = query.casefold()

        def name(record: dict[str, Any]) -> str:
            return str(record.get(name_key) or record.get("name") or "")

        exact = [item for item in records if name(item).casefold() == needle]
        contains = [
            item for item in records if needle in name(item).casefold() and item not in exact
        ]
        return (exact + contains)[:limit]

    @classmethod
    def _flatten_device_records(cls, value: Any) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        seen_ids: set[int] = set()

        def visit(item: Any) -> None:
            if isinstance(item, list):
                for child in item:
                    visit(child)
                return
            if not isinstance(item, dict):
                return
            device_id = item.get("device_id")
            if isinstance(device_id, int) and device_id not in seen_ids:
                seen_ids.add(device_id)
                records.append(dict(item))
            for child in item.values():
                if isinstance(child, (dict, list)):
                    visit(child)

        visit(value)
        return records

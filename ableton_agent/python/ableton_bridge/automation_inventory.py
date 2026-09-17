"""Bounded, resumable automation-state discovery over existing read-only routes."""
from __future__ import annotations

from collections import deque
import time
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AutomationScan(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    track_ids: list[Annotated[int, Field(strict=True, gt=0)]] | None = Field(default=None, max_length=64)
    sections: list[Literal["track", "return", "main"]] = Field(default_factory=lambda: ["track", "return", "main"], min_length=1, max_length=3)
    include_nested: bool = True
    states: list[Literal["none", "active", "overridden"]] = Field(default_factory=lambda: ["active", "overridden"], min_length=1, max_length=3)
    limit: Annotated[int, Field(strict=True, ge=1, le=32)] = 4
    max_pages: Annotated[int, Field(strict=True, ge=1, le=64)] = 32
    total_timeout: Annotated[float, Field(ge=1, le=30)] = 10
    trace_level: Literal["none", "page", "parameter", "field"] = "none"
    continuation: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def scope(self):
        if self.track_ids is not None and (not self.track_ids or len(set(self.track_ids)) != len(self.track_ids)):
            raise ValueError("track_ids must be a nonempty unique list when supplied")
        return self


class AutomationInventory:
    """Caller holds the MCP service lock. Each underlying client holds UDP's lock."""

    def __init__(self, operations, connection, clock=time.monotonic):
        self.ops, self.connection, self.clock = operations, connection, clock
        self.sessions = {}

    def scan(self, fields):
        request = AutomationScan.model_validate(fields)
        scope = request.model_dump(exclude={"continuation", "max_pages", "total_timeout", "trace_level"})
        now = self.clock()
        self.sessions = {k: v for k, v in self.sessions.items() if now - v["started"] < 300}
        state = None
        if request.continuation:
            state = self.sessions.pop(request.continuation, None)
            if state is None or state["scope"] != scope:
                raise ValueError("stale_scan: continuation expired, consumed, or scope changed; start a new scan")
        if state is None:
            state = dict(scope=scope, started=now, scan_id=uuid.uuid4().hex, revision=None,
                         queue=deque([dict(kind="tracks", cursor=0, token=None)]),
                         tracks=set(), devices=set(), parameters=set(), devices_completed=0,
                         counts={"none": 0, "active": 0, "overridden": 0}, page_count=0)
        deadline = now + request.total_timeout
        rows, pages, error, stop = [], [], None, None
        job = None

        def connection():
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise TimeoutError("Automation inventory time budget exhausted")
            return self.connection(min(5.0, remaining))

        def checked(result):
            if not result.get("ok"):
                raise InventoryFailure(result)
            warnings = result.get("warnings") or result.get("read", {}).get("warnings")
            if warnings:
                raise InventoryFailure({"ok": False, "error": "Read warnings; scan stopped", "warnings": warnings,
                                        "request_id": result.get("request_id")})
            return result

        try:
            revision = checked(self.ops.track_management("lookup_revision", commit=False, **connection())).get("revision")
            if not revision or state["revision"] not in (None, revision):
                raise ValueError("stale_scan: Set/track revision changed; discard previous scan pages")
            state["revision"] = revision
            while state["queue"]:
                if len(pages) >= request.max_pages or self.clock() >= deadline - 0.1:
                    stop = "max_pages" if len(pages) >= request.max_pages else "time_budget"
                    break
                job = state["queue"][0]
                common = dict(cursor=job["cursor"], expected_collection_token=job["token"],
                              limit=request.limit, budget_ms=1000)
                if job["kind"] == "tracks":
                    result = self.ops.track_management("scan_tracks", commit=False, auto_collect=False,
                        include_returns=True, include_main=True, projection=["identity"],
                        **common, **connection())
                elif job["kind"] == "devices":
                    result = self.ops.device_chain("scan_children", commit=False,
                        section=job["section"], track_id=job["track_id"], root_device_id=job.get("root"),
                        **common, **connection())
                else:
                    result = self.ops.inspect_device_parameters(action="list_parameters", auto_collect=False,
                        section=job["section"], track_id=job["track_id"], device_id=job["device_id"],
                        offset=job["cursor"], limit=request.limit, expected_collection_token=job["token"],
                        projection=["identity", "automation_state"], trace_level=request.trace_level,
                        budget_ms=1000, **connection())
                checked(result)
                page = result.get("tree", {}) if job["kind"] == "devices" else result
                checked({"ok": True, **page})
                read = page.get("read", {})
                token = read.get("collection_token")
                if not token or (job["token"] and job["token"] != token):
                    raise ValueError("stale_collection: page token missing or changed")
                if read.get("cursor") != job["cursor"]:
                    raise ValueError("Invalid page cursor")
                more, next_cursor = read.get("has_more"), read.get("next_cursor")
                if type(more) is not bool or (more and (type(next_cursor) is not int or next_cursor <= job["cursor"])):
                    raise ValueError("Invalid/non-progressing page continuation")
                items = page.get("devices") if job["kind"] == "devices" else page.get("items")
                if not isinstance(items, list) or len(items) > request.limit:
                    raise ValueError("Invalid bounded page items")
                if not more and read.get("complete") is not True:
                    raise ValueError("Incomplete page without continuation")
                pages.append({"kind": job["kind"], "track_id": job.get("track_id"),
                              "device_id": job.get("device_id"), "cursor": job["cursor"],
                              "request_id": result.get("request_id"), "elapsed_ms": read.get("elapsed_ms"),
                              "collection_token": token})
                for item in items:
                    if job["kind"] == "tracks":
                        tid, section = item["track_id"], item["section"]
                        if section not in request.sections or (request.track_ids is not None and tid not in request.track_ids):
                            continue
                        if tid in state["tracks"] or len(state["tracks"]) >= 512:
                            raise ValueError("Duplicate track or track safety limit reached")
                        state["tracks"].add(tid)
                        state["queue"].append(dict(kind="devices", track_id=tid, section=section,
                            track_name=item.get("track_name"), root=None, cursor=0, token=None))
                    elif job["kind"] == "devices":
                        did = item["device_id"]
                        if did in state["devices"] or len(state["devices"]) >= 512:
                            raise ValueError("Duplicate device or device safety limit reached")
                        state["devices"].add(did)
                        target = dict(track_id=job["track_id"], section=job["section"],
                                      track_name=job.get("track_name"), device_id=did,
                                      device_name=item.get("name"), chain_path=item.get("chain_path", []))
                        state["queue"].append(dict(target, kind="parameters", cursor=0, token=None))
                        if request.include_nested and item.get("can_have_chains"):
                            state["queue"].append(dict(target, kind="devices", root=did, cursor=0, token=None))
                    else:
                        key = (job["device_id"], item["id"])
                        value = item.get("automation_state")
                        if type(value) is not int or value not in (0, 1, 2):
                            raise ValueError("Missing/unknown automation_state; cannot infer none")
                        if key in state["parameters"] or len(state["parameters"]) >= 32768:
                            raise ValueError("Duplicate parameter or parameter safety limit reached")
                        state["parameters"].add(key)
                        name = ("none", "active", "overridden")[value]
                        state["counts"][name] += 1
                        if name in request.states:
                            rows.append({k: job[k] for k in ("section", "track_id", "track_name", "device_id", "device_name", "chain_path")} |
                                dict(parameter_id=item["id"], parameter_index=item["index"],
                                     parameter_name=item.get("name"), automation_state=value,
                                     automation_state_name=name))
                state["page_count"] += 1
                if more:
                    job.update(cursor=next_cursor, token=token)
                else:
                    state["queue"].popleft()
                    if job["kind"] == "parameters":
                        state["devices_completed"] += 1
                    if job["kind"] == "tracks" and request.track_ids is not None and set(request.track_ids) != state["tracks"]:
                        raise ValueError("Requested tracks absent from selected sections; inventory incomplete")
            if self.clock() < deadline - 0.1:
                after = checked(self.ops.track_management("lookup_revision", commit=False, **connection()))
                if after.get("revision") != state["revision"]:
                    raise ValueError("stale_scan: Set/track revision changed during scan; discard this scan")
            else:
                stop = "time_budget"
                # Revision must be verified before claiming a completed inventory.
                if not state["queue"]:
                    raise TimeoutError("No budget for final revision verification; restart scan")
        except Exception as exc:
            convert = getattr(exc, "to_dict", None)
            error = convert() if callable(convert) else {"error": str(exc)}
            stop = "read_failed"

        continuation = None
        if state["queue"] and error is None:
            continuation = uuid.uuid4().hex
            while len(self.sessions) >= 8:
                self.sessions.pop(next(iter(self.sessions)))
            self.sessions[continuation] = state
        complete = not state["queue"] and error is None
        return dict(ok=error is None, read_only=True, scan_id=state["scan_id"], complete=complete,
            partial=not complete, stop_reason=None if complete else stop, continuation=continuation,
            scope=scope, items=rows, items_scope="This response only; concatenate pages of the same scan_id",
            tracks_scanned=len(state["tracks"]), devices_discovered=len(state["devices"]),
            devices_completed=state["devices_completed"], parameters_scanned=len(state["parameters"]),
            state_counts=dict(state["counts"]), pending_jobs=len(state["queue"]), pages=pages,
            page_count=state["page_count"], elapsed_ms=round((self.clock()-now)*1000, 3),
            failure=error, failed_target=dict(job) if error and job else None,
            warnings=["Current device-parameter state only; no breakpoint positions, mixer automation or atomic snapshot. Re-read targets before writing."])


class InventoryFailure(RuntimeError):
    def __init__(self, result):
        self.result = result
        super().__init__(result.get("error", "Hub read failed"))

    def to_dict(self):
        return self.result

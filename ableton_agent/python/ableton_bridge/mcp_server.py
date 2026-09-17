from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, model_validator
from .ui_input import validate_value_input

from .mcp_tools import AbletonMcpService


SERVER_INSTRUCTIONS = (
    "All Ableton Hub calls share UDP reply port 7401 and must run one at a time; this server "
    "serializes them. Use ableton_status when the current Live/Hub state is unknown. Discover "
    "stable track_id, device_id, and parameter_id values before writes. Read tools never modify "
    "Live. Explicitly requested writes apply directly, return exact readback, and default "
    "to Live UI-formatted output while preserving internal values. Do not invent IDs or issue "
    "parallel Ableton tool calls. Transport auto applies ephemeral actions; status is read-only. "
    "Tempo defaults to inspect and cannot manage tempo automation. No clear, replace, "
    "or unrestricted structural tools are exposed. Creative tools use stable IDs; inspect and plan tokens are optional. "
    "Track/scene creation and new MIDI Clips are supported without overwriting existing content. "
    "manage_tracks delete_track deletes a whole ordinary non-Group track, including content, "
    "only after explicit user intent; Hub host and last track are protected. "
    "Sample loading remains manual; search is local catalog discovery only. "
    "Use scan_automation for bounded resumable device automation states; incomplete is not none. "
    "edit_arrangement supports same-track audio moves and MIDI note-data copies, not full Clip envelopes."
)


class ScalarInput(BaseModel):
    value: float | int | None = None
    ui_value: str | None = Field(default=None, description="Live UI text, mutually exclusive with internal value; only supported adapters.")

    @model_validator(mode="after")
    def validate_input(self):
        validate_value_input(self.model_dump())
        return self


class MixChange(ScalarInput):
    section: Literal["track", "return", "main", "master"] = "track"
    track_id: int = Field(gt=0, description="Session-stable Live track ID.")
    field: Literal["volume", "pan", "mute", "solo", "arm", "send"]
    send: int | str | None = Field(
        default=None, description="Return index, stable ID, or name when field is send."
    )
    expected_before: float | int | None = Field(
        default=None, description="Optional stale-state guard using the exact internal value."
    )


class ParameterChange(ScalarInput):
    section: Literal["track", "return", "main", "master"] = "track"
    track_id: int = Field(gt=0, description="Session-stable Live track ID.")
    device_id: int = Field(gt=0, description="Session-stable Live device ID.")
    parameter_id: int = Field(gt=0, description="Session-stable Live parameter ID.")
    expected_before: float | int | None = Field(
        default=None, description="Optional stale-state guard using the exact internal value."
    )


service = AbletonMcpService()
mcp = MCPServer(
    "Ableton Agent",
    title="Ableton Agent Hub",
    description="Low-latency, serialized tools for the currently open Ableton Live Set.",
    instructions=SERVER_INSTRUCTIONS,
    version="0.1.0",
)


READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
SCALAR_WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)


@mcp.tool(title="Check Ableton Hub", annotations=READ_ONLY)
def ableton_status(timeout: Annotated[float, Field(gt=0, le=10)] = 2.0,
                   probe_modules: bool = False) -> dict[str, Any]:
    """Ping by default. Explicit probe_modules checks four module handlers read-only and reports running build evidence; never proves write acceptance."""
    return service.status(timeout=timeout, probe_modules=probe_modules)


@mcp.tool(title="Read Current Live Set", annotations=READ_ONLY)
def ableton_read_set(
    depth: Literal["quick", "full"] = "quick",
    detail: Literal["summary", "context"] = "summary",
    include_raw_notes: bool = False,
    note_tracks: list[str] | None = None,
    max_note_clips: Annotated[int, Field(ge=1, le=512)] = 64,
    total_timeout: Annotated[float, Field(gt=0, le=120)] = 30.0,
    als_path: str | None = None,
    saved_sections: list[
        Literal["tracks", "scenes", "audio_clips", "automation", "grooves", "midi"]
    ]
    | None = None,
    include_saved_device_parameters: bool = False,
    include_saved_midi_notes: bool = False,
) -> dict[str, Any]:
    """Read the current Set through the canonical progressive reader.

    When an explicit absolute ALS path is supplied, the result also contains a
    read-only saved-file layer and a field-level comparison using the already
    collected Live metadata. Saved XML IDs never become Live write targets.
    """
    return service.read_set(
        depth=depth,
        detail=detail,
        include_raw_notes=include_raw_notes,
        note_tracks=note_tracks,
        max_note_clips=max_note_clips,
        total_timeout=total_timeout,
        als_path=als_path,
        saved_sections=saved_sections,
        include_saved_device_parameters=include_saved_device_parameters,
        include_saved_midi_notes=include_saved_midi_notes,
    )


@mcp.tool(title="Find Stable Ableton Target", annotations=READ_ONLY)
def ableton_find_target(
    target_type: Literal["track", "device", "parameter"],
    query: Annotated[str, Field(min_length=1, description="Case-insensitive name fragment.")],
    section: Literal["track", "return", "main", "master"] = "track",
    track_id: Annotated[int | None, Field(gt=0)] = None,
    device_id: Annotated[int | None, Field(gt=0)] = None,
    root_device_id: Annotated[int | None, Field(gt=0)] = None,
    limit: Annotated[int, Field(ge=1, le=32)] = 12,
    cursor: Annotated[int, Field(ge=0, le=65536)] = 0,
    collection_token: str | None = None,
    page_limit: Annotated[int, Field(ge=1, le=32)] = 4,
    max_pages: Annotated[int, Field(ge=1, le=32)] = 32,
    scan_mode: Literal["children", "recursive"] = "children",
    max_depth: Annotated[int, Field(ge=0, le=12)] = 4,
    max_devices: Annotated[int, Field(ge=1, le=512)] = 64,
    budget_ms: Annotated[int, Field(ge=1, le=5000)] = 1000,
    match_offset: Annotated[int, Field(ge=0, le=512)] = 0,
    refresh: bool = False,
) -> dict[str, Any]:
    """Find stable IDs. Devices default to direct-child pages: follow continuation for siblings,
    then root_device_id for child Racks. Keep all other search arguments when continuing.
    Track discovery may use a revision-checked five-second cache; refresh bypasses it.
    """
    return service.find_target(
        target_type=target_type,
        query=query,
        section=section,
        track_id=track_id,
        device_id=device_id,
        root_device_id=root_device_id,
        limit=limit,
        cursor=cursor, collection_token=collection_token, page_limit=page_limit,
        max_pages=max_pages, scan_mode=scan_mode, max_depth=max_depth,
        max_devices=max_devices, budget_ms=budget_ms, match_offset=match_offset, refresh=refresh,
    )


@mcp.tool(title="Read Ableton Parameters", annotations=READ_ONLY)
def ableton_read_parameters(
    track_id: Annotated[int, Field(gt=0)],
    device_id: Annotated[int, Field(gt=0)],
    section: Literal["track", "return", "main", "master"] = "track",
    query: str | None = None,
    cursor: Annotated[int, Field(ge=0, le=512)] = 0,
    limit: Annotated[int, Field(ge=1, le=32)] = 4,
    projection: list[
        Literal["identity", "metadata", "internal_value", "display_value", "enum_values", "automation_state"]
    ]
    | None = None,
    collection_token: str | None = None,
    collect_all: bool = False,
    total_timeout: Annotated[float, Field(gt=0, le=120)] = 15.0,
    trace_level: Literal["none", "page", "parameter", "field"] = "none",
) -> dict[str, Any]:
    """Read one bounded parameter page by default; opt into sequential auto-collection explicitly."""
    return service.read_parameters(
        track_id=track_id,
        device_id=device_id,
        section=section,
        query=query,
        cursor=cursor,
        limit=limit,
        projection=projection,
        collection_token=collection_token,
        collect_all=collect_all,
        total_timeout=total_timeout,
        trace_level=trace_level,
    )


@mcp.tool(title="Set Ableton Mixer Values", annotations=SCALAR_WRITE)
def ableton_set_mix(
    changes: Annotated[list[MixChange], Field(min_length=1, max_length=32)],
    execution: Literal["auto", "inspect", "apply"] = "auto",
    value_display: Literal["ui", "both", "internal"] = "ui",
) -> dict[str, Any]:
    """Apply guarded scalar mixer changes by stable track ID and return exact readback."""
    return service.apply_mix(
        [change.model_dump(exclude_none=True) for change in changes],
        execution=execution,
        value_display=value_display,
    )


@mcp.tool(title="Set Ableton Device Parameters", annotations=SCALAR_WRITE)
def ableton_set_parameters(
    changes: Annotated[list[ParameterChange], Field(min_length=1, max_length=16)],
    execution: Literal["auto", "inspect", "apply"] = "auto",
    value_display: Literal["ui", "both", "internal"] = "ui",
) -> dict[str, Any]:
    """Apply guarded device-parameter changes by stable IDs and return exact readback."""
    return service.apply_parameters(
        [change.model_dump(exclude_none=True) for change in changes],
        execution=execution,
        value_display=value_display,
    )


@mcp.tool(title="Diagnose Ableton Parameter Reads", annotations=READ_ONLY)
def ableton_diagnose_parameters(
    track_id: Annotated[int, Field(gt=0)],
    device_id: Annotated[int, Field(gt=0)],
    section: Literal["track", "return", "main", "master"] = "track",
    cursor: Annotated[int, Field(ge=0, le=512)] = 0,
    limit: Annotated[int, Field(ge=1, le=4)] = 4,
    total_timeout: Annotated[float, Field(gt=0, le=120, allow_inf_nan=False)] = 30.0,
) -> dict[str, Any]:
    """Read-only bounded field probes with health checks, no writes or reloads.
    Sequential; at most 16 requests. Reports a window, never a whole-Set pass.
    """
    return service.diagnose_parameters(track_id=track_id, device_id=device_id, section=section,
                                       cursor=cursor, limit=limit, total_timeout=total_timeout)


@mcp.tool(title="Apply Ableton Scalar Batch", annotations=SCALAR_WRITE)
def ableton_apply_batch(
    mix_changes: Annotated[list[MixChange], Field(max_length=32)],
    parameter_changes: Annotated[list[ParameterChange], Field(max_length=16)],
    execution: Literal["auto", "inspect", "apply"] = "auto",
    value_display: Literal["ui", "both", "internal"] = "ui",
) -> dict[str, Any]:
    """One tool call: mixer batch then parameter batch, using resolved stable IDs.
    Not atomic. Stops at first failure, never retries or rolls back automatically.
    Pass an empty list for an unused group. Native readback and receipts are retained.
    """
    return service.apply_batch(
        mix_changes=[change.model_dump(exclude_none=True) for change in mix_changes],
        parameter_changes=[change.model_dump(exclude_none=True) for change in parameter_changes],
        execution=execution, value_display=value_display)


@mcp.tool(title="Control Ableton Playback", annotations=SCALAR_WRITE)
def ableton_transport(
    action: Literal["status", "play", "stop", "continue", "jump", "set_position"] = "status",
    beat: Annotated[float | None, Field(ge=0, allow_inf_nan=False)] = None,
    execution: Literal["auto", "inspect", "apply"] = "auto",
) -> dict[str, Any]:
    """Read transport or play/stop/jump. Auto applies requested actions; inspect never changes Live.
    Beat is a zero-based quarter-note position, not a bar number. Use play with beat to
    audition that position; jump alone does not guarantee the next Play starts there.
    """
    return service.control_transport(action=action, beat=beat, execution=execution)


@mcp.tool(title="Read Or Set Ableton Tempo", annotations=SCALAR_WRITE)
def ableton_tempo(
    bpm: Annotated[float | None, Field(ge=20, le=999, allow_inf_nan=False)] = None,
    execution: Literal["inspect", "apply"] = "inspect",
) -> dict[str, Any]:
    """Without bpm, read current tempo. With bpm, inspect by default; apply explicitly writes.
    Only live_set.tempo is handled: Song Tempo automation can still override it later.
    This legacy route reports before/current BPM but has no guarded restore receipt.
    """
    return service.read_or_set_tempo(bpm=bpm, execution=execution)


@mcp.tool(title="List Ableton Locators", annotations=READ_ONLY)
def ableton_list_locators() -> dict[str, Any]:
    """Read Arrangement locator IDs, names and beat positions; never create/delete/jump."""
    return service.list_locators()


@mcp.tool(title="List Ableton Clips", annotations=READ_ONLY)
def ableton_scan_clips(
    target: Literal["arrangement", "session"] = "arrangement",
    track_index: Annotated[int | None, Field(ge=0, le=65536)] = None,
    cursor: Annotated[int, Field(ge=0, le=512)] = 0,
    limit: Annotated[int, Field(ge=1, le=64)] = 4,
    collection_token: str | None = None,
    budget_ms: Annotated[int, Field(ge=1, le=5000)] = 1000,
) -> dict[str, Any]:
    """Read one clip metadata page, no note bodies. Return stable clip IDs for note reads.
    track_index is optional, zero-based, read-only filtering; keep target/filter unchanged
    when resuming cursor/token. Hub collection cap is 512, not an unlimited Set scan.
    """
    return service.scan_clips(target=target, track_index=track_index, cursor=cursor,
                              limit=limit, collection_token=collection_token, budget_ms=budget_ms)


@mcp.tool(title="Read Ableton MIDI Notes", annotations=READ_ONLY)
def ableton_read_clip_notes(
    clip_id: Annotated[int, Field(gt=0, le=2147483647)],
    cursor: Annotated[int, Field(ge=0, le=1000000)] = 0,
    beat_window: Annotated[int, Field(ge=1, le=64)] = 4,
    collection_token: str | None = None,
    budget_ms: Annotated[int, Field(ge=1, le=5000)] = 1000,
) -> dict[str, Any]:
    """Read one MIDI clip-local beat window by stable clip_id. Cursor/window are beats,
    not note indexes/counts. Follow returned continuation with the same clip ID.
    Token guards clip ID/length, not simultaneous note edits. Dense windows may still
    exceed UDP limits; stop on failure and narrow deliberately, never blind retry.
    """
    return service.read_clip_notes(clip_id=clip_id, cursor=cursor, beat_window=beat_window,
                                   collection_token=collection_token, budget_ms=budget_ms)


@mcp.tool(title="Read Ableton Track Meters", annotations=READ_ONLY)
def ableton_read_meters(
    track_id: Annotated[int, Field(gt=0, le=2147483647)],
    section: Literal["track", "return", "main", "master"] = "track",
) -> dict[str, Any]:
    """Read one stable track's instantaneous meters, no polling or automatic playback.
    Silent-now/clipping-risk are rough indications, not proof of whole-song silence or clipping.
    """
    return service.read_meters(track_id=track_id, section=section)


from .mcp_creative import register_creative_tools

register_creative_tools(mcp, lambda: service)

if __name__ == "__main__":
    mcp.run()

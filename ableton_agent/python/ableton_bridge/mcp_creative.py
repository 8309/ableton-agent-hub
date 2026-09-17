"""Typed creative tools over existing routes; no public arbitrary-command escape hatch."""
from __future__ import annotations

from pathlib import Path
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .automation_inventory import AutomationScan
from .als_bundle import (
    ALL_SECTIONS as SAVED_ALS_SECTIONS,
    DEFAULT_MAX_AUDIO_CLIPS,
    DEFAULT_MAX_AUTOMATION_EVENTS,
    DEFAULT_MAX_DEVICES,
    DEFAULT_MAX_PARAMETERS_PER_DEVICE,
    DEFAULT_MAX_WARP_MARKERS_PER_CLIP,
    read_saved_set,
)
from .saved_automation import SavedAutomationReader, SavedAutomationRequest

_saved_automation = SavedAutomationReader()

LiveId = Annotated[int, Field(strict=True, gt=0, le=2147483647)]
Name = Annotated[str, Field(min_length=1, max_length=128)]
Beat = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class WriteRequest(Request):
    execution: Literal["auto", "inspect", "apply"] = "auto"
    plan_token: str | None = None


class Note(Request):
    pitch: Annotated[int, Field(strict=True, ge=0, le=127)]
    start_time: Beat
    duration: Annotated[float, Field(gt=0)]
    velocity: Annotated[float, Field(ge=1, le=127)] = 100
    mute: bool = False
    probability: Annotated[float, Field(ge=0, le=1)] = 1


class WriteMidi(WriteRequest):
    track_id: LiveId
    location: Literal["session", "arrangement"] = "session"
    scene_id: LiveId | None = None
    start: Beat | None = None
    length: Annotated[float, Field(gt=0, le=256)] = 16
    name: Name = "Agent MIDI"
    notes: Annotated[list[Note], Field(max_length=512)]

    @model_validator(mode="after")
    def check_target(self):
        if self.location == "session" and (not self.scene_id or self.start is not None):
            raise ValueError("Session writing requires scene_id and no Arrangement start")
        if self.location == "arrangement" and (self.start is None or self.scene_id is not None):
            raise ValueError("Arrangement writing requires start and no scene_id")
        if any(n.start_time + n.duration > self.length for n in self.notes):
            raise ValueError("Notes must fit entirely inside the Clip")
        return self


class EditMidi(WriteRequest):
    track_id: LiveId
    clip_id: LiveId
    action: Literal["shift_notes", "quantize_notes", "scale_velocity"]
    start: Beat = 0
    end: Beat | None = None
    beats: Annotated[float, Field(ge=-256, le=256)] = 0
    grid: Annotated[float, Field(gt=0, le=16)] = 0.25
    factor: Annotated[float, Field(gt=0, le=4)] = 1

    @model_validator(mode="after")
    def window(self):
        if self.end is not None and self.end <= self.start:
            raise ValueError("end must follow start in Clip-local beats")
        return self


class VaryMidi(WriteRequest):
    track_id: LiveId
    clip_id: LiveId
    action: Literal["duplicate_clip", "make_fill", "thin_notes", "mute_notes_in_range"] = "make_fill"
    target_start: Beat
    name: Name = "MIDI Variation"
    start: Beat | None = None
    end: Beat | None = None
    fill_length: Annotated[float, Field(ge=0.25, le=256)] = 4
    keep_every: Annotated[int, Field(strict=True, ge=2, le=32)] = 2

    @model_validator(mode="after")
    def window(self):
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("end must follow start")
        return self


class ConfirmSample(Request):
    track_id: LiveId
    device_id: LiveId
    target: Literal["simpler", "drum_rack_pad"] = "simpler"
    pad_note: Annotated[int, Field(strict=True, ge=0, le=127)] | None = None
    intended_path: str | None = None

    @model_validator(mode="after")
    def pad(self):
        if self.target == "drum_rack_pad" and self.pad_note is None:
            raise ValueError("Drum Rack confirmation requires a specific pad_note")
        return self


class InsertDevice(WriteRequest):
    track_id: LiveId
    section: Literal["track", "return", "main"] = "track"
    kind: Literal["instrument", "effect"]
    device: Name


class EqPreset(WriteRequest):
    action: Literal["list_presets", "apply_preset"] = "list_presets"
    track_id: LiveId | None = None
    section: Literal["track", "return", "main"] = "track"
    device_id: LiveId | None = None
    preset: Name | None = None

    @model_validator(mode="after")
    def target(self):
        if self.action == "apply_preset" and not all((self.track_id, self.device_id, self.preset)):
            raise ValueError("Preset requires track_id, device_id and preset")
        if self.action == "list_presets" and self.execution == "apply":
            raise ValueError("Preset listing is read-only")
        return self


class ManageTracks(WriteRequest):
    action: Literal["create_midi_track", "create_audio_track", "rename_track", "color_track", "delete_track"]
    track_id: LiveId | None = None
    section: Literal["track", "return", "main"] = "track"
    name: Name | None = None
    color: Annotated[int, Field(strict=True, ge=0, le=16777215)] | None = None

    @model_validator(mode="after")
    def target(self):
        if self.action.startswith("create_"):
            if self.section != "track" or self.track_id is not None:
                raise ValueError("New ordinary tracks append only; no target ID or special section")
        elif self.track_id is None:
            raise ValueError("Existing track requires stable track_id")
        if self.action == "delete_track":
            if self.section != "track" or self.name is not None or self.color is not None:
                raise ValueError("Delete accepts an ordinary track_id only; no rename/color")
        if self.action == "rename_track" and not self.name:
            raise ValueError("Rename requires name")
        if self.action == "color_track" and self.color is None:
            raise ValueError("Color action requires color")
        return self


class EditArrangement(WriteRequest):
    action: Literal["move_audio_clip", "copy_midi_clip"]
    track_id: LiveId
    clip_id: LiveId
    target_start: Annotated[float, Field(ge=0, le=1576800)]
    name: Name | None = None

    @model_validator(mode="after")
    def naming(self):
        if self.action == "move_audio_clip" and self.name is not None:
            raise ValueError("Audio move preserves the name; omit name")
        return self


class ManageScenes(WriteRequest):
    action: Literal["list", "create", "duplicate", "rename", "fire"] = "list"
    scene_id: LiveId | None = None
    name: Name | None = None
    cursor: Annotated[int, Field(strict=True, ge=0)] = 0
    limit: Annotated[int, Field(strict=True, ge=1, le=32)] = 16

    @model_validator(mode="after")
    def target(self):
        if self.action in {"duplicate", "rename", "fire"} and self.scene_id is None:
            raise ValueError("Existing scene requires stable scene_id")
        if self.action == "rename" and not self.name:
            raise ValueError("Rename requires name")
        if self.action == "fire" and self.name:
            raise ValueError("Fire does not rename")
        if self.action == "list" and self.execution == "apply":
            raise ValueError("Scene listing is read-only")
        return self


class SearchSounds(Request):
    reference_audio: str | None = None
    candidate_limit: Annotated[int, Field(strict=True, ge=1, le=64)] = 24
    query: str | None = None
    role: str | None = None
    kind: str | None = None
    pack: str | None = None
    official_tag: str | None = None
    device: str | None = None
    rack_type: str | None = None
    key: str | None = None
    root_note: str | None = None
    bpm_min: Beat | None = None
    bpm_max: Beat | None = None
    duration_min: Beat | None = None
    duration_max: Beat | None = None
    is_loop: bool | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=20)] = 5

    @model_validator(mode="after")
    def bounds(self):
        if self.reference_audio:
            if not Path(self.reference_audio).is_absolute():
                raise ValueError("reference_audio must be an absolute path")
            if self.candidate_limit < self.limit:
                raise ValueError("candidate_limit must be at least limit")
        for lower, upper in ((self.bpm_min, self.bpm_max), (self.duration_min, self.duration_max)):
            if lower is not None and upper is not None and lower > upper:
                raise ValueError("Minimum filter cannot exceed maximum")
        return self


class SavedSetRequest(Request):
    """Bounded, read-only request for the complete saved-ALS reader family."""

    als_path: str = Field(min_length=1)
    sections: list[
        Literal["tracks", "scenes", "audio_clips", "automation", "grooves", "midi"]
    ] | None = None
    include_device_parameters: bool = False
    include_midi_notes: bool = False
    midi_track_name: str | None = None
    midi_clip_name: str | None = None
    midi_clip_source: Literal["arrangement", "session", "all"] = "all"
    midi_cursor: Annotated[int, Field(strict=True, ge=0)] = 0
    midi_limit: Annotated[int, Field(strict=True, ge=1, le=64)] = 64
    midi_start_beat: Beat | None = None
    midi_end_beat: Beat | None = None
    max_parameters_per_device: Annotated[int, Field(strict=True, ge=1, le=4096)] = DEFAULT_MAX_PARAMETERS_PER_DEVICE
    max_automation_events: Annotated[int, Field(strict=True, ge=1, le=16384)] = DEFAULT_MAX_AUTOMATION_EVENTS
    max_audio_clips: Annotated[int, Field(strict=True, ge=1, le=4096)] = DEFAULT_MAX_AUDIO_CLIPS
    max_warp_markers_per_clip: Annotated[int, Field(strict=True, ge=1, le=4096)] = DEFAULT_MAX_WARP_MARKERS_PER_CLIP
    max_devices: Annotated[int, Field(strict=True, ge=1, le=8192)] = DEFAULT_MAX_DEVICES
    max_notes_per_clip: Annotated[int, Field(strict=True, ge=1, le=16384)] = 4096
    max_occurrences_per_clip: Annotated[int, Field(strict=True, ge=1, le=65536)] = 16384
    max_file_references: Annotated[int, Field(strict=True, ge=0, le=8192)] = 512

    @model_validator(mode="after")
    def valid_request(self):
        path = Path(self.als_path).expanduser()
        if not path.is_absolute() or path.suffix.casefold() != ".als":
            raise ValueError("als_path must be an explicit absolute .als path")
        if self.sections is not None:
            unknown = set(self.sections) - SAVED_ALS_SECTIONS
            if unknown:
                raise ValueError(f"Unknown saved-set sections: {', '.join(sorted(unknown))}")
            if len(set(self.sections)) != len(self.sections):
                raise ValueError("sections cannot contain duplicates")
        if self.midi_end_beat is not None and self.midi_start_beat is not None and self.midi_end_beat <= self.midi_start_beat:
            raise ValueError("midi_end_beat must be greater than midi_start_beat")
        return self


MODELS = {"write_midi_clip": WriteMidi, "edit_midi_notes": EditMidi,
          "vary_midi_clip": VaryMidi, "confirm_sample": ConfirmSample,
          "insert_device": InsertDevice, "eq": EqPreset,
          "manage_tracks": ManageTracks, "manage_scenes": ManageScenes, "edit_arrangement": EditArrangement}
ROUTES = {"write_midi_clip": "/write_clip", "edit_midi_notes": "/clip_note_tools",
          "vary_midi_clip": "/clip_variation", "confirm_sample": "/sample_confirm",
          "insert_device": "/insert_effect", "eq": "/eq_tools",
          "manage_tracks": "/track_management", "manage_scenes": "/scene", "edit_arrangement": "/arrangement_tools"}


def prepare_request(tool: str, fields: dict[str, Any]):
    model = MODELS[tool].model_validate(fields)
    payload = model.model_dump(exclude_none=True)
    execution = payload.pop("execution", "inspect")
    read_only = isinstance(model, ConfirmSample) or (
        isinstance(model, EqPreset) and model.action == "list_presets") or (
        isinstance(model, ManageScenes) and model.action == "list")
    if execution == "auto":
        execution = "inspect" if read_only else "apply"
    if execution == "apply" and not payload.get("plan_token"):
        payload["direct_apply"] = True
    if isinstance(model, ConfirmSample) and model.intended_path and not Path(model.intended_path).is_file():
        raise ValueError("Intended sample file no longer exists; refresh its catalog location")
    if isinstance(model, InsertDevice):
        from .inserter import resolve_device, resolve_effect
        resolver = resolve_effect if model.kind == "effect" else resolve_device
        payload["device"] = resolver(model.device)
        if model.kind == "instrument" and model.section != "track":
            raise ValueError("Instruments require an ordinary MIDI track")
    route = ROUTES[tool]
    if isinstance(model, WriteMidi) and model.location == "arrangement":
        route = "/write_arrangement_clip"
    # Legacy handlers reject this unknown action/missing target instead of ignoring
    # a new guard and applying the ordinary legacy request.
    wire = {"mcp_safe": 1, "action": "mcp_creative_v1", "creative": payload}
    if len(json.dumps(wire, ensure_ascii=False).encode("utf-8")) > 48000:
        raise ValueError("Creative payload exceeds 48000 bytes; use fewer notes in a shorter Clip")
    return route, wire, execution == "apply"


def search_sounds(fields: dict[str, Any], *, database_path=None):
    from .sound_catalog_db import LOCAL_DATABASE, search_database
    options = SearchSounds.model_validate(fields).model_dump(exclude_none=True)
    path = Path(database_path or LOCAL_DATABASE)
    if not path.is_file():
        return {"ok": False, "error": "Local SQLite sound catalog missing; run the documented catalog scan explicitly"}
    reference = options.pop("reference_audio", None)
    candidate_limit = options.pop("candidate_limit")
    if reference:
        from .audio_similarity import rank_sounds
        return rank_sounds(path, reference, candidate_limit=candidate_limit, **options)
    rows = search_database(path, **options)
    good, missing = [], []
    for row in rows:
        if not Path(row["path"]).is_file():
            missing.append(row["path"])
        else:
            good.append({k: v for k, v in row.items() if k in {
                "id", "name", "path", "kind", "pack", "duration_seconds", "estimated_bpm", "estimated_key", "tags",
                "bpm_confidence", "key_confidence", "root_note", "root_note_confidence", "is_loop", "loop_confidence",
                "primary_device", "rack_type", "load_mode", "agent_control", "auto_insert"}})
    return {"ok": True, "read_only": True, "resources": good, "missing_paths": missing,
            "warning": "Discovery is not insertion or loaded-state confirmation; missing paths require a targeted refresh",
            "database": str(path)}


def register_creative_tools(mcp, service_getter):
    from mcp.types import ToolAnnotations
    write = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)
    read = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

    @mcp.tool(annotations=write)
    def ableton_write_midi_clip(request: WriteMidi) -> dict[str, Any]:
        """Create MIDI in an empty slot or non-overlapping range. Auto writes directly; inspect is optional."""
        return service_getter().creative("write_midi_clip", request.model_dump(exclude_none=True))

    @mcp.tool(annotations=write)
    def ableton_edit_midi_notes(request: EditMidi) -> dict[str, Any]:
        """Shift/quantize/scale velocities in Clip-local beats, preserving original note IDs. Max 512 notes."""
        return service_getter().creative("edit_midi_notes", request.model_dump(exclude_none=True))

    @mcp.tool(annotations=write)
    def ableton_vary_midi_clip(request: VaryMidi) -> dict[str, Any]:
        """Create a new Arrangement note-data variation; source untouched. Does not copy envelopes or MPE."""
        return service_getter().creative("vary_midi_clip", request.model_dump(exclude_none=True))

    @mcp.tool(annotations=read)
    def ableton_search_sounds(request: SearchSounds) -> dict[str, Any]:
        """Search catalog; optional reference_audio ranks a bounded pool using cached waveform features. Writes local cache only; never loads or plays sounds."""
        return search_sounds(request.model_dump(exclude_none=True))

    @mcp.tool(annotations=read)
    def ableton_confirm_sample(request: ConfirmSample) -> dict[str, Any]:
        """Read a manually loaded Simpler sample or specific Drum Rack pad. Direct track device IDs only."""
        return service_getter().creative("confirm_sample", request.model_dump(exclude_none=True))

    @mcp.tool(annotations=write)
    def ableton_insert_device(request: InsertDevice) -> dict[str, Any]:
        """Insert one whitelisted native instrument/effect. No plugin/preset loading or duplicate instruments."""
        return service_getter().creative("insert_device", request.model_dump(exclude_none=True))

    @mcp.tool(annotations=write)
    def ableton_eq(request: EqPreset) -> dict[str, Any]:
        """List presets or directly apply one to a stable EQ Eight device. Returns internal and UI values; inspect is optional."""
        return service_getter().creative("eq", request.model_dump(exclude_none=True))

    @mcp.tool(annotations=write)
    def ableton_manage_tracks(request: ManageTracks) -> dict[str, Any]:
        """Create, rename/color, or delete_track directly by stable ID. Deletion requires explicit user intent; rejects Group/Return/Main, the Hub host and last track. Inspect is optional. Never arm or move tracks."""
        return service_getter().creative("manage_tracks", request.model_dump(exclude_none=True))

    @mcp.tool(annotations=write)
    def ableton_manage_scenes(request: ManageScenes) -> dict[str, Any]:
        """List one scene page, append, duplicate, rename or fire by stable ID. Writes apply directly; firing requires user playback intent. Inspect is optional."""
        return service_getter().creative("manage_scenes", request.model_dump(exclude_none=True))

    @mcp.tool(annotations=read)
    def ableton_scan_automation(request: AutomationScan) -> dict[str, Any]:
        """Read paged device automation states, including nested Racks. Default active/overridden only; no mixer/envelope breakpoints. Continue with returned token and unchanged scope. Items are per response; counts cumulative. Stop on warnings/errors; re-read before writes."""
        return service_getter().scan_automation(request.model_dump(exclude_none=True))

    @mcp.tool(annotations=write)
    def ableton_edit_arrangement(request: EditArrangement) -> dict[str, Any]:
        """Direct same-track audio move or MIDI note-data copy to an empty Arrangement range. Stable track/clip IDs required; inspect token optional. Moves can replace the source ID; return ID is authoritative. No cross-track moves, replacement or envelope copying."""
        return service_getter().creative("edit_arrangement", request.model_dump(exclude_none=True))

    @mcp.tool(annotations=read)
    def ableton_read_saved_automation(request: SavedAutomationRequest) -> dict[str, Any]:
        """Read Arrangement curve nodes from an explicit saved .als path, NOT live state. List envelope keys then read a key/range. File IDs are never runtime IDs. Bar references assume constant caller meter (default 4/4). No file/Live writes or UDP; save in Live manually for fresh data."""
        try:
            return _saved_automation.read(request.model_dump(exclude_none=True))
        except (OSError, ValueError, EOFError) as error:
            return {"ok": False, "read_only": True, "source_kind": "saved_als", "error": str(error)}

    @mcp.tool(annotations=read)
    def ableton_read_saved_set(request: SavedSetRequest) -> dict[str, Any]:
        """Read the legacy complete saved-ALS scheme locally: tracks/devices, scenes,
        audio clips, MIDI clips/notes, automation and GroovePool. It never calls
        Hub, writes Live, or treats XML IDs as runtime IDs."""
        try:
            fields = request.model_dump(exclude_none=True)
            path = fields.pop("als_path")
            return read_saved_set(path, **fields)
        except (OSError, ValueError, EOFError, RuntimeError) as error:
            return {
                "ok": False,
                "read_only": True,
                "source_kind": "saved_als",
                "error": str(error),
            }

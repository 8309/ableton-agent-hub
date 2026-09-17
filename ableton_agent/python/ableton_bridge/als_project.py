from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
import xml.etree.ElementTree as ET

from .als_midi import _bool_value, _clip_metadata, _load_live_set
from .als_snapshot import (
    DEFAULT_MAX_UNCOMPRESSED_BYTES,
    AlsSnapshotError,
    TRACK_TAGS,
    _float_value,
    _int_value,
    _normalized_windows_path,
    _track_name,
    _value,
)


DEFAULT_SECTIONS = {
    "tracks",
    "scenes",
    "audio_clips",
    "automation",
    "grooves",
}
ALL_SECTIONS = DEFAULT_SECTIONS
DEFAULT_MAX_PARAMETERS_PER_DEVICE = 256
DEFAULT_MAX_AUTOMATION_EVENTS = 4096
DEFAULT_MAX_AUDIO_CLIPS = 512
DEFAULT_MAX_WARP_MARKERS_PER_CLIP = 512
DEFAULT_MAX_DEVICES = 1024


class AlsProjectError(RuntimeError):
    pass


def _coerce(value: str | None) -> Any:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _target_id(parameter: ET.Element | None) -> int | None:
    target = parameter.find("AutomationTarget") if parameter is not None else None
    return _int_value(target.attrib.get("Id", "")) if target is not None else None


def _parameter(parameter: ET.Element | None) -> dict[str, Any] | None:
    if parameter is None or parameter.find("Manual") is None:
        return None
    return {
        "internal_value": _coerce(_value(parameter, "Manual")),
        "minimum": _coerce(_value(parameter, "MidiControllerRange/Min")),
        "maximum": _coerce(_value(parameter, "MidiControllerRange/Max")),
        "automation_target_id": _target_id(parameter),
        "lom_id": _int_value(_value(parameter, "LomId")),
    }


def _read_routing(track: ET.Element) -> dict[str, Any]:
    result = {}
    for key, tag in (
        ("audio_input", "AudioInputRouting"),
        ("midi_input", "MidiInputRouting"),
        ("audio_output", "AudioOutputRouting"),
        ("midi_output", "MidiOutputRouting"),
    ):
        node = track.find(f"./DeviceChain/{tag}")
        if node is None:
            continue
        result[key] = {
            "target": _value(node, "Target"),
            "upper_display": _value(node, "UpperDisplayString"),
            "lower_display": _value(node, "LowerDisplayString"),
            "mpe_zone_type": _int_value(_value(node, "MpeSettings/ZoneType")),
            "mpe_first_channel": _int_value(
                _value(node, "MpeSettings/FirstNoteChannel")
            ),
            "mpe_last_channel": _int_value(
                _value(node, "MpeSettings/LastNoteChannel")
            ),
        }
    return result


def _read_mixer(track: ET.Element) -> dict[str, Any]:
    mixer = track.find("./DeviceChain/Mixer")
    if mixer is None:
        return {"present": False}
    sends = []
    for holder in mixer.findall("./Sends/TrackSendHolder"):
        sends.append(
            {
                "return_index": _int_value(holder.attrib.get("Id", "")),
                "enabled_by_user": _bool_value(_value(holder, "EnabledByUser"), True),
                "send": _parameter(holder.find("Send")),
            }
        )
    return {
        "present": True,
        "on": _parameter(mixer.find("On")),
        "activator": _parameter(mixer.find("Speaker")),
        "saved_solo": _bool_value(_value(mixer, "SoloSink")),
        "pan_mode": _int_value(_value(mixer, "PanMode")),
        "pan": _parameter(mixer.find("Pan")),
        "split_stereo_pan_left": _parameter(mixer.find("SplitStereoPanL")),
        "split_stereo_pan_right": _parameter(mixer.find("SplitStereoPanR")),
        "volume": _parameter(mixer.find("Volume")),
        "crossfade_assignment": _parameter(mixer.find("CrossFadeState")),
        "tempo": _parameter(mixer.find("Tempo")),
        "time_signature": _parameter(mixer.find("TimeSignature")),
        "global_groove_amount": _parameter(mixer.find("GlobalGrooveAmount")),
        "crossfader": _parameter(mixer.find("CrossFade")),
        "sends": sends,
        "is_folded": _bool_value(_value(mixer, "IsFolded")),
        "session_width": _float_value(_value(mixer, "ViewStateSessionTrackWidth")),
    }


def _device_parameters(device: ET.Element, maximum: int) -> dict[str, Any]:
    parameters = []
    for child in list(device):
        parsed = _parameter(child)
        if parsed is None:
            continue
        parameters.append({"name": child.tag, **parsed})
    return {
        "count": len(parameters),
        "returned_count": min(len(parameters), maximum),
        "has_more": len(parameters) > maximum,
        "items": parameters[:maximum],
    }


def _device_preset(device: ET.Element) -> dict[str, Any] | None:
    reference = device.find("./LastPresetRef/Value/*/FileRef")
    if reference is None:
        return None
    return {
        "path": _value(reference, "Path"),
        "relative_path": _value(reference, "RelativePath"),
        "pack_name": _value(reference, "LivePackName"),
        "pack_id": _value(reference, "LivePackId"),
    }


def _plugin_metadata(device: ET.Element) -> dict[str, Any] | None:
    values: dict[str, Any] = {}
    state_bytes = 0
    state_hash = None
    for node in device.iter():
        if node is device:
            continue
        lowered = node.tag.lower()
        is_plugin_field = (
            "plugin" in lowered
            or "vst" in lowered
            or "audiounit" in lowered
            or lowered.startswith("auplugin")
        )
        if not is_plugin_field:
            continue
        if "value" in node.attrib and len(values) < 64:
            values[node.tag] = _coerce(node.attrib["Value"])
        text = (node.text or "").strip()
        if text and len(text) > 128:
            state_bytes += len(text.encode("utf-8"))
            state_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if not values and not state_bytes and not any(
        marker in device.tag.lower() for marker in ("plugin", "vst", "audiounit")
    ):
        return None
    return {
        "descriptor_values": values,
        "opaque_state_bytes": state_bytes,
        "opaque_state_sha256": state_hash,
        "opaque_state_omitted": state_bytes > 0,
    }


def _nested_device_nodes(device: ET.Element) -> Iterable[tuple[str, ET.Element]]:
    branches = device.find("Branches")
    if branches is None:
        return
    for branch in list(branches):
        branch_name = (
            _value(branch, "Name/EffectiveName")
            or _value(branch, "Name/UserName")
            or _value(branch, "Name")
            or f"{branch.tag}:{branch.attrib.get('Id', '')}"
        )
        chain = branch.find("DeviceChain")
        if chain is None:
            continue
        for chain_node in list(chain):
            devices = chain_node.find("Devices")
            if devices is None:
                continue
            for child in list(devices):
                yield branch_name, child


def _read_device(
    device: ET.Element,
    *,
    chain_path: list[str],
    include_parameters: bool,
    max_parameters: int,
    budget: dict[str, int],
) -> dict[str, Any]:
    budget["seen"] += 1
    item = {
        "device_type": device.tag,
        "file_id": _int_value(device.attrib.get("Id", "")),
        "lom_id": _int_value(_value(device, "LomId")),
        "user_name": _value(device, "UserName"),
        "annotation": _value(device, "Annotation"),
        "on": _parameter(device.find("On")),
        "is_folded": _bool_value(_value(device, "IsFolded")),
        "is_expanded": _bool_value(_value(device, "IsExpanded")),
        "chain_path": chain_path,
        "preset": _device_preset(device),
        "plugin": _plugin_metadata(device),
    }
    if include_parameters:
        item["parameters"] = _device_parameters(device, max_parameters)
    children = []
    for branch_name, child in _nested_device_nodes(device):
        if budget["returned"] >= budget["maximum"]:
            budget["truncated"] = 1
            break
        budget["returned"] += 1
        children.append(
            _read_device(
                child,
                chain_path=[*chain_path, branch_name],
                include_parameters=include_parameters,
                max_parameters=max_parameters,
                budget=budget,
            )
        )
    item["nested_devices"] = children
    return item


def _read_track_devices(
    track: ET.Element,
    *,
    include_parameters: bool,
    max_parameters: int,
    budget: dict[str, int],
) -> list[dict[str, Any]]:
    devices = track.find("./DeviceChain/DeviceChain/Devices")
    if devices is None:
        return []
    result = []
    for device in list(devices):
        if budget["returned"] >= budget["maximum"]:
            budget["truncated"] = 1
            break
        budget["returned"] += 1
        result.append(
            _read_device(
                device,
                chain_path=[],
                include_parameters=include_parameters,
                max_parameters=max_parameters,
                budget=budget,
            )
        )
    return result


def _read_track(
    track: ET.Element,
    order: int,
    *,
    include_parameters: bool,
    max_parameters: int,
    device_budget: dict[str, int],
) -> dict[str, Any]:
    name, user_name, effective_name = _track_name(track)
    return {
        "order": order,
        "track_type": track.tag,
        "file_id": _int_value(track.attrib.get("Id", "")),
        "lom_id": _int_value(_value(track, "LomId")),
        "name": name,
        "user_name": user_name,
        "effective_name": effective_name,
        "color": _int_value(_value(track, "Color")),
        "parent_group_id": _int_value(_value(track, "TrackGroupId")),
        "track_unfolded": _bool_value(_value(track, "TrackUnfolded")),
        "track_delay": _float_value(_value(track, "TrackDelay/Value")),
        "monitoring": _int_value(
            _value(track, "DeviceChain/MainSequencer/MonitoringEnum")
        ),
        "routing": _read_routing(track),
        "mixer": _read_mixer(track),
        "devices": _read_track_devices(
            track,
            include_parameters=include_parameters,
            max_parameters=max_parameters,
            budget=device_budget,
        ),
    }


def _read_follow_action(node: ET.Element) -> dict[str, Any]:
    action = node.find("FollowAction")
    return {
        "enabled": _bool_value(_value(action, "FollowActionEnabled")),
        "follow_time": _float_value(_value(action, "FollowTime")),
        "loop_iterations": _int_value(_value(action, "LoopIterations")),
        "action_a": _int_value(_value(action, "FollowActionA")),
        "action_b": _int_value(_value(action, "FollowActionB")),
        "chance_a": _float_value(_value(action, "FollowChanceA")),
        "chance_b": _float_value(_value(action, "FollowChanceB")),
        "jump_index_a": _int_value(_value(action, "JumpIndexA")),
        "jump_index_b": _int_value(_value(action, "JumpIndexB")),
    }


def _read_scenes(live_set: ET.Element) -> list[dict[str, Any]]:
    result = []
    for index, scene in enumerate(live_set.findall("./Scenes/Scene")):
        result.append(
            {
                "index": index,
                "file_id": _int_value(scene.attrib.get("Id", "")),
                "lom_id": _int_value(_value(scene, "LomId")),
                "name": _value(scene, "Name"),
                "annotation": _value(scene, "Annotation"),
                "color": _int_value(_value(scene, "Color")),
                "tempo": _float_value(_value(scene, "Tempo")),
                "tempo_enabled": _bool_value(_value(scene, "IsTempoEnabled")),
                "time_signature_id": _int_value(_value(scene, "TimeSignatureId")),
                "time_signature_enabled": _bool_value(
                    _value(scene, "IsTimeSignatureEnabled")
                ),
                "follow_action": _read_follow_action(scene),
            }
        )
    return result


def _file_reference(reference: ET.Element | None) -> dict[str, Any] | None:
    if reference is None:
        return None
    path = _value(reference, "Path")
    normalized = _normalized_windows_path(path)
    return {
        "path": path,
        "relative_path": _value(reference, "RelativePath"),
        "pack_name": _value(reference, "LivePackName"),
        "pack_id": _value(reference, "LivePackId"),
        "original_file_size": _int_value(_value(reference, "OriginalFileSize")),
        "exists": normalized.exists() if normalized is not None and normalized.is_absolute() else None,
    }


def _read_clip_envelopes(clip: ET.Element, maximum: int) -> dict[str, Any]:
    envelopes = []
    container = clip.find("./Envelopes/Envelopes")
    if container is not None:
        for envelope in list(container)[:maximum]:
            envelopes.append(_read_envelope(envelope, {}, maximum))
    return {
        "count": len(container) if container is not None else 0,
        "returned_count": len(envelopes),
        "has_more": container is not None and len(container) > maximum,
        "items": envelopes,
    }


def _read_audio_clip(
    track: ET.Element,
    order: int,
    clip: ET.Element,
    *,
    source: str,
    scene_index: int | None,
    max_warp_markers: int,
    max_automation_events: int,
) -> dict[str, Any]:
    name, _, _ = _track_name(track)
    markers = [
        {
            "file_id": _int_value(marker.attrib.get("Id", "")),
            "seconds": _float_value(marker.attrib.get("SecTime", "")),
            "beat": _float_value(marker.attrib.get("BeatTime", "")),
        }
        for marker in clip.findall("./WarpMarkers/WarpMarker")
    ]
    start = _float_value(_value(clip, "CurrentStart"))
    end = _float_value(_value(clip, "CurrentEnd"))
    return {
        "source": source,
        "track_order": order,
        "track_file_id": _int_value(track.attrib.get("Id", "")),
        "track_name": name,
        "scene_index": scene_index,
        "clip_file_id": _int_value(clip.attrib.get("Id", "")),
        "clip_lom_id": _int_value(_value(clip, "LomId")),
        "clip_name": _value(clip, "Name"),
        "color": _int_value(_value(clip, "Color")),
        "start": start,
        "end": end,
        "length": end - start if start is not None and end is not None else None,
        "loop": {
            "start": _float_value(_value(clip, "Loop/LoopStart")),
            "end": _float_value(_value(clip, "Loop/LoopEnd")),
            "start_relative": _float_value(_value(clip, "Loop/StartRelative")),
            "enabled": _bool_value(_value(clip, "Loop/LoopOn")),
        },
        **_clip_metadata(clip),
        "sample": _file_reference(clip.find("./SampleRef/FileRef")),
        "is_warped": _bool_value(_value(clip, "IsWarped")),
        "warp_mode": _int_value(_value(clip, "WarpMode")),
        "pitch_coarse": _float_value(_value(clip, "PitchCoarse")),
        "pitch_fine": _float_value(_value(clip, "PitchFine")),
        "sample_volume": _float_value(_value(clip, "SampleVolume")),
        "fades": {
            "fade_in": _float_value(_value(clip, "Fades/FadeInLength")),
            "fade_out": _float_value(_value(clip, "Fades/FadeOutLength")),
        },
        "warp_marker_count": len(markers),
        "warp_markers_has_more": len(markers) > max_warp_markers,
        "warp_markers": markers[:max_warp_markers],
        "clip_envelopes": _read_clip_envelopes(clip, max_automation_events),
    }


def _read_audio_clips(
    live_set: ET.Element,
    maximum: int,
    max_warp_markers: int,
    max_automation_events: int,
) -> dict[str, Any]:
    clips = []
    tracks = live_set.find("Tracks")
    if tracks is not None:
        for order, track in enumerate(list(tracks)):
            if track.tag != "AudioTrack":
                continue
            for clip in track.findall(
                "./DeviceChain/MainSequencer/Sample/ArrangerAutomation/Events/AudioClip"
            ):
                clips.append(
                    _read_audio_clip(
                        track,
                        order,
                        clip,
                        source="arrangement",
                        scene_index=None,
                        max_warp_markers=max_warp_markers,
                        max_automation_events=max_automation_events,
                    )
                )
            for slot in track.findall("./DeviceChain/MainSequencer/ClipSlotList/ClipSlot"):
                clip = slot.find("./ClipSlot/Value/AudioClip")
                if clip is not None:
                    clips.append(
                        _read_audio_clip(
                            track,
                            order,
                            clip,
                            source="session",
                            scene_index=_int_value(slot.attrib.get("Id", "")),
                            max_warp_markers=max_warp_markers,
                            max_automation_events=max_automation_events,
                        )
                    )
    clips.sort(key=lambda item: (item["track_order"], item["source"], item["start"] or 0))
    return {
        "count": len(clips),
        "returned_count": min(len(clips), maximum),
        "has_more": len(clips) > maximum,
        "items": clips[:maximum],
    }


def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _ancestor(
    node: ET.Element,
    parents: dict[ET.Element, ET.Element],
    predicate,
) -> ET.Element | None:
    current = parents.get(node)
    while current is not None:
        if predicate(current):
            return current
        current = parents.get(current)
    return None


def _target_descriptors(root: ET.Element) -> dict[int, dict[str, Any]]:
    parents = _parent_map(root)
    result = {}
    for parameter in root.iter():
        target = parameter.find("AutomationTarget")
        if target is None:
            continue
        target_id = _int_value(target.attrib.get("Id", ""))
        if target_id is None:
            continue
        track = _ancestor(
            parameter,
            parents,
            lambda item: item.tag in TRACK_TAGS or item.tag == "MainTrack",
        )
        device = _ancestor(
            parameter,
            parents,
            lambda item: parents.get(item) is not None
            and parents[item].tag == "Devices",
        )
        track_name = "Main" if track is not None and track.tag == "MainTrack" else ""
        if track is not None and track.tag != "MainTrack":
            track_name = _track_name(track)[0]
        result[target_id] = {
            "target_id": target_id,
            "track_section": "main" if track is not None and track.tag == "MainTrack" else "tracks",
            "track_file_id": _int_value(track.attrib.get("Id", "")) if track is not None else None,
            "track_name": track_name,
            "device_type": device.tag if device is not None else None,
            "device_file_id": _int_value(device.attrib.get("Id", "")) if device is not None else None,
            "parameter": parameter.tag,
            "manual_value": _coerce(_value(parameter, "Manual")),
        }
    return result


def _read_event(event: ET.Element) -> dict[str, Any]:
    return {
        "type": event.tag,
        "attributes": {key: _coerce(value) for key, value in event.attrib.items()},
        "values": {
            child.tag: _coerce(child.attrib.get("Value"))
            for child in list(event)
            if "Value" in child.attrib
        },
    }


def _read_envelope(
    envelope: ET.Element,
    targets: dict[int, dict[str, Any]],
    maximum: int,
) -> dict[str, Any]:
    pointee = _int_value(_value(envelope, "EnvelopeTarget/PointeeId"))
    events_node = envelope.find("./Automation/Events")
    events = list(events_node) if events_node is not None else []
    parsed = [_read_event(event) for event in events[:maximum]]
    float_points = [
        event["attributes"]
        for event in parsed
        if event["type"] == "FloatEvent"
        and "Time" in event["attributes"]
        and "Value" in event["attributes"]
    ]
    has_value_change = any(
        left.get("Value") != right.get("Value")
        for left, right in zip(float_points, float_points[1:])
    )
    return {
        "file_id": _int_value(envelope.attrib.get("Id", "")),
        "target_id": pointee,
        "target": targets.get(pointee),
        "event_count": len(events),
        "returned_event_count": len(parsed),
        "events_has_more": len(events) > maximum,
        "has_continuous_value_change": has_value_change,
        "events": parsed,
    }


def _read_automation(
    root: ET.Element,
    live_set: ET.Element,
    maximum: int,
) -> dict[str, Any]:
    targets = _target_descriptors(root)
    envelopes = []
    remaining = maximum
    for envelope in live_set.findall(".//AutomationEnvelopes/Envelopes/AutomationEnvelope"):
        parsed = _read_envelope(envelope, targets, max(0, remaining))
        remaining -= parsed["returned_event_count"]
        envelopes.append(parsed)
    tempo = [
        envelope
        for envelope in envelopes
        if envelope.get("target")
        and envelope["target"].get("track_section") == "main"
        and envelope["target"].get("parameter") == "Tempo"
    ]
    return {
        "target_count": len(targets),
        "envelope_count": len(envelopes),
        "returned_event_count": maximum - max(0, remaining),
        "events_has_more": remaining < 0
        or any(envelope["events_has_more"] for envelope in envelopes),
        "tempo_envelopes": tempo,
        "items": envelopes,
    }


def _read_grooves(live_set: ET.Element) -> dict[str, Any]:
    grooves = []
    for groove in live_set.findall("./GroovePool/Grooves/Groove"):
        grooves.append(
            {
                "file_id": _int_value(groove.attrib.get("Id", "")),
                "lom_id": _int_value(_value(groove, "LomId")),
                "name": _value(groove, "Name"),
                "grid": _int_value(_value(groove, "Grid")),
                "quantization_amount": _float_value(_value(groove, "QuantizationAmount")),
                "timing_amount": _float_value(_value(groove, "TimingAmount")),
                "random_amount": _float_value(_value(groove, "RandomAmount")),
                "velocity_amount": _float_value(_value(groove, "VelocityAmount")),
            }
        )
    return {
        "default_groove_id": _int_value(_value(live_set, "GroovePool/DefaultGrooveId")),
        "count": len(grooves),
        "items": grooves,
    }


def read_als_project(
    path: str | Path,
    *,
    sections: set[str] | None = None,
    include_device_parameters: bool = False,
    max_parameters_per_device: int = DEFAULT_MAX_PARAMETERS_PER_DEVICE,
    max_automation_events: int = DEFAULT_MAX_AUTOMATION_EVENTS,
    max_audio_clips: int = DEFAULT_MAX_AUDIO_CLIPS,
    max_warp_markers_per_clip: int = DEFAULT_MAX_WARP_MARKERS_PER_CLIP,
    max_devices: int = DEFAULT_MAX_DEVICES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> dict[str, Any]:
    selected = set(sections or DEFAULT_SECTIONS)
    unknown = selected - ALL_SECTIONS
    if unknown:
        raise AlsProjectError(f"Unknown sections: {', '.join(sorted(unknown))}")
    for label, value in (
        ("max_parameters_per_device", max_parameters_per_device),
        ("max_automation_events", max_automation_events),
        ("max_audio_clips", max_audio_clips),
        ("max_warp_markers_per_clip", max_warp_markers_per_clip),
        ("max_devices", max_devices),
    ):
        if value < 1:
            raise AlsProjectError(f"{label} must be positive")

    _, _, _, root, live_set, source_info, warnings = _load_live_set(
        path, max_uncompressed_bytes
    )
    result: dict[str, Any] = {
        "ok": True,
        "read_only": True,
        "source": source_info,
        "format": {
            "major_version": root.attrib.get("MajorVersion", ""),
            "minor_version": root.attrib.get("MinorVersion", ""),
            "creator": root.attrib.get("Creator", ""),
            "revision": root.attrib.get("Revision", ""),
        },
        "sections": sorted(selected),
        "warnings": [
            *warnings,
            "Internal values are preserved exactly; this reader does not claim Live UI formatting.",
            "XML file IDs are not Live runtime IDs and cannot authorize Hub writes.",
        ],
    }
    if "tracks" in selected:
        device_budget = {"seen": 0, "returned": 0, "maximum": max_devices, "truncated": 0}
        tracks = []
        tracks_node = live_set.find("Tracks")
        if tracks_node is not None:
            for order, track in enumerate(list(tracks_node)):
                if track.tag in TRACK_TAGS:
                    tracks.append(
                        _read_track(
                            track,
                            order,
                            include_parameters=include_device_parameters,
                            max_parameters=max_parameters_per_device,
                            device_budget=device_budget,
                        )
                    )
        main = live_set.find("MainTrack")
        result["tracks"] = tracks
        result["main_track"] = (
            _read_track(
                main,
                len(tracks),
                include_parameters=include_device_parameters,
                max_parameters=max_parameters_per_device,
                device_budget=device_budget,
            )
            if main is not None
            else None
        )
        result["device_read"] = device_budget
    if "scenes" in selected:
        result["scenes"] = _read_scenes(live_set)
    if "audio_clips" in selected:
        result["audio_clips"] = _read_audio_clips(
            live_set,
            max_audio_clips,
            max_warp_markers_per_clip,
            max_automation_events,
        )
    if "automation" in selected:
        result["automation"] = _read_automation(
            root, live_set, max_automation_events
        )
    if "grooves" in selected:
        result["grooves"] = _read_grooves(live_set)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read extended static project structure from a saved ALS file"
    )
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--sections",
        default=",".join(sorted(DEFAULT_SECTIONS)),
        help="Comma-separated: tracks,scenes,audio_clips,automation,grooves",
    )
    parser.add_argument("--include-device-parameters", action="store_true")
    parser.add_argument("--max-parameters-per-device", type=int, default=256)
    parser.add_argument("--max-automation-events", type=int, default=4096)
    parser.add_argument("--max-audio-clips", type=int, default=512)
    parser.add_argument("--max-warp-markers-per-clip", type=int, default=512)
    parser.add_argument("--max-devices", type=int, default=1024)
    parser.add_argument("--max-uncompressed-mb", type=int, default=128)
    args = parser.parse_args()
    try:
        result = read_als_project(
            args.path,
            sections={item.strip() for item in args.sections.split(",") if item.strip()},
            include_device_parameters=args.include_device_parameters,
            max_parameters_per_device=args.max_parameters_per_device,
            max_automation_events=args.max_automation_events,
            max_audio_clips=args.max_audio_clips,
            max_warp_markers_per_clip=args.max_warp_markers_per_clip,
            max_devices=args.max_devices,
            max_uncompressed_bytes=args.max_uncompressed_mb * 1024 * 1024,
        )
    except (AlsProjectError, AlsSnapshotError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), flush=True)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

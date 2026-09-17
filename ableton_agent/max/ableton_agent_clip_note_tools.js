autowatch = 1;
include("ableton_agent_creative_control.js");
inlets = 1;
outlets = 1;

include("ableton_agent_read_core.js");

var MAX_DETAIL_NOTES = 4096;
var MAX_CLIP_METADATA = 512;

function prepareCreativeClipNoteTools(p) {
    if (["shift_notes", "quantize_notes", "scale_velocity"].indexOf(p.action)<0) { throw new Error("Unsupported safe note action"); }
    var t = AgentCreative.track(p), c = AgentCreative.clip(t, p.clip_id, false);
    var before = AgentCreative.notes(c), after = JSON.parse(JSON.stringify(before)), changes = [];
    var length = Number(AgentCreative.value(c.get("length")));
    var start = p.start === undefined ? 0 : p.start, end = p.end === undefined ? length : p.end;
    if (!(end>start)) { throw new Error("Invalid note window"); }
    for (var i=0; i<after.length; i+=1) {
        var n=after[i];
        if (n.start_time<start || n.start_time>=end) { continue; }
        if (p.action === "shift_notes") { n.start_time += p.beats; }
        if (p.action === "quantize_notes") { n.start_time = Math.round(n.start_time/p.grid)*p.grid; }
        if (p.action === "scale_velocity") { n.velocity = Math.max(1,Math.min(127,n.velocity*p.factor)); }
        if (!isFinite(n.start_time) || n.start_time<0 || n.start_time>=length || !isFinite(n.velocity)) { throw new Error("Edited note outside supported range"); }
        if (JSON.stringify(n)!==JSON.stringify(before[i])) { changes.push(n); }
    }
    return {state:[before,length], plan:{track_id:t.id,clip_id:p.clip_id,changed_count:changes.length,
        range:[start,end],before_examples:before.slice(0,4),after_examples:after.slice(0,4)}, apply:function() {
        if (changes.length) { AgentCreative.writeNotes(c,changes,"apply_note_modifications"); }
        AgentCreative.checkNotes(after,AgentCreative.notes(c),true);
        return {clip_id:p.clip_id,changed_count:changes.length,verified:true,original_note_ids_preserved:true};
    }};
}


function list() {
    var args = arrayfromargs(arguments);
    handleClipNoteTools(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleClipNoteTools(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function valueOf(raw, fallback) {
    if (raw instanceof Array) {
        return raw.length ? raw[0] : fallback;
    }
    return raw === undefined || raw === null ? fallback : raw;
}


function idFrom(raw) {
    if (!(raw instanceof Array)) {
        return 0;
    }
    for (var index = 0; index < raw.length - 1; index += 1) {
        if (raw[index] === "id") {
            return Number(raw[index + 1]);
        }
    }
    return 0;
}


function idsFrom(raw) {
    var ids = [];
    if (!(raw instanceof Array)) {
        return ids;
    }
    for (var index = 0; index < raw.length; index += 1) {
        if (raw[index] === "id" && index + 1 < raw.length) {
            ids.push(Number(raw[index + 1]));
            index += 1;
        }
    }
    return ids;
}


function safeGet(api, propertyName, fallback) {
    try {
        return api.get(propertyName);
    } catch (_error) {
        return fallback;
    }
}


function parseNotes(raw) {
    if (raw instanceof Dict) {
        return JSON.parse(raw.stringify()).notes || [];
    }
    if (raw instanceof Array && raw.length >= 2 && String(raw[0]) === "dictionary") {
        var dict = new Dict(String(raw[1]));
        return JSON.parse(dict.stringify()).notes || [];
    }
    if (typeof raw === "string") {
        try {
            return JSON.parse(raw).notes || [];
        } catch (_error) {
            return [];
        }
    }
    return [];
}


function normalize(value) {
    return String(value || "").toLowerCase().replace(/^\s+|\s+$/g, "");
}


function noteNumber(note, key, fallback) {
    var value = Number(note[key]);
    return isFinite(value) ? value : fallback;
}


function noteForWrite(note) {
    return {
        pitch: Math.max(0, Math.min(127, Math.round(noteNumber(note, "pitch", 0)))),
        start_time: Math.max(0, noteNumber(note, "start_time", 0.0)),
        duration: Math.max(noteNumber(note, "duration", 0.0), 0.0001),
        velocity: Math.max(1, Math.min(127, Math.round(noteNumber(note, "velocity", 100)))),
        mute: note.mute ? 1 : 0,
        probability: note.probability === undefined ? 1.0 : noteNumber(note, "probability", 1.0)
    };
}


function noteSummary(note) {
    var start = noteNumber(note, "start_time", 0.0);
    return {
        pitch: Math.round(noteNumber(note, "pitch", 0)),
        start_time: start,
        duration: noteNumber(note, "duration", 0.0),
        velocity: Math.round(noteNumber(note, "velocity", 0)),
        mute: note.mute ? 1 : 0,
        bar: Math.floor(start / 4) + 1,
        beat: (start % 4) + 1
    };
}


function readClipNotes(clipId, fallbackLength) {
    var clip = new LiveAPI(function () {}, "id " + clipId);
    var isMidi = Boolean(Number(valueOf(clip.get("is_midi_clip"), 0)));
    var name = String(valueOf(clip.get("name"), ""));
    var length = Number(valueOf(safeGet(clip, "length", fallbackLength || 0.0), fallbackLength || 0.0));
    if (!isMidi) {
        throw new Error("Target clip is not a MIDI clip: " + name);
    }
    var raw = clip.call("get_notes_extended", 0, 128, 0.0, Math.max(length, 1.0));
    var notes = parseNotes(raw);
    if (notes.length > MAX_DETAIL_NOTES) {
        throw new Error("Too many notes in current clip; maximum is " + MAX_DETAIL_NOTES);
    }
    notes.sort(function (left, right) {
        var startDelta = noteNumber(left, "start_time", 0.0) - noteNumber(right, "start_time", 0.0);
        if (startDelta !== 0) {
            return startDelta;
        }
        return noteNumber(left, "pitch", 0) - noteNumber(right, "pitch", 0);
    });
    return {api: clip, id: clipId, name: name, length: length, notes: notes};
}


function readClipNotesWindow(clipId, fallbackLength, startBeat, lengthBeats) {
    var clip = new LiveAPI(function () {}, "id " + clipId);
    var isMidi = Boolean(Number(valueOf(clip.get("is_midi_clip"), 0)));
    var name = String(valueOf(clip.get("name"), ""));
    var length = Number(valueOf(safeGet(clip, "length", fallbackLength || 0.0), fallbackLength || 0.0));
    if (!isMidi) {
        throw new Error("Target clip is not a MIDI clip: " + name);
    }
    var start = Math.max(0, Number(startBeat || 0));
    var windowLength = Math.max(0.0001, Number(lengthBeats || Math.max(length, 1.0)));
    var raw = clip.call("get_notes_extended", 0, 128, start, windowLength);
    var notes = parseNotes(raw);
    if (notes.length > MAX_DETAIL_NOTES) {
        throw new Error("Too many notes in current clip window; maximum is " + MAX_DETAIL_NOTES);
    }
    notes.sort(function (left, right) {
        var startDelta = noteNumber(left, "start_time", 0.0) - noteNumber(right, "start_time", 0.0);
        if (startDelta !== 0) {
            return startDelta;
        }
        return noteNumber(left, "pitch", 0) - noteNumber(right, "pitch", 0);
    });
    return {api: clip, id: clipId, name: name, length: length, notes: notes};
}


function clipLength(clip) {
    var length = Number(valueOf(safeGet(clip, "length", 0.0), 0.0));
    if (length > 0) {
        return length;
    }
    var start = Number(valueOf(safeGet(clip, "start_time", safeGet(clip, "start_marker", 0.0)), 0.0));
    var end = Number(valueOf(safeGet(clip, "end_time", safeGet(clip, "end_marker", start)), start));
    return Math.max(0, end - start);
}


function clipSummary(clipId, source, trackIndex, trackName, extra) {
    var clip = new LiveAPI(function () {}, "id " + clipId);
    var detail = readClipNotes(clipId, clipLength(clip));
    detail.target = {
        source: source,
        track_index: trackIndex,
        track_name: trackName,
        clip_id: clipId,
        clip_name: detail.name
    };
    for (var key in extra || {}) {
        detail.target[key] = extra[key];
    }
    return detail;
}


function clipMetadata(clipId, source, trackIndex, trackId, trackName, extra) {
    var clip = new LiveAPI(function () {}, "id " + clipId);
    var isMidi = Boolean(Number(valueOf(safeGet(clip, "is_midi_clip", 0), 0)));
    var isAudio = Boolean(Number(valueOf(safeGet(clip, "is_audio_clip", 0), 0)));
    var start = Number(valueOf(safeGet(clip, "start_time", safeGet(clip, "start_marker", 0.0)), 0.0));
    var length = clipLength(clip);
    var end = Number(valueOf(safeGet(clip, "end_time", start + length), start + length));
    var record = {
        source: source,
        track_index: trackIndex,
        track_id: trackId,
        track_name: trackName,
        clip_id: clipId,
        clip_name: String(valueOf(safeGet(clip, "name", ""), "")),
        clip_type: isMidi ? "midi" : (isAudio ? "audio" : "unknown"),
        is_midi_clip: isMidi,
        is_audio_clip: isAudio,
        start_time: start,
        end_time: end,
        length: length
    };
    for (var key in extra || {}) {
        record[key] = extra[key];
    }
    return record;
}


function candidateFromDetail(detail, index) {
    var candidate = {
        candidate_index: index,
        source: detail.target.source,
        track_index: detail.target.track_index,
        track_name: detail.target.track_name,
        clip_id: detail.target.clip_id,
        clip_name: detail.target.clip_name,
        length: detail.length,
        note_count: detail.notes.length
    };
    if (detail.target.start_time !== undefined) {
        candidate.start_time = detail.target.start_time;
    }
    if (detail.target.scene_index !== undefined) {
        candidate.scene_index = detail.target.scene_index;
    }
    return candidate;
}


function candidateSummaries(candidates) {
    var out = [];
    for (var index = 0; index < candidates.length; index += 1) {
        out.push(candidateFromDetail(candidates[index], index));
    }
    return out;
}


function readDetailMidiClip() {
    var view = new LiveAPI(function () {}, "live_set view");
    var clipId = idFrom(view.get("detail_clip"));
    if (!clipId) {
        return null;
    }
    var detail = clipSummary(clipId, "detail_clip", null, "", {});
    return detail;
}


function resolveTrackByNameOrIndex(song, selector) {
    var trackIds = idsFrom(song.get("tracks"));
    if (selector === undefined || selector === null || selector === "") {
        return null;
    }
    if (typeof selector === "number") {
        if (selector < 0 || selector >= trackIds.length || Math.floor(selector) !== selector) {
            throw new Error("track_index is outside the ordinary track list");
        }
        var byIndex = new LiveAPI(function () {}, "id " + trackIds[selector]);
        return {index: selector, id: trackIds[selector], name: String(valueOf(byIndex.get("name"), "")), api: byIndex};
    }
    var wanted = normalize(selector);
    for (var index = 0; index < trackIds.length; index += 1) {
        var track = new LiveAPI(function () {}, "id " + trackIds[index]);
        var name = String(valueOf(track.get("name"), ""));
        if (normalize(name) === wanted) {
            return {index: index, id: trackIds[index], name: name, api: track};
        }
    }
    throw new Error("Track not found: " + selector);
}


function collectArrangementMidiClips(song, targetTrack, candidates, limit) {
    var trackIds = idsFrom(song.get("tracks"));
    for (var trackIndex = 0; trackIndex < trackIds.length; trackIndex += 1) {
        if (candidates.length >= limit) {
            break;
        }
        var track = new LiveAPI(function () {}, "id " + trackIds[trackIndex]);
        var trackName = String(valueOf(track.get("name"), ""));
        if (targetTrack && trackIndex !== targetTrack.index) {
            continue;
        }
        var clipIds = idsFrom(safeGet(track, "arrangement_clips", []));
        for (var clipIndex = 0; clipIndex < clipIds.length; clipIndex += 1) {
            if (candidates.length >= limit) {
                break;
            }
            var clip = new LiveAPI(function () {}, "id " + clipIds[clipIndex]);
            if (!Boolean(Number(valueOf(safeGet(clip, "is_midi_clip", 0), 0)))) {
                continue;
            }
            var start = Number(valueOf(safeGet(clip, "start_time", safeGet(clip, "start_marker", 0.0)), 0.0));
            var detail = clipSummary(clipIds[clipIndex], "arrangement", trackIndex, trackName, {start_time: start});
            candidates.push(detail);
        }
    }
}


function collectArrangementClipMetadata(song, targetTrack, references, tokenIds, limit) {
    var trackIds = idsFrom(song.get("tracks"));
    for (var trackIndex = 0; trackIndex < trackIds.length; trackIndex += 1) {
        if (references.length >= limit) {
            break;
        }
        var track = new LiveAPI(function () {}, "id " + trackIds[trackIndex]);
        var trackName = String(valueOf(track.get("name"), ""));
        if (targetTrack && trackIndex !== targetTrack.index) {
            continue;
        }
        var clipIds = idsFrom(safeGet(track, "arrangement_clips", []));
        for (var clipIndex = 0; clipIndex < clipIds.length; clipIndex += 1) {
            if (references.length >= limit) {
                break;
            }
            references.push({
                clip_id: clipIds[clipIndex],
                source: "arrangement",
                track_index: trackIndex,
                track_id: trackIds[trackIndex],
                track_name: trackName
            });
            tokenIds.push(clipIds[clipIndex]);
        }
    }
}


function collectSessionMidiClips(song, targetTrack, candidates, limit) {
    var trackIds = idsFrom(song.get("tracks"));
    var sceneIds = idsFrom(song.get("scenes"));
    for (var trackIndex = 0; trackIndex < trackIds.length; trackIndex += 1) {
        if (candidates.length >= limit) {
            break;
        }
        var track = new LiveAPI(function () {}, "id " + trackIds[trackIndex]);
        var trackName = String(valueOf(track.get("name"), ""));
        if (targetTrack && trackIndex !== targetTrack.index) {
            continue;
        }
        for (var sceneIndex = 0; sceneIndex < sceneIds.length; sceneIndex += 1) {
            if (candidates.length >= limit) {
                break;
            }
            var slot = new LiveAPI(function () {}, "live_set tracks " + trackIndex + " clip_slots " + sceneIndex);
            if (!Boolean(Number(valueOf(safeGet(slot, "has_clip", 0), 0)))) {
                continue;
            }
            var clip = new LiveAPI(function () {}, "live_set tracks " + trackIndex + " clip_slots " + sceneIndex + " clip");
            if (!Boolean(Number(valueOf(safeGet(clip, "is_midi_clip", 0), 0)))) {
                continue;
            }
            var clipId = Number(valueOf(clip.id, 0));
            if (!clipId) {
                clipId = idFrom(slot.get("clip"));
            }
            var detail = clipSummary(clipId, "session", trackIndex, trackName, {scene_index: sceneIndex});
            candidates.push(detail);
        }
    }
}


function collectSessionClipMetadata(song, targetTrack, references, tokenIds, limit) {
    var trackIds = idsFrom(song.get("tracks"));
    var sceneIds = idsFrom(song.get("scenes"));
    for (var trackIndex = 0; trackIndex < trackIds.length; trackIndex += 1) {
        if (references.length >= limit) {
            break;
        }
        var track = new LiveAPI(function () {}, "id " + trackIds[trackIndex]);
        var trackName = String(valueOf(track.get("name"), ""));
        if (targetTrack && trackIndex !== targetTrack.index) {
            continue;
        }
        for (var sceneIndex = 0; sceneIndex < sceneIds.length; sceneIndex += 1) {
            if (references.length >= limit) {
                break;
            }
            var slot = new LiveAPI(function () {}, "live_set tracks " + trackIndex + " clip_slots " + sceneIndex);
            if (!Boolean(Number(valueOf(safeGet(slot, "has_clip", 0), 0)))) {
                continue;
            }
            var clipId = idFrom(slot.get("clip"));
            if (!clipId) {
                continue;
            }
            references.push({
                clip_id: clipId,
                source: "session",
                track_index: trackIndex,
                track_id: trackIds[trackIndex],
                track_name: trackName,
                scene_index: sceneIndex
            });
            tokenIds.push(clipId);
        }
    }
}


function boundedClipMetadataRecord(reference, read) {
    var extra = {};
    if (reference.scene_index !== undefined) {
        extra.scene_index = reference.scene_index;
    }
    var record = clipMetadata(
        reference.clip_id,
        reference.source,
        reference.track_index,
        reference.track_id,
        reference.track_name,
        extra
    );
    var out = {};
    if (AbletonAgentReadCore.has(read, "identity")) {
        out.source = record.source;
        out.track_index = record.track_index;
        out.track_id = record.track_id;
        out.track_name = record.track_name;
        out.clip_id = record.clip_id;
        out.clip_name = record.clip_name;
        if (record.scene_index !== undefined) {
            out.scene_index = record.scene_index;
        }
    }
    if (AbletonAgentReadCore.has(read, "timing")) {
        out.start_time = record.start_time;
        out.end_time = record.end_time;
        out.length = record.length;
    }
    if (AbletonAgentReadCore.has(read, "type")) {
        out.clip_type = record.clip_type;
        out.is_midi_clip = record.is_midi_clip;
        out.is_audio_clip = record.is_audio_clip;
    }
    return out;
}


function clipMetadataCollection(payload) {
    var song = new LiveAPI(function () {}, "live_set");
    var targetMode = String(payload.target || "arrangement");
    var trackSelector = payload.track_index !== undefined ? payload.track_index : payload.track;
    if (trackSelector === undefined || trackSelector === null || trackSelector === "") {
        trackSelector = payload.track_name;
    }
    var targetTrack = resolveTrackByNameOrIndex(song, trackSelector);
    var references = [];
    var tokenIds = [];
    if (targetMode === "arrangement" || targetMode === "auto") {
        collectArrangementClipMetadata(song, targetTrack, references, tokenIds, MAX_CLIP_METADATA);
    }
    if (targetMode === "session" || targetMode === "auto") {
        collectSessionClipMetadata(song, targetTrack, references, tokenIds, MAX_CLIP_METADATA);
    }
    return {references: references, token_ids: tokenIds};
}


function scanClipMetadataBounded(payload) {
    var read = AbletonAgentReadCore.parse(payload, {
        max_limit: 64,
        max_cursor: MAX_CLIP_METADATA,
        allowed_projection: ["identity", "timing", "type"],
        default_projection: ["identity", "timing", "type"]
    });
    var collection = clipMetadataCollection(payload);
    var token = AbletonAgentReadCore.collectionToken(collection.token_ids);
    AbletonAgentReadCore.verifyCollection(read, token);
    if (read.cursor > collection.references.length) {
        throw new Error("read.cursor is outside the clip metadata collection");
    }
    var items = [];
    var scanned = 0;
    var partial = false;
    while (read.cursor + scanned < collection.references.length && scanned < read.limit) {
        if (scanned > 0 && AbletonAgentReadCore.budgetExceeded(read)) {
            partial = true;
            break;
        }
        items.push(boundedClipMetadataRecord(collection.references[read.cursor + scanned], read));
        scanned += 1;
    }
    var nextCursor = read.cursor + scanned;
    return {
        ok: true,
        dry_run: true,
        applied: false,
        action: "scan_clips_metadata",
        total_item_count: collection.references.length,
        items: items,
        read: AbletonAgentReadCore.metadata(read, {
            next_cursor: nextCursor,
            scanned_count: scanned,
            returned_count: items.length,
            has_more: nextCursor < collection.references.length,
            partial: partial,
            collection_token: token,
            warnings: []
        }),
        message: "Clip metadata scanned without reading note bodies"
    };
}


function readNotesByClipIdBounded(payload) {
    if (payload.clip_id === undefined || payload.clip_id === null) {
        throw new Error("clip_id is required for read_notes_by_clip_id");
    }
    var clipId = Number(payload.clip_id);
    if (!isFinite(clipId) || Math.floor(clipId) !== clipId || clipId <= 0) {
        throw new Error("clip_id must be a positive Live clip id");
    }
    var read = AbletonAgentReadCore.parse(payload, {
        max_limit: 64,
        max_cursor: 1000000,
        allowed_projection: ["notes"],
        default_projection: ["notes"],
        default_limit: 8
    });
    var clip = new LiveAPI(function () {}, "id " + clipId);
    var length = clipLength(clip);
    var token = AbletonAgentReadCore.collectionToken([clipId, Math.round(length * 10000)]);
    AbletonAgentReadCore.verifyCollection(read, token);
    if (read.cursor > Math.ceil(length)) {
        throw new Error("read.cursor is outside the clip note time range");
    }
    var windowEnd = Math.min(length, read.cursor + read.limit);
    var detail = readClipNotesWindow(clipId, length, read.cursor, Math.max(windowEnd - read.cursor, 0.0001));
    var notes = [];
    var selected = 0;
    for (var index = 0; index < detail.notes.length; index += 1) {
        if (selectedByRange(detail.notes[index], payload)) {
            notes.push(noteSummary(detail.notes[index]));
            selected += 1;
        }
    }
    var nextCursor = windowEnd >= length ? Math.ceil(length) : Math.ceil(windowEnd);
    return {
        ok: true,
        dry_run: true,
        applied: false,
        action: "read_notes_by_clip_id",
        target: {
            source: "direct_clip_id",
            clip_id: clipId,
            clip_name: detail.name
        },
        clip_name: detail.name,
        length: length,
        window_start: read.cursor,
        window_end: windowEnd,
        selected_count: selected,
        notes: notes,
        read: AbletonAgentReadCore.metadata(read, {
            next_cursor: nextCursor,
            scanned_count: 1,
            returned_count: notes.length,
            has_more: windowEnd < length,
            partial: false,
            collection_token: token,
            warnings: []
        }),
        message: "Target MIDI clip notes read directly by clip_id"
    };
}


function scanMidiClips(payload) {
    var song = new LiveAPI(function () {}, "live_set");
    var targetMode = String(payload.target || "auto");
    var limit = Math.max(1, Math.min(64, Math.round(Number(payload.candidate_limit || 16))));
    var trackSelector = payload.track_index !== undefined ? payload.track_index : payload.track;
    if (trackSelector === undefined || trackSelector === null || trackSelector === "") {
        trackSelector = payload.track_name;
    }
    var targetTrack = resolveTrackByNameOrIndex(song, trackSelector);
    var candidates = [];

    if (targetMode === "detail" || targetMode === "auto") {
        try {
            var detail = readDetailMidiClip();
            if (detail) {
                candidates.push(detail);
            }
        } catch (detailError) {
            if (targetMode === "detail") {
                throw detailError;
            }
        }
        if (targetMode === "detail") {
            throw new Error("No current detail clip; click/open a MIDI clip in Live first");
        }
    }
    if (targetMode === "arrangement" || targetMode === "auto") {
        collectArrangementMidiClips(song, targetTrack, candidates, limit);
    }
    if (targetMode === "session" || targetMode === "auto") {
        collectSessionMidiClips(song, targetTrack, candidates, limit);
    }
    return candidates;
}


function resolveTargetClip(payload) {
    var candidates = scanMidiClips(payload);
    if (!candidates.length) {
        throw new Error("No readable MIDI clip found in the current Live set");
    }
    if (payload.candidate_index === undefined && payload.clip_id === undefined) {
        throw new Error("Run scan_clips first, then pass candidate_index to choose a MIDI clip");
    }
    if (payload.clip_id !== undefined) {
        var clipId = Number(payload.clip_id);
        for (var byId = 0; byId < candidates.length; byId += 1) {
            if (Number(candidates[byId].target.clip_id) === clipId) {
                return candidates[byId];
            }
        }
        throw new Error("clip_id was not found in scanned MIDI candidates");
    }
    var candidateIndex = Number(payload.candidate_index);
    if (!isFinite(candidateIndex) || candidateIndex < 0 || Math.floor(candidateIndex) !== candidateIndex) {
        throw new Error("candidate_index must be a non-negative integer");
    }
    if (candidateIndex >= candidates.length) {
        throw new Error("candidate_index is outside the scanned MIDI candidate list");
    }
    return candidates[candidateIndex];
}


function firstCandidate(candidates) {
    if (!candidates.length) {
        return null;
    }
    return candidateFromDetail(candidates[0], 0);
}


function applyNotes(clip, notes, length) {
    clip.call("remove_notes_extended", 0, 128, 0.0, Math.max(length, 1.0));
    if (notes.length) {
        var wrapper = new Dict();
        wrapper.setparse("wrapper", JSON.stringify({notes: notes}));
        clip.call("add_new_notes", wrapper.get("wrapper"));
    }
}


function selectedByRange(note, payload) {
    var start = noteNumber(note, "start_time", 0.0);
    var pitch = noteNumber(note, "pitch", 0);
    var startMin = payload.start === undefined ? 0 : Number(payload.start);
    var endMax = payload.end === undefined ? Infinity : Number(payload.end);
    var pitchMin = payload.pitch_min === undefined ? 0 : Number(payload.pitch_min);
    var pitchMax = payload.pitch_max === undefined ? 127 : Number(payload.pitch_max);
    if (!isFinite(startMin) || (payload.end !== undefined && !isFinite(endMax)) || !isFinite(pitchMin) || !isFinite(pitchMax)) {
        throw new Error("start/end/pitch_min/pitch_max must be numbers");
    }
    return start >= startMin && start < endMax && pitch >= pitchMin && pitch <= pitchMax;
}


function quantizeValue(value, grid) {
    return Math.max(0, Math.round(value / grid) * grid);
}


function transformNotes(notes, payload) {
    var action = String(payload.action || "read_notes");
    var changed = 0;
    var out = [];
    var beforeExamples = [];
    var afterExamples = [];
    var deltaBeats = Number(payload.delta_beats || 0);
    var semitones = Number(payload.semitones || 0);
    var grid = Number(payload.grid || 0.25);
    var velocityScale = Number(payload.scale === undefined ? 1 : payload.scale);
    var velocityOffset = Number(payload.offset || 0);

    if (action === "shift_notes" && (!isFinite(deltaBeats) || !isFinite(semitones))) {
        throw new Error("delta_beats and semitones must be numbers");
    }
    if (action === "quantize_notes" && (!isFinite(grid) || grid <= 0)) {
        throw new Error("grid must be a positive number");
    }
    if (action === "scale_velocity" && (!isFinite(velocityScale) || !isFinite(velocityOffset))) {
        throw new Error("scale and offset must be numbers");
    }

    for (var index = 0; index < notes.length; index += 1) {
        var original = noteForWrite(notes[index]);
        var next = noteForWrite(notes[index]);
        var selected = selectedByRange(original, payload);

        if (selected && action === "delete_notes_in_range") {
            changed += 1;
            if (beforeExamples.length < 8) {
                beforeExamples.push(noteSummary(original));
            }
            continue;
        }
        if (selected && action === "shift_notes") {
            next.start_time = Math.max(0, next.start_time + deltaBeats);
            next.pitch = Math.max(0, Math.min(127, Math.round(next.pitch + semitones)));
        } else if (selected && action === "quantize_notes") {
            next.start_time = quantizeValue(next.start_time, grid);
        } else if (selected && action === "scale_velocity") {
            next.velocity = Math.max(1, Math.min(127, Math.round(next.velocity * velocityScale + velocityOffset)));
        }

        if (JSON.stringify(original) !== JSON.stringify(next)) {
            changed += 1;
            if (beforeExamples.length < 8) {
                beforeExamples.push(noteSummary(original));
                afterExamples.push(noteSummary(next));
            }
        }
        out.push(next);
    }
    return {notes: out, changed: changed, before_examples: beforeExamples, after_examples: afterExamples};
}


function handleClipNoteTools(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        if (payload.mcp_safe !== undefined) {
            AgentCreative.handle("clip_note_tools", requestId, payload, mode, prepareCreativeClipNoteTools, agentCreativeEmit);
            return;
        }
        var action = String(payload.action || "read_notes");
        var allowed = ["scan_clips", "scan_clips_metadata", "read_notes", "read_notes_by_clip_id", "shift_notes", "quantize_notes", "delete_notes_in_range", "scale_velocity"];
        if (allowed.indexOf(action) < 0) {
            throw new Error("action must be scan_clips, scan_clips_metadata, read_notes, read_notes_by_clip_id, shift_notes, quantize_notes, delete_notes_in_range, or scale_velocity");
        }

        if (action === "scan_clips") {
            var candidates = scanMidiClips(payload);
            outlet(0, [requestId, JSON.stringify({
                ok: true,
                dry_run: true,
                applied: false,
                action: action,
                candidate_count: candidates.length,
                recommended_candidate: firstCandidate(candidates),
                candidates: candidateSummaries(candidates),
                message: candidates.length
                    ? "MIDI clip candidates scanned; choose candidate_index before reading or editing"
                    : "No readable MIDI clip candidates found"
            })]);
            return;
        }

        if (action === "scan_clips_metadata") {
            outlet(0, [requestId, JSON.stringify(scanClipMetadataBounded(payload))]);
            return;
        }

        if (action === "read_notes_by_clip_id") {
            outlet(0, [requestId, JSON.stringify(readNotesByClipIdBounded(payload))]);
            return;
        }

        var detail = resolveTargetClip(payload);
        var limit = Math.max(1, Math.min(256, Math.round(Number(payload.limit || 64))));
        var visibleNotes = [];
        for (var index = 0; index < detail.notes.length && visibleNotes.length < limit; index += 1) {
            if (selectedByRange(detail.notes[index], payload)) {
                visibleNotes.push(noteSummary(detail.notes[index]));
            }
        }

        var transform = {notes: detail.notes, changed: 0, before_examples: [], after_examples: []};
        if (action !== "read_notes") {
            transform = transformNotes(detail.notes, payload);
            if (!dryRun) {
                applyNotes(detail.api, transform.notes, detail.length);
            }
        }

        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: dryRun,
            applied: !dryRun && action !== "read_notes",
            action: action,
            target: detail.target,
            clip_name: detail.name,
            length: detail.length,
            note_count: detail.notes.length,
            selected_count: visibleNotes.length,
            changed_count: transform.changed,
            notes: action === "read_notes" ? visibleNotes : undefined,
            before_examples: transform.before_examples,
            after_examples: transform.after_examples,
            message: action === "read_notes"
                ? "Target MIDI clip notes read"
                : (dryRun ? "Ready to edit target MIDI clip notes" : "Target MIDI clip notes edited")
        })]);
    } catch (error) {
        outlet(0, [requestId, JSON.stringify({
            ok: false,
            dry_run: dryRun,
            applied: false,
            error: error && error.message ? error.message : String(error)
        })]);
    }
}

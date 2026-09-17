autowatch = 1;
include("ableton_agent_creative_control.js");

function prepareCreativeArrangement(p) {
    if (["move_audio_clip", "copy_midi_clip"].indexOf(p.action) < 0) { throw new Error("Unsupported safe Arrangement action"); }
    if (typeof p.target_start !== "number" || !isFinite(p.target_start) || p.target_start < 0 || p.target_start > 1576800) {
        throw new Error("Invalid target_start");
    }
    if (p.action === "move_audio_clip") {
        if (p.name !== undefined) { throw new Error("Move does not rename"); }
        var preview = moveAudioClip(p, true);
        var nativeToken = preview.plan_token;
        delete preview.plan_token;
        preview.warning = "Same-track native duplicate/delete move; source ID can change. Fingerprint verification is not a full envelope/sample backup.";
        // Reuse the existing move checks/readback; do not rescan unrelated Clip properties here.
        return {state:preview, plan:preview, apply:function () {
            var result = moveAudioClip({track_id:p.track_id, clip_id:p.clip_id,
                target_start:p.target_start, plan_token:nativeToken}, false);
            result.clip_id = result.no_op ? p.clip_id : result.after_clip_id;
            result.verified = true;
            return result;
        }};
    }
    var t = AgentCreative.track(p), c = AgentCreative.clip(t, p.clip_id, true);
    if (t.section !== "track") { throw new Error("Ordinary track required"); }
    var ns = AgentCreative.notes(c), length = Number(AgentCreative.value(c.get("length")));
    if (Number(AgentCreative.value(c.get("loop_start"))) !== 0 ||
        Number(AgentCreative.value(c.get("start_marker"))) !== 0 ||
        Math.abs(Number(AgentCreative.value(c.get("loop_end"))) - length) > 0.0001) {
        throw new Error("MIDI copy requires a zero-origin single-loop source");
    }
    if (p.target_start + length > 1576800) { throw new Error("Destination exceeds Arrangement range"); }
    var copied = ns.map(function (note) {
        var out = {};
        for (var k in note) { if (k !== "note_id") { out[k] = note[k]; } }
        return out;
    });
    var name = p.name || String(AgentCreative.value(c.get("name"))) + " Copy";
    var work = AgentCreative.newClip(t, {location:"arrangement",start:p.target_start,length:length,name:name}, copied);
    work.state = [ns, length, name, work.state];
    work.plan.action = p.action;
    work.plan.source_clip_id = p.clip_id;
    work.plan.warning = "Note-data copy only; no Clip envelopes, MPE or launch settings. Source remains untouched.";
    return work;
}
inlets = 1;
outlets = 1;


var MAX_NOTES = 4096;


function list() {
    var args = arrayfromargs(arguments);
    handleArrangementTools(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleArrangementTools(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function valueOf(raw, fallback) {
    if (raw instanceof Array) {
        return raw.length ? raw[0] : fallback;
    }
    return raw === undefined || raw === null ? fallback : raw;
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


function safeGet(api, propertyName, fallback) {
    try {
        return api.get(propertyName);
    } catch (_error) {
        return fallback;
    }
}


function normalize(value) {
    return String(value || "").toLowerCase().replace(/^\s+|\s+$/g, "");
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


function clipStart(clip) {
    return Number(valueOf(safeGet(clip, "start_time", safeGet(clip, "start_marker", 0.0)), 0.0));
}


function clipLength(clip) {
    var length = Number(valueOf(safeGet(clip, "length", 0.0), 0.0));
    if (length > 0) {
        return length;
    }
    var start = clipStart(clip);
    var end = Number(valueOf(safeGet(clip, "end_time", safeGet(clip, "end_marker", start)), start));
    return Math.max(0, end - start);
}


function readClipNotes(clipId, fallbackLength) {
    var clip = new LiveAPI(function () {}, "id " + clipId);
    if (!Boolean(Number(valueOf(safeGet(clip, "is_midi_clip", 0), 0)))) {
        throw new Error("Target clip is not a MIDI clip");
    }
    var length = Number(valueOf(safeGet(clip, "length", fallbackLength || 0.0), fallbackLength || 0.0));
    var raw = clip.call("get_notes_extended", 0, 128, 0.0, Math.max(length, 1.0));
    var notes = parseNotes(raw);
    if (notes.length > MAX_NOTES) {
        throw new Error("Too many notes in target clip; maximum is " + MAX_NOTES);
    }
    var out = [];
    for (var index = 0; index < notes.length; index += 1) {
        out.push(noteForWrite(notes[index]));
    }
    return out;
}


function applyNotes(clip, notes, length, name) {
    clip.set("looping", 1);
    clip.set("loop_start", 0.0);
    clip.set("loop_end", length);
    clip.call("remove_notes_extended", 0, 128, 0.0, Math.max(length, 1.0));
    if (notes.length) {
        var wrapper = new Dict();
        wrapper.setparse("wrapper", JSON.stringify({notes: notes}));
        clip.call("add_new_notes", wrapper.get("wrapper"));
    }
    if (name) {
        clip.set("name", name);
    }
}


function clipType(clip) {
    if (Boolean(Number(valueOf(safeGet(clip, "is_midi_clip", 0), 0)))) {
        return "midi";
    }
    if (Boolean(Number(valueOf(safeGet(clip, "is_audio_clip", 0), 0)))) {
        return "audio";
    }
    return "unknown";
}


function overlaps(start, length, regionStart, regionEnd) {
    var end = start + length;
    return start < regionEnd && end > regionStart;
}


function resolveTrackFilter(song, payload) {
    var trackSelector = payload.track_index !== undefined ? payload.track_index : payload.track;
    if (trackSelector === undefined || trackSelector === null || trackSelector === "") {
        trackSelector = payload.track_name;
    }
    if (trackSelector === undefined || trackSelector === null || trackSelector === "") {
        return null;
    }

    var trackIds = idsFrom(song.get("tracks"));
    if (typeof trackSelector === "number") {
        if (trackSelector < 0 || trackSelector >= trackIds.length || Math.floor(trackSelector) !== trackSelector) {
            throw new Error("track_index is outside the ordinary track list");
        }
        return Number(trackSelector);
    }

    var wanted = normalize(trackSelector);
    for (var index = 0; index < trackIds.length; index += 1) {
        var track = new LiveAPI(function () {}, "id " + trackIds[index]);
        if (normalize(valueOf(track.get("name"), "")) === wanted) {
            return index;
        }
    }
    throw new Error("Track not found: " + trackSelector);
}


function normalizeRegion(payload) {
    var start = Number(payload.start === undefined ? 0.0 : payload.start);
    var length = Number(payload.length === undefined ? 32.0 : payload.length);
    if (!isFinite(start) || start < 0) {
        throw new Error("start must be a non-negative beat position");
    }
    if (!isFinite(length) || length <= 0) {
        throw new Error("length must be a positive beat length");
    }
    return {start: start, length: length, end: start + length};
}


function collectRegion(payload) {
    var region = normalizeRegion(payload);
    var song = new LiveAPI(function () {}, "live_set");
    var trackFilter = resolveTrackFilter(song, payload);
    var trackIds = idsFrom(song.get("tracks"));
    var limit = Math.max(1, Math.min(256, Math.round(Number(payload.limit || 128))));
    var clips = [];
    var touchedTracks = {};

    for (var trackIndex = 0; trackIndex < trackIds.length; trackIndex += 1) {
        if (clips.length >= limit) {
            break;
        }
        if (trackFilter !== null && trackFilter !== trackIndex) {
            continue;
        }
        var track = new LiveAPI(function () {}, "id " + trackIds[trackIndex]);
        var trackName = String(valueOf(track.get("name"), ""));
        var clipIds = idsFrom(safeGet(track, "arrangement_clips", []));
        for (var clipIndex = 0; clipIndex < clipIds.length; clipIndex += 1) {
            if (clips.length >= limit) {
                break;
            }
            var clip = new LiveAPI(function () {}, "id " + clipIds[clipIndex]);
            var clipStartBeat = clipStart(clip);
            var lengthBeats = clipLength(clip);
            if (!overlaps(clipStartBeat, lengthBeats, region.start, region.end)) {
                continue;
            }
            touchedTracks[trackIndex] = true;
            clips.push({
                track_index: trackIndex,
                track_name: trackName,
                track_id: trackIds[trackIndex],
                clip_id: clipIds[clipIndex],
                clip_name: String(valueOf(clip.get("name"), "")),
                clip_type: clipType(clip),
                start_time: clipStartBeat,
                length: lengthBeats,
                end_time: clipStartBeat + lengthBeats,
                fully_inside: clipStartBeat >= region.start && clipStartBeat + lengthBeats <= region.end
            });
        }
    }

    var trackCount = 0;
    for (var key in touchedTracks) {
        if (touchedTracks.hasOwnProperty(key)) {
            trackCount += 1;
        }
    }

    return {
        region: region,
        clip_count: clips.length,
        track_count: trackCount,
        clips: clips,
        truncated: clips.length >= limit
    };
}


function scanRegion(payload) {
    return collectRegion(payload);
}


function rejectUnsafePartialClips(scan, payload) {
    var includePartial = Boolean(payload.include_partial);
    var partial = [];
    for (var index = 0; index < scan.clips.length; index += 1) {
        if (!scan.clips[index].fully_inside) {
            partial.push(scan.clips[index]);
        }
    }
    if (partial.length && !includePartial) {
        throw new Error("Region contains partially overlapping clips; pass include_partial=true if you really want to affect whole clips");
    }
    return partial;
}


function findExactArrangementClip(track, start, length) {
    var clipIds = idsFrom(safeGet(track, "arrangement_clips", []));
    for (var index = 0; index < clipIds.length; index += 1) {
        var clip = new LiveAPI(function () {}, "id " + clipIds[index]);
        if (Math.abs(clipStart(clip) - start) < 0.0001 && Math.abs(clipLength(clip) - length) < 0.0001) {
            return clipIds[index];
        }
    }
    return 0;
}


function containsNumber(values, wanted) {
    for (var index = 0; index < values.length; index += 1) {
        if (Number(values[index]) === Number(wanted)) {
            return true;
        }
    }
    return false;
}


function clipFingerprint(clip) {
    return {
        clip_type: clipType(clip),
        name: String(valueOf(safeGet(clip, "name", ""), "")),
        file_path: String(valueOf(safeGet(clip, "file_path", ""), "")),
        length: clipLength(clip),
        looping: Number(valueOf(safeGet(clip, "looping", 0), 0)),
        start_marker: Number(valueOf(safeGet(clip, "start_marker", 0.0), 0.0)),
        end_marker: Number(valueOf(safeGet(clip, "end_marker", 0.0), 0.0)),
        loop_start: Number(valueOf(safeGet(clip, "loop_start", 0.0), 0.0)),
        loop_end: Number(valueOf(safeGet(clip, "loop_end", 0.0), 0.0)),
        gain: Number(valueOf(safeGet(clip, "gain", 0.0), 0.0)),
        pitch_coarse: Number(valueOf(safeGet(clip, "pitch_coarse", 0), 0)),
        pitch_fine: Number(valueOf(safeGet(clip, "pitch_fine", 0.0), 0.0)),
        warping: Number(valueOf(safeGet(clip, "warping", 0), 0)),
        warp_mode: Number(valueOf(safeGet(clip, "warp_mode", -1), -1)),
        ram_mode: Number(valueOf(safeGet(clip, "ram_mode", 0), 0)),
        muted: Number(valueOf(safeGet(clip, "muted", 0), 0)),
        color: Number(valueOf(safeGet(clip, "color", 0), 0)),
        has_envelopes: Number(valueOf(safeGet(clip, "has_envelopes", 0), 0))
    };
}


function sameFingerprint(before, after) {
    for (var key in before) {
        if (!before.hasOwnProperty(key)) {
            continue;
        }
        if (typeof before[key] === "number") {
            if (Math.abs(Number(before[key]) - Number(after[key])) > 0.0001) {
                return false;
            }
        } else if (String(before[key]) !== String(after[key])) {
            return false;
        }
    }
    return true;
}


function findDuplicatedClip(track, beforeIds, start, length) {
    var afterIds = idsFrom(safeGet(track, "arrangement_clips", []));
    for (var index = 0; index < afterIds.length; index += 1) {
        if (containsNumber(beforeIds, afterIds[index])) {
            continue;
        }
        var clip = new LiveAPI(function () {}, "id " + afterIds[index]);
        if (Math.abs(clipStart(clip) - start) < 0.0001 && Math.abs(clipLength(clip) - length) < 0.0001) {
            return Number(afterIds[index]);
        }
    }
    return 0;
}


function moveAudioClip(payload, dryRun) {
    var trackId = Number(payload.track_id);
    var clipId = Number(payload.clip_id);
    var targetStart = Number(payload.target_start);
    if (!isFinite(trackId) || trackId <= 0 || Math.floor(trackId) !== trackId) {
        throw new Error("move_audio_clip requires a positive stable track_id");
    }
    if (!isFinite(clipId) || clipId <= 0 || Math.floor(clipId) !== clipId) {
        throw new Error("move_audio_clip requires a positive stable clip_id");
    }
    if (!isFinite(targetStart) || targetStart < 0 || targetStart > 1576800) {
        throw new Error("target_start must be within the Arrangement beat range");
    }

    var song = new LiveAPI(function () {}, "live_set");
    var trackIds = idsFrom(song.get("tracks"));
    if (!containsNumber(trackIds, trackId)) {
        throw new Error("Stable track_id was not found in ordinary tracks");
    }
    var track = new LiveAPI(function () {}, "id " + trackId);
    var clipIds = idsFrom(safeGet(track, "arrangement_clips", []));
    if (!containsNumber(clipIds, clipId)) {
        throw new Error("Stable clip_id is not an Arrangement clip on the requested track_id");
    }

    var source = new LiveAPI(function () {}, "id " + clipId);
    if (clipType(source) !== "audio") {
        throw new Error("move_audio_clip only accepts an existing Arrangement audio clip");
    }
    var sourceStart = clipStart(source);
    var length = clipLength(source);
    if (!(length > 0) || targetStart + length > 1576800) {
        throw new Error("Audio clip length or requested destination is outside the supported Arrangement range");
    }
    var fingerprint = clipFingerprint(source);
    var trackName = String(valueOf(safeGet(track, "name", ""), ""));
    var planToken = [trackId, clipId, sourceStart.toFixed(6), length.toFixed(6), targetStart.toFixed(6)].join(":");

    for (var index = 0; index < clipIds.length; index += 1) {
        if (Number(clipIds[index]) === clipId) {
            continue;
        }
        var other = new LiveAPI(function () {}, "id " + clipIds[index]);
        var otherStart = clipStart(other);
        var otherLength = clipLength(other);
        if (overlaps(otherStart, otherLength, targetStart, targetStart + length)) {
            throw new Error("Target range overlaps another Arrangement clip; move_audio_clip never replaces unrelated clips");
        }
    }

    var plan = {
        track_id: trackId,
        track_name: trackName,
        source_clip_id: clipId,
        clip_name: fingerprint.name,
        clip_type: fingerprint.clip_type,
        file_path: fingerprint.file_path,
        before_start: sourceStart,
        after_start: targetStart,
        length: length,
        plan_token: planToken,
        same_track_only: true,
        preserves_by: "Track.duplicate_clip_to_arrangement",
        no_op: Math.abs(sourceStart - targetStart) < 0.0001
    };
    if (dryRun || plan.no_op) {
        return plan;
    }
    if (String(payload.plan_token || "") !== planToken) {
        throw new Error("Commit requires the current dry-run plan_token");
    }

    var maxEnd = Math.max(sourceStart + length, targetStart + length);
    for (var scanIndex = 0; scanIndex < clipIds.length; scanIndex += 1) {
        var scanClip = new LiveAPI(function () {}, "id " + clipIds[scanIndex]);
        maxEnd = Math.max(maxEnd, clipStart(scanClip) + clipLength(scanClip));
    }
    var stagingStart = maxEnd + 8.0;
    if (stagingStart + length > 1576800) {
        throw new Error("No safe temporary Arrangement position is available for this move");
    }

    var stagingId = 0;
    var finalId = 0;
    var sourceDeleted = false;
    var restoredId = 0;
    var beforeStageIds = idsFrom(safeGet(track, "arrangement_clips", []));
    track.call("duplicate_clip_to_arrangement", "id " + clipId, stagingStart);
    stagingId = findDuplicatedClip(track, beforeStageIds, stagingStart, length);
    if (!stagingId) {
        throw new Error("Live duplicated the audio clip but the temporary copy could not be resolved");
    }
    var stagingClip = new LiveAPI(function () {}, "id " + stagingId);
    if (!sameFingerprint(fingerprint, clipFingerprint(stagingClip))) {
        track.call("delete_clip", "id " + stagingId);
        throw new Error("Temporary audio copy did not preserve the verified clip fingerprint");
    }

    try {
        track.call("delete_clip", "id " + clipId);
        sourceDeleted = true;
        var beforeFinalIds = idsFrom(safeGet(track, "arrangement_clips", []));
        track.call("duplicate_clip_to_arrangement", "id " + stagingId, targetStart);
        finalId = findDuplicatedClip(track, beforeFinalIds, targetStart, length);
        if (!finalId) {
            throw new Error("Moved audio clip could not be resolved at the requested beat");
        }
        var finalClip = new LiveAPI(function () {}, "id " + finalId);
        if (!sameFingerprint(fingerprint, clipFingerprint(finalClip))) {
            throw new Error("Moved audio clip failed property readback verification");
        }
        track.call("delete_clip", "id " + stagingId);
    } catch (moveError) {
        if (finalId) {
            try {
                track.call("delete_clip", "id " + finalId);
            } catch (_deleteFinalError) {}
        }
        if (sourceDeleted && stagingId) {
            try {
                var beforeRestoreIds = idsFrom(safeGet(track, "arrangement_clips", []));
                track.call("duplicate_clip_to_arrangement", "id " + stagingId, sourceStart);
                restoredId = findDuplicatedClip(track, beforeRestoreIds, sourceStart, length);
                if (restoredId && sameFingerprint(fingerprint, clipFingerprint(new LiveAPI(function () {}, "id " + restoredId)))) {
                    track.call("delete_clip", "id " + stagingId);
                    throw new Error(String(moveError.message || moveError) + "; original position was restored as clip_id " + restoredId);
                }
            } catch (restoreError) {
                if (String(restoreError.message || restoreError).indexOf("original position was restored") >= 0) {
                    throw restoreError;
                }
                throw new Error(String(moveError.message || moveError) + "; automatic restore failed and temporary clip_id " + stagingId + " was retained at beat " + stagingStart);
            }
        }
        throw moveError;
    }

    plan.after_clip_id = finalId;
    plan.after_readback = {
        clip_id: finalId,
        start_time: clipStart(new LiveAPI(function () {}, "id " + finalId)),
        fingerprint: clipFingerprint(new LiveAPI(function () {}, "id " + finalId))
    };
    return plan;
}


function clearRegion(payload, dryRun) {
    var scan = collectRegion(payload);
    rejectUnsafePartialClips(scan, payload);
    if (!dryRun) {
        for (var index = 0; index < scan.clips.length; index += 1) {
            var clipInfo = scan.clips[index];
            var track = new LiveAPI(function () {}, "id " + clipInfo.track_id);
            track.call("delete_clip", "id " + clipInfo.clip_id);
        }
    }
    return {
        region: scan.region,
        affected_count: scan.clips.length,
        affected_clips: scan.clips
    };
}


function copyRegion(payload, dryRun) {
    var scan = collectRegion(payload);
    rejectUnsafePartialClips(scan, payload);
    var targetStart = Number(payload.target_start === undefined ? scan.region.start + scan.region.length : payload.target_start);
    if (!isFinite(targetStart) || targetStart < 0) {
        throw new Error("target_start must be a non-negative beat position");
    }
    var replace = Boolean(payload.replace);
    var copied = [];
    var skipped = [];

    for (var index = 0; index < scan.clips.length; index += 1) {
        var clipInfo = scan.clips[index];
        if (clipInfo.clip_type !== "midi") {
            skipped.push({clip_id: clipInfo.clip_id, clip_name: clipInfo.clip_name, reason: "only MIDI Arrangement clips are copied safely"});
            continue;
        }
        var destinationStart = targetStart + (clipInfo.start_time - scan.region.start);
        var planned = {
            source_clip_id: clipInfo.clip_id,
            source_clip_name: clipInfo.clip_name,
            track_index: clipInfo.track_index,
            track_name: clipInfo.track_name,
            start_time: destinationStart,
            length: clipInfo.length,
            clip_name: String(clipInfo.clip_name || "Arrangement Clip") + String(payload.name_suffix || " Copy")
        };
        if (!dryRun) {
            var track = new LiveAPI(function () {}, "id " + clipInfo.track_id);
            var existingId = findExactArrangementClip(track, destinationStart, clipInfo.length);
            if (existingId && !replace) {
                throw new Error("Target range already has a matching clip on " + clipInfo.track_name + "; set replace=true");
            }
            if (existingId && replace) {
                track.call("delete_clip", "id " + existingId);
            }
            var created = track.call("create_midi_clip", destinationStart, clipInfo.length);
            var targetClipId = idFrom(created) || findExactArrangementClip(track, destinationStart, clipInfo.length);
            if (!targetClipId) {
                throw new Error("Copied clip was created but could not be resolved through Live API");
            }
            var targetClip = new LiveAPI(function () {}, "id " + targetClipId);
            applyNotes(targetClip, readClipNotes(clipInfo.clip_id, clipInfo.length), clipInfo.length, planned.clip_name);
            planned.clip_id = targetClipId;
        }
        copied.push(planned);
    }

    return {
        source_region: scan.region,
        target_start: targetStart,
        copied_count: copied.length,
        skipped_count: skipped.length,
        copied_clips: copied,
        skipped_clips: skipped
    };
}


function renameRegionClip(payload, dryRun) {
    var scan = collectRegion(payload);
    var newName = payload.name === undefined ? "" : String(payload.name);
    var prefix = payload.name_prefix === undefined ? "" : String(payload.name_prefix);
    var suffix = payload.name_suffix === undefined ? "" : String(payload.name_suffix);
    if (!newName && !prefix && !suffix) {
        throw new Error("rename_region_clip requires name, name_prefix, or name_suffix");
    }
    var renamed = [];
    for (var index = 0; index < scan.clips.length; index += 1) {
        var clipInfo = scan.clips[index];
        var afterName = newName
            ? (scan.clips.length === 1 ? newName : newName + " " + String(index + 1))
            : prefix + clipInfo.clip_name + suffix;
        if (!dryRun) {
            var clip = new LiveAPI(function () {}, "id " + clipInfo.clip_id);
            clip.set("name", afterName);
        }
        renamed.push({
            clip_id: clipInfo.clip_id,
            track_index: clipInfo.track_index,
            track_name: clipInfo.track_name,
            before_name: clipInfo.clip_name,
            after_name: afterName
        });
    }
    return {
        region: scan.region,
        renamed_count: renamed.length,
        renamed_clips: renamed
    };
}


function handleArrangementTools(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        if (payload.mcp_safe !== undefined) {
            AgentCreative.handle("arrangement_tools", requestId, payload, mode, prepareCreativeArrangement, agentCreativeEmit);
            return;
        }
        var action = String(payload.action || "scan_region");
        var allowed = ["scan_region", "clear_region", "copy_region", "duplicate_region", "rename_region_clip", "move_audio_clip"];
        if (allowed.indexOf(action) < 0) {
            throw new Error("action must be scan_region, clear_region, copy_region, duplicate_region, rename_region_clip, or move_audio_clip");
        }
        if (action === "scan_region") {
            var scan = scanRegion(payload);
            outlet(0, [requestId, JSON.stringify({
                ok: true,
                dry_run: true,
                applied: false,
                action: action,
                region: scan.region,
                clip_count: scan.clip_count,
                track_count: scan.track_count,
                clips: scan.clips,
                truncated: scan.truncated,
                message: scan.clip_count
                    ? "Arrangement region scanned; choose a commit action after reviewing clips"
                    : "Arrangement region scanned; no clips overlap this beat range"
            })]);
            return;
        }

        var result = action === "clear_region"
            ? clearRegion(payload, dryRun)
            : action === "move_audio_clip"
                ? moveAudioClip(payload, dryRun)
            : action === "rename_region_clip"
                ? renameRegionClip(payload, dryRun)
                : copyRegion(payload, dryRun);

        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: dryRun,
            applied: !dryRun,
            action: action,
            plan: result,
            message: dryRun ? "Ready to apply Arrangement region action" : "Arrangement region action applied"
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

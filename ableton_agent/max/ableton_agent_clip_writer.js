autowatch = 1;
include("ableton_agent_health.js");
include("ableton_agent_creative_control.js");
inlets = 1;
outlets = 1;


var MAX_NOTES = 512;

function prepareCreativeClipWriter(p) {
    var t = AgentCreative.track(p);
    return AgentCreative.newClip(t, p, normalizeNotes(p.notes, p.length));
}


function bang() {
    writeClip("", "{}", "dry_run");
}


function list() {
    var args = arrayfromargs(arguments);
    writeClip(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    if (messagename === "write_arrangement_clip") {
        writeArrangementClip(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
        return;
    }
    args.unshift(messagename);
    writeClip(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
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


function normalize(value) {
    return String(value || "").toLowerCase().replace(/^\s+|\s+$/g, "");
}


function safeGet(api, propertyName, fallback) {
    try {
        return api.get(propertyName);
    } catch (_error) {
        return fallback;
    }
}


function trackPath(trackIndex) {
    return "live_set tracks " + trackIndex;
}


function clipSlotPath(trackIndex, sceneIndex) {
    return trackPath(trackIndex) + " clip_slots " + sceneIndex;
}


function clipPath(trackIndex, sceneIndex) {
    return clipSlotPath(trackIndex, sceneIndex) + " clip";
}


function sceneCount() {
    var song = new LiveAPI(function () {}, "live_set");
    return idsFrom(song.get("scenes")).length;
}


function ensureScene(sceneIndex) {
    var song = new LiveAPI(function () {}, "live_set");
    var count = idsFrom(song.get("scenes")).length;
    while (count <= sceneIndex) {
        song.call("create_scene", -1);
        count += 1;
    }
}


function resolveTrack(payload) {
    var song = new LiveAPI(function () {}, "live_set");
    var ids = idsFrom(song.get("tracks"));
    var selector = payload.track_index !== undefined ? payload.track_index : payload.track;
    if (selector === undefined || selector === null || selector === "") {
        selector = payload.track_name;
    }
    if (selector === undefined || selector === null || selector === "") {
        throw new Error("Missing track selector");
    }

    if (typeof selector === "number") {
        if (selector < 0 || selector >= ids.length || Math.floor(selector) !== selector) {
            throw new Error("track_index is outside the ordinary track list");
        }
        return {
            index: selector,
            id: ids[selector],
            api: new LiveAPI(function () {}, "id " + ids[selector])
        };
    }

    var wanted = normalize(selector);
    for (var index = 0; index < ids.length; index += 1) {
        var track = new LiveAPI(function () {}, "id " + ids[index]);
        var name = String(valueOf(track.get("name"), ""));
        if (normalize(name) === wanted) {
            return {index: index, id: ids[index], api: track};
        }
    }
    throw new Error("Track not found: " + selector);
}


function normalizeNotes(rawNotes, length) {
    if (!(rawNotes instanceof Array)) {
        throw new Error("notes must be an array");
    }
    if (rawNotes.length > MAX_NOTES) {
        throw new Error("Too many notes; maximum is " + MAX_NOTES);
    }

    var notes = [];
    for (var index = 0; index < rawNotes.length; index += 1) {
        var source = rawNotes[index];
        var pitch = Number(source.pitch);
        var start = Number(source.start_time !== undefined ? source.start_time : source.start);
        var duration = Number(source.duration);
        var velocity = source.velocity === undefined ? 100 : Number(source.velocity);
        if (!isFinite(pitch) || pitch < 0 || pitch > 127) {
            throw new Error("notes[" + index + "].pitch must be 0..127");
        }
        if (!isFinite(start) || start < 0 || start >= length) {
            throw new Error("notes[" + index + "].start_time is outside the clip");
        }
        if (!isFinite(duration) || duration <= 0) {
            throw new Error("notes[" + index + "].duration must be greater than zero");
        }
        if (!isFinite(velocity) || velocity < 1 || velocity > 127) {
            throw new Error("notes[" + index + "].velocity must be 1..127");
        }
        notes.push({
            pitch: Math.round(pitch),
            start_time: start,
            duration: Math.min(duration, length - start),
            velocity: velocity,
            mute: source.mute ? 1 : 0,
            probability: source.probability === undefined ? 1.0 : Number(source.probability)
        });
    }
    return notes;
}


function slotState(trackIndex, sceneIndex, sceneExists) {
    if (!sceneExists) {
        return {has_scene: false, has_clip: false, is_midi: false, clip_name: ""};
    }
    var slot = new LiveAPI(function () {}, clipSlotPath(trackIndex, sceneIndex));
    var hasClip = Boolean(Number(valueOf(slot.get("has_clip"), 0)));
    if (!hasClip) {
        return {has_scene: true, has_clip: false, is_midi: false, clip_name: ""};
    }
    var clip = new LiveAPI(function () {}, clipPath(trackIndex, sceneIndex));
    return {
        has_scene: true,
        has_clip: true,
        is_midi: Boolean(Number(valueOf(clip.get("is_midi_clip"), 0))),
        clip_name: String(valueOf(clip.get("name"), "")),
        clip_length: Number(valueOf(clip.get("length"), 0))
    };
}


function applyNotes(clip, notes, length, name) {
    clip.set("looping", 1);
    clip.set("loop_start", 0.0);
    clip.set("loop_end", length);
    clip.call("remove_notes_extended", 0, 128, 0.0, 999999.0);
    if (notes.length) {
        var wrapper = new Dict();
        wrapper.setparse("wrapper", JSON.stringify({notes: notes}));
        clip.call("add_new_notes", wrapper.get("wrapper"));
    }
    if (name) {
        clip.set("name", String(name));
    }
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


function arrangementClipIds(track) {
    return idsFrom(safeGet(track, "arrangement_clips", []));
}


function arrangementClipInfo(clipId) {
    var clip = new LiveAPI(function () {}, "id " + clipId);
    return {
        id: clipId,
        name: String(valueOf(safeGet(clip, "name", ""), "")),
        is_midi: Boolean(Number(valueOf(safeGet(clip, "is_midi_clip", 0), 0))),
        start_time: clipStart(clip),
        length: clipLength(clip)
    };
}


function findArrangementClip(track, start, length) {
    var clipIds = arrangementClipIds(track);
    var best = null;
    for (var index = 0; index < clipIds.length; index += 1) {
        var info = arrangementClipInfo(clipIds[index]);
        if (Math.abs(info.start_time - start) < 0.0001 && Math.abs(info.length - length) < 0.0001) {
            best = info;
            break;
        }
    }
    return best;
}


function arrangementClipSummary(track, start, length) {
    var existing = findArrangementClip(track, start, length);
    return existing || {has_clip: false, start_time: start, length: length};
}


function writeClip(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        if (payload.action === "_module_health") {
            AgentHealth.reply(requestId, "clips", mode); return;
        }
        if (payload.mcp_safe !== undefined) {
            AgentCreative.handle("write_clip", requestId, payload, mode, prepareCreativeClipWriter, agentCreativeEmit);
            return;
        }
        var track = resolveTrack(payload);
        var sceneIndex = Number(payload.scene_index !== undefined ? payload.scene_index : payload.scene);
        if (!isFinite(sceneIndex) || sceneIndex < 0 || Math.floor(sceneIndex) !== sceneIndex) {
            throw new Error("scene_index must be a non-negative integer");
        }
        var length = Number(payload.length || 4);
        if (!isFinite(length) || length <= 0 || length > 1024) {
            throw new Error("length must be greater than 0 and no more than 1024 beats");
        }
        var replace = Boolean(payload.replace);
        var trackName = String(valueOf(track.api.get("name"), ""));
        if (!Boolean(Number(valueOf(track.api.get("has_midi_input"), 0)))) {
            throw new Error("Target track is not a MIDI track: " + trackName);
        }

        var notes = normalizeNotes(payload.notes || [], length);
        var currentSceneCount = sceneCount();
        var sceneExists = sceneIndex < currentSceneCount;
        var before = slotState(track.index, sceneIndex, sceneExists);
        if (before.has_clip && !replace) {
            throw new Error("Target clip slot already has a clip; set replace=true to overwrite notes");
        }
        if (before.has_clip && !before.is_midi) {
            throw new Error("Target clip slot contains a non-MIDI clip");
        }

        if (!dryRun) {
            ensureScene(sceneIndex);
            var slot = new LiveAPI(function () {}, clipSlotPath(track.index, sceneIndex));
            var hasClip = Boolean(Number(valueOf(slot.get("has_clip"), 0)));
            if (!hasClip) {
                slot.call("create_clip", length);
            }
            var clip = new LiveAPI(function () {}, clipPath(track.index, sceneIndex));
            applyNotes(clip, notes, length, payload.name || "");
        }

        var after = dryRun ? before : slotState(track.index, sceneIndex, true);
        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: dryRun,
            applied: !dryRun,
            track_index: track.index,
            track_name: trackName,
            scene_index: sceneIndex,
            length: length,
            note_count: notes.length,
            replace: replace,
            before: before,
            after: after,
            message: dryRun ? "Ready to write; rerun with commit to change the Set" : "Clip written"
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


function writeArrangementClip(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        if (payload.mcp_safe !== undefined) {
            payload.location = "arrangement";
            AgentCreative.handle("write_arrangement_clip", requestId, payload, mode, prepareCreativeClipWriter, agentCreativeEmit);
            return;
        }
        var track = resolveTrack(payload);
        var start = Number(payload.start_time !== undefined ? payload.start_time : payload.start);
        var length = Number(payload.length || 4);
        if (!isFinite(start) || start < 0 || start > 999999) {
            throw new Error("start must be a non-negative beat position");
        }
        if (!isFinite(length) || length <= 0 || length > 1024) {
            throw new Error("length must be greater than 0 and no more than 1024 beats");
        }
        var replace = Boolean(payload.replace);
        var trackName = String(valueOf(track.api.get("name"), ""));
        if (!Boolean(Number(valueOf(track.api.get("has_midi_input"), 0)))) {
            throw new Error("Target track is not a MIDI track: " + trackName);
        }
        var notes = normalizeNotes(payload.notes || [], length);
        var before = arrangementClipSummary(track.api, start, length);
        if (before.id && !replace) {
            throw new Error("Target arrangement range already has a matching clip; set replace=true to overwrite notes");
        }
        if (before.id && !before.is_midi) {
            throw new Error("Target arrangement range contains a non-MIDI clip");
        }

        var after = before;
        if (!dryRun) {
            var targetClipId = before.id || 0;
            if (!targetClipId) {
                var created = track.api.call("create_midi_clip", start, length);
                targetClipId = idFrom(created);
                if (!targetClipId) {
                    var createdInfo = findArrangementClip(track.api, start, length);
                    targetClipId = createdInfo ? createdInfo.id : 0;
                }
            }
            if (!targetClipId) {
                throw new Error("Arrangement clip was created but could not be resolved through Live API");
            }
            var clip = new LiveAPI(function () {}, "id " + targetClipId);
            applyNotes(clip, notes, length, payload.name || "");
            after = arrangementClipInfo(targetClipId);
        }

        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: dryRun,
            applied: !dryRun,
            track_index: track.index,
            track_name: trackName,
            start_time: start,
            length: length,
            note_count: notes.length,
            replace: replace,
            before: before,
            after: after,
            message: dryRun ? "Ready to write Arrangement clip; rerun with commit to change the Set" : "Arrangement clip written"
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

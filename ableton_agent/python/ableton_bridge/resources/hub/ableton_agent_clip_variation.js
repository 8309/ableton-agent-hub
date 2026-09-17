autowatch = 1;
include("ableton_agent_creative_control.js");
function prepareCreativeClipVariation(p) {
    if (["duplicate_clip","make_fill","thin_notes","mute_notes_in_range"].indexOf(p.action)<0) { throw new Error("Unsupported variation"); }
    var t=AgentCreative.track(p), c=AgentCreative.clip(t,p.clip_id,true);
    var ns=AgentCreative.notes(c), length=Number(AgentCreative.value(c.get("length")));
    if(Number(AgentCreative.value(c.get("loop_start")))!==0 ||
       Number(AgentCreative.value(c.get("start_marker")))!==0 ||
       Math.abs(Number(AgentCreative.value(c.get("loop_end")))-length)>0.0001) {
        throw new Error("Variation currently requires a zero-origin, single-loop source Clip");
    }
    var candidate={notes:ns,length:length};
    var varied=variationNotes(candidate,p);
    var target={location:"arrangement",start:p.target_start,length:length,name:p.name || "MIDI Variation"};
    var work=AgentCreative.newClip(t,target,varied.notes);
    work.state=[ns,length,work.state];
    work.plan.source_clip_id=p.clip_id;
    work.plan.warning="New note-data variation only; Clip envelopes, MPE and launch settings are not copied. Original is untouched.";
    return work;
}
inlets = 1;
outlets = 1;


var MAX_NOTES = 4096;


function list() {
    var args = arrayfromargs(arguments);
    handleClipVariation(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleClipVariation(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
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


function noteSummary(note) {
    return {
        pitch: Math.round(noteNumber(note, "pitch", 0)),
        start_time: noteNumber(note, "start_time", 0.0),
        duration: noteNumber(note, "duration", 0.0),
        velocity: Math.round(noteNumber(note, "velocity", 0)),
        mute: note.mute ? 1 : 0
    };
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


function clipStart(clip) {
    return Number(valueOf(safeGet(clip, "start_time", safeGet(clip, "start_marker", 0.0)), 0.0));
}


function readClipNotes(clipId, fallbackLength) {
    var clip = new LiveAPI(function () {}, "id " + clipId);
    var isMidi = Boolean(Number(valueOf(clip.get("is_midi_clip"), 0)));
    if (!isMidi) {
        throw new Error("Target clip is not a MIDI clip");
    }
    var length = Number(valueOf(safeGet(clip, "length", fallbackLength || 0.0), fallbackLength || 0.0));
    var raw = clip.call("get_notes_extended", 0, 128, 0.0, Math.max(length, 1.0));
    var notes = parseNotes(raw);
    if (notes.length > MAX_NOTES) {
        throw new Error("Too many notes in target clip; maximum is " + MAX_NOTES);
    }
    notes.sort(function (left, right) {
        var startDelta = noteNumber(left, "start_time", 0.0) - noteNumber(right, "start_time", 0.0);
        if (startDelta !== 0) {
            return startDelta;
        }
        return noteNumber(left, "pitch", 0) - noteNumber(right, "pitch", 0);
    });
    return notes;
}


function candidateFromClip(clipId, trackIndex, trackName, candidateIndex) {
    var clip = new LiveAPI(function () {}, "id " + clipId);
    var length = clipLength(clip);
    var start = clipStart(clip);
    var notes = readClipNotes(clipId, length);
    return {
        candidate_index: candidateIndex,
        source: "arrangement",
        track_index: trackIndex,
        track_name: trackName,
        clip_id: clipId,
        clip_name: String(valueOf(clip.get("name"), "")),
        start_time: start,
        length: length,
        note_count: notes.length,
        notes: notes
    };
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


function scanArrangementClips(payload) {
    var song = new LiveAPI(function () {}, "live_set");
    var trackSelector = payload.track_index !== undefined ? payload.track_index : payload.track;
    if (trackSelector === undefined || trackSelector === null || trackSelector === "") {
        trackSelector = payload.track_name;
    }
    var targetTrack = resolveTrackByNameOrIndex(song, trackSelector);
    var trackIds = idsFrom(song.get("tracks"));
    var limit = Math.max(1, Math.min(64, Math.round(Number(payload.candidate_limit || 16))));
    var candidates = [];
    for (var trackIndex = 0; trackIndex < trackIds.length; trackIndex += 1) {
        if (candidates.length >= limit) {
            break;
        }
        if (targetTrack && targetTrack.index !== trackIndex) {
            continue;
        }
        var track = new LiveAPI(function () {}, "id " + trackIds[trackIndex]);
        var trackName = String(valueOf(track.get("name"), ""));
        var clipIds = idsFrom(safeGet(track, "arrangement_clips", []));
        for (var clipIndex = 0; clipIndex < clipIds.length; clipIndex += 1) {
            if (candidates.length >= limit) {
                break;
            }
            var clip = new LiveAPI(function () {}, "id " + clipIds[clipIndex]);
            if (!Boolean(Number(valueOf(safeGet(clip, "is_midi_clip", 0), 0)))) {
                continue;
            }
            candidates.push(candidateFromClip(clipIds[clipIndex], trackIndex, trackName, candidates.length));
        }
    }
    return candidates;
}


function publicCandidate(candidate) {
    return {
        candidate_index: candidate.candidate_index,
        source: candidate.source,
        track_index: candidate.track_index,
        track_name: candidate.track_name,
        clip_id: candidate.clip_id,
        clip_name: candidate.clip_name,
        start_time: candidate.start_time,
        length: candidate.length,
        note_count: candidate.note_count
    };
}


function publicCandidates(candidates) {
    var out = [];
    for (var index = 0; index < candidates.length; index += 1) {
        out.push(publicCandidate(candidates[index]));
    }
    return out;
}


function resolveCandidate(payload) {
    var candidates = scanArrangementClips(payload);
    if (!candidates.length) {
        throw new Error("No Arrangement MIDI clip candidates found");
    }
    if (payload.candidate_index === undefined && payload.clip_id === undefined) {
        throw new Error("Run scan_clips first, then pass candidate_index to choose a source clip");
    }
    if (payload.clip_id !== undefined) {
        var clipId = Number(payload.clip_id);
        for (var byId = 0; byId < candidates.length; byId += 1) {
            if (Number(candidates[byId].clip_id) === clipId) {
                return candidates[byId];
            }
        }
        throw new Error("clip_id was not found in scanned Arrangement MIDI candidates");
    }
    var candidateIndex = Number(payload.candidate_index);
    if (!isFinite(candidateIndex) || candidateIndex < 0 || Math.floor(candidateIndex) !== candidateIndex) {
        throw new Error("candidate_index must be a non-negative integer");
    }
    if (candidateIndex >= candidates.length) {
        throw new Error("candidate_index is outside the scanned candidate list");
    }
    return candidates[candidateIndex];
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


function variationNotes(candidate, payload) {
    var action = String(payload.action || "duplicate_clip");
    var notes = [];
    var changed = 0;
    var examplesBefore = [];
    var examplesAfter = [];
    var keepEvery = Math.max(2, Math.round(Number(payload.keep_every || 2)));
    var fillLength = Math.max(0.25, Number(payload.fill_length || 4.0));
    var fillStart = payload.start === undefined ? Math.max(0, candidate.length - fillLength) : Number(payload.start);
    var fillEnd = payload.end === undefined ? candidate.length : Number(payload.end);
    var selectedOrdinal = 0;

    for (var index = 0; index < candidate.notes.length; index += 1) {
        var original = noteForWrite(candidate.notes[index]);
        var next = noteForWrite(candidate.notes[index]);
        var selected = selectedByRange(original, payload);
        if (action === "thin_notes" && selected) {
            if (selectedOrdinal % keepEvery !== 0) {
                changed += 1;
                if (examplesBefore.length < 8) {
                    examplesBefore.push(noteSummary(original));
                }
                selectedOrdinal += 1;
                continue;
            }
            selectedOrdinal += 1;
        } else if (action === "mute_notes_in_range" && selected) {
            next.mute = 1;
        }
        if (JSON.stringify(original) !== JSON.stringify(next)) {
            changed += 1;
            if (examplesBefore.length < 8) {
                examplesBefore.push(noteSummary(original));
                examplesAfter.push(noteSummary(next));
            }
        }
        notes.push(next);
    }

    if (action === "make_fill") {
        var extras = [];
        for (var fillIndex = 0; fillIndex < notes.length; fillIndex += 1) {
            var source = noteForWrite(notes[fillIndex]);
            var sourceStart = noteNumber(source, "start_time", 0.0);
            if (sourceStart < fillStart || sourceStart >= fillEnd) {
                continue;
            }
            var duplicate = noteForWrite(source);
            duplicate.start_time = sourceStart + 0.25;
            duplicate.velocity = Math.max(1, Math.min(127, duplicate.velocity - 10));
            if (duplicate.start_time < fillEnd && extras.length < 64) {
                extras.push(duplicate);
                changed += 1;
                if (examplesBefore.length < 8) {
                    examplesBefore.push(noteSummary(source));
                    examplesAfter.push(noteSummary(duplicate));
                }
            }
        }
        notes = notes.concat(extras);
    }

    notes.sort(function (left, right) {
        var startDelta = noteNumber(left, "start_time", 0.0) - noteNumber(right, "start_time", 0.0);
        if (startDelta !== 0) {
            return startDelta;
        }
        return noteNumber(left, "pitch", 0) - noteNumber(right, "pitch", 0);
    });
    return {notes: notes, changed: changed, before_examples: examplesBefore, after_examples: examplesAfter};
}


function arrangementClipIds(track) {
    return idsFrom(safeGet(track, "arrangement_clips", []));
}


function findArrangementClip(track, start, length) {
    var clipIds = arrangementClipIds(track);
    for (var index = 0; index < clipIds.length; index += 1) {
        var clip = new LiveAPI(function () {}, "id " + clipIds[index]);
        if (!Boolean(Number(valueOf(safeGet(clip, "is_midi_clip", 0), 0)))) {
            continue;
        }
        if (Math.abs(clipStart(clip) - start) < 0.0001 && Math.abs(clipLength(clip) - length) < 0.0001) {
            return clipIds[index];
        }
    }
    return 0;
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


function writeVariation(candidate, payload, notes) {
    var song = new LiveAPI(function () {}, "live_set");
    var trackIds = idsFrom(song.get("tracks"));
    var track = new LiveAPI(function () {}, "id " + trackIds[candidate.track_index]);
    var replace = Boolean(payload.replace);
    var targetStart = replace ? candidate.start_time : Number(payload.target_start === undefined ? candidate.start_time + candidate.length : payload.target_start);
    if (!isFinite(targetStart) || targetStart < 0) {
        throw new Error("target_start must be a non-negative beat position");
    }
    var targetClipId = replace ? candidate.clip_id : findArrangementClip(track, targetStart, candidate.length);
    if (targetClipId && !replace) {
        throw new Error("Target Arrangement range already has a MIDI clip; choose another target_start or set replace=true");
    }
    if (!targetClipId) {
        var created = track.call("create_midi_clip", targetStart, candidate.length);
        targetClipId = idFrom(created);
        if (!targetClipId) {
            targetClipId = findArrangementClip(track, targetStart, candidate.length);
        }
    }
    if (!targetClipId) {
        throw new Error("Variation clip was created but could not be resolved through Live API");
    }
    var targetClip = new LiveAPI(function () {}, "id " + targetClipId);
    var suffix = payload.name_suffix || " Variation";
    applyNotes(targetClip, notes, candidate.length, replace ? candidate.clip_name : candidate.clip_name + suffix);
    return {
        clip_id: targetClipId,
        track_index: candidate.track_index,
        track_name: candidate.track_name,
        start_time: targetStart,
        length: candidate.length,
        clip_name: String(valueOf(targetClip.get("name"), ""))
    };
}


function handleClipVariation(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        if (payload.mcp_safe !== undefined) {
            AgentCreative.handle("clip_variation", requestId, payload, mode, prepareCreativeClipVariation, agentCreativeEmit);
            return;
        }
        var action = String(payload.action || "scan_clips");
        var allowed = ["scan_clips", "duplicate_clip", "make_fill", "thin_notes", "mute_notes_in_range"];
        if (allowed.indexOf(action) < 0) {
            throw new Error("action must be scan_clips, duplicate_clip, make_fill, thin_notes, or mute_notes_in_range");
        }
        if (action === "scan_clips") {
            var candidates = scanArrangementClips(payload);
            outlet(0, [requestId, JSON.stringify({
                ok: true,
                dry_run: true,
                applied: false,
                action: action,
                candidate_count: candidates.length,
                candidates: publicCandidates(candidates),
                message: candidates.length
                    ? "Arrangement MIDI clip candidates scanned; choose candidate_index before making a variation"
                    : "No Arrangement MIDI clip candidates found"
            })]);
            return;
        }

        var candidate = resolveCandidate(payload);
        var variation = variationNotes(candidate, payload);
        var targetStart = Boolean(payload.replace) ? candidate.start_time : Number(payload.target_start === undefined ? candidate.start_time + candidate.length : payload.target_start);
        var after = {
            source_preserved: !Boolean(payload.replace),
            track_index: candidate.track_index,
            track_name: candidate.track_name,
            start_time: targetStart,
            length: candidate.length,
            clip_name: candidate.clip_name + String(payload.name_suffix || " Variation")
        };
        if (!dryRun) {
            after = writeVariation(candidate, payload, variation.notes);
        }

        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: dryRun,
            applied: !dryRun,
            action: action,
            source: publicCandidate(candidate),
            planned_target: after,
            original_note_count: candidate.note_count,
            result_note_count: variation.notes.length,
            changed_count: variation.changed,
            before_examples: variation.before_examples,
            after_examples: variation.after_examples,
            message: dryRun ? "Ready to create Arrangement clip variation" : "Arrangement clip variation created"
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

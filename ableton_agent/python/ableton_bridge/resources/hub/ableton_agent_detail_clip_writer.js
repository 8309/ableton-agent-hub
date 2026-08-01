autowatch = 1;
inlets = 1;
outlets = 1;


var MAX_DETAIL_NOTES = 4096;


function bang() {
    transposeDetailNote("", "{}", "dry_run");
}


function list() {
    var args = arrayfromargs(arguments);
    transposeDetailNote(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    transposeDetailNote(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
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
        pitch: Math.round(noteNumber(note, "pitch", 0)),
        start_time: noteNumber(note, "start_time", 0.0),
        duration: Math.max(noteNumber(note, "duration", 0.0), 0.0001),
        velocity: Math.max(1, Math.min(127, Math.round(noteNumber(note, "velocity", 100)))),
        mute: note.mute ? 1 : 0,
        probability: note.probability === undefined ? 1.0 : noteNumber(note, "probability", 1.0)
    };
}


function noteSummary(note) {
    var start = noteNumber(note, "start_time", 0.0);
    var pitch = Math.round(noteNumber(note, "pitch", 0));
    return {
        pitch: pitch,
        start_time: start,
        duration: noteNumber(note, "duration", 0.0),
        velocity: Math.round(noteNumber(note, "velocity", 0)),
        bar: Math.floor(start / 4) + 1,
        beat: (start % 4) + 1
    };
}


function isMusicalNote(note) {
    return noteNumber(note, "velocity", 0) > 1 && noteNumber(note, "duration", 0.0) >= 0.03;
}


function selectTargetIndex(notes, requestedIndex, selector) {
    if (String(selector || "first_musical") === "absolute") {
        return requestedIndex;
    }
    var musicalIndex = 0;
    for (var index = 0; index < notes.length; index += 1) {
        if (!isMusicalNote(notes[index])) {
            continue;
        }
        if (musicalIndex === requestedIndex) {
            return index;
        }
        musicalIndex += 1;
    }
    throw new Error("No matching musical note found at note_index " + requestedIndex);
}


function readDetailMidiClip() {
    var view = new LiveAPI(function () {}, "live_set view");
    var clipId = idFrom(view.get("detail_clip"));
    if (!clipId) {
        throw new Error("No current detail clip; click/open the MIDI clip in Live first");
    }
    var clip = new LiveAPI(function () {}, "id " + clipId);
    var isMidi = Boolean(Number(valueOf(clip.get("is_midi_clip"), 0)));
    var name = String(valueOf(clip.get("name"), ""));
    var length = Number(valueOf(clip.get("length"), 0.0));
    if (!isMidi) {
        throw new Error("Current detail clip is not a MIDI clip: " + name);
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
    return {api: clip, name: name, length: length, notes: notes};
}


function applyNotes(clip, notes, length) {
    clip.call("remove_notes_extended", 0, 128, 0.0, Math.max(length, 1.0));
    if (notes.length) {
        var wrapper = new Dict();
        wrapper.setparse("wrapper", JSON.stringify({notes: notes}));
        clip.call("add_new_notes", wrapper.get("wrapper"));
    }
}


function transposeDetailNote(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var noteIndex = Number(payload.note_index === undefined ? 0 : payload.note_index);
        var semitones = Number(payload.semitones === undefined ? 12 : payload.semitones);
        var selector = String(payload.selector || "first_musical");
        if (!isFinite(noteIndex) || noteIndex < 0 || Math.floor(noteIndex) !== noteIndex) {
            throw new Error("note_index must be a non-negative integer");
        }
        if (!isFinite(semitones) || Math.floor(semitones) !== semitones) {
            throw new Error("semitones must be an integer");
        }

        var detail = readDetailMidiClip();
        if (!detail.notes.length) {
            throw new Error("Current detail clip has no MIDI notes");
        }
        if (noteIndex >= detail.notes.length) {
            throw new Error("note_index is outside the current clip note list");
        }

        var targetIndex = selectTargetIndex(detail.notes, noteIndex, selector);
        var before = noteSummary(detail.notes[targetIndex]);
        var afterPitch = before.pitch + semitones;
        if (afterPitch < 0 || afterPitch > 127) {
            throw new Error("Transposed pitch would be outside 0..127");
        }
        var after = {
            pitch: afterPitch,
            start_time: before.start_time,
            duration: before.duration,
            velocity: before.velocity,
            bar: before.bar,
            beat: before.beat
        };

        if (!dryRun) {
            var notesForWrite = [];
            for (var index = 0; index < detail.notes.length; index += 1) {
                var writeNote = noteForWrite(detail.notes[index]);
                if (index === targetIndex) {
                    writeNote.pitch = afterPitch;
                }
                notesForWrite.push(writeNote);
            }
            applyNotes(detail.api, notesForWrite, detail.length);
        }

        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: dryRun,
            applied: !dryRun,
            clip_name: detail.name,
            length: detail.length,
            note_count: detail.notes.length,
            note_index: noteIndex,
            source_note_index: targetIndex,
            selector: selector,
            semitones: semitones,
            before: before,
            after: after,
            message: dryRun ? "Ready to transpose current detail clip note" : "Current detail clip note transposed"
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

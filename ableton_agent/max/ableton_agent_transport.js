autowatch = 1;
inlets = 1;
outlets = 1;


function list() {
    var args = arrayfromargs(arguments);
    handleTransport(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleTransport(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function valueOf(raw, fallback) {
    if (raw instanceof Array) {
        return raw.length ? raw[0] : fallback;
    }
    return raw === undefined || raw === null ? fallback : raw;
}


function boolValue(raw) {
    return Boolean(Number(valueOf(raw, 0)));
}


function songState(song) {
    return {
        current_song_time: Number(valueOf(song.get("current_song_time"), 0)),
        is_playing: boolValue(song.get("is_playing")),
        loop: boolValue(song.get("loop")),
        metronome: boolValue(song.get("metronome"))
    };
}


function emit(requestId, payload) {
    outlet(0, [requestId, JSON.stringify(payload)]);
}


function targetBeat(payload) {
    var beat = payload.beat !== undefined ? payload.beat : payload.position;
    if (beat === undefined || beat === null || beat === "") {
        throw new Error("beat is required for jump/set_position");
    }
    var value = Number(beat);
    if (!isFinite(value) || value < 0) {
        throw new Error("beat must be a non-negative number");
    }
    return value;
}


function jumpToBeat(song, beat) {
    song.set("current_song_time", Number(beat));
}


function handleTransport(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    var song = new LiveAPI(function () {}, "live_set");
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var action = String(payload.action || "status").toLowerCase();
        var before = songState(song);
        var target = null;

        if (action === "jump" || action === "set_position") {
            target = targetBeat(payload);
        } else if (["status", "play", "stop", "continue"].indexOf(action) < 0) {
            throw new Error("action must be status, play, stop, continue, jump, or set_position");
        } else if (action === "play" && payload.beat !== undefined) {
            target = targetBeat(payload);
        }

        if (!dryRun) {
            if (action === "play") {
                song.call("start_playing");
                if (target !== null) {
                    jumpToBeat(song, target);
                }
            } else if (action === "stop") {
                song.call("stop_playing");
            } else if (action === "continue") {
                song.call("continue_playing");
            } else if (action === "jump" || action === "set_position") {
                jumpToBeat(song, target);
            }
        }

        emit(requestId, {
            ok: true,
            dry_run: dryRun,
            action: action,
            target_beat: target,
            before: before,
            after: dryRun ? before : songState(song),
            changed: !dryRun && action !== "status",
            message: dryRun ? "Transport action validated; rerun with commit to apply" : "Transport action applied"
        });
    } catch (error) {
        emit(requestId, {
            ok: false,
            dry_run: dryRun,
            changed: false,
            error: error && error.message ? error.message : String(error)
        });
    }
}

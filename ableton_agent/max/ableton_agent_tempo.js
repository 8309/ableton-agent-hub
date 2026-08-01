autowatch = 1;
inlets = 1;
outlets = 1;


function bang() {
    handleTempo("", "{}", "dry_run");
}


function list() {
    var args = arrayfromargs(arguments);
    handleTempo(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleTempo(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function valueOf(raw, fallback) {
    if (raw instanceof Array) {
        return raw.length ? raw[0] : fallback;
    }
    return raw === undefined || raw === null ? fallback : raw;
}


function readTempo(song) {
    return Number(valueOf(song.get("tempo"), 0));
}


function emit(requestId, payload) {
    outlet(0, [requestId, JSON.stringify(payload)]);
}


function handleTempo(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    var song = new LiveAPI(function () {}, "live_set");
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var currentTempo = readTempo(song);
        var wantsSet = payload.tempo !== undefined && payload.tempo !== null && payload.tempo !== "";
        if (!wantsSet) {
            emit(requestId, {
                ok: true,
                dry_run: true,
                tempo: currentTempo,
                changed: false,
                message: "Current tempo read"
            });
            return;
        }
        var targetTempo = Number(payload.tempo);
        if (!isFinite(targetTempo) || targetTempo < 20 || targetTempo > 999) {
            throw new Error("tempo must be a number between 20 and 999 BPM");
        }
        if (!dryRun) {
            song.set("tempo", targetTempo);
        }
        emit(requestId, {
            ok: true,
            dry_run: dryRun,
            tempo_before: currentTempo,
            tempo: dryRun ? currentTempo : readTempo(song),
            target_tempo: targetTempo,
            changed: !dryRun,
            message: dryRun ? "Tempo change validated; rerun with commit to apply" : "Tempo changed"
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

autowatch = 1;
inlets = 1;
outlets = 1;

function list() {
    var args = arrayfromargs(arguments);
    handleMeterMonitor(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}

function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleMeterMonitor(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
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
    var ids = idsFrom(raw);
    return ids.length ? ids[0] : 0;
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

function trackIds() {
    var song = new LiveAPI(function () {}, "live_set");
    return idsFrom(song.get("tracks"));
}

function meterNumber(track, propertyName) {
    return Number(valueOf(safeGet(track, propertyName, 0), 0));
}

function readTrackMeter(section, index, id) {
    var track = new LiveAPI(function () {}, "id " + id);
    var left = meterNumber(track, "output_meter_left");
    var right = meterNumber(track, "output_meter_right");
    var peak = Math.max(left, right);
    return {
        section: section,
        track_index: index,
        track_id: id,
        track_name: String(valueOf(track.get("name"), "")),
        output_meter_left: left,
        output_meter_right: right,
        peak: peak,
        silent_now: peak <= 0.0001,
        clipping_risk: peak >= 0.98,
        mute: Boolean(Number(valueOf(safeGet(track, "mute", 0), 0))),
        solo: Boolean(Number(valueOf(safeGet(track, "solo", 0), 0)))
    };
}

function readMeters(payload) {
    var section = normalize(payload.section || "track");
    if (section === "master") {
        section = "main";
    }
    var song = new LiveAPI(function () {}, "live_set");
    var ids = section === "return" ? idsFrom(song.get("return_tracks")) : trackIds();
    if (section === "main") {
        ids = [idFrom(song.get("master_track"))];
    } else if (section !== "return") {
        section = "track";
    }
    if (payload.track_id !== undefined && payload.track_id !== null && payload.track_id !== "") {
        var requestedId = Number(payload.track_id);
        var idIndex = ids.indexOf(requestedId);
        if (idIndex < 0) {
            throw new Error("track_id is not in the requested " + section + " section");
        }
        return summarizeMeters([readTrackMeter(section, idIndex, requestedId)]);
    }
    var target = payload.track_index !== undefined ? Number(payload.track_index) : null;
    var meters = [];
    if (target !== null && isFinite(target)) {
        if (target < 0 || target >= ids.length || Math.floor(target) !== target) {
            throw new Error("track_index is outside the " + section + " track list");
        }
        meters.push(readTrackMeter(section, target, ids[target]));
    } else {
        if (section !== "track") {
            throw new Error("Return/Main meter reads require an explicit track_id or track_index");
        }
        var limit = Math.max(1, Math.min(ids.length, Math.round(Number(payload.limit || ids.length))));
        for (var index = 0; index < ids.length && meters.length < limit; index += 1) {
            meters.push(readTrackMeter(section, index, ids[index]));
        }
    }
    return summarizeMeters(meters);
}

function summarizeMeters(meters) {
    var silentCount = 0;
    var clippingCount = 0;
    for (var meterIndex = 0; meterIndex < meters.length; meterIndex += 1) {
        if (meters[meterIndex].silent_now) {
            silentCount += 1;
        }
        if (meters[meterIndex].clipping_risk) {
            clippingCount += 1;
        }
    }
    return {meters: meters, silent_count: silentCount, clipping_risk_count: clippingCount};
}

function analyzeMeters(payload) {
    var result = readMeters(payload);
    var active = [];
    var silent = [];
    var clipping = [];
    for (var index = 0; index < result.meters.length; index += 1) {
        var meter = result.meters[index];
        if (meter.silent_now) {
            silent.push(meter);
        } else {
            active.push(meter);
        }
        if (meter.clipping_risk) {
            clipping.push(meter);
        }
    }
    active.sort(function (left, right) {
        return right.peak - left.peak;
    });
    var loudest = active.length ? active[0] : null;
    var quietestActive = active.length ? active[active.length - 1] : null;
    var spread = loudest && quietestActive ? loudest.peak - quietestActive.peak : 0;
    var notes = [];
    if (!active.length) {
        notes.push("No active ordinary tracks were detected at this instant");
    }
    if (silent.length) {
        notes.push(String(silent.length) + " ordinary tracks are silent right now");
    }
    if (clipping.length) {
        notes.push(String(clipping.length) + " ordinary tracks are near clipping");
    }
    if (spread > 0.35) {
        notes.push("Active track balance is wide; compare the loudest and quietest active tracks by ear");
    }
    return {
        meters: result.meters,
        active_count: active.length,
        silent_count: silent.length,
        clipping_risk_count: clipping.length,
        loudest_track: loudest,
        quietest_active_track: quietestActive,
        active_peak_spread: spread,
        silent_tracks: silent,
        clipping_risk_tracks: clipping,
        balance_notes: notes
    };
}

function handleMeterMonitor(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var action = String(payload.action || "read_meters");
        var allowed = ["read_meters", "detect_silent", "detect_clipping", "balance_report"];
        if (allowed.indexOf(action) < 0) {
            throw new Error("action must be read_meters, detect_silent, detect_clipping, or balance_report");
        }
        var result = action === "read_meters" ? readMeters(payload) : analyzeMeters(payload);
        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: true,
            applied: false,
            action: action,
            track_count: result.meters.length,
            silent_count: result.silent_count,
            clipping_risk_count: result.clipping_risk_count,
            active_count: result.active_count,
            loudest_track: result.loudest_track,
            quietest_active_track: result.quietest_active_track,
            active_peak_spread: result.active_peak_spread,
            silent_tracks: result.silent_tracks,
            clipping_risk_tracks: result.clipping_risk_tracks,
            balance_notes: result.balance_notes,
            meters: result.meters,
            message: "Meters read once; no continuous polling was started"
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

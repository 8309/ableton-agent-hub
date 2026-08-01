autowatch = 1;
inlets = 1;
outlets = 1;


var MAX_CHANGES = 32;
var MIX_FIELDS = {
    volume: true,
    pan: true,
    send: true,
    mute: true,
    solo: true,
    arm: true
};


function bang() {
    setMix("", "{\"changes\":[]}", "dry_run");
}


function list() {
    var args = arrayfromargs(arguments);
    setMix(String(args[0] || ""), String(args[1] || "{\"changes\":[]}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    setMix(String(args[0] || ""), String(args[1] || "{\"changes\":[]}"), String(args[2] || "dry_run"));
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


function ordinaryTrackIds() {
    var song = new LiveAPI(function () {}, "live_set");
    return idsFrom(song.get("tracks"));
}


function returnTrackIds() {
    var song = new LiveAPI(function () {}, "live_set");
    return idsFrom(song.get("return_tracks"));
}


function resolveTrack(change) {
    var section = normalize(change.section || "");
    if (section === "master") {
        section = "main";
    }
    var song = new LiveAPI(function () {}, "live_set");
    if (change.track_id !== undefined && change.track_id !== null && change.track_id !== "") {
        var requestedId = Number(change.track_id);
        var ordinaryIdsById = ordinaryTrackIds();
        var returnIdsById = returnTrackIds();
        var mainIdById = idFrom(song.get("master_track"));
        var resolvedSectionById = ordinaryIdsById.indexOf(requestedId) >= 0 ? "track"
            : returnIdsById.indexOf(requestedId) >= 0 ? "return"
            : requestedId === mainIdById ? "main" : "";
        if (!resolvedSectionById || (section && section !== resolvedSectionById)) {
            throw new Error("track_id is not in the requested track section");
        }
        var resolvedIndexById = resolvedSectionById === "track" ? ordinaryIdsById.indexOf(requestedId)
            : resolvedSectionById === "return" ? returnIdsById.indexOf(requestedId) : 0;
        return {index: resolvedIndexById, id: requestedId, section: resolvedSectionById, api: new LiveAPI(function () {}, "id " + requestedId)};
    }
    if (section === "main") {
        var mainIdForSection = idFrom(song.get("master_track"));
        return {index: 0, id: mainIdForSection, section: "main", api: new LiveAPI(function () {}, "id " + mainIdForSection)};
    }
    var selector = change.track_index !== undefined ? change.track_index : change.track;
    if (selector === undefined || selector === null || selector === "") {
        selector = change.track_name;
    }
    if (selector === undefined || selector === null || selector === "") {
        throw new Error("Missing track selector");
    }
    if (selector === "master" || selector === "main" || section === "main") {
        var mainId = idFrom(song.get("master_track"));
        return {index: 0, id: mainId, section: "main", api: new LiveAPI(function () {}, "id " + mainId)};
    }

    var ids = section === "return" ? returnTrackIds() : ordinaryTrackIds();
    var resolvedSection = section === "return" ? "return" : "track";
    if (typeof selector === "number" || /^[0-9]+$/.test(String(selector))) {
        var requestedIndex = Number(selector);
        if (requestedIndex < 0 || requestedIndex >= ids.length || Math.floor(requestedIndex) !== requestedIndex) {
            throw new Error("track index is outside the " + resolvedSection + " list");
        }
        return {index: requestedIndex, id: ids[requestedIndex], section: resolvedSection, api: new LiveAPI(function () {}, "id " + ids[requestedIndex])};
    }

    var wanted = normalize(selector);
    for (var index = 0; index < ids.length; index += 1) {
        var track = new LiveAPI(function () {}, "id " + ids[index]);
        var name = String(valueOf(track.get("name"), ""));
        if (normalize(name) === wanted) {
            return {index: index, id: ids[index], section: resolvedSection, api: track};
        }
    }
    throw new Error("Track not found: " + selector);
}


function parameterInfo(parameterId) {
    var parameter = new LiveAPI(function () {}, "id " + parameterId);
    var value = Number(valueOf(parameter.get("value"), 0));
    var displayValue = "";
    try {
        displayValue = String(valueOf(parameter.call("str_for_value", value), ""));
    } catch (_error) {
        displayValue = "";
    }
    return {
        id: parameterId,
        name: String(valueOf(parameter.get("name"), "")),
        value: value,
        min: Number(valueOf(parameter.get("min"), 0)),
        max: Number(valueOf(parameter.get("max"), 1)),
        display_value: displayValue
    };
}


function mixerDevice(track) {
    var mixerId = idFrom(track.get("mixer_device"));
    if (!mixerId) {
        throw new Error("Track has no mixer_device");
    }
    return new LiveAPI(function () {}, "id " + mixerId);
}


function resolveMixerParameter(track, change) {
    var mixer = mixerDevice(track);
    var field = normalize(change.field);
    if (field === "volume") {
        return idFrom(mixer.get("volume"));
    }
    if (field === "pan" || field === "panning") {
        return idFrom(mixer.get("panning"));
    }
    if (field === "send") {
        var sendSelector = change.send !== undefined ? change.send : change.send_index;
        if (sendSelector === undefined || sendSelector === null || sendSelector === "") {
            throw new Error("Missing send selector");
        }
        var sendIds = idsFrom(mixer.get("sends"));
        var sendIndex = typeof sendSelector === "number" ? sendSelector : Number(sendSelector);
        if (!isFinite(sendIndex)) {
            sendIndex = String(sendSelector).toUpperCase().charCodeAt(0) - 65;
        }
        if (sendIndex < 0 || sendIndex >= sendIds.length || Math.floor(sendIndex) !== sendIndex) {
            throw new Error("send selector is outside this track send list");
        }
        return sendIds[sendIndex];
    }
    throw new Error("Not a mixer parameter field: " + field);
}


function normalizeChanges(payload) {
    var changes = payload instanceof Array ? payload : payload.changes;
    if (!(changes instanceof Array)) {
        throw new Error("payload must be an array or contain a changes array");
    }
    if (!changes.length) {
        throw new Error("changes cannot be empty");
    }
    if (changes.length > MAX_CHANGES) {
        throw new Error("Too many changes; maximum is " + MAX_CHANGES);
    }
    return changes;
}


function preflightChange(change, changeIndex) {
    var field = normalize(change.field);
    if (!MIX_FIELDS[field]) {
        throw new Error("Unsupported mix field: " + field);
    }
    var track = resolveTrack(change);
    var trackName = String(valueOf(track.api.get("name"), ""));
    var requestedValue = change.value;

    if (field === "mute" || field === "solo" || field === "arm") {
        if (field === "arm" && !Boolean(Number(valueOf(safeGet(track.api, "can_be_armed", 0), 0)))) {
            throw new Error("Track cannot be armed: " + trackName);
        }
        var beforeBool = Boolean(Number(valueOf(safeGet(track.api, field, 0), 0)));
        var boolValue = Boolean(Number(requestedValue));
        return {
            change_index: changeIndex,
            kind: "property",
            field: field,
            track: track,
            track_name: trackName,
            before: beforeBool,
            value: boolValue
        };
    }

    var parameterId = resolveMixerParameter(track.api, change);
    var before = parameterInfo(parameterId);
    var value = Number(requestedValue);
    if (!isFinite(value)) {
        throw new Error("value must be a number");
    }
    if (value < before.min || value > before.max) {
        throw new Error("Value must be between " + before.min + " and " + before.max);
    }
    return {
        change_index: changeIndex,
        kind: "parameter",
        field: field,
        send: change.send !== undefined ? change.send : change.send_index,
        track: track,
        track_name: trackName,
        parameter_id: parameterId,
        before: before,
        value: value
    };
}


function resultForResolved(resolved) {
    if (resolved.kind === "property") {
        var afterBool = Boolean(Number(valueOf(safeGet(resolved.track.api, resolved.field, 0), 0)));
        return {
            change_index: resolved.change_index,
            track_index: resolved.track.index,
            track_id: resolved.track.id,
            section: resolved.track.section,
            track_name: resolved.track_name,
            field: resolved.field,
            before: resolved.before,
            requested_value: resolved.value,
            after: afterBool
        };
    }
    var after = parameterInfo(resolved.parameter_id);
    return {
        change_index: resolved.change_index,
        track_index: resolved.track.index,
        track_id: resolved.track.id,
        section: resolved.track.section,
        track_name: resolved.track_name,
        field: resolved.field,
        send: resolved.send,
        parameter: {
            id: resolved.before.id,
            name: resolved.before.name,
            min: resolved.before.min,
            max: resolved.before.max
        },
        before: {
            value: resolved.before.value,
            display_value: resolved.before.display_value
        },
        requested_value: resolved.value,
        after: {
            value: after.value,
            display_value: after.display_value
        }
    };
}


function setMix(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var changes = normalizeChanges(payload);
        var resolved = [];
        var results = [];

        for (var index = 0; index < changes.length; index += 1) {
            resolved.push(preflightChange(changes[index], index));
        }

        if (!dryRun) {
            for (var identityIndex = 0; identityIndex < resolved.length; identityIndex += 1) {
                if (resolved[identityIndex].track.section !== "track" && Number(changes[identityIndex].track_id) !== resolved[identityIndex].track.id) {
                    throw new Error("Commit to Return/Main requires track_id from the preceding dry-run");
                }
            }
        }

        if (!dryRun) {
            for (var writeIndex = 0; writeIndex < resolved.length; writeIndex += 1) {
                if (resolved[writeIndex].kind === "property") {
                    resolved[writeIndex].track.api.set(resolved[writeIndex].field, resolved[writeIndex].value ? 1 : 0);
                } else {
                    var parameter = new LiveAPI(function () {}, "id " + resolved[writeIndex].parameter_id);
                    parameter.set("value", resolved[writeIndex].value);
                }
            }
        }

        for (var resultIndex = 0; resultIndex < resolved.length; resultIndex += 1) {
            results.push(resultForResolved(resolved[resultIndex]));
        }

        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: dryRun,
            applied: !dryRun,
            change_count: results.length,
            results: results,
            message: dryRun ? "Ready to set mixer values; rerun with commit to change the Set" : "Mixer values updated"
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

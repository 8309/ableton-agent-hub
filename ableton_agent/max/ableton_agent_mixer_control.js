autowatch = 1;
inlets = 1;
outlets = 1;

include("ableton_agent_value_display.js");
include("ableton_agent_ui_input.js");


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


function nowMs() {
    return new Date().getTime();
}


function valuesEqual(left, right) {
    if (typeof left === "boolean" || typeof right === "boolean") {
        return Boolean(left) === Boolean(right);
    }
    return Math.abs(Number(left) - Number(right)) <= 0.000001;
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
    return AbletonAgentValueDisplay.attachCurrent({
        id: parameterId,
        name: String(valueOf(parameter.get("name"), "")),
        value: value,
        min: Number(valueOf(parameter.get("min"), 0)),
        max: Number(valueOf(parameter.get("max"), 1))
    }, parameter, value);
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
    AgentUiInput.exclusive(change);
    var field = normalize(change.field);
    if (!MIX_FIELDS[field]) {
        throw new Error("Unsupported mix field: " + field);
    }
    var track = resolveTrack(change);
    var trackName = String(valueOf(track.api.get("name"), ""));
    var requestedValue = change.value;

    if (field === "mute" || field === "solo" || field === "arm") {
        if (change.ui_value !== undefined) { throw new Error("unsupported_ui_value: use numeric value for track switches"); }
        if (field === "arm" && !Boolean(Number(valueOf(safeGet(track.api, "can_be_armed", 0), 0)))) {
            throw new Error("Track cannot be armed: " + trackName);
        }
        var beforeBool = Boolean(Number(valueOf(safeGet(track.api, field, 0), 0)));
        var boolValue = Boolean(Number(requestedValue));
        if (change.expected_before !== undefined && !valuesEqual(beforeBool, Boolean(Number(change.expected_before)))) {
            throw new Error("stale_before_value: current " + beforeBool + " does not match expected " + Boolean(Number(change.expected_before)));
        }
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
    var value = AgentUiInput.resolve(change, new LiveAPI(function () {}, "id " + parameterId), before, {field:field});
    if (!isFinite(value)) {
        throw new Error("value must be a number");
    }
    if (value < before.min || value > before.max) {
        throw new Error("Value must be between " + before.min + " and " + before.max);
    }
    if (change.expected_before !== undefined && !valuesEqual(before.value, change.expected_before)) {
        throw new Error("stale_before_value: current " + before.value + " does not match expected " + change.expected_before);
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
        value: value,
        requested_ui_value: change.ui_value
    };
}


function currentInternalValue(resolved) {
    if (resolved.kind === "property") {
        return Boolean(Number(valueOf(safeGet(resolved.track.api, resolved.field, 0), 0)));
    }
    return Number(valueOf(new LiveAPI(function () {}, "id " + resolved.parameter_id).get("value"), 0));
}


function writeResolved(resolved, value) {
    if (resolved.kind === "property") {
        resolved.track.api.set(resolved.field, value ? 1 : 0);
    } else {
        new LiveAPI(function () {}, "id " + resolved.parameter_id).set("value", Number(value));
    }
}


function restoreChange(resolved, afterValue) {
    var beforeValue = resolved.kind === "property" ? resolved.before : resolved.before.value;
    var change = {
        section: resolved.track.section,
        track_id: resolved.track.id,
        field: resolved.field,
        value: beforeValue,
        expected_before: afterValue
    };
    if (resolved.field === "send") {
        change.send = resolved.send;
    }
    return change;
}


function resultForResolved(resolved, dryRun) {
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
    if (dryRun) {
        after.value = resolved.value;
        AbletonAgentValueDisplay.attachTarget(after, new LiveAPI(function () {}, "id " + resolved.parameter_id), resolved.value);
    }
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
        before: AbletonAgentValueDisplay.valuePayload(resolved.before),
        requested_ui_value: resolved.requested_ui_value,
        requested_value: resolved.value,
        after: AbletonAgentValueDisplay.valuePayload(after)
    };
}


function setMix(requestId, payloadText, mode) {
    var normalizedMode = String(mode || "dry_run").toLowerCase();
    var dryRun = normalizedMode !== "commit" && normalizedMode !== "apply";
    var startedAt = nowMs();
    var resolved = [];
    var written = [];
    var timing = {resolve_ms: 0, write_ms: 0, readback_ms: 0, total_ms: 0};
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var changes = normalizeChanges(payload);
        var results = [];

        var resolveStartedAt = nowMs();
        for (var index = 0; index < changes.length; index += 1) {
            resolved.push(preflightChange(changes[index], index));
        }
        timing.resolve_ms = nowMs() - resolveStartedAt;

        if (!dryRun) {
            var writeStartedAt = nowMs();
            for (var writeIndex = 0; writeIndex < resolved.length; writeIndex += 1) {
                writeResolved(resolved[writeIndex], resolved[writeIndex].value);
                written.push(resolved[writeIndex]);
            }
            timing.write_ms = nowMs() - writeStartedAt;
        }

        var readbackStartedAt = nowMs();
        for (var resultIndex = 0; resultIndex < resolved.length; resultIndex += 1) {
            if (!dryRun && !valuesEqual(currentInternalValue(resolved[resultIndex]), resolved[resultIndex].value)) {
                throw new Error("readback_mismatch at change " + resultIndex);
            }
            results.push(resultForResolved(resolved[resultIndex], dryRun));
        }
        timing.readback_ms = nowMs() - readbackStartedAt;
        timing.total_ms = nowMs() - startedAt;

        var restoreChanges = [];
        if (!dryRun) {
            for (var receiptIndex = 0; receiptIndex < resolved.length; receiptIndex += 1) {
                restoreChanges.push(restoreChange(resolved[receiptIndex], currentInternalValue(resolved[receiptIndex])));
            }
        }

        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: dryRun,
            applied: !dryRun,
            operation: dryRun ? "inspect" : "apply",
            inspection_kind: dryRun ? "target_and_projected_value" : null,
            simulated: false,
            change_count: results.length,
            results: results,
            timings: timing,
            undo_receipt: dryRun ? null : {
                operation_id: requestId,
                route: "/set_mix",
                restore_changes: restoreChanges
            },
            message: dryRun ? "Targets inspected; no Live state changed" : "Mixer values updated and read back"
        })]);
    } catch (error) {
        var rollbackErrors = [];
        if (!dryRun && written.length) {
            for (var rollbackIndex = written.length - 1; rollbackIndex >= 0; rollbackIndex -= 1) {
                try {
                    writeResolved(written[rollbackIndex], written[rollbackIndex].kind === "property"
                        ? written[rollbackIndex].before : written[rollbackIndex].before.value);
                } catch (rollbackError) {
                    rollbackErrors.push(rollbackError && rollbackError.message ? rollbackError.message : String(rollbackError));
                }
            }
        }
        timing.total_ms = nowMs() - startedAt;
        outlet(0, [requestId, JSON.stringify({
            ok: false,
            dry_run: dryRun,
            applied: false,
            operation: dryRun ? "inspect" : "apply",
            rolled_back: !dryRun && written.length > 0 && rollbackErrors.length === 0,
            rollback_errors: rollbackErrors,
            completed_before_failure: written.length,
            timings: timing,
            error: error && error.message ? error.message : String(error)
        })]);
    }
}

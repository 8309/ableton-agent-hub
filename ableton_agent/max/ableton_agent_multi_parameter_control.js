autowatch = 1;
inlets = 1;
outlets = 1;


var MAX_CHANGES = 16;
var BLOCKED_PARAMETERS = {
    "device on": true
};


function bang() {
    setParameters("", "{\"changes\":[]}", "dry_run");
}


function list() {
    var args = arrayfromargs(arguments);
    setParameters(String(args[0] || ""), String(args[1] || "{\"changes\":[]}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    setParameters(String(args[0] || ""), String(args[1] || "{\"changes\":[]}"), String(args[2] || "dry_run"));
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


function normalize(value) {
    return String(value || "").toLowerCase().replace(/^\s+|\s+$/g, "");
}


function displayValue(parameter, value) {
    try {
        return String(valueOf(parameter.call("str_for_value", value), ""));
    } catch (_error) {
        return "";
    }
}


function automationState(parameter) {
    try {
        return Number(valueOf(parameter.get("automation_state"), 0));
    } catch (_error) {
        return 0;
    }
}


function automationStateName(value) {
    if (value === 1) {
        return "active";
    }
    if (value === 2) {
        return "overridden";
    }
    return "none";
}


function parameterInfo(parameter, index, id) {
    var value = Number(valueOf(parameter.get("value"), 0));
    var currentAutomationState = automationState(parameter);
    return {
        index: index,
        id: id,
        name: String(valueOf(parameter.get("name"), "")),
        value: value,
        min: Number(valueOf(parameter.get("min"), 0)),
        max: Number(valueOf(parameter.get("max"), 1)),
        is_quantized: Boolean(Number(valueOf(parameter.get("is_quantized"), 0))),
        display_value: displayValue(parameter, value),
        automation_state: currentAutomationState,
        automation_state_name: automationStateName(currentAutomationState)
    };
}


function getTrackIds(section) {
    var song = new LiveAPI(function () {}, "live_set");
    return idsFrom(song.get(section === "return" ? "return_tracks" : "tracks"));
}


function trackSelector(change) {
    if (change.track_index !== undefined) {
        return change.track_index;
    }
    if (change.track_name !== undefined) {
        return change.track_name;
    }
    if (change.track !== undefined) {
        return change.track;
    }
    return undefined;
}


function resolveTrack(change) {
    var section = normalize(change.section || "track");
    if (section === "master") {
        section = "main";
    }
    var song = new LiveAPI(function () {}, "live_set");
    if (section === "main") {
        var mainId = idFrom(song.get("master_track"));
        if (change.track_id !== undefined && Number(change.track_id) !== mainId) {
            throw new Error("track_id does not match the current Main track");
        }
        return {section: "main", index: 0, id: mainId, api: new LiveAPI(function () {}, "id " + mainId)};
    }
    var resolvedSection = section === "return" ? "return" : "track";
    var ids = getTrackIds(resolvedSection);
    if (change.track_id !== undefined && change.track_id !== null && change.track_id !== "") {
        var requestedId = Number(change.track_id);
        var idIndex = ids.indexOf(requestedId);
        if (idIndex < 0) {
            throw new Error("track_id is not in the requested " + resolvedSection + " section");
        }
        return {section: resolvedSection, index: idIndex, id: requestedId, api: new LiveAPI(function () {}, "id " + requestedId)};
    }
    var selector = trackSelector(change);
    if (selector === undefined || selector === null || selector === "") {
        throw new Error("Missing track selector");
    }

    if (typeof selector === "number" || /^\d+$/.test(String(selector))) {
        var requestedIndex = Number(selector);
        if (requestedIndex < 0 || requestedIndex >= ids.length || Math.floor(requestedIndex) !== requestedIndex) {
            throw new Error("track index is outside the ordinary track list");
        }
        return {
            section: resolvedSection,
            index: requestedIndex,
            id: ids[requestedIndex],
            api: new LiveAPI(function () {}, "id " + ids[requestedIndex])
        };
    }

    var wanted = normalize(selector);
    for (var index = 0; index < ids.length; index += 1) {
        var track = new LiveAPI(function () {}, "id " + ids[index]);
        var name = String(valueOf(track.get("name"), ""));
        if (normalize(name) === wanted) {
            return {section: resolvedSection, index: index, id: ids[index], api: track};
        }
    }
    throw new Error("Track not found: " + selector);
}


function targetDeviceId(track, change) {
    var deviceIds = idsFrom(track.get("devices"));
    if (!deviceIds.length) {
        throw new Error("Track has no devices");
    }

    if (change.device_index !== undefined) {
        var requestedIndex = Number(change.device_index);
        if (requestedIndex < 0 || requestedIndex >= deviceIds.length || Math.floor(requestedIndex) !== requestedIndex) {
            throw new Error("device_index is outside this track device list");
        }
        return deviceIds[requestedIndex];
    }

    if (change.device_name || change.device) {
        var wanted = normalize(change.device_name || change.device);
        for (var namedIndex = 0; namedIndex < deviceIds.length; namedIndex += 1) {
            var namedDevice = new LiveAPI(function () {}, "id " + deviceIds[namedIndex]);
            var namedName = String(valueOf(namedDevice.get("name"), ""));
            if (normalize(namedName) === wanted) {
                return deviceIds[namedIndex];
            }
        }
        throw new Error("Device not found on track: " + (change.device_name || change.device));
    }

    for (var index = 0; index < deviceIds.length; index += 1) {
        var device = new LiveAPI(function () {}, "id " + deviceIds[index]);
        var className = String(valueOf(device.get("class_name"), ""));
        var name = String(valueOf(device.get("name"), ""));
        if (className !== "MxDeviceMidiEffect" && name.indexOf("Ableton Agent") !== 0) {
            return deviceIds[index];
        }
    }
    return deviceIds[0];
}


function selectorIsIndex(selector) {
    return /^[0-9]+$/.test(String(selector || ""));
}


function resolveParameter(device, selector) {
    var parameterIds = idsFrom(device.get("parameters"));
    if (!parameterIds.length) {
        throw new Error("Target device has no parameters");
    }
    if (selector === undefined || selector === null || selector === "") {
        throw new Error("Missing parameter selector");
    }

    if (typeof selector === "number" || selectorIsIndex(selector)) {
        var requestedIndex = Number(selector);
        if (requestedIndex < 0 || requestedIndex >= parameterIds.length || Math.floor(requestedIndex) !== requestedIndex) {
            throw new Error("Parameter index is outside this device parameter list");
        }
        return {
            index: requestedIndex,
            id: parameterIds[requestedIndex],
            api: new LiveAPI(function () {}, "id " + parameterIds[requestedIndex])
        };
    }

    var wanted = normalize(selector);
    for (var index = 0; index < parameterIds.length; index += 1) {
        var parameter = new LiveAPI(function () {}, "id " + parameterIds[index]);
        var name = String(valueOf(parameter.get("name"), ""));
        if (normalize(name) === wanted) {
            return {index: index, id: parameterIds[index], api: parameter};
        }
    }
    throw new Error("Parameter not found on target device: " + selector);
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
    var track = resolveTrack(change);
    var deviceId = targetDeviceId(track.api, change);
    var device = new LiveAPI(function () {}, "id " + deviceId);
    var selector = change.parameter !== undefined ? change.parameter : change.parameter_name;
    var parameter = resolveParameter(device, selector);
    var before = parameterInfo(parameter.api, parameter.index, parameter.id);
    var value = Number(change.value);
    if (!isFinite(value)) {
        throw new Error("value must be a number");
    }
    if (BLOCKED_PARAMETERS[normalize(before.name)]) {
        throw new Error("Refusing to control protected parameter: " + before.name);
    }
    if (value < before.min || value > before.max) {
        throw new Error("Value must be between " + before.min + " and " + before.max);
    }
    if (before.is_quantized) {
        value = Math.round(value);
    }
    return {
        change_index: changeIndex,
        track: track,
        device_id: deviceId,
        device: device,
        parameter: parameter,
        before: before,
        value: value
    };
}


function resultForResolved(resolved, after) {
    return {
        change_index: resolved.change_index,
        section: resolved.track.section,
        track_index: resolved.track.index,
        track_id: resolved.track.id,
        track_name: String(valueOf(resolved.track.api.get("name"), "")),
        device_name: String(valueOf(resolved.device.get("name"), "")),
        device_class_name: String(valueOf(resolved.device.get("class_name"), "")),
        parameter: {
            index: resolved.before.index,
            id: resolved.before.id,
            name: resolved.before.name,
            min: resolved.before.min,
            max: resolved.before.max,
            is_quantized: resolved.before.is_quantized
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


function setParameters(requestId, payloadText, mode) {
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
                resolved[writeIndex].parameter.api.set("value", resolved[writeIndex].value);
            }
        }

        for (var resultIndex = 0; resultIndex < resolved.length; resultIndex += 1) {
            var after = parameterInfo(
                resolved[resultIndex].parameter.api,
                resolved[resultIndex].parameter.index,
                resolved[resultIndex].parameter.id
            );
            results.push(resultForResolved(resolved[resultIndex], after));
        }

        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: dryRun,
            applied: !dryRun,
            change_count: results.length,
            results: results,
            message: dryRun ? "Ready to set; rerun with commit to change the Set" : "Parameters updated"
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

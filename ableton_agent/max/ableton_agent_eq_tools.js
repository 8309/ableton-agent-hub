autowatch = 1;
inlets = 1;
outlets = 1;


var EQ_PRESETS = {
    lead_presence_soft: {
        description: "Small lead cleanup and presence lift",
        moves: [
            {band: 2, parameter: "Frequency", value: 350},
            {band: 2, parameter: "Gain", value: -1.5},
            {band: 5, parameter: "Frequency", value: 2800},
            {band: 5, parameter: "Gain", value: 1.0}
        ]
    },
    chord_stab_cleanup: {
        description: "Reduce low-mid boxiness while keeping chord stabs natural",
        moves: [
            {band: 2, parameter: "Frequency", value: 280},
            {band: 2, parameter: "Gain", value: -2.0},
            {band: 6, parameter: "Frequency", value: 5200},
            {band: 6, parameter: "Gain", value: 0.8}
        ]
    },
    sub_tighten: {
        description: "Small low-mid cleanup for bass without changing filter types",
        moves: [
            {band: 2, parameter: "Frequency", value: 180},
            {band: 2, parameter: "Gain", value: -2.0},
            {band: 4, parameter: "Frequency", value: 700},
            {band: 4, parameter: "Gain", value: -1.0}
        ]
    },
    drum_top_sparkle: {
        description: "Light drum top lift and mild low-mid cleanup",
        moves: [
            {band: 2, parameter: "Frequency", value: 320},
            {band: 2, parameter: "Gain", value: -1.0},
            {band: 7, parameter: "Frequency", value: 9000},
            {band: 7, parameter: "Gain", value: 1.2}
        ]
    },
    gentle_cleanup: {
        description: "Very conservative general cleanup",
        moves: [
            {band: 2, parameter: "Frequency", value: 250},
            {band: 2, parameter: "Gain", value: -1.0}
        ]
    }
};


function list() {
    var args = arrayfromargs(arguments);
    handleEqTools(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleEqTools(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
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


function normalize(value) {
    return String(value || "").toLowerCase().replace(/^\s+|\s+$/g, "").replace(/[^a-z0-9]+/g, "");
}


function objectKeys(object) {
    var keys = [];
    for (var key in object) {
        if (object.hasOwnProperty(key)) {
            keys.push(key);
        }
    }
    return keys;
}


function safeGet(api, propertyName, fallback) {
    try {
        return api.get(propertyName);
    } catch (_error) {
        return fallback;
    }
}


function displayValue(parameter, value) {
    try {
        return String(valueOf(parameter.call("str_for_value", value), ""));
    } catch (_error) {
        return "";
    }
}


function trackIds() {
    var song = new LiveAPI(function () {}, "live_set");
    return idsFrom(song.get("tracks"));
}


function resolveTrack(payload) {
    var ids = trackIds();
    var selector = payload.track_index !== undefined ? payload.track_index : payload.track;
    if (selector === undefined || selector === null || selector === "") {
        selector = payload.track_name;
    }
    if (selector === undefined || selector === null || selector === "") {
        throw new Error("Missing track selector");
    }
    if (typeof selector === "number" || /^[0-9]+$/.test(String(selector))) {
        var index = Number(selector);
        if (index < 0 || index >= ids.length || Math.floor(index) !== index) {
            throw new Error("track_index is outside the ordinary track list");
        }
        var byIndex = new LiveAPI(function () {}, "id " + ids[index]);
        return {index: index, id: ids[index], name: String(valueOf(byIndex.get("name"), "")), api: byIndex};
    }
    var wanted = normalize(selector);
    for (var namedIndex = 0; namedIndex < ids.length; namedIndex += 1) {
        var track = new LiveAPI(function () {}, "id " + ids[namedIndex]);
        var name = String(valueOf(track.get("name"), ""));
        if (normalize(name) === wanted) {
            return {index: namedIndex, id: ids[namedIndex], name: name, api: track};
        }
    }
    throw new Error("Track not found: " + selector);
}


function devicePayload(device, index) {
    return {
        index: index,
        id: device.id,
        name: String(valueOf(device.api.get("name"), "")),
        class_name: String(valueOf(safeGet(device.api, "class_name", ""), ""))
    };
}


function isEqEight(device) {
    var name = normalize(valueOf(device.get("name"), ""));
    var className = normalize(valueOf(safeGet(device, "class_name", ""), ""));
    return name === "eqeight" || className === "eqeight" || name.indexOf("eqeight") >= 0;
}


function resolveEqDevice(track, payload) {
    var ids = idsFrom(track.api.get("devices"));
    if (!ids.length) {
        throw new Error("Track has no devices");
    }
    if (payload.device_index !== undefined) {
        var requestedIndex = Number(payload.device_index);
        if (requestedIndex < 0 || requestedIndex >= ids.length || Math.floor(requestedIndex) !== requestedIndex) {
            throw new Error("device_index is outside this track device list");
        }
        return {index: requestedIndex, id: ids[requestedIndex], api: new LiveAPI(function () {}, "id " + ids[requestedIndex])};
    }
    var selector = payload.device || payload.device_name;
    if (selector !== undefined && selector !== null && selector !== "") {
        var wanted = normalize(selector);
        for (var namedIndex = 0; namedIndex < ids.length; namedIndex += 1) {
            var namedDevice = new LiveAPI(function () {}, "id " + ids[namedIndex]);
            if (normalize(valueOf(namedDevice.get("name"), "")) === wanted) {
                return {index: namedIndex, id: ids[namedIndex], api: namedDevice};
            }
        }
        throw new Error("Device not found on track: " + selector);
    }
    for (var index = 0; index < ids.length; index += 1) {
        var device = new LiveAPI(function () {}, "id " + ids[index]);
        if (isEqEight(device)) {
            return {index: index, id: ids[index], api: device};
        }
    }
    throw new Error("EQ Eight not found on target track");
}


function parameterInfo(parameter, index, id) {
    var value = Number(valueOf(parameter.get("value"), 0));
    return {
        index: index,
        id: id,
        name: String(valueOf(parameter.get("name"), "")),
        value: value,
        min: Number(valueOf(safeGet(parameter, "min", 0), 0)),
        max: Number(valueOf(safeGet(parameter, "max", 1), 1)),
        is_quantized: Boolean(Number(valueOf(safeGet(parameter, "is_quantized", 0), 0))),
        display_value: displayValue(parameter, value)
    };
}


function eqParameters(device, limit) {
    var parameterIds = idsFrom(device.api.get("parameters"));
    var parameters = [];
    var maxCount = limit !== undefined ? Number(limit) : 32;
    if (!isFinite(maxCount) || maxCount <= 0) {
        maxCount = 32;
    }
    for (var index = 0; index < parameterIds.length && parameters.length < maxCount; index += 1) {
        var parameter = new LiveAPI(function () {}, "id " + parameterIds[index]);
        parameters.push(parameterInfo(parameter, index, parameterIds[index]));
    }
    return {
        total_count: parameterIds.length,
        parameters: parameters,
        truncated: parameters.length < parameterIds.length
    };
}


function bandParameterNames(band, parameterName) {
    var number = String(band);
    var compact = normalize(parameterName);
    var names = [];
    names.push(normalize(number + " " + parameterName));
    names.push(normalize(number + parameterName));
    names.push(normalize("Band " + number + " " + parameterName));
    names.push(normalize("Band " + number + " " + parameterName + " A"));
    names.push(normalize(number + " " + parameterName + " A"));
    names.push(normalize(number + compact + "a"));
    names.push(normalize(number + parameterName + "A"));
    return names;
}


function resolveBandParameter(device, band, parameterName) {
    var wanted = bandParameterNames(band, parameterName);
    var parameterIds = idsFrom(device.api.get("parameters"));
    for (var index = 0; index < parameterIds.length; index += 1) {
        var parameter = new LiveAPI(function () {}, "id " + parameterIds[index]);
        var name = normalize(valueOf(parameter.get("name"), ""));
        for (var wantedIndex = 0; wantedIndex < wanted.length; wantedIndex += 1) {
            if (name === wanted[wantedIndex]) {
                return {
                    index: index,
                    id: parameterIds[index],
                    api: parameter,
                    name: String(valueOf(parameter.get("name"), ""))
                };
            }
        }
    }
    return null;
}


function clamp(value, min, max) {
    return Math.max(min, Math.min(max, Number(value)));
}


function hzToEqFrequencyValue(hz) {
    var frequency = Math.max(10, Math.min(22000, Number(hz)));
    return Math.log(frequency / 10) / Math.log(22000 / 10);
}


function valueForMove(move, parameter) {
    if (normalize(move.parameter) === "frequency" && parameter.min === 0 && parameter.max === 1) {
        return hzToEqFrequencyValue(move.value);
    }
    return Number(move.value);
}


function presetList() {
    var names = objectKeys(EQ_PRESETS);
    var presets = [];
    for (var index = 0; index < names.length; index += 1) {
        var preset = EQ_PRESETS[names[index]];
        presets.push({
            name: names[index],
            description: preset.description,
            moves: preset.moves
        });
    }
    return presets;
}


function readEq(payload) {
    var track = resolveTrack(payload);
    var device = resolveEqDevice(track, payload);
    var parameterResult = eqParameters(device, payload.limit);
    return {
        track_index: track.index,
        track_id: track.id,
        track_name: track.name,
        device: devicePayload(device, device.index),
        parameter_count: parameterResult.total_count,
        returned_parameter_count: parameterResult.parameters.length,
        truncated: parameterResult.truncated,
        parameters: parameterResult.parameters
    };
}


function applyMoves(track, device, moves, dryRun) {
    var changes = [];
    var skipped = [];
    for (var index = 0; index < moves.length; index += 1) {
        var move = moves[index];
        var band = Number(move.band);
        var parameterName = String(move.parameter || "");
        var parameter = resolveBandParameter(device, band, parameterName);
        if (!parameter) {
            skipped.push({band: band, parameter: parameterName, reason: "parameter not found"});
            continue;
        }
        var before = parameterInfo(parameter.api, parameter.index, parameter.id);
        var afterValue = clamp(valueForMove(move, before), before.min, before.max);
        if (before.is_quantized) {
            afterValue = Math.round(afterValue);
        }
        if (!dryRun) {
            parameter.api.set("value", afterValue);
        }
        var after = parameterInfo(parameter.api, parameter.index, parameter.id);
        if (dryRun) {
            after.value = afterValue;
            after.display_value = displayValue(parameter.api, afterValue);
        }
        changes.push({
            band: band,
            requested_parameter: parameterName,
            parameter: {
                index: before.index,
                id: before.id,
                name: before.name,
                min: before.min,
                max: before.max,
                is_quantized: before.is_quantized
            },
            before: {
                value: before.value,
                display_value: before.display_value
            },
            requested_value: Number(move.value),
            after: {
                value: after.value,
                display_value: after.display_value
            }
        });
    }
    return {
        track_index: track.index,
        track_id: track.id,
        track_name: track.name,
        device: devicePayload(device, device.index),
        changed_count: changes.length,
        skipped_count: skipped.length,
        changes: changes,
        skipped: skipped
    };
}


function applyPreset(payload, dryRun) {
    var presetName = String(payload.preset || payload.name || "");
    var preset = EQ_PRESETS[presetName];
    if (!preset) {
        throw new Error("Unknown EQ preset: " + presetName);
    }
    var track = resolveTrack(payload);
    var device = resolveEqDevice(track, payload);
    var plan = applyMoves(track, device, preset.moves, dryRun);
    plan.preset = presetName;
    plan.description = preset.description;
    return plan;
}


function setBand(payload, dryRun) {
    if (payload.band === undefined || payload.parameter === undefined || payload.value === undefined) {
        throw new Error("band, parameter, and value are required");
    }
    var track = resolveTrack(payload);
    var device = resolveEqDevice(track, payload);
    return applyMoves(track, device, [{
        band: payload.band,
        parameter: payload.parameter,
        value: payload.value
    }], dryRun);
}


function handleEqTools(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var action = String(payload.action || "list_presets");
        var allowed = ["list_presets", "read_eq", "apply_preset", "set_band"];
        if (allowed.indexOf(action) < 0) {
            throw new Error("action must be list_presets, read_eq, apply_preset, or set_band");
        }
        if (action === "list_presets") {
            outlet(0, [requestId, JSON.stringify({
                ok: true,
                dry_run: true,
                applied: false,
                action: action,
                presets: presetList(),
                message: "EQ presets listed"
            })]);
            return;
        }
        var result = action === "read_eq"
            ? readEq(payload)
            : (action === "apply_preset" ? applyPreset(payload, dryRun) : setBand(payload, dryRun));
        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: action === "read_eq" ? true : dryRun,
            applied: action === "read_eq" ? false : !dryRun,
            action: action,
            result: result,
            message: action === "read_eq" ? "EQ Eight read" : (dryRun ? "Ready to apply EQ change" : "EQ change applied")
        })]);
    } catch (error) {
        outlet(0, [requestId, JSON.stringify({
            ok: false,
            dry_run: dryRun,
            applied: false,
            error: error && error.message ? error.message : String(error),
            presets: presetList()
        })]);
    }
}

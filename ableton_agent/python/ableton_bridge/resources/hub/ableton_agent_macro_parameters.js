autowatch = 1;
inlets = 1;
outlets = 1;

var MAX_PARAMETERS = 64;

function list() {
    var args = arrayfromargs(arguments);
    handleMacroParameters(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}

function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleMacroParameters(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
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
    return String(value || "").toLowerCase().replace(/^\s+|\s+$/g, "");
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

function resolveDevice(track, payload) {
    var deviceIds = idsFrom(track.api.get("devices"));
    if (!deviceIds.length) {
        throw new Error("Track has no devices");
    }
    if (payload.device_index !== undefined) {
        var requestedIndex = Number(payload.device_index);
        if (requestedIndex < 0 || requestedIndex >= deviceIds.length || Math.floor(requestedIndex) !== requestedIndex) {
            throw new Error("device_index is outside this track device list");
        }
        return {index: requestedIndex, id: deviceIds[requestedIndex], api: new LiveAPI(function () {}, "id " + deviceIds[requestedIndex])};
    }
    var selector = payload.device || payload.device_name;
    if (selector !== undefined && selector !== null && selector !== "") {
        var wanted = normalize(selector);
        for (var namedIndex = 0; namedIndex < deviceIds.length; namedIndex += 1) {
            var namedDevice = new LiveAPI(function () {}, "id " + deviceIds[namedIndex]);
            if (normalize(valueOf(namedDevice.get("name"), "")) === wanted) {
                return {index: namedIndex, id: deviceIds[namedIndex], api: namedDevice};
            }
        }
        throw new Error("Device not found on track: " + selector);
    }
    for (var index = 0; index < deviceIds.length; index += 1) {
        var device = new LiveAPI(function () {}, "id " + deviceIds[index]);
        var name = String(valueOf(device.get("name"), ""));
        var className = String(valueOf(device.get("class_name"), ""));
        if (className !== "MxDeviceMidiEffect" && name.indexOf("Ableton Agent") !== 0) {
            return {index: index, id: deviceIds[index], api: device};
        }
    }
    return {index: 0, id: deviceIds[0], api: new LiveAPI(function () {}, "id " + deviceIds[0])};
}

function parameterSnapshot(parameterId, index) {
    var parameter = new LiveAPI(function () {}, "id " + parameterId);
    var value = Number(valueOf(parameter.get("value"), 0));
    return {
        parameter_index: index,
        parameter_id: parameterId,
        name: String(valueOf(parameter.get("name"), "")),
        value: value,
        display_value: displayValue(parameter, value),
        min: Number(valueOf(parameter.get("min"), 0)),
        max: Number(valueOf(parameter.get("max"), 1)),
        is_quantized: Boolean(Number(valueOf(parameter.get("is_quantized"), 0)))
    };
}

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, Number(value)));
}

function resolveParameterBySnapshot(device, snapshotParameter) {
    var parameterIds = idsFrom(device.api.get("parameters"));
    if (snapshotParameter.parameter_index !== undefined) {
        var requestedIndex = Number(snapshotParameter.parameter_index);
        if (isFinite(requestedIndex) && requestedIndex >= 0 && requestedIndex < parameterIds.length && Math.floor(requestedIndex) === requestedIndex) {
            return parameterSnapshot(parameterIds[requestedIndex], requestedIndex);
        }
    }
    var wanted = normalize(snapshotParameter.name || snapshotParameter.parameter || "");
    if (wanted) {
        for (var index = 0; index < parameterIds.length; index += 1) {
            var parameter = new LiveAPI(function () {}, "id " + parameterIds[index]);
            if (normalize(valueOf(parameter.get("name"), "")) === wanted) {
                return parameterSnapshot(parameterIds[index], index);
            }
        }
    }
    return null;
}

function scanSnapshot(payload) {
    var track = resolveTrack(payload);
    var device = resolveDevice(track, payload);
    var deviceName = String(valueOf(device.api.get("name"), ""));
    var parameterIds = idsFrom(device.api.get("parameters"));
    var limit = Math.max(1, Math.min(MAX_PARAMETERS, Math.round(Number(payload.limit || 16))));
    var parameters = [];
    for (var index = 0; index < parameterIds.length && parameters.length < limit; index += 1) {
        parameters.push(parameterSnapshot(parameterIds[index], index));
    }
    return {
        snapshot_name: String(payload.snapshot_name || payload.name || ""),
        track_index: track.index,
        track_id: track.id,
        track_name: track.name,
        device_index: device.index,
        device_id: device.id,
        device_name: deviceName,
        parameter_count: parameterIds.length,
        summarized_parameter_count: parameters.length,
        parameters: parameters
    };
}

function snapshotFromPayload(payload, key) {
    var snapshot = payload[key];
    if (typeof snapshot === "string") {
        try {
            snapshot = JSON.parse(snapshot);
        } catch (_error) {
            throw new Error(key + " must be a snapshot object or JSON string");
        }
    }
    if (!snapshot || !(snapshot.parameters instanceof Array)) {
        throw new Error(key + " must contain a parameters array");
    }
    return snapshot;
}

function plannedChangesFromSnapshot(payload, dryRun, parameters) {
    var track = resolveTrack(payload);
    var device = resolveDevice(track, payload);
    var changes = [];
    var skipped = [];
    for (var index = 0; index < parameters.length; index += 1) {
        var wanted = parameters[index];
        var resolved = resolveParameterBySnapshot(device, wanted);
        if (!resolved) {
            skipped.push({name: wanted.name || "", parameter_index: wanted.parameter_index, reason: "parameter not found"});
            continue;
        }
        var parameter = new LiveAPI(function () {}, "id " + resolved.parameter_id);
        var before = Number(valueOf(parameter.get("value"), 0));
        var target = clamp(wanted.value, resolved.min, resolved.max);
        if (!dryRun) {
            parameter.set("value", target);
        }
        changes.push({
            parameter_index: resolved.parameter_index,
            parameter_id: resolved.parameter_id,
            name: resolved.name,
            before_value: before,
            before_display: displayValue(parameter, before),
            after_value: target,
            after_display: displayValue(parameter, target)
        });
    }
    return {
        track_index: track.index,
        track_id: track.id,
        track_name: track.name,
        device_index: device.index,
        device_id: device.id,
        device_name: String(valueOf(device.api.get("name"), "")),
        changed_count: changes.length,
        skipped_count: skipped.length,
        changes: changes,
        skipped: skipped
    };
}

function applySnapshot(payload, dryRun) {
    var snapshot = snapshotFromPayload(payload, "snapshot");
    return plannedChangesFromSnapshot(payload, dryRun, snapshot.parameters);
}

function morphSnapshots(payload, dryRun) {
    var fromSnapshot = snapshotFromPayload(payload, "from_snapshot");
    var toSnapshot = snapshotFromPayload(payload, "to_snapshot");
    var amount = Number(payload.amount === undefined ? payload.morph : payload.amount);
    if (!isFinite(amount)) {
        amount = 0.5;
    }
    amount = clamp(amount, 0.0, 1.0);
    var fromByKey = {};
    for (var fromIndex = 0; fromIndex < fromSnapshot.parameters.length; fromIndex += 1) {
        var fromParam = fromSnapshot.parameters[fromIndex];
        fromByKey[String(fromParam.parameter_index) + "|" + normalize(fromParam.name)] = fromParam;
    }
    var morphed = [];
    for (var toIndex = 0; toIndex < toSnapshot.parameters.length; toIndex += 1) {
        var toParam = toSnapshot.parameters[toIndex];
        var key = String(toParam.parameter_index) + "|" + normalize(toParam.name);
        var source = fromByKey[key];
        if (!source) {
            continue;
        }
        morphed.push({
            parameter_index: toParam.parameter_index,
            name: toParam.name,
            value: Number(source.value) + (Number(toParam.value) - Number(source.value)) * amount
        });
    }
    var result = plannedChangesFromSnapshot(payload, dryRun, morphed);
    result.amount = amount;
    result.morphed_parameter_count = morphed.length;
    return result;
}

function handleMacroParameters(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var action = String(payload.action || "scan_snapshot");
        var allowed = ["scan_snapshot", "apply_snapshot", "morph_snapshots"];
        if (allowed.indexOf(action) < 0) {
            throw new Error("action must be scan_snapshot, apply_snapshot, or morph_snapshots");
        }
        if (action === "apply_snapshot") {
            var applied = applySnapshot(payload, dryRun);
            outlet(0, [requestId, JSON.stringify({
                ok: true,
                dry_run: dryRun,
                applied: !dryRun,
                action: action,
                plan: applied,
                message: dryRun ? "Ready to apply parameter snapshot" : "Parameter snapshot applied"
            })]);
            return;
        }
        if (action === "morph_snapshots") {
            var morphed = morphSnapshots(payload, dryRun);
            outlet(0, [requestId, JSON.stringify({
                ok: true,
                dry_run: dryRun,
                applied: !dryRun,
                action: action,
                plan: morphed,
                message: dryRun ? "Ready to apply morphed parameter state" : "Morphed parameter state applied"
            })]);
            return;
        }
        var snapshot = scanSnapshot(payload);
        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: true,
            applied: false,
            action: action,
            snapshot: snapshot,
            message: "Parameter snapshot scanned; Python can save this JSON snapshot"
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

autowatch = 1;
inlets = 1;
outlets = 1;

include("ableton_agent_device_tree.js");
include("ableton_agent_value_display.js");
include("ableton_agent_ui_input.js");


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


function nowMs() {
    return new Date().getTime();
}


function valuesEqual(left, right) {
    return Math.abs(Number(left) - Number(right)) <= 0.000001;
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
    return AbletonAgentValueDisplay.attachCurrent({
        index: index,
        id: id,
        name: String(valueOf(parameter.get("name"), "")),
        value: value,
        min: Number(valueOf(parameter.get("min"), 0)),
        max: Number(valueOf(parameter.get("max"), 1)),
        is_quantized: Boolean(Number(valueOf(parameter.get("is_quantized"), 0))),
        is_enabled: Boolean(Number(valueOf(AbletonAgentDeviceTree.safeGet(parameter, "is_enabled", 1), 1))),
        automation_state: currentAutomationState,
        automation_state_name: automationStateName(currentAutomationState)
    }, parameter, value);
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


function targetDevice(track, change) {
    var deviceIds = idsFrom(track.get("devices"));
    if (!deviceIds.length) {
        throw new Error("Track has no devices");
    }

    if (change.device_id !== undefined && change.device_id !== null && change.device_id !== "") {
        return AbletonAgentDeviceTree.findDevice(track, change.device_id, {
            max_depth: change.max_device_depth,
            max_devices: change.max_device_count
        });
    }

    if (change.device_index !== undefined) {
        var requestedIndex = Number(change.device_index);
        if (requestedIndex < 0 || requestedIndex >= deviceIds.length || Math.floor(requestedIndex) !== requestedIndex) {
            throw new Error("device_index is outside this track device list");
        }
        return {
            id: deviceIds[requestedIndex],
            api: new LiveAPI(function () {}, "id " + deviceIds[requestedIndex]),
            record: null
        };
    }

    if (change.device_name || change.device) {
        var wanted = normalize(change.device_name || change.device);
        for (var namedIndex = 0; namedIndex < deviceIds.length; namedIndex += 1) {
            var namedDevice = new LiveAPI(function () {}, "id " + deviceIds[namedIndex]);
            var namedName = String(valueOf(namedDevice.get("name"), ""));
            if (normalize(namedName) === wanted) {
                return {id: deviceIds[namedIndex], api: namedDevice, record: null};
            }
        }
        throw new Error("Device not found on track: " + (change.device_name || change.device));
    }

    for (var index = 0; index < deviceIds.length; index += 1) {
        var device = new LiveAPI(function () {}, "id " + deviceIds[index]);
        var className = String(valueOf(device.get("class_name"), ""));
        var name = String(valueOf(device.get("name"), ""));
        if (className !== "MxDeviceMidiEffect" && name.indexOf("Ableton Agent") !== 0) {
            return {id: deviceIds[index], api: device, record: null};
        }
    }
    return {id: deviceIds[0], api: new LiveAPI(function () {}, "id " + deviceIds[0]), record: null};
}


function selectorIsIndex(selector) {
    return /^[0-9]+$/.test(String(selector || ""));
}


function resolveParameter(device, selector, parameterId) {
    var parameterIds = idsFrom(device.get("parameters"));
    if (!parameterIds.length) {
        throw new Error("Target device has no parameters");
    }
    if (parameterId !== undefined && parameterId !== null && parameterId !== "") {
        var wantedId = Number(parameterId);
        var idIndex = parameterIds.indexOf(wantedId);
        if (idIndex < 0) {
            throw new Error("parameter_id is not on the target device");
        }
        return {
            index: idIndex,
            id: wantedId,
            api: new LiveAPI(function () {}, "id " + wantedId)
        };
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
    var deviceTarget = targetDevice(track.api, change);
    var deviceId = deviceTarget.id;
    var device = deviceTarget.api;
    var selector = change.parameter !== undefined ? change.parameter : change.parameter_name;
    var parameter = resolveParameter(device, selector, change.parameter_id);
    var before = parameterInfo(parameter.api, parameter.index, parameter.id);
    var value = AgentUiInput.resolve(change, parameter.api, before,
        {device_class:change.ui_value !== undefined ? String(valueOf(device.get("class_name"), "")) : ""});
    if (!isFinite(value)) {
        throw new Error("value must be a number");
    }
    if (BLOCKED_PARAMETERS[normalize(before.name)]) {
        throw new Error("Refusing to control protected parameter: " + before.name);
    }
    if (!before.is_enabled) {
        throw new Error("Parameter is disabled in Live and may be Macro-controlled: " + before.name);
    }
    if (value < before.min || value > before.max) {
        throw new Error("Value must be between " + before.min + " and " + before.max);
    }
    if (before.is_quantized) {
        value = Math.round(value);
    }
    if (change.expected_before !== undefined && !valuesEqual(before.value, change.expected_before)) {
        throw new Error("stale_before_value: current " + before.value + " does not match expected " + change.expected_before);
    }
    return {
        change_index: changeIndex,
        track: track,
        device_id: deviceId,
        device: device,
        device_record: deviceTarget.record,
        parameter: parameter,
        before: before,
        value: value,
        requested_ui_value: change.ui_value
    };
}


function restoreChange(resolved, afterValue) {
    return {
        section: resolved.track.section,
        track_id: resolved.track.id,
        device_id: resolved.device_id,
        parameter_id: resolved.parameter.id,
        value: resolved.before.value,
        expected_before: afterValue,
        max_device_depth: resolved.device_record ? resolved.device_record.depth : 0
    };
}


function resultForResolved(resolved, after) {
    return {
        change_index: resolved.change_index,
        section: resolved.track.section,
        track_index: resolved.track.index,
        track_id: resolved.track.id,
        track_name: String(valueOf(resolved.track.api.get("name"), "")),
        device_id: resolved.device_id,
        device_name: String(valueOf(resolved.device.get("name"), "")),
        device_class_name: String(valueOf(resolved.device.get("class_name"), "")),
        device_depth: resolved.device_record ? resolved.device_record.depth : 0,
        parent_chain_id: resolved.device_record ? resolved.device_record.parent_chain_id : null,
        parent_rack_device_id: resolved.device_record ? resolved.device_record.parent_rack_device_id : null,
        chain_path: resolved.device_record ? resolved.device_record.chain_path : [],
        target_kind: Boolean(Number(valueOf(AbletonAgentDeviceTree.safeGet(resolved.device, "can_have_chains", 0), 0)))
            ? "rack_parameter"
            : (resolved.device_record && resolved.device_record.depth > 0 ? "nested_device_parameter" : "device_parameter"),
        parameter: {
            index: resolved.before.index,
            id: resolved.before.id,
            name: resolved.before.name,
            min: resolved.before.min,
            max: resolved.before.max,
            is_quantized: resolved.before.is_quantized,
            is_enabled: resolved.before.is_enabled
        },
        before: AbletonAgentValueDisplay.valuePayload(resolved.before),
        requested_value: resolved.value,
        requested_ui_value: resolved.requested_ui_value,
        after: AbletonAgentValueDisplay.valuePayload(after)
    };
}


function setParameters(requestId, payloadText, mode) {
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
            for (var identityIndex = 0; identityIndex < resolved.length; identityIndex += 1) {
                if (resolved[identityIndex].device_record && resolved[identityIndex].device_record.depth > 0) {
                    if (changes[identityIndex].track_id === undefined || changes[identityIndex].device_id === undefined || changes[identityIndex].parameter_id === undefined) {
                        throw new Error("Apply to a nested device requires stable track_id, device_id, and parameter_id");
                    }
                }
            }
        }

        if (!dryRun) {
            var writeStartedAt = nowMs();
            for (var writeIndex = 0; writeIndex < resolved.length; writeIndex += 1) {
                resolved[writeIndex].parameter.api.set("value", resolved[writeIndex].value);
                written.push(resolved[writeIndex]);
            }
            timing.write_ms = nowMs() - writeStartedAt;
        }

        var readbackStartedAt = nowMs();
        for (var resultIndex = 0; resultIndex < resolved.length; resultIndex += 1) {
            var after = parameterInfo(
                resolved[resultIndex].parameter.api,
                resolved[resultIndex].parameter.index,
                resolved[resultIndex].parameter.id
            );
            if (!dryRun && !valuesEqual(after.value, resolved[resultIndex].value)) {
                throw new Error("readback_mismatch at change " + resultIndex);
            }
            if (dryRun) {
                after.value = resolved[resultIndex].value;
                AbletonAgentValueDisplay.attachTarget(
                    after,
                    resolved[resultIndex].parameter.api,
                    resolved[resultIndex].value
                );
            }
            results.push(resultForResolved(resolved[resultIndex], after));
        }
        timing.readback_ms = nowMs() - readbackStartedAt;
        timing.total_ms = nowMs() - startedAt;

        var restoreChanges = [];
        if (!dryRun) {
            for (var receiptIndex = 0; receiptIndex < resolved.length; receiptIndex += 1) {
                var currentValue = Number(valueOf(resolved[receiptIndex].parameter.api.get("value"), 0));
                restoreChanges.push(restoreChange(resolved[receiptIndex], currentValue));
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
                route: "/set_parameters",
                restore_changes: restoreChanges
            },
            message: dryRun ? "Targets inspected; no Live state changed" : "Parameters updated and read back"
        })]);
    } catch (error) {
        var rollbackErrors = [];
        if (!dryRun && written.length) {
            for (var rollbackIndex = written.length - 1; rollbackIndex >= 0; rollbackIndex -= 1) {
                try {
                    written[rollbackIndex].parameter.api.set("value", written[rollbackIndex].before.value);
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

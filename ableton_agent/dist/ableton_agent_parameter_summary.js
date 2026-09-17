autowatch = 1;
include("ableton_agent_health.js");
inlets = 1;
outlets = 2;

include("ableton_agent_read_core.js");
include("ableton_agent_device_tree.js");
include("ableton_agent_value_display.js");
include("ableton_agent_parameter_diagnostics.js");


var DEFAULT_MAX_DEVICES_PER_TRACK = 2;
var DEFAULT_MAX_PARAMETERS_PER_DEVICE = 16;
var DEFAULT_BOUNDED_PARAMETER_LIMIT = 4;
var MAX_TRACKS = 64;
var MAX_DEVICES_PER_TRACK = 8;
var MAX_PARAMETERS_PER_DEVICE = 32;
var MAX_PARAMETER_SCAN = 512;
var MAX_ENUM_VALUES = 64;


function bang() {
    readParameterSummary("", "{}");
}


function list() {
    var args = arrayfromargs(arguments);
    readParameterSummary(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    readParameterSummary(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
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


function safeGet(api, propertyName, fallback) {
    try {
        return api.get(propertyName);
    } catch (_error) {
        return fallback;
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


function deviceTypeName(typeValue) {
    if (typeValue === 0) {
        return "audio_effect";
    }
    if (typeValue === 1) {
        return "instrument";
    }
    if (typeValue === 2) {
        return "midi_effect";
    }
    if (typeValue === 4) {
        return "max_for_live";
    }
    return "unknown";
}


function isAgentDevice(device) {
    var name = String(valueOf(safeGet(device, "name", ""), ""));
    var className = String(valueOf(safeGet(device, "class_name", ""), ""));
    return name.indexOf("Ableton Agent") === 0 || className === "MxDeviceMidiEffect";
}


function parameterInfo(parameterId, index, includeDisplayValues) {
    var parameter = new LiveAPI(function () {}, "id " + parameterId);
    var value = Number(valueOf(safeGet(parameter, "value", 0), 0));
    var currentAutomationState = Number(valueOf(safeGet(parameter, "automation_state", 0), 0));
    var result = {
        index: index,
        id: parameterId,
        name: String(valueOf(safeGet(parameter, "name", ""), "")),
        value: value,
        min: Number(valueOf(safeGet(parameter, "min", 0), 0)),
        max: Number(valueOf(safeGet(parameter, "max", 1), 1)),
        is_quantized: Boolean(Number(valueOf(safeGet(parameter, "is_quantized", 0), 0))),
        is_enabled: Boolean(Number(valueOf(safeGet(parameter, "is_enabled", 1), 1))),
        automation_state: currentAutomationState,
        automation_state_name: automationStateName(currentAutomationState)
    };
    if (includeDisplayValues) {
        AbletonAgentValueDisplay.attachCurrent(result, parameter, value);
    }
    return result;
}


function readDevice(deviceId, index, maxParameters, includeDisplayValues) {
    var device = new LiveAPI(function () {}, "id " + deviceId);
    var typeValue = Number(valueOf(safeGet(device, "type", -1), -1));
    var parameterIds = idsFrom(safeGet(device, "parameters", []));
    var parameters = [];
    var limit = Math.min(parameterIds.length, maxParameters);
    for (var parameterIndex = 0; parameterIndex < limit; parameterIndex += 1) {
        parameters.push(parameterInfo(parameterIds[parameterIndex], parameterIndex, includeDisplayValues));
    }
    return {
        index: index,
        id: deviceId,
        name: String(valueOf(safeGet(device, "name", ""), "")),
        class_name: String(valueOf(safeGet(device, "class_name", ""), "")),
        type: typeValue,
        type_name: deviceTypeName(typeValue),
        parameter_count: parameterIds.length,
        summarized_parameter_count: parameters.length,
        parameters: parameters
    };
}


function readTrack(trackId, index, maxDevices, maxParameters, includeDisplayValues) {
    var track = new LiveAPI(function () {}, "id " + trackId);
    var deviceIds = idsFrom(safeGet(track, "devices", []));
    var devices = [];
    var selectedDeviceName = "";
    var scanned = 0;
    for (var deviceIndex = 0; deviceIndex < deviceIds.length; deviceIndex += 1) {
        var device = new LiveAPI(function () {}, "id " + deviceIds[deviceIndex]);
        if (isAgentDevice(device)) {
            continue;
        }
        if (!selectedDeviceName) {
            selectedDeviceName = String(valueOf(safeGet(device, "name", ""), ""));
        }
        devices.push(readDevice(deviceIds[deviceIndex], deviceIndex, maxParameters, includeDisplayValues));
        scanned += 1;
        if (scanned >= maxDevices) {
            break;
        }
    }
    return {
        index: index,
        id: trackId,
        name: String(valueOf(safeGet(track, "name", ""), "")),
        device_count: deviceIds.length,
        summarized_device_count: devices.length,
        target_device: selectedDeviceName,
        devices: devices
    };
}


function clampInt(value, fallback, minimum, maximum) {
    var number = Number(value);
    if (!isFinite(number)) {
        return fallback;
    }
    number = Math.floor(number);
    return Math.max(minimum, Math.min(maximum, number));
}


function truthy(value) {
    return value === true || value === 1 || value === "1" || value === "true";
}


function normalize(value) {
    return String(value || "").toLowerCase().replace(/^\s+|\s+$/g, "");
}


function idFrom(raw) {
    var ids = idsFrom(raw);
    return ids.length ? ids[0] : 0;
}


function resolveInspectionTrack(payload) {
    var song = new LiveAPI(function () {}, "live_set");
    var section = normalize(payload.section || "track");
    if (section === "master") {
        section = "main";
    }
    if (section === "main") {
        var mainId = idFrom(safeGet(song, "master_track", []));
        if (payload.track_id !== undefined && Number(payload.track_id) !== mainId) {
            throw new Error("track_id does not match the current Main track");
        }
        return {section: "main", index: 0, id: mainId, api: new LiveAPI(function () {}, "id " + mainId)};
    }

    section = section === "return" ? "return" : "track";
    var trackIds = idsFrom(safeGet(song, section === "return" ? "return_tracks" : "tracks", []));
    if (payload.track_id !== undefined && payload.track_id !== null && payload.track_id !== "") {
        var wantedId = Number(payload.track_id);
        var idIndex = trackIds.indexOf(wantedId);
        if (idIndex < 0) {
            throw new Error("track_id is not in the requested " + section + " section");
        }
        return {section: section, index: idIndex, id: wantedId, api: new LiveAPI(function () {}, "id " + wantedId)};
    }

    var selector = payload.track_index !== undefined ? payload.track_index : (payload.track_name !== undefined ? payload.track_name : payload.track);
    if (selector === undefined || selector === null || selector === "") {
        throw new Error("Missing track selector; use section + track_id or an ordinary track name/index");
    }
    if (typeof selector === "number" || /^\d+$/.test(String(selector))) {
        var requestedIndex = Number(selector);
        if (requestedIndex < 0 || requestedIndex >= trackIds.length || Math.floor(requestedIndex) !== requestedIndex) {
            throw new Error("track index is outside the requested track section");
        }
        return {section: section, index: requestedIndex, id: trackIds[requestedIndex], api: new LiveAPI(function () {}, "id " + trackIds[requestedIndex])};
    }

    var wantedName = normalize(selector);
    for (var index = 0; index < trackIds.length; index += 1) {
        var track = new LiveAPI(function () {}, "id " + trackIds[index]);
        if (normalize(valueOf(safeGet(track, "name", ""), "")) === wantedName) {
            return {section: section, index: index, id: trackIds[index], api: track};
        }
    }
    throw new Error("Track not found: " + selector);
}


function resolveInspectionDevice(track, payload) {
    var deviceIds = idsFrom(safeGet(track.api, "devices", []));
    if (!deviceIds.length) {
        throw new Error("Target track has no devices");
    }
    if (payload.device_id !== undefined && payload.device_id !== null && payload.device_id !== "") {
        var found = AbletonAgentDeviceTree.findDevice(track.api, payload.device_id, {
            max_depth: payload.max_device_depth,
            max_devices: payload.max_device_count
        });
        return {
            index: found.record.device_index,
            id: found.id,
            api: found.api,
            record: found.record
        };
    }
    if (payload.device_index !== undefined) {
        var requestedIndex = Number(payload.device_index);
        if (requestedIndex < 0 || requestedIndex >= deviceIds.length || Math.floor(requestedIndex) !== requestedIndex) {
            throw new Error("device_index is outside the target track device list");
        }
        return {index: requestedIndex, id: deviceIds[requestedIndex], api: new LiveAPI(function () {}, "id " + deviceIds[requestedIndex]), record: null};
    }
    if (payload.device_name || payload.device) {
        var wantedName = normalize(payload.device_name || payload.device);
        for (var namedIndex = 0; namedIndex < deviceIds.length; namedIndex += 1) {
            var namedDevice = new LiveAPI(function () {}, "id " + deviceIds[namedIndex]);
            if (normalize(valueOf(safeGet(namedDevice, "name", ""), "")) === wantedName) {
                return {index: namedIndex, id: deviceIds[namedIndex], api: namedDevice, record: null};
            }
        }
        throw new Error("Device not found on target track: " + (payload.device_name || payload.device));
    }
    return {index: 0, id: deviceIds[0], api: new LiveAPI(function () {}, "id " + deviceIds[0]), record: null};
}


function enumValues(parameter, minimum, maximum) {
    var first = Math.ceil(minimum);
    var last = Math.floor(maximum);
    if (last < first || last - first + 1 > MAX_ENUM_VALUES) {
        return {available: false, reason: "quantized range exceeds safe enumeration limit", values: []};
    }
    var values = [];
    for (var value = first; value <= last; value += 1) {
        values.push(AbletonAgentValueDisplay.attachTarget({value: value}, parameter, value));
    }
    return {available: true, values: values};
}


function inspectedParameterInfo(parameterId, index, includeDisplayValues, includeEnumValues) {
    var result = parameterInfo(parameterId, index, includeDisplayValues);
    if (includeEnumValues && result.is_quantized) {
        var parameter = new LiveAPI(function () {}, "id " + parameterId);
        result.enum_values = enumValues(parameter, result.min, result.max);
    }
    return result;
}


function projectedParameterInfo(parameterId, index, name, read, diagnostics) {
    var parameter = new LiveAPI(function () {}, "id " + parameterId);
    var result = {};
    var parameterContext = {index: index, id: parameterId, name: name};
    var needsValue = AbletonAgentReadCore.has(read, "internal_value") || AbletonAgentReadCore.has(read, "display_value");
    var needsMetadata = AbletonAgentReadCore.has(read, "metadata") || AbletonAgentReadCore.has(read, "enum_values");
    var value = needsValue ? Number(valueOf(AbletonAgentParameterDiagnostics.readProperty(
        parameter, "value", diagnostics, "internal_value", parameterContext
    ), 0)) : null;
    var minimum = needsMetadata ? Number(valueOf(AbletonAgentParameterDiagnostics.readProperty(
        parameter, "min", diagnostics, "metadata", parameterContext
    ), 0)) : null;
    var maximum = needsMetadata ? Number(valueOf(AbletonAgentParameterDiagnostics.readProperty(
        parameter, "max", diagnostics, "metadata", parameterContext
    ), 1)) : null;
    var isQuantized = needsMetadata ? Boolean(Number(valueOf(AbletonAgentParameterDiagnostics.readProperty(
        parameter, "is_quantized", diagnostics, "metadata", parameterContext
    ), 0))) : null;
    var isEnabled = needsMetadata ? Boolean(Number(valueOf(AbletonAgentParameterDiagnostics.readProperty(
        parameter, "is_enabled", diagnostics, "metadata", parameterContext
    ), 1))) : null;
    var needsAutomation = AbletonAgentReadCore.has(read, "automation_state");
    var automationState = needsMetadata || needsAutomation ? valueOf(AbletonAgentParameterDiagnostics.readProperty(
        parameter, "automation_state", diagnostics, "metadata", parameterContext
    ), null) : null;
    if (needsAutomation && (automationState === null || [0, 1, 2].indexOf(Number(automationState)) < 0)) {
        throw new Error("Missing or invalid automation_state for parameter " + parameterId);
    }
    automationState = automationState === null ? 0 : Number(automationState);
    if (AbletonAgentReadCore.has(read, "identity")) {
        result.index = index;
        result.id = parameterId;
        result.name = name;
    }
    if (AbletonAgentReadCore.has(read, "metadata")) {
        result.min = minimum;
        result.max = maximum;
        result.is_quantized = isQuantized;
        result.is_enabled = isEnabled;
    }
    if (AbletonAgentReadCore.has(read, "metadata") || needsAutomation) {
        result.automation_state = automationState;
        result.automation_state_name = automationStateName(automationState);
    }
    if (AbletonAgentReadCore.has(read, "internal_value")) {
        result.value = value;
    }
    if (AbletonAgentReadCore.has(read, "display_value")) {
        AbletonAgentParameterDiagnostics.runField(
            diagnostics, "display_value", parameterContext, "display_value/str_for_value", function () {
                return AbletonAgentValueDisplay.attachCurrent(result,
                    AbletonAgentParameterDiagnostics.tracedApi(parameter, diagnostics, "display_value", parameterContext), value);
            }
        );
    }
    if (AbletonAgentReadCore.has(read, "enum_values")) {
        result.enum_values = AbletonAgentParameterDiagnostics.runField(
            diagnostics, "enum_values", parameterContext, "str_for_value", function () {
                return isQuantized
                    ? enumValues(AbletonAgentParameterDiagnostics.tracedApi(parameter, diagnostics, "enum_values", parameterContext), minimum, maximum)
                    : {available: false, reason: "parameter is not quantized", values: []};
            }
        );
    }
    AbletonAgentParameterDiagnostics.mark(diagnostics, "parameter_completed", {
        operation: null,
        parameter: parameterContext,
        property: null
    });
    return result;
}


function readDeviceParameterPageBounded(requestId, payload, mode, diagnostics) {
    if (normalize(mode || "dry_run") !== "dry_run") {
        throw new Error("parameter_summary inspection actions are read-only and only accept dry_run mode");
    }
    var action = normalize(payload.action);
    var query = normalize(payload.query || "");
    if (action === "search_parameters" && !query) {
        throw new Error("search_parameters requires a non-empty query");
    }
    var read = AbletonAgentReadCore.parse(payload, {
        max_limit: MAX_PARAMETERS_PER_DEVICE,
        max_cursor: MAX_PARAMETER_SCAN,
        default_limit: DEFAULT_BOUNDED_PARAMETER_LIMIT,
        allowed_projection: ["identity", "metadata", "internal_value", "display_value", "enum_values", "automation_state"],
        default_projection: ["identity", "metadata", "internal_value"]
    });
    AbletonAgentParameterDiagnostics.mark(diagnostics, "payload_validated");
    AbletonAgentParameterDiagnostics.mark(diagnostics, "track_resolving");
    var track = resolveInspectionTrack(payload);
    AbletonAgentParameterDiagnostics.mark(diagnostics, "track_resolved");
    AbletonAgentParameterDiagnostics.mark(diagnostics, "device_resolving");
    var device = resolveInspectionDevice(track, payload);
    AbletonAgentParameterDiagnostics.mark(diagnostics, "device_resolved");
    AbletonAgentParameterDiagnostics.mark(diagnostics, "parameter_collection_loading");
    var rawParameterIds;
    try {
        rawParameterIds = device.api.get("parameters");
    } catch (collectionError) {
        throw AbletonAgentParameterDiagnostics.failure(
            "lom_collection_read_failed", "LiveAPI parameter collection read failed", diagnostics, collectionError
        );
    }
    var allParameterIds = idsFrom(rawParameterIds);
    var parameterIds = allParameterIds.slice(0, MAX_PARAMETER_SCAN);
    AbletonAgentParameterDiagnostics.mark(diagnostics, "parameter_collection_loaded");
    var token = AbletonAgentReadCore.collectionToken(parameterIds);
    AbletonAgentParameterDiagnostics.mark(diagnostics, "collection_token_verifying");
    AbletonAgentReadCore.verifyCollection(read, token);
    AbletonAgentParameterDiagnostics.mark(diagnostics, "collection_token_verified");
    AbletonAgentParameterDiagnostics.mark(diagnostics, "page_started");
    if (read.cursor > parameterIds.length) {
        throw new Error("read.cursor is outside the parameter collection");
    }

    var parameters = [];
    var scanned = 0;
    var partial = false;
    while (read.cursor + scanned < parameterIds.length && scanned < read.limit) {
        if (scanned > 0 && AbletonAgentReadCore.budgetExceeded(read)) {
            partial = true;
            break;
        }
        var rawIndex = read.cursor + scanned;
        var parameterId = parameterIds[rawIndex];
        var parameter = new LiveAPI(function () {}, "id " + parameterId);
        var parameterContext = {index: rawIndex, id: parameterId, name: null};
        AbletonAgentParameterDiagnostics.mark(diagnostics, "parameter_started", {
            parameter: parameterContext, operation: "identity", property: "name"
        });
        var name = String(valueOf(AbletonAgentParameterDiagnostics.readProperty(
            parameter, "name", diagnostics, "identity", parameterContext
        ), ""));
        parameterContext.name = name;
        scanned += 1;
        if (action === "list_parameters" || normalize(name).indexOf(query) >= 0) {
            parameters.push(projectedParameterInfo(parameterId, rawIndex, name, read, diagnostics));
        } else {
            AbletonAgentParameterDiagnostics.mark(diagnostics, "parameter_completed", {
                parameter: parameterContext, operation: null, property: null
            });
        }
    }
    var nextCursor = read.cursor + scanned;
    var hasMore = nextCursor < parameterIds.length;
    var readMetadata = AbletonAgentReadCore.metadata(read, {
        next_cursor: nextCursor,
        scanned_count: scanned,
        returned_count: parameters.length,
        has_more: hasMore,
        partial: partial,
        collection_token: token,
        warnings: allParameterIds.length > MAX_PARAMETER_SCAN ? ["Parameter collection exceeds scan cap; inventory is incomplete"] : []
    });
    AbletonAgentParameterDiagnostics.mark(diagnostics, "page_completed");
    var response = {
        ok: true,
        kind: "final",
        request_id: requestId,
        dry_run: true,
        action: action,
        query: query,
        target: {
            section: track.section,
            track_index: track.index,
            track_id: track.id,
            track_name: String(valueOf(safeGet(track.api, "name", ""), "")),
            device_index: device.index,
            device_id: device.id,
            device_name: String(valueOf(safeGet(device.api, "name", ""), "")),
            device_depth: device.record ? device.record.depth : 0,
            parent_chain_id: device.record ? device.record.parent_chain_id : null,
            parent_rack_device_id: device.record ? device.record.parent_rack_device_id : null,
            chain_path: device.record ? device.record.chain_path : []
        },
        parameter_count: parameterIds.length,
        scanned_parameter_count: scanned,
        matched_parameter_count: null,
        page_matched_parameter_count: parameters.length,
        offset: read.cursor,
        limit: read.limit,
        returned_parameter_count: parameters.length,
        has_more: hasMore,
        include_display_values: AbletonAgentReadCore.has(read, "display_value"),
        include_enum_values: AbletonAgentReadCore.has(read, "enum_values"),
        read: readMetadata,
        items: parameters,
        parameters: parameters,
        diagnostics: AbletonAgentParameterDiagnostics.snapshot(diagnostics)
    };
    AbletonAgentParameterDiagnostics.mark(diagnostics, "reply_serializing");
    response.diagnostics = AbletonAgentParameterDiagnostics.snapshot(diagnostics);
    var serialized = JSON.stringify(response);
    AbletonAgentParameterDiagnostics.mark(diagnostics, "reply_serialized");
    outlet(0, [requestId, serialized]);
}


function readDeviceParameterPage(requestId, payload, mode, diagnostics) {
    if (payload.read && typeof payload.read === "object") {
        readDeviceParameterPageBounded(requestId, payload, mode, diagnostics);
        return;
    }
    if (normalize(mode || "dry_run") !== "dry_run") {
        throw new Error("parameter_summary inspection actions are read-only and only accept dry_run mode");
    }
    var action = normalize(payload.action);
    var query = normalize(payload.query || "");
    if (action === "search_parameters" && !query) {
        throw new Error("search_parameters requires a non-empty query");
    }
    var offset = clampInt(payload.offset, 0, 0, MAX_PARAMETER_SCAN);
    var limit = clampInt(payload.limit, DEFAULT_BOUNDED_PARAMETER_LIMIT, 1, MAX_PARAMETERS_PER_DEVICE);
    var includeDisplayValues = truthy(payload.include_display_values);
    var includeEnumValues = truthy(payload.include_enum_values);
    var track = resolveInspectionTrack(payload);
    var device = resolveInspectionDevice(track, payload);
    var parameterIds = idsFrom(safeGet(device.api, "parameters", []));
    var scanCount = Math.min(parameterIds.length, MAX_PARAMETER_SCAN);
    var matches = [];
    for (var index = 0; index < scanCount; index += 1) {
        var parameter = new LiveAPI(function () {}, "id " + parameterIds[index]);
        var name = String(valueOf(safeGet(parameter, "name", ""), ""));
        if (action === "list_parameters" || normalize(name).indexOf(query) >= 0) {
            matches.push({index: index, id: parameterIds[index]});
        }
    }
    var page = matches.slice(offset, offset + limit);
    var parameters = [];
    for (var pageIndex = 0; pageIndex < page.length; pageIndex += 1) {
        parameters.push(inspectedParameterInfo(page[pageIndex].id, page[pageIndex].index, includeDisplayValues, includeEnumValues));
    }
    outlet(0, [requestId, JSON.stringify({
        ok: true,
        dry_run: true,
        action: action,
        query: query,
        target: {
            section: track.section,
            track_index: track.index,
            track_id: track.id,
            track_name: String(valueOf(safeGet(track.api, "name", ""), "")),
            device_index: device.index,
            device_id: device.id,
            device_name: String(valueOf(safeGet(device.api, "name", ""), ""))
        },
        parameter_count: parameterIds.length,
        scanned_parameter_count: scanCount,
        matched_parameter_count: matches.length,
        offset: offset,
        limit: limit,
        returned_parameter_count: parameters.length,
        has_more: offset + parameters.length < matches.length,
        include_display_values: includeDisplayValues,
        include_enum_values: includeEnumValues,
        parameters: parameters
    })]);
}


function readParameterSummary(requestId, payloadText, mode) {
    var diagnostics = AbletonAgentParameterDiagnostics.create(requestId);
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        if (payload.action === "_module_health") {
            AgentHealth.reply(requestId, "parameters", mode); return;
        }
        if (payload.request_id !== undefined && String(payload.request_id) !== String(requestId)) {
            throw AbletonAgentParameterDiagnostics.failure(
                "hub_route_failed", "OSC request_id does not match payload request_id", diagnostics, null
            );
        }
        AbletonAgentParameterDiagnostics.configure(diagnostics, payload.trace_level, function (packet) {
            outlet(1, [requestId, JSON.stringify(packet)]);
        }, payload.read ? payload.read.cursor : payload.offset);
        AbletonAgentParameterDiagnostics.mark(diagnostics, "payload_validated");
        var action = normalize(payload.action || "summary");
        if (action === "list_parameters" || action === "search_parameters") {
            readDeviceParameterPage(requestId, payload, mode, diagnostics);
            return;
        }
        if (action !== "summary") {
            throw new Error("Unsupported parameter_summary action: " + action);
        }
        var maxDevices = clampInt(payload.max_devices_per_track, DEFAULT_MAX_DEVICES_PER_TRACK, 1, MAX_DEVICES_PER_TRACK);
        var maxParameters = clampInt(payload.max_parameters_per_device, DEFAULT_MAX_PARAMETERS_PER_DEVICE, 1, MAX_PARAMETERS_PER_DEVICE);
        var includeDisplayValues = truthy(payload.include_display_values);
        var song = new LiveAPI(function () {}, "live_set");
        var trackIds = idsFrom(safeGet(song, "tracks", []));
        var limit = Math.min(trackIds.length, MAX_TRACKS);
        var tracks = [];
        for (var trackIndex = 0; trackIndex < limit; trackIndex += 1) {
            tracks.push(readTrack(trackIds[trackIndex], trackIndex, maxDevices, maxParameters, includeDisplayValues));
        }
        outlet(0, [requestId, JSON.stringify({
            ok: true,
            track_count: tracks.length,
            total_track_count: trackIds.length,
            max_devices_per_track: maxDevices,
            max_parameters_per_device: maxParameters,
            include_display_values: includeDisplayValues,
            tracks: tracks
        })]);
    } catch (error) {
        var failure = AbletonAgentParameterDiagnostics.structuredError(diagnostics, error);
        try {
            outlet(0, [requestId, JSON.stringify(failure)]);
        } catch (serializationError) {
            AbletonAgentParameterDiagnostics.mark(diagnostics, "reply_serializing");
            outlet(0, [requestId, JSON.stringify(AbletonAgentParameterDiagnostics.structuredError(
                diagnostics,
                AbletonAgentParameterDiagnostics.failure(
                    "response_serialization_failed", "Could not serialize parameter_summary response", diagnostics, serializationError
                )
            ))]);
        }
    }
}

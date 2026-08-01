autowatch = 1;
inlets = 1;
outlets = 1;


function list() {
    var args = arrayfromargs(arguments);
    handleRouting(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleRouting(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
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


function safeSet(api, propertyName, value) {
    try {
        api.set(propertyName, value);
        return true;
    } catch (_error) {
        return false;
    }
}


function routingSetValue(raw, direction, field) {
    var text = String(raw || "");
    if (!looksLikeRawRoutingValue(text, direction, field)) {
        return text;
    }
    try {
        var parsed = JSON.parse(text);
        var wrapper = new Dict();
        wrapper.setparse("routing_value", JSON.stringify(parsed));
        return wrapper.get("routing_value");
    } catch (_error) {
        return text;
    }
}


function normalize(value) {
    return String(value || "").toLowerCase().replace(/^\s+|\s+$/g, "");
}


function arrayFromRaw(raw) {
    if (raw instanceof Array) {
        return raw;
    }
    if (raw === undefined || raw === null || raw === "") {
        return [];
    }
    return [raw];
}


function routingDisplayName(raw) {
    var text = String(raw || "");
    if (!text) {
        return "";
    }
    var marker = '"display_name":';
    var markerIndex = text.indexOf(marker);
    if (markerIndex >= 0) {
        var quoteStart = text.indexOf('"', markerIndex + marker.length);
        if (quoteStart >= 0) {
            var quoteEnd = text.indexOf('"', quoteStart + 1);
            if (quoteEnd >= quoteStart) {
                return text.substring(quoteStart + 1, quoteEnd);
            }
        }
    }
    return text;
}


function routingValue(raw) {
    var text = String(raw === undefined || raw === null ? "" : raw);
    return {
        raw: text,
        display_name: routingDisplayName(text)
    };
}


function routingValues(raw) {
    var list = arrayFromRaw(raw);
    var out = [];
    for (var index = 0; index < list.length; index += 1) {
        out.push(routingValue(list[index]));
    }
    return out;
}


function trackIdsForSection(song, section) {
    if (section === "return") {
        return idsFrom(song.get("return_tracks"));
    }
    return idsFrom(song.get("tracks"));
}


function trackInfo(section, index, id, includeAvailable, includeInput) {
    var track = new LiveAPI(function () {}, "id " + id);
    var info = {
        section: section,
        track_index: index,
        track_id: id,
        track_name: String(valueOf(track.get("name"), "")),
        current: {}
    };
    if (section === "return") {
        info.routing_limited = true;
        info.note = "Return track routing is not read by this tool because Live can block on return routing properties";
        return info;
    }
    var outputType = valueOf(safeGet(track, "output_routing_type", ""), "");
    var outputChannel = valueOf(safeGet(track, "output_routing_channel", ""), "");
    info.current.output_routing_type = routingValue(outputType);
    info.current.output_routing_channel = routingValue(outputChannel);
    if (includeInput && section === "track") {
        var inputType = valueOf(safeGet(track, "input_routing_type", ""), "");
        var inputChannel = valueOf(safeGet(track, "input_routing_channel", ""), "");
        info.current.input_routing_type = routingValue(inputType);
        info.current.input_routing_channel = routingValue(inputChannel);
    }
    if (includeAvailable) {
        info.available = {
            output_routing_types: routingValues(safeGet(track, "available_output_routing_types", [])),
            output_routing_channels: routingValues(safeGet(track, "available_output_routing_channels", []))
        };
        if (includeInput && section === "track") {
            info.available.input_routing_types = routingValues(safeGet(track, "available_input_routing_types", []));
            info.available.input_routing_channels = routingValues(safeGet(track, "available_input_routing_channels", []));
        }
    }
    return info;
}


function scanRouting(payload) {
    var song = new LiveAPI(function () {}, "live_set");
    var includeReturns = payload.include_returns === undefined ? true : Boolean(payload.include_returns);
    var includeAvailable = Boolean(payload.include_available);
    var includeInput = Boolean(payload.include_input);
    var tracks = [];
    var ordinaryIds = trackIdsForSection(song, "track");
    for (var index = 0; index < ordinaryIds.length; index += 1) {
        tracks.push(trackInfo("track", index, ordinaryIds[index], includeAvailable, includeInput));
    }
    if (includeReturns) {
        var returnIds = trackIdsForSection(song, "return");
        for (var returnIndex = 0; returnIndex < returnIds.length; returnIndex += 1) {
            tracks.push(trackInfo("return", returnIndex, returnIds[returnIndex], includeAvailable, false));
        }
    }
    return tracks;
}


function resolveTrack(song, payload) {
    var section = normalize(payload.section || "");
    var resolvedSection = section === "return" ? "return" : "track";
    var ids = trackIdsForSection(song, resolvedSection);
    var selector = payload.track_index !== undefined ? payload.track_index : payload.track;
    if (selector === undefined || selector === null || selector === "") {
        selector = payload.track_name;
    }
    if (selector === undefined || selector === null || selector === "") {
        throw new Error("Missing track selector");
    }
    if (typeof selector === "number" || /^[0-9]+$/.test(String(selector))) {
        var requestedIndex = Number(selector);
        if (requestedIndex < 0 || requestedIndex >= ids.length || Math.floor(requestedIndex) !== requestedIndex) {
            throw new Error("track_index is outside the " + resolvedSection + " list");
        }
        return trackInfo(resolvedSection, requestedIndex, ids[requestedIndex], Boolean(payload.include_available), Boolean(payload.include_input) || String(payload.action || "") === "set_input_routing");
    }
    var wanted = normalize(selector);
    for (var index = 0; index < ids.length; index += 1) {
        var info = trackInfo(resolvedSection, index, ids[index], Boolean(payload.include_available), Boolean(payload.include_input) || String(payload.action || "") === "set_input_routing");
        if (normalize(info.track_name) === wanted) {
            return info;
        }
    }
    throw new Error("Track not found: " + selector);
}


function findRoutingRaw(list, value) {
    var target = String(value);
    for (var index = 0; index < list.length; index += 1) {
        var item = list[index];
        if (String(item.raw) === target || String(item.display_name) === target) {
            return item.raw;
        }
    }
    return null;
}


function sameRoutingValue(requested, currentValue) {
    return String(requested) === String(currentValue.raw) || String(requested) === String(currentValue.display_name);
}


function looksLikeRawRoutingValue(requested, direction, field) {
    var text = String(requested || "");
    return text.charAt(0) === "{" && text.indexOf(direction + "_routing_" + field) >= 0 && text.indexOf("identifier") >= 0;
}


function coerceRequestedRouting(target, direction, field, requestedValue) {
    if (requestedValue === undefined || requestedValue === null || requestedValue === "") {
        return null;
    }
    var current = target.current[direction + "_routing_" + field];
    if (sameRoutingValue(requestedValue, current)) {
        return current.raw;
    }
    if (looksLikeRawRoutingValue(requestedValue, direction, field)) {
        return String(requestedValue);
    }
    if (!target.available) {
        throw new Error("Run scan_routing with include_available before changing " + direction + "_routing_" + field + " to a new value");
    }
    var list = target.available[direction + "_routing_" + field + "s"];
    var raw = findRoutingRaw(list, requestedValue);
    if (raw === null) {
        throw new Error(direction + "_routing_" + field + " is not in this track's available routing " + field + "s");
    }
    return raw;
}


function setRouting(payload, dryRun, direction) {
    var song = new LiveAPI(function () {}, "live_set");
    var target = resolveTrack(song, payload);
    if (target.section === "return") {
        throw new Error("Routing edits for return tracks are not supported because Live can block on return routing properties");
    }
    if (direction === "input" && target.section !== "track") {
        throw new Error("set_input_routing only supports ordinary tracks");
    }
    var requestedType = payload[direction + "_routing_type"];
    var requestedChannel = payload[direction + "_routing_channel"];
    if ((requestedType === undefined || requestedType === null || requestedType === "") &&
            (requestedChannel === undefined || requestedChannel === null || requestedChannel === "")) {
        throw new Error("Provide " + direction + "_routing_type and/or " + direction + "_routing_channel from scan_routing results");
    }
    var coercedType = coerceRequestedRouting(target, direction, "type", requestedType);
    var coercedChannel = coerceRequestedRouting(target, direction, "channel", requestedChannel);

    var before = target.current;
    if (!dryRun) {
        var track = new LiveAPI(function () {}, "id " + target.track_id);
        if (coercedType !== null) {
            if (!sameRoutingValue(coercedType, before[direction + "_routing_type"])) {
                if (!safeSet(track, direction + "_routing_type", routingSetValue(coercedType, direction, "type"))) {
                    throw new Error("Live rejected " + direction + "_routing_type");
                }
            }
        }
        if (coercedChannel !== null) {
            if (!sameRoutingValue(coercedChannel, before[direction + "_routing_channel"])) {
                if (!safeSet(track, direction + "_routing_channel", routingSetValue(coercedChannel, direction, "channel"))) {
                    throw new Error("Live rejected " + direction + "_routing_channel");
                }
            }
        }
        target = trackInfo(target.section, target.track_index, target.track_id, Boolean(payload.include_available));
        if (coercedType !== null && !sameRoutingValue(coercedType, target.current[direction + "_routing_type"])) {
            throw new Error("Live accepted the routing command but readback did not change " + direction + "_routing_type");
        }
        if (coercedChannel !== null && !sameRoutingValue(coercedChannel, target.current[direction + "_routing_channel"])) {
            throw new Error("Live accepted the routing command but readback did not change " + direction + "_routing_channel");
        }
    }
    return {
        target: {
            section: target.section,
            track_index: target.track_index,
            track_id: target.track_id,
            track_name: target.track_name
        },
        before: before,
        requested: {
            routing_type: requestedType,
            routing_channel: requestedChannel,
            coerced_type: coercedType,
            coerced_channel: coercedChannel
        },
        after: dryRun ? before : target.current
    };
}


function handleRouting(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var action = String(payload.action || "scan_routing");
        var allowed = ["scan_routing", "set_input_routing", "set_output_routing"];
        if (allowed.indexOf(action) < 0) {
            throw new Error("action must be scan_routing, set_input_routing, or set_output_routing");
        }
        if (action === "scan_routing") {
            var tracks = scanRouting(payload);
            outlet(0, [requestId, JSON.stringify({
                ok: true,
                dry_run: true,
                applied: false,
                action: action,
                track_count: tracks.length,
                tracks: tracks,
                message: "Routing scanned; use current values for same-value validation, or include available values in a later routing edit step"
            })]);
            return;
        }
        var result = setRouting(payload, dryRun, action === "set_input_routing" ? "input" : "output");
        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: dryRun,
            applied: !dryRun,
            action: action,
            plan: result,
            message: dryRun ? "Ready to set routing" : "Routing action applied"
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

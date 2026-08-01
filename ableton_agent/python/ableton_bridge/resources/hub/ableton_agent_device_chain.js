autowatch = 1;
inlets = 1;
outlets = 1;

var CHAIN_TEMPLATES = {
    drum_bus_clean: ["Drum Buss", "Glue Compressor"],
    lead_light_space: ["EQ Eight", "Reverb"],
    bass_control: ["EQ Eight", "Compressor", "Utility"],
    chord_filter_motion: ["Auto Filter", "Chorus-Ensemble"],
    utility_gain_stage: ["Utility"]
};

var CHAIN_PARAMETER_PRESETS = {
    lead_light_space: [
        {device: "Reverb", parameter: "Dry/Wet", value: 0.05}
    ],
    bass_control: [
        {device: "Utility", parameter: "Gain", value: 0.0},
        {device: "Compressor", parameter: "Ratio", value: 4.0}
    ],
    chord_filter_motion: [
        {device: "Auto Filter", parameter: "Frequency", value: 10000.0},
        {device: "Auto Filter", parameter: "Resonance", value: 0.0},
        {device: "Chorus-Ensemble", parameter: "Amount", value: 0.2}
    ],
    utility_gain_stage: [
        {device: "Utility", parameter: "Gain", value: 0.0}
    ],
    drum_bus_clean: [
        {device: "Glue Compressor", parameter: "Dry/Wet", value: 1.0}
    ]
};

var ALLOWED_EFFECTS = {
    "Auto Filter": true,
    "Chorus-Ensemble": true,
    "Compressor": true,
    "Drum Buss": true,
    "EQ Eight": true,
    "Glue Compressor": true,
    "Reverb": true,
    "Utility": true
};

function list() {
    var args = arrayfromargs(arguments);
    handleDeviceChain(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}

function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleDeviceChain(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
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

function objectKeys(object) {
    var keys = [];
    for (var key in object) {
        if (object.hasOwnProperty(key)) {
            keys.push(key);
        }
    }
    return keys;
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

function deviceNames(track) {
    var names = [];
    var deviceIds = idsFrom(track.get("devices"));
    for (var index = 0; index < deviceIds.length; index += 1) {
        var device = new LiveAPI(function () {}, "id " + deviceIds[index]);
        names.push(String(valueOf(device.get("name"), "")));
    }
    return names;
}

function safeGet(api, propertyName, fallback) {
    try {
        return api.get(propertyName);
    } catch (_error) {
        return fallback;
    }
}

function resolveDeviceByName(track, name) {
    var wanted = normalize(name);
    var deviceIds = idsFrom(track.api.get("devices"));
    for (var index = 0; index < deviceIds.length; index += 1) {
        var device = new LiveAPI(function () {}, "id " + deviceIds[index]);
        if (normalize(valueOf(device.get("name"), "")) === wanted) {
            return {index: index, id: deviceIds[index], name: String(valueOf(device.get("name"), "")), api: device};
        }
    }
    return null;
}

function parameterDisplay(parameter, value) {
    try {
        return String(valueOf(parameter.call("str_for_value", value), ""));
    } catch (_error) {
        return "";
    }
}

function resolveParameter(device, name) {
    var wanted = normalize(name);
    var parameterIds = idsFrom(device.api.get("parameters"));
    for (var index = 0; index < parameterIds.length; index += 1) {
        var parameter = new LiveAPI(function () {}, "id " + parameterIds[index]);
        if (normalize(valueOf(parameter.get("name"), "")) === wanted) {
            return {
                index: index,
                id: parameterIds[index],
                name: String(valueOf(parameter.get("name"), "")),
                api: parameter,
                min: Number(valueOf(safeGet(parameter, "min", 0), 0)),
                max: Number(valueOf(safeGet(parameter, "max", 1), 1))
            };
        }
    }
    return null;
}

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, Number(value)));
}

function hasName(names, target) {
    var wanted = normalize(target);
    for (var index = 0; index < names.length; index += 1) {
        if (normalize(names[index]) === wanted) {
            return true;
        }
    }
    return false;
}

function templates() {
    var out = [];
    var names = objectKeys(CHAIN_TEMPLATES);
    for (var index = 0; index < names.length; index += 1) {
        out.push({name: names[index], devices: CHAIN_TEMPLATES[names[index]], parameter_preset: CHAIN_PARAMETER_PRESETS[names[index]] || []});
    }
    return out;
}

function applyTemplate(payload, dryRun) {
    var templateName = String(payload.template || payload.name || "");
    if (!CHAIN_TEMPLATES[templateName]) {
        throw new Error("Unknown chain template: " + templateName);
    }
    var track = resolveTrack(payload);
    var existing = deviceNames(track.api);
    var allowDuplicate = Boolean(payload.allow_duplicate);
    var required = CHAIN_TEMPLATES[templateName];
    var inserted = [];
    var skipped = [];
    for (var index = 0; index < required.length; index += 1) {
        var effect = required[index];
        if (!ALLOWED_EFFECTS[effect]) {
            throw new Error("Effect is not in the safe native-effect whitelist: " + effect);
        }
        if (!allowDuplicate && hasName(existing, effect)) {
            skipped.push(effect);
            continue;
        }
        inserted.push(effect);
        if (!dryRun) {
            track.api.call("insert_device", effect);
        }
    }
    var presetResult = null;
    if (payload.apply_preset || payload.apply_parameter_preset) {
        presetResult = applyParameterPreset({
            track_index: track.index,
            preset: templateName
        }, dryRun);
    }
    return {
        template: templateName,
        track_index: track.index,
        track_id: track.id,
        track_name: track.name,
        required_devices: required,
        inserted_devices: inserted,
        skipped_existing_devices: skipped,
        parameter_preset: presetResult
    };
}

function applyParameterPreset(payload, dryRun) {
    var presetName = String(payload.preset || payload.template || payload.name || "");
    var changes = CHAIN_PARAMETER_PRESETS[presetName];
    if (!changes) {
        throw new Error("Unknown parameter preset: " + presetName);
    }
    var track = resolveTrack(payload);
    var planned = [];
    var skipped = [];
    for (var index = 0; index < changes.length; index += 1) {
        var change = changes[index];
        var device = resolveDeviceByName(track, change.device);
        if (!device) {
            skipped.push({device: change.device, parameter: change.parameter, reason: "device not found"});
            continue;
        }
        var parameter = resolveParameter(device, change.parameter);
        if (!parameter) {
            skipped.push({device: change.device, parameter: change.parameter, reason: "parameter not found"});
            continue;
        }
        var before = Number(valueOf(parameter.api.get("value"), 0));
        var after = clamp(change.value, parameter.min, parameter.max);
        if (!dryRun) {
            parameter.api.set("value", after);
        }
        planned.push({
            device: device.name,
            device_index: device.index,
            parameter: parameter.name,
            parameter_index: parameter.index,
            before_value: before,
            before_display: parameterDisplay(parameter.api, before),
            after_value: after,
            after_display: parameterDisplay(parameter.api, after)
        });
    }
    return {
        preset: presetName,
        track_index: track.index,
        track_id: track.id,
        track_name: track.name,
        changed_count: planned.length,
        skipped_count: skipped.length,
        changes: planned,
        skipped: skipped
    };
}

function handleDeviceChain(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var action = String(payload.action || "list_templates");
        var allowed = ["list_templates", "apply_template", "apply_parameter_preset"];
        if (allowed.indexOf(action) < 0) {
            throw new Error("action must be list_templates, apply_template, or apply_parameter_preset");
        }
        if (action === "list_templates") {
            outlet(0, [requestId, JSON.stringify({
                ok: true,
                dry_run: true,
                applied: false,
                action: action,
                templates: templates(),
                message: "Device chain templates listed"
            })]);
            return;
        }
        var result = action === "apply_parameter_preset"
            ? applyParameterPreset(payload, dryRun)
            : applyTemplate(payload, dryRun);
        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: dryRun,
            applied: !dryRun,
            action: action,
            plan: result,
            message: dryRun ? "Ready to apply device chain template" : "Device chain template applied"
        })]);
    } catch (error) {
        outlet(0, [requestId, JSON.stringify({
            ok: false,
            dry_run: dryRun,
            applied: false,
            error: error && error.message ? error.message : String(error),
            templates: templates()
        })]);
    }
}

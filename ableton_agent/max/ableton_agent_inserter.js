autowatch = 1;
inlets = 1;
outlets = 1;


var ROLE_DEVICES = {
    drums: "Drum Rack",
    percussion: "Drum Rack",
    bass: "Operator",
    chords: "Electric",
    keys: "Electric",
    piano: "Electric",
    lead: "Drift",
    pad: "Wavetable",
    synth: "Drift",
    fm: "Operator",
    analog: "Analog",
    wavetable: "Wavetable",
    meld: "Meld",
    mallet: "Collision",
    string: "Tension",
    sample: "Simpler",
    sampler: "Simpler",
    vocal: "Simpler",
    fx: "Drum Rack",
    rack: "Instrument Rack"
};

var DEVICE_ALIASES = {
    analog: "Analog",
    collision: "Collision",
    drift: "Drift",
    drumrack: "Drum Rack",
    drumsampler: "Drum Sampler",
    electric: "Electric",
    impulse: "Impulse",
    instrumentrack: "Instrument Rack",
    meld: "Meld",
    operator: "Operator",
    sampler: "Sampler",
    simpler: "Simpler",
    tension: "Tension",
    wavetable: "Wavetable"
};

var ALLOWED_DEVICES = {
    "Analog": true,
    "Collision": true,
    "Drift": true,
    "Drum Rack": true,
    "Drum Sampler": true,
    "Electric": true,
    "Impulse": true,
    "Instrument Rack": true,
    "Meld": true,
    "Operator": true,
    "Sampler": true,
    "Simpler": true,
    "Tension": true,
    "Wavetable": true
};

var EFFECT_ROLE_DEVICES = {
    reverb: "Reverb",
    room: "Reverb",
    hybridreverb: "Hybrid Reverb",
    delay: "Delay",
    echo: "Echo",
    compressor: "Compressor",
    sidechain: "Compressor",
    glue: "Glue Compressor",
    limiter: "Limiter",
    eq: "EQ Eight",
    eq8: "EQ Eight",
    filter: "Auto Filter",
    autofilter: "Auto Filter",
    saturation: "Saturator",
    saturator: "Saturator",
    drive: "Overdrive",
    overdrive: "Overdrive",
    utility: "Utility",
    width: "Utility",
    gain: "Utility",
    chorus: "Chorus-Ensemble",
    redux: "Redux",
    erosion: "Erosion",
    beatrepeat: "Beat Repeat",
    drumbuss: "Drum Buss",
    amp: "Amp",
    cabinet: "Cabinet",
    pedal: "Pedal"
};

var EFFECT_ALIASES = {
    amp: "Amp",
    autofilter: "Auto Filter",
    beatrepeat: "Beat Repeat",
    cabinet: "Cabinet",
    chorusensemble: "Chorus-Ensemble",
    compressor: "Compressor",
    delay: "Delay",
    drumbuss: "Drum Buss",
    echo: "Echo",
    eqeight: "EQ Eight",
    erosion: "Erosion",
    gluecompressor: "Glue Compressor",
    hybridreverb: "Hybrid Reverb",
    limiter: "Limiter",
    overdrive: "Overdrive",
    pedal: "Pedal",
    redux: "Redux",
    reverb: "Reverb",
    saturator: "Saturator",
    utility: "Utility"
};

var ALLOWED_EFFECTS = {
    "Amp": true,
    "Auto Filter": true,
    "Beat Repeat": true,
    "Cabinet": true,
    "Chorus-Ensemble": true,
    "Compressor": true,
    "Delay": true,
    "Drum Buss": true,
    "Echo": true,
    "EQ Eight": true,
    "Erosion": true,
    "Glue Compressor": true,
    "Hybrid Reverb": true,
    "Limiter": true,
    "Overdrive": true,
    "Pedal": true,
    "Redux": true,
    "Reverb": true,
    "Saturator": true,
    "Utility": true
};


function bang() {
    insertDevice("", "", "dry_run");
}


function list() {
    var args = arrayfromargs(arguments);
    insertDevice(String(args[0] || ""), String(args[1] || ""), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    if (messagename === "create_midi_track") {
        createMidiTrack(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
        return;
    }
    if (messagename === "insert_devices") {
        insertDevices(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
        return;
    }
    if (messagename === "insert_effect") {
        insertEffect(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
        return;
    }
    if (messagename === "insert_effects") {
        insertEffects(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
        return;
    }
    args.unshift(messagename);
    insertDevice(String(args[0] || ""), String(args[1] || ""), String(args[2] || "dry_run"));
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


function normalizeRole(value) {
    return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
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


function resolveDeviceName(requested) {
    var text = String(requested || "");
    var role = normalizeRole(text);
    if (ROLE_DEVICES[role]) {
        return ROLE_DEVICES[role];
    }
    if (DEVICE_ALIASES[role]) {
        return DEVICE_ALIASES[role];
    }
    return text;
}


function resolveEffectName(requested) {
    var text = String(requested || "");
    var role = normalizeRole(text);
    if (EFFECT_ROLE_DEVICES[role]) {
        return EFFECT_ROLE_DEVICES[role];
    }
    if (EFFECT_ALIASES[role]) {
        return EFFECT_ALIASES[role];
    }
    return text;
}


function inferDeviceFromTrackName(trackName) {
    var normalized = normalizeRole(trackName);
    var roleKeys = objectKeys(ROLE_DEVICES);
    for (var index = 0; index < roleKeys.length; index += 1) {
        var role = roleKeys[index];
        if (normalized.indexOf(role) >= 0) {
            return {role: role, device: ROLE_DEVICES[role]};
        }
    }
    var aliasKeys = objectKeys(DEVICE_ALIASES);
    for (var aliasIndex = 0; aliasIndex < aliasKeys.length; aliasIndex += 1) {
        var alias = aliasKeys[aliasIndex];
        if (normalized.indexOf(alias) >= 0) {
            return {role: alias, device: DEVICE_ALIASES[alias]};
        }
    }
    return {role: "", device: ""};
}


function hasInstrument(track) {
    var deviceIds = idsFrom(track.get("devices"));
    for (var index = 0; index < deviceIds.length; index += 1) {
        var device = new LiveAPI(function () {}, "id " + deviceIds[index]);
        if (Number(valueOf(device.get("type"), -1)) === 1) {
            return true;
        }
    }
    return false;
}


function hasDeviceNamed(track, deviceName) {
    var normalizedName = normalizeRole(deviceName);
    var deviceIds = idsFrom(track.get("devices"));
    for (var index = 0; index < deviceIds.length; index += 1) {
        var device = new LiveAPI(function () {}, "id " + deviceIds[index]);
        var name = String(valueOf(device.get("name"), ""));
        var className = String(valueOf(device.get("class_name"), ""));
        if (normalizeRole(name) === normalizedName || normalizeRole(className) === normalizedName) {
            return true;
        }
    }
    return false;
}


function ordinaryTrackIds() {
    var song = new LiveAPI(function () {}, "live_set");
    return idsFrom(song.get("tracks"));
}


function selectedTrack() {
    var view = new LiveAPI(function () {}, "live_set view");
    var trackId = idFrom(view.get("selected_track"));
    if (!trackId) {
        throw new Error("No selected track");
    }
    return {section: "selected", index: -1, id: trackId, api: new LiveAPI(function () {}, "id " + trackId)};
}


function resolveTrack(selector) {
    if (selector === undefined || selector === null || selector === "" || selector === "selected") {
        return selectedTrack();
    }
    var ids = ordinaryTrackIds();
    if (typeof selector === "number") {
        if (selector < 0 || selector >= ids.length || Math.floor(selector) !== selector) {
            throw new Error("track index is outside the ordinary track list");
        }
        return {section: "track", index: selector, id: ids[selector], api: new LiveAPI(function () {}, "id " + ids[selector])};
    }
    var numericSelector = Number(selector);
    if (String(selector).match(/^\d+$/) && numericSelector >= 0 && numericSelector < ids.length) {
        return {section: "track", index: numericSelector, id: ids[numericSelector], api: new LiveAPI(function () {}, "id " + ids[numericSelector])};
    }
    var wanted = String(selector || "").toLowerCase().replace(/^\s+|\s+$/g, "");
    for (var index = 0; index < ids.length; index += 1) {
        var track = new LiveAPI(function () {}, "id " + ids[index]);
        var name = String(valueOf(track.get("name"), ""));
        if (name.toLowerCase().replace(/^\s+|\s+$/g, "") === wanted) {
            return {section: "track", index: index, id: ids[index], api: track};
        }
    }
    throw new Error("Track not found: " + selector);
}


function effectSectionForId(trackId) {
    var song = new LiveAPI(function () {}, "live_set");
    var ordinaryIds = idsFrom(song.get("tracks"));
    var returnIds = idsFrom(song.get("return_tracks"));
    var mainId = idFrom(song.get("master_track"));
    if (ordinaryIds.indexOf(trackId) >= 0) {
        return {section: "track", index: ordinaryIds.indexOf(trackId)};
    }
    if (returnIds.indexOf(trackId) >= 0) {
        return {section: "return", index: returnIds.indexOf(trackId)};
    }
    if (mainId === trackId) {
        return {section: "main", index: 0};
    }
    throw new Error("track_id is not an ordinary, Return, or Main track in the current Set");
}


function resolveEffectTrack(target) {
    if (!(target instanceof Object) || target instanceof Array) {
        if (target === "master" || target === "main") {
            target = {section: "main"};
        } else {
            target = {track: target};
        }
    }
    var section = String(target.section || "").toLowerCase();
    if (section === "master") {
        section = "main";
    }
    if (target.track_id !== undefined && target.track_id !== null && target.track_id !== "") {
        var requestedId = Number(target.track_id);
        var identity = effectSectionForId(requestedId);
        if (section && section !== identity.section) {
            throw new Error("track_id does not belong to requested section " + section);
        }
        return {section: identity.section, index: identity.index, id: requestedId, api: new LiveAPI(function () {}, "id " + requestedId)};
    }
    if (section === "main") {
        var song = new LiveAPI(function () {}, "live_set");
        var mainId = idFrom(song.get("master_track"));
        return {section: "main", index: 0, id: mainId, api: new LiveAPI(function () {}, "id " + mainId)};
    }
    if (section === "return") {
        var returnSong = new LiveAPI(function () {}, "live_set");
        var returnIds = idsFrom(returnSong.get("return_tracks"));
        var returnSelector = target.track_index !== undefined ? target.track_index : target.track;
        if (returnSelector === undefined || returnSelector === null || returnSelector === "") {
            returnSelector = target.track_name;
        }
        if (typeof returnSelector === "number" || /^\d+$/.test(String(returnSelector))) {
            var returnIndex = Number(returnSelector);
            if (returnIndex < 0 || returnIndex >= returnIds.length || Math.floor(returnIndex) !== returnIndex) {
                throw new Error("track index is outside the Return Track list");
            }
            return {section: "return", index: returnIndex, id: returnIds[returnIndex], api: new LiveAPI(function () {}, "id " + returnIds[returnIndex])};
        }
        var wanted = String(returnSelector || "").toLowerCase().replace(/^\s+|\s+$/g, "");
        for (var returnNameIndex = 0; returnNameIndex < returnIds.length; returnNameIndex += 1) {
            var returnTrack = new LiveAPI(function () {}, "id " + returnIds[returnNameIndex]);
            var returnName = String(valueOf(returnTrack.get("name"), "")).toLowerCase().replace(/^\s+|\s+$/g, "");
            if (returnName === wanted) {
                return {section: "return", index: returnNameIndex, id: returnIds[returnNameIndex], api: returnTrack};
            }
        }
        throw new Error("Return Track not found: " + returnSelector);
    }
    var selector = target.track_index !== undefined ? target.track_index : target.track;
    if (selector === undefined || selector === null || selector === "") {
        selector = target.track_name || "selected";
    }
    var resolved = resolveTrack(selector);
    if (resolved.section === "selected") {
        var selectedIdentity = effectSectionForId(resolved.id);
        resolved.section = selectedIdentity.section;
        resolved.index = selectedIdentity.index;
    }
    return resolved;
}


function trackInsertPlan(trackRef, requestedDevice, allowExisting, inferredRole) {
    var track = trackRef.api;
    var trackName = String(valueOf(track.get("name"), ""));
    var hasMidiInput = Boolean(Number(valueOf(track.get("has_midi_input"), 0)));
    var existingInstrument = hasInstrument(track);
    var deviceName = resolveDeviceName(requestedDevice);
    if (!deviceName) {
        throw new Error("Missing device role or device name");
    }
    if (!ALLOWED_DEVICES[deviceName]) {
        throw new Error("Device is not in the safe native-device whitelist: " + deviceName);
    }
    if (!hasMidiInput) {
        return {
            ok: false,
            skipped: true,
            reason: "Track is not a MIDI track",
            track_index: trackRef.index,
            track_name: trackName,
            requested: requestedDevice,
            resolved_device: deviceName,
            inferred_role: inferredRole || ""
        };
    }
    if (existingInstrument && !allowExisting) {
        return {
            ok: false,
            skipped: true,
            reason: "Track already has an instrument",
            track_index: trackRef.index,
            track_name: trackName,
            requested: requestedDevice,
            resolved_device: deviceName,
            inferred_role: inferredRole || ""
        };
    }
    return {
        ok: true,
        skipped: false,
        track_index: trackRef.index,
        track_name: trackName,
        requested: requestedDevice,
        resolved_device: deviceName,
        inferred_role: inferredRole || "",
        already_had_instrument: existingInstrument
    };
}


function emit(command, requestId, payload) {
    outlet(0, [command, requestId, JSON.stringify(payload)]);
}


function coerceTrackIndex(value, fallback) {
    if (value === undefined || value === null || value === "" || value === "end") {
        return fallback;
    }
    var numeric = Number(value);
    if (!isFinite(numeric) || Math.floor(numeric) !== numeric || numeric < 0 || numeric > fallback) {
        throw new Error("index must be an integer between 0 and the current track count");
    }
    return numeric;
}


function trackInfoAt(index) {
    var ids = ordinaryTrackIds();
    if (index < 0 || index >= ids.length) {
        throw new Error("created track could not be resolved");
    }
    var track = new LiveAPI(function () {}, "id " + ids[index]);
    return {
        index: index,
        id: ids[index],
        name: String(valueOf(track.get("name"), "")),
        has_midi_input: Boolean(Number(valueOf(track.get("has_midi_input"), 0)))
    };
}


function createMidiTrack(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var ids = ordinaryTrackIds();
        var index = coerceTrackIndex(payload.index !== undefined ? payload.index : payload.track_index, ids.length);
        var name = String(payload.name || payload.track_name || "");
        var requestedDevice = payload.device || payload.role || "";
        var resolvedDevice = requestedDevice ? resolveDeviceName(requestedDevice) : "";
        if (resolvedDevice && !ALLOWED_DEVICES[resolvedDevice]) {
            throw new Error("Device is not in the safe native-device whitelist: " + resolvedDevice);
        }

        var created = null;
        if (!dryRun) {
            var song = new LiveAPI(function () {}, "live_set");
            song.call("create_midi_track", index);
            created = trackInfoAt(index);
            var track = new LiveAPI(function () {}, "id " + created.id);
            if (name) {
                track.set("name", name);
                created.name = name;
            }
            if (resolvedDevice) {
                track.call("insert_device", resolvedDevice);
            }
            if (payload.select) {
                var view = new LiveAPI(function () {}, "live_set view");
                view.set("selected_track", "id " + created.id);
            }
        }

        emit("create_midi_track", requestId, {
            ok: true,
            dry_run: dryRun,
            created: !dryRun,
            index: index,
            name: name,
            requested_device: requestedDevice,
            resolved_device: resolvedDevice,
            inserted_device: dryRun ? false : Boolean(resolvedDevice),
            track: created,
            message: dryRun ? "Ready to create MIDI track; rerun with commit to change the Set" : "MIDI track created"
        });
    } catch (error) {
        emit("create_midi_track", requestId, {
            ok: false,
            dry_run: dryRun,
            created: false,
            error: error && error.message ? error.message : String(error),
            allowed_devices: objectKeys(ALLOWED_DEVICES),
            roles: objectKeys(ROLE_DEVICES)
        });
    }
}


function effectInsertPlan(trackRef, requestedEffect, allowDuplicate) {
    var track = trackRef.api;
    var trackName = String(valueOf(track.get("name"), ""));
    var effectName = resolveEffectName(requestedEffect);
    if (!effectName) {
        throw new Error("Missing effect role or device name");
    }
    if (!ALLOWED_EFFECTS[effectName]) {
        throw new Error("Effect is not in the safe native-effect whitelist: " + effectName);
    }
    var alreadyHasEffect = hasDeviceNamed(track, effectName);
    if (alreadyHasEffect && !allowDuplicate) {
        return {
            ok: false,
            skipped: true,
            reason: "Track already has this effect",
            section: trackRef.section,
            track_index: trackRef.index,
            track_id: trackRef.id,
            track_name: trackName,
            requested: requestedEffect,
            resolved_effect: effectName
        };
    }
    return {
        ok: true,
        skipped: false,
        section: trackRef.section,
        track_index: trackRef.index,
        track_id: trackRef.id,
        track_name: trackName,
        requested: requestedEffect,
        resolved_effect: effectName,
        already_had_effect: alreadyHasEffect,
        before_device_ids: idsFrom(track.get("devices"))
    };
}


function requireStableSpecialTarget(target, trackRef, dryRun) {
    if (!dryRun && trackRef.section !== "track" && Number(target.track_id) !== trackRef.id) {
        throw new Error("Commit to Return/Main requires track_id from the preceding dry-run");
    }
}


function commitEffectPlan(plan) {
    var trackRef = resolveEffectTrack({section: plan.section, track_id: plan.track_id});
    var beforeIds = idsFrom(trackRef.api.get("devices"));
    trackRef.api.call("insert_device", plan.resolved_effect);
    var afterIds = idsFrom(trackRef.api.get("devices"));
    var createdIds = [];
    for (var index = 0; index < afterIds.length; index += 1) {
        if (beforeIds.indexOf(afterIds[index]) < 0) {
            createdIds.push(afterIds[index]);
        }
    }
    if (afterIds.length !== beforeIds.length + 1 || createdIds.length !== 1) {
        throw new Error("Effect insertion was not observable as exactly one new device");
    }
    plan.after_device_ids = afterIds;
    plan.created_device_id = createdIds[0];
    plan.verified_inserted = true;
}


function insertEffect(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var trackRef = resolveEffectTrack(payload);
        requireStableSpecialTarget(payload, trackRef, dryRun);
        var requestedEffect = payload.effect || payload.role || payload.device;
        var plan = effectInsertPlan(trackRef, requestedEffect, Boolean(payload.allow_duplicate));
        if (!plan.ok) {
            emit("insert_effect", requestId, {
                ok: false,
                dry_run: dryRun,
                inserted: false,
                error: plan.reason,
                plan: plan
            });
            return;
        }
        if (!dryRun) {
            commitEffectPlan(plan);
        }
        emit("insert_effect", requestId, {
            ok: true,
            dry_run: dryRun,
            inserted: !dryRun,
            plan: plan,
            message: dryRun ? "Ready to insert effect; rerun with commit to change the Set" : "Audio effect inserted"
        });
    } catch (error) {
        emit("insert_effect", requestId, {
            ok: false,
            dry_run: dryRun,
            inserted: false,
            error: error && error.message ? error.message : String(error),
            allowed_effects: objectKeys(ALLOWED_EFFECTS),
            roles: objectKeys(EFFECT_ROLE_DEVICES)
        });
    }
}


function effectPlans(targets, defaultEffect, allowDuplicate) {
    var plans = [];
    for (var index = 0; index < targets.length; index += 1) {
        var target = targets[index];
        var requestedEffect = target.effect || target.role || target.device || defaultEffect;
        var trackRef = resolveEffectTrack(target);
        plans.push({target: target, plan: effectInsertPlan(trackRef, requestedEffect, allowDuplicate), track_ref: trackRef});
    }
    return plans;
}


function insertEffects(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var plans = effectPlans(payload.targets || [], payload.effect || payload.role || payload.device || "", Boolean(payload.allow_duplicate));
        if (!plans.length) {
            throw new Error("No target tracks were provided");
        }
        var insertableCount = 0;
        var skippedCount = 0;
        for (var index = 0; index < plans.length; index += 1) {
            requireStableSpecialTarget(plans[index].target, plans[index].track_ref, dryRun);
        }
        for (var countIndex = 0; countIndex < plans.length; countIndex += 1) {
            var planned = plans[countIndex].plan;
            if (planned.ok && !planned.skipped) {
                insertableCount += 1;
            } else {
                skippedCount += 1;
            }
        }
        if (!dryRun) {
            for (var commitIndex = 0; commitIndex < plans.length; commitIndex += 1) {
                if (plans[commitIndex].plan.ok && !plans[commitIndex].plan.skipped) {
                    commitEffectPlan(plans[commitIndex].plan);
                }
            }
        }
        var outputPlans = [];
        for (var outputIndex = 0; outputIndex < plans.length; outputIndex += 1) {
            outputPlans.push(plans[outputIndex].plan);
        }
        emit("insert_effects", requestId, {
            ok: true,
            dry_run: dryRun,
            inserted: dryRun ? 0 : insertableCount,
            insertable_count: insertableCount,
            skipped_count: skippedCount,
            total_count: plans.length,
            plans: outputPlans,
            message: dryRun ? "Ready to batch insert effects; rerun with commit to change the Set" : "Batch effect insert finished"
        });
    } catch (error) {
        emit("insert_effects", requestId, {
            ok: false,
            dry_run: dryRun,
            inserted: 0,
            error: error && error.message ? error.message : String(error),
            allowed_effects: objectKeys(ALLOWED_EFFECTS),
            roles: objectKeys(EFFECT_ROLE_DEVICES)
        });
    }
}


function insertDevice(requestId, requestedDevice, mode) {
    try {
        var dryRun = String(mode || "dry_run") !== "commit";
        var deviceName = resolveDeviceName(requestedDevice);
        if (!deviceName) {
            emit("insert_device", requestId, {
                ok: false,
                error: "Missing device role or device name",
                allowed_devices: objectKeys(ALLOWED_DEVICES),
                roles: objectKeys(ROLE_DEVICES)
            });
            return;
        }
        if (!ALLOWED_DEVICES[deviceName]) {
            emit("insert_device", requestId, {
                ok: false,
                error: "Device is not in the safe native-device whitelist",
                requested: requestedDevice,
                resolved_device: deviceName,
                allowed_devices: objectKeys(ALLOWED_DEVICES)
            });
            return;
        }

        var trackRef = selectedTrack();
        var plan = trackInsertPlan(trackRef, requestedDevice, false, "");
        if (!plan.ok) {
            emit("insert_device", requestId, {
                ok: false,
                error: plan.reason === "Track is not a MIDI track" ? "Selected track is not a MIDI track" : "Selected track already has an instrument; refusing to add another one",
                track_name: plan.track_name,
                resolved_device: plan.resolved_device
            });
            return;
        }

        if (!dryRun) {
            trackRef.api.call("insert_device", deviceName);
        }

        emit("insert_device", requestId, {
            ok: true,
            dry_run: dryRun,
            inserted: !dryRun,
            track_name: plan.track_name,
            requested: requestedDevice,
            resolved_device: deviceName,
            message: dryRun ? "Ready to insert; rerun with commit to change the Set" : "Device inserted"
        });
    } catch (error) {
        emit("insert_device", requestId, {
            ok: false,
            error: error && error.message ? error.message : String(error),
            hint: "Track.insert_device requires Ableton Live 12.3 or newer and only supports native Live devices"
        });
    }
}


function autoPlans(allowExisting) {
    var plans = [];
    var ids = ordinaryTrackIds();
    for (var index = 0; index < ids.length; index += 1) {
        var trackRef = {index: index, id: ids[index], api: new LiveAPI(function () {}, "id " + ids[index])};
        var trackName = String(valueOf(trackRef.api.get("name"), ""));
        var inferred = inferDeviceFromTrackName(trackName);
        if (!inferred.device) {
            plans.push({
                ok: false,
                skipped: true,
                reason: "Could not infer role from track name",
                track_index: index,
                track_name: trackName
            });
            continue;
        }
        plans.push(trackInsertPlan(trackRef, inferred.device, allowExisting, inferred.role));
    }
    return plans;
}


function explicitPlans(targets, defaultDevice, allowExisting) {
    var plans = [];
    for (var index = 0; index < targets.length; index += 1) {
        var target = targets[index];
        var selector = target.track_index !== undefined ? target.track_index : target.track;
        if (selector === undefined || selector === null || selector === "") {
            selector = target.track_name;
        }
        var requestedDevice = target.device || target.role || defaultDevice;
        var trackRef = resolveTrack(selector);
        plans.push(trackInsertPlan(trackRef, requestedDevice, allowExisting, target.role || ""));
    }
    return plans;
}


function insertDevices(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var allowExisting = Boolean(payload.allow_existing);
        var targets = payload.targets || [];
        var plans = payload.auto_empty ? autoPlans(allowExisting) : explicitPlans(targets, payload.device || payload.role || "", allowExisting);
        if (!plans.length) {
            throw new Error("No target tracks were provided");
        }

        var insertableCount = 0;
        var skippedCount = 0;
        for (var index = 0; index < plans.length; index += 1) {
            if (plans[index].ok && !plans[index].skipped) {
                insertableCount += 1;
                if (!dryRun) {
                    resolveTrack(plans[index].track_index).api.call("insert_device", plans[index].resolved_device);
                }
            } else {
                skippedCount += 1;
            }
        }

        emit("insert_devices", requestId, {
            ok: true,
            dry_run: dryRun,
            inserted: dryRun ? 0 : insertableCount,
            insertable_count: insertableCount,
            skipped_count: skippedCount,
            total_count: plans.length,
            plans: plans,
            message: dryRun ? "Ready to batch insert; rerun with commit to change the Set" : "Batch device insert finished"
        });
    } catch (error) {
        emit("insert_devices", requestId, {
            ok: false,
            dry_run: dryRun,
            inserted: 0,
            error: error && error.message ? error.message : String(error),
            hint: "Use targets [{track, role/device}] or auto_empty=true. Only whitelisted native Live instruments are allowed."
        });
    }
}

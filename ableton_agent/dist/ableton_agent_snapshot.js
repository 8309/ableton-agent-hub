autowatch = 1;
inlets = 1;
outlets = 1;


function bang() {
    readSnapshot("");
}


function list() {
    readSnapshot(String(arrayfromargs(arguments)[0] || ""));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    readSnapshot(String(args[0] || ""));
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


function safeGet(api, propertyName, fallback) {
    try {
        return api.get(propertyName);
    } catch (_error) {
        return fallback;
    }
}


function boolProperty(api, propertyName, fallback) {
    return Boolean(Number(valueOf(safeGet(api, propertyName, fallback ? 1 : 0), fallback ? 1 : 0)));
}


function numberProperty(api, propertyName, fallback) {
    return Number(valueOf(safeGet(api, propertyName, fallback), fallback));
}


function stringProperty(api, propertyName, fallback) {
    return String(valueOf(safeGet(api, propertyName, fallback), fallback));
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


function trackKind(track, section) {
    if (section === "return") {
        return "return";
    }
    if (section === "master") {
        return "master";
    }
    if (boolProperty(track, "has_midi_input", false)) {
        return "midi";
    }
    if (boolProperty(track, "has_audio_input", false)) {
        return "audio";
    }
    return "unknown";
}


function readDevices(track) {
    var deviceIds = idsFrom(safeGet(track, "devices", []));
    var devices = [];
    for (var index = 0; index < deviceIds.length; index += 1) {
        var device = new LiveAPI(function () {}, "id " + deviceIds[index]);
        var typeValue = numberProperty(device, "type", -1);
        devices.push({
            index: index,
            id: deviceIds[index],
            name: stringProperty(device, "name", ""),
            class_name: stringProperty(device, "class_name", ""),
            type: typeValue,
            type_name: deviceTypeName(typeValue),
            is_active: boolProperty(device, "is_active", true),
            parameter_count: idsFrom(safeGet(device, "parameters", [])).length,
            chain_count: idsFrom(safeGet(device, "chains", [])).length
        });
    }
    return devices;
}


function parameterSnapshot(parameterId) {
    if (!parameterId) {
        return null;
    }
    var parameter = new LiveAPI(function () {}, "id " + parameterId);
    var value = numberProperty(parameter, "value", 0);
    var displayValue = "";
    try {
        displayValue = String(valueOf(parameter.call("str_for_value", value), ""));
    } catch (_error) {
        displayValue = "";
    }
    return {
        id: parameterId,
        name: stringProperty(parameter, "name", ""),
        value: value,
        min: numberProperty(parameter, "min", 0),
        max: numberProperty(parameter, "max", 1),
        display_value: displayValue
    };
}


function mixerParameter(track, propertyName) {
    var mixerId = idFrom(safeGet(track, "mixer_device", []));
    if (!mixerId) {
        return null;
    }
    var mixer = new LiveAPI(function () {}, "id " + mixerId);
    return parameterSnapshot(idFrom(safeGet(mixer, propertyName, [])));
}


function sendSnapshots(track) {
    var mixerId = idFrom(safeGet(track, "mixer_device", []));
    if (!mixerId) {
        return [];
    }
    var mixer = new LiveAPI(function () {}, "id " + mixerId);
    var sendIds = idsFrom(safeGet(mixer, "sends", []));
    var sends = [];
    for (var index = 0; index < sendIds.length; index += 1) {
        var snapshot = parameterSnapshot(sendIds[index]);
        if (snapshot) {
            snapshot.index = index;
            snapshot.label = String.fromCharCode(65 + index);
            sends.push(snapshot);
        }
    }
    return sends;
}


function readMix(track) {
    return {
        volume: mixerParameter(track, "volume"),
        pan: mixerParameter(track, "panning"),
        sends: sendSnapshots(track),
        output_meter_left: numberProperty(track, "output_meter_left", 0),
        output_meter_right: numberProperty(track, "output_meter_right", 0),
        input_meter_left: numberProperty(track, "input_meter_left", 0),
        input_meter_right: numberProperty(track, "input_meter_right", 0),
        crossfade_assign: numberProperty(track, "crossfade_assign", -1)
    };
}


function readTrack(trackId, index, section, selectedTrackId) {
    var track = new LiveAPI(function () {}, "id " + trackId);
    var devices = readDevices(track);
    var kind = trackKind(track, section);
    return {
        index: index,
        id: trackId,
        section: section,
        kind: kind,
        name: stringProperty(track, "name", ""),
        is_selected: trackId === selectedTrackId,
        has_midi_input: boolProperty(track, "has_midi_input", false),
        has_audio_input: boolProperty(track, "has_audio_input", false),
        can_be_armed: boolProperty(track, "can_be_armed", false),
        arm: boolProperty(track, "arm", false),
        mute: boolProperty(track, "mute", false),
        solo: boolProperty(track, "solo", false),
        mix: readMix(track),
        device_count: devices.length,
        devices: devices
    };
}


function readSnapshot(requestId) {
    try {
        var song = new LiveAPI(function () {}, "live_set");
        var view = new LiveAPI(function () {}, "live_set view");
        var selectedTrackId = idFrom(safeGet(view, "selected_track", []));
        var trackIds = idsFrom(safeGet(song, "tracks", []));
        var returnTrackIds = idsFrom(safeGet(song, "return_tracks", []));
        var masterTrackId = idFrom(safeGet(song, "master_track", []));
        var tracks = [];
        var returnTracks = [];
        var masterTrack = null;

        for (var trackIndex = 0; trackIndex < trackIds.length; trackIndex += 1) {
            tracks.push(readTrack(trackIds[trackIndex], trackIndex, "track", selectedTrackId));
        }
        for (var returnIndex = 0; returnIndex < returnTrackIds.length; returnIndex += 1) {
            returnTracks.push(readTrack(returnTrackIds[returnIndex], returnIndex, "return", selectedTrackId));
        }
        if (masterTrackId) {
            masterTrack = readTrack(masterTrackId, 0, "master", selectedTrackId);
        }

        outlet(0, [requestId, JSON.stringify({
            ok: true,
            tempo: numberProperty(song, "tempo", 0),
            track_count: tracks.length,
            return_track_count: returnTracks.length,
            has_master_track: Boolean(masterTrack),
            selected_track_id: selectedTrackId,
            tracks: tracks,
            return_tracks: returnTracks,
            master_track: masterTrack
        })]);
    } catch (error) {
        outlet(0, [requestId, JSON.stringify({
            ok: false,
            error: error && error.message ? error.message : String(error)
        })]);
    }
}

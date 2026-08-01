autowatch = 1;
inlets = 1;
outlets = 1;


function list() {
    var args = arrayfromargs(arguments);
    handleSampleConfirm(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleSampleConfirm(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
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


function normalizePath(value) {
    return String(value || "").replace(/\\/g, "/").toLowerCase();
}


function basename(value) {
    var parts = String(value || "").replace(/\\/g, "/").split("/");
    return parts.length ? parts[parts.length - 1].toLowerCase() : "";
}


function safeGet(api, propertyName, fallback) {
    try {
        return api.get(propertyName);
    } catch (_error) {
        return fallback;
    }
}


function isSimplerDevice(deviceApi) {
    var name = normalize(valueOf(safeGet(deviceApi, "name", ""), ""));
    var className = normalize(valueOf(safeGet(deviceApi, "class_name", ""), ""));
    return name.indexOf("simpler") >= 0 || className.indexOf("simpler") >= 0;
}


function isDrumRackDevice(deviceApi) {
    var name = normalize(valueOf(safeGet(deviceApi, "name", ""), ""));
    var className = normalize(valueOf(safeGet(deviceApi, "class_name", ""), ""));
    return name.indexOf("drum rack") >= 0 || className.indexOf("drumrack") >= 0 || className.indexOf("drumgroup") >= 0;
}


function trackIds() {
    var song = new LiveAPI(function () {}, "live_set");
    return idsFrom(song.get("tracks"));
}


function selectedTrack() {
    var view = new LiveAPI(function () {}, "live_set view");
    var trackId = idFrom(view.get("selected_track"));
    if (!trackId) {
        throw new Error("No selected track");
    }
    return {index: -1, id: trackId, name: "", api: new LiveAPI(function () {}, "id " + trackId)};
}


function resolveTrack(payload) {
    var selector = payload.track_index !== undefined ? payload.track_index : payload.track;
    if (selector === undefined || selector === null || selector === "" || selector === "selected") {
        var selected = selectedTrack();
        selected.name = String(valueOf(selected.api.get("name"), ""));
        return selected;
    }
    var ids = trackIds();
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


function resolveDevice(track, payload, preferred) {
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
        var name = normalize(valueOf(device.get("name"), ""));
        var className = normalize(valueOf(safeGet(device, "class_name", ""), ""));
        if (preferred === "drum_rack_pad" && (name.indexOf("drum rack") >= 0 || className.indexOf("drumrack") >= 0)) {
            return {index: index, id: ids[index], api: device};
        }
        if (preferred !== "drum_rack_pad" && (name.indexOf("simpler") >= 0 || className.indexOf("simpler") >= 0)) {
            return {index: index, id: ids[index], api: device};
        }
    }
    for (var fallbackIndex = 0; fallbackIndex < ids.length; fallbackIndex += 1) {
        var fallback = new LiveAPI(function () {}, "id " + ids[fallbackIndex]);
        var fallbackName = String(valueOf(fallback.get("name"), ""));
        if (fallbackName.indexOf("Ableton Agent") !== 0) {
            return {index: fallbackIndex, id: ids[fallbackIndex], api: fallback};
        }
    }
    return {index: 0, id: ids[0], api: new LiveAPI(function () {}, "id " + ids[0])};
}


function sampleFromDevice(device) {
    var sampleId = idFrom(safeGet(device.api, "sample", []));
    if (!sampleId) {
        return null;
    }
    var sample = new LiveAPI(function () {}, "id " + sampleId);
    return {
        sample_id: sampleId,
        sample_name: String(valueOf(safeGet(sample, "name", ""), "")),
        file_path: String(valueOf(safeGet(sample, "file_path", ""), "")),
        length: Number(valueOf(safeGet(sample, "length", 0), 0))
    };
}


function findSimplerInChain(chainId) {
    var chain = new LiveAPI(function () {}, "id " + chainId);
    var deviceIds = idsFrom(safeGet(chain, "devices", []));
    for (var index = 0; index < deviceIds.length; index += 1) {
        var device = new LiveAPI(function () {}, "id " + deviceIds[index]);
        var name = normalize(valueOf(device.get("name"), ""));
        var className = normalize(valueOf(safeGet(device, "class_name", ""), ""));
        if (name.indexOf("simpler") >= 0 || className.indexOf("simpler") >= 0) {
            return {index: index, id: deviceIds[index], api: device};
        }
    }
    return null;
}


function sampleFromDrumRackPad(device, payload) {
    var padIds = idsFrom(safeGet(device.api, "drum_pads", []));
    if (!padIds.length) {
        return {
            supported: false,
            limitation: "Drum Rack pad traversal is not exposed here, or this device is not a Drum Rack"
        };
    }
    var targetPadIndex = payload.pad_index !== undefined ? Number(payload.pad_index) : null;
    var targetPadNote = payload.pad_note !== undefined ? Number(payload.pad_note) : null;
    for (var index = 0; index < padIds.length; index += 1) {
        var pad = new LiveAPI(function () {}, "id " + padIds[index]);
        var note = Number(valueOf(safeGet(pad, "note", -1), -1));
        if (targetPadIndex !== null && index !== targetPadIndex) {
            continue;
        }
        if (targetPadNote !== null && note !== targetPadNote) {
            continue;
        }
        var chainIds = idsFrom(safeGet(pad, "chains", []));
        for (var chainIndex = 0; chainIndex < chainIds.length; chainIndex += 1) {
            var simpler = findSimplerInChain(chainIds[chainIndex]);
            if (!simpler) {
                continue;
            }
            var sample = sampleFromDevice(simpler);
            if (sample) {
                sample.pad_index = index;
                sample.pad_id = padIds[index];
                sample.pad_note = note;
                sample.pad_name = String(valueOf(safeGet(pad, "name", ""), ""));
                sample.chain_id = chainIds[chainIndex];
                sample.device_id = simpler.id;
                return {supported: true, sample: sample};
            }
        }
        if (targetPadIndex !== null || targetPadNote !== null) {
            return {
                supported: true,
                sample: null,
                limitation: "Target Drum Rack pad exists, but no Simpler sample was found on its chains"
            };
        }
    }
    return {
        supported: true,
        sample: null,
        limitation: "No loaded Simpler sample found on Drum Rack pads"
    };
}


function samplesFromDrumRackPads(device, payload) {
    var padIds = idsFrom(safeGet(device.api, "drum_pads", []));
    var samples = [];
    var limitations = [];
    if (!padIds.length) {
        return {
            supported: false,
            samples: samples,
            limitations: ["Drum Rack pad traversal is not exposed here, or this device is not a Drum Rack"]
        };
    }
    var targetPadIndex = payload.pad_index !== undefined ? Number(payload.pad_index) : null;
    var targetPadNote = payload.pad_note !== undefined ? Number(payload.pad_note) : null;
    for (var index = 0; index < padIds.length; index += 1) {
        var pad = new LiveAPI(function () {}, "id " + padIds[index]);
        var note = Number(valueOf(safeGet(pad, "note", -1), -1));
        if (targetPadIndex !== null && index !== targetPadIndex) {
            continue;
        }
        if (targetPadNote !== null && note !== targetPadNote) {
            continue;
        }
        var chainIds = idsFrom(safeGet(pad, "chains", []));
        var foundOnPad = false;
        for (var chainIndex = 0; chainIndex < chainIds.length; chainIndex += 1) {
            var simpler = findSimplerInChain(chainIds[chainIndex]);
            if (!simpler) {
                continue;
            }
            var sample = sampleFromDevice(simpler);
            if (sample) {
                sample.pad_index = index;
                sample.pad_id = padIds[index];
                sample.pad_note = note;
                sample.pad_name = String(valueOf(safeGet(pad, "name", ""), ""));
                sample.chain_id = chainIds[chainIndex];
                sample.device_id = simpler.id;
                samples.push(sample);
                foundOnPad = true;
            }
        }
        if ((targetPadIndex !== null || targetPadNote !== null) && !foundOnPad) {
            limitations.push("Target Drum Rack pad exists, but no Simpler sample was found on its chains");
        }
    }
    if (!samples.length && !limitations.length) {
        limitations.push("No loaded Simpler sample found on Drum Rack pads");
    }
    return {supported: true, samples: samples, limitations: limitations};
}


function compareLoadedPath(loadedPath, intendedPath) {
    if (!intendedPath) {
        return null;
    }
    var loaded = normalizePath(loadedPath);
    var intended = normalizePath(intendedPath);
    return {
        intended_path: intendedPath,
        exact_match: loaded !== "" && loaded === intended,
        basename_match: basename(loadedPath) !== "" && basename(loadedPath) === basename(intendedPath)
    };
}


function candidateFromSample(track, device, target, sample, intendedPath) {
    return {
        track_index: track.index,
        track_id: track.id,
        track_name: track.name,
        target: target,
        device: devicePayload(device, device.index),
        loaded: Boolean(sample && sample.file_path),
        sample: sample,
        comparison: compareLoadedPath(sample ? sample.file_path : "", intendedPath)
    };
}


function scanTrackLoadedSamples(track, payload, candidates, limitations, includeDrumRack) {
    var deviceIds = idsFrom(track.api.get("devices"));
    for (var index = 0; index < deviceIds.length; index += 1) {
        var device = {index: index, id: deviceIds[index], api: new LiveAPI(function () {}, "id " + deviceIds[index])};
        if (isSimplerDevice(device.api)) {
            var directSample = sampleFromDevice(device);
            if (directSample && directSample.file_path) {
                candidates.push(candidateFromSample(track, device, "simpler", directSample, payload.intended_path));
            }
        }
        if (includeDrumRack && isDrumRackDevice(device.api)) {
            var drumRack = samplesFromDrumRackPads(device, payload);
            if (drumRack.supported) {
                for (var sampleIndex = 0; sampleIndex < drumRack.samples.length; sampleIndex += 1) {
                    candidates.push(candidateFromSample(track, device, "drum_rack_pad", drumRack.samples[sampleIndex], payload.intended_path));
                }
                if (!drumRack.samples.length && (payload.include_empty || payload.pad_index !== undefined || payload.pad_note !== undefined)) {
                    limitations.push({
                        track_index: track.index,
                        track_name: track.name,
                        device: devicePayload(device, device.index),
                        limitations: drumRack.limitations
                    });
                }
            }
        }
    }
}


function tracksForScan(payload) {
    if (payload.track_index !== undefined || payload.track !== undefined || payload.track_name !== undefined) {
        return [resolveTrack(payload)];
    }
    var ids = trackIds();
    var tracks = [];
    var limit = payload.limit !== undefined ? Number(payload.limit) : ids.length;
    if (!isFinite(limit) || limit <= 0) {
        limit = ids.length;
    }
    for (var index = 0; index < ids.length && index < limit; index += 1) {
        var track = new LiveAPI(function () {}, "id " + ids[index]);
        tracks.push({index: index, id: ids[index], name: String(valueOf(track.get("name"), "")), api: track});
    }
    return tracks;
}


function scanLoadedSamples(payload) {
    var tracks = tracksForScan(payload);
    var candidates = [];
    var limitations = [];
    var specificTrack = payload.track_index !== undefined || payload.track !== undefined || payload.track_name !== undefined;
    var includeDrumRack = specificTrack || Boolean(payload.include_drum_rack);
    for (var index = 0; index < tracks.length; index += 1) {
        scanTrackLoadedSamples(tracks[index], payload, candidates, limitations, includeDrumRack);
    }
    for (var candidateIndex = 0; candidateIndex < candidates.length; candidateIndex += 1) {
        candidates[candidateIndex].candidate_index = candidateIndex;
    }
    return {
        scanned_track_count: tracks.length,
        drum_rack_scanned: includeDrumRack,
        loaded_count: candidates.length,
        candidates: candidates,
        limitations: limitations
    };
}


function confirmLoadedSample(payload) {
    if (payload.candidate_index !== undefined) {
        var scan = scanLoadedSamples(payload);
        var requestedCandidate = Number(payload.candidate_index);
        if (requestedCandidate < 0 || requestedCandidate >= scan.candidates.length || Math.floor(requestedCandidate) !== requestedCandidate) {
            throw new Error("candidate_index is outside the loaded sample scan result");
        }
        return scan.candidates[requestedCandidate];
    }
    var track = resolveTrack(payload);
    var target = String(payload.target || "auto");
    var preferred = target === "drum_rack_pad" ? "drum_rack_pad" : "simpler";
    var device = resolveDevice(track, payload, preferred);
    var deviceInfo = devicePayload(device, device.index);
    var sample = null;
    var drumRack = null;
    if (target === "drum_rack_pad") {
        drumRack = sampleFromDrumRackPad(device, payload);
        sample = drumRack.sample || null;
    } else {
        sample = sampleFromDevice(device);
        if (!sample && target === "auto") {
            drumRack = sampleFromDrumRackPad(device, payload);
            sample = drumRack.sample || null;
        }
    }
    return {
        track_index: track.index,
        track_id: track.id,
        track_name: track.name,
        target: target,
        device: deviceInfo,
        loaded: Boolean(sample && sample.file_path),
        sample: sample,
        comparison: compareLoadedPath(sample ? sample.file_path : "", payload.intended_path),
        drum_rack: drumRack
    };
}


function handleSampleConfirm(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var action = String(payload.action || "confirm_loaded_sample");
        if (action !== "confirm_loaded_sample" && action !== "scan_loaded_samples") {
            throw new Error("action must be confirm_loaded_sample or scan_loaded_samples");
        }
        var result = action === "scan_loaded_samples" ? scanLoadedSamples(payload) : confirmLoadedSample(payload);
        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: true,
            applied: false,
            action: action,
            result: result,
            message: action === "scan_loaded_samples"
                ? "Loaded samples scanned from Live"
                : (result.loaded ? "Loaded sample path read from Live" : "No loaded sample path found on the target")
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

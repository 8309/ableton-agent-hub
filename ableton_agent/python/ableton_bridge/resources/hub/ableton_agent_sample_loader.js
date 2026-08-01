autowatch = 1;
inlets = 1;
outlets = 1;


var DEFAULT_BROWSER_SCAN_LIMIT = 1500;
var SCRIPT_VERSION = "sample_loader_browser_roots_v2";
var AUDIO_EXTENSIONS = {
    ".wav": true,
    ".aif": true,
    ".aiff": true,
    ".flac": true,
    ".mp3": true
};


function anything() {
    var args = arrayfromargs(arguments);
    if (messagename === "load_sample") {
        loadSample(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
    }
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


function emit(command, requestId, payload) {
    outlet(0, [command, requestId, JSON.stringify(payload)]);
}


function normalizePath(path) {
    return String(path || "").replace(/\\/g, "/").toLowerCase();
}


function basename(path) {
    var normalized = String(path || "").replace(/\\/g, "/");
    var parts = normalized.split("/");
    return parts.length ? parts[parts.length - 1].toLowerCase() : normalized.toLowerCase();
}


function extensionOf(path) {
    var name = basename(path);
    var index = name.lastIndexOf(".");
    return index >= 0 ? name.slice(index) : "";
}


function validateSamplePath(path) {
    var text = String(path || "");
    if (!text) {
        throw new Error("sample_path is required");
    }
    var extension = extensionOf(text);
    if (!AUDIO_EXTENSIONS[extension]) {
        throw new Error("sample_path must be an audio file: wav, aif, aiff, flac, or mp3");
    }
    return text;
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
    return {index: -1, id: trackId, api: new LiveAPI(function () {}, "id " + trackId)};
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
        return {index: selector, id: ids[selector], api: new LiveAPI(function () {}, "id " + ids[selector])};
    }
    var numericSelector = Number(selector);
    if (String(selector).match(/^\d+$/) && numericSelector >= 0 && numericSelector < ids.length) {
        return {index: numericSelector, id: ids[numericSelector], api: new LiveAPI(function () {}, "id " + ids[numericSelector])};
    }
    var wanted = String(selector || "").toLowerCase().replace(/^\s+|\s+$/g, "");
    for (var index = 0; index < ids.length; index += 1) {
        var track = new LiveAPI(function () {}, "id " + ids[index]);
        var name = String(valueOf(track.get("name"), ""));
        if (name.toLowerCase().replace(/^\s+|\s+$/g, "") === wanted) {
            return {index: index, id: ids[index], api: track};
        }
    }
    throw new Error("Track not found: " + selector);
}


function selectTrack(trackRef) {
    var view = new LiveAPI(function () {}, "live_set view");
    view.set("selected_track", "id " + trackRef.id);
}


function hasDeviceNamed(track, deviceName) {
    var normalizedName = String(deviceName || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
    var deviceIds = idsFrom(track.get("devices"));
    for (var index = 0; index < deviceIds.length; index += 1) {
        var device = new LiveAPI(function () {}, "id " + deviceIds[index]);
        var name = String(valueOf(device.get("name"), ""));
        var className = String(valueOf(device.get("class_name"), ""));
        if (name.toLowerCase().replace(/[^a-z0-9]+/g, "") === normalizedName ||
                className.toLowerCase().replace(/[^a-z0-9]+/g, "") === normalizedName) {
            return true;
        }
    }
    return false;
}


function ensureTargetDevice(trackRef, target) {
    var normalized = String(target || "simpler").toLowerCase();
    if (normalized === "drum_rack" || normalized === "drum_rack_pad" || normalized === "drumrack") {
        if (!hasDeviceNamed(trackRef.api, "Drum Rack")) {
            trackRef.api.call("insert_device", "Drum Rack");
        }
        return "Drum Rack";
    }
    if (!hasDeviceNamed(trackRef.api, "Simpler")) {
        trackRef.api.call("insert_device", "Simpler");
    }
    return "Simpler";
}


function browserApis() {
    var apis = [
        new LiveAPI(function () {}, "live_app browser"),
        new LiveAPI(function () {}, "live_app view browser")
    ];
    try {
        var app = new LiveAPI(function () {}, "live_app");
        var appBrowserId = idFrom(app.get("browser"));
        if (appBrowserId) {
            apis.push(new LiveAPI(function () {}, "id " + appBrowserId));
        }
    } catch (_appError) {
    }
    try {
        var view = new LiveAPI(function () {}, "live_app view");
        var viewBrowserId = idFrom(view.get("browser"));
        if (viewBrowserId) {
            apis.push(new LiveAPI(function () {}, "id " + viewBrowserId));
        }
    } catch (_viewError) {
    }
    return apis;
}


function browserRootIds(browser) {
    var roots = [];
    var properties = [
        "children",
        "places",
        "user_library",
        "current_project",
        "packs",
        "samples",
        "drums",
        "sounds",
        "instruments",
        "audio_effects",
        "midi_effects",
        "max_for_live",
        "plug_ins",
        "clips",
        "grooves",
        "templates",
        "tunings"
    ];
    for (var index = 0; index < properties.length; index += 1) {
        try {
            roots = roots.concat(idsFrom(browser.get(properties[index])));
        } catch (_error) {
        }
    }
    return roots;
}


function browserRootDiagnostics() {
    var browsers = browserApis();
    var properties = [
        "children",
        "places",
        "user_library",
        "current_project",
        "packs",
        "samples",
        "drums",
        "sounds",
        "instruments",
        "audio_effects",
        "midi_effects",
        "max_for_live",
        "plug_ins",
        "clips",
        "grooves",
        "templates",
        "tunings"
    ];
    var diagnostics = [];
    for (var browserIndex = 0; browserIndex < browsers.length; browserIndex += 1) {
        var browser = browsers[browserIndex];
        var item = {
            path: browserIndex === 0 ? "live_app browser" : browserIndex === 1 ? "live_app view browser" : "browser id lookup " + browserIndex,
            id: 0,
            info: "",
            properties: []
        };
        try {
            item.id = Number(browser.id || 0);
        } catch (_idError) {
        }
        try {
            item.info = String(browser.info || "").slice(0, 600);
        } catch (_infoError) {
        }
        for (var propertyIndex = 0; propertyIndex < properties.length; propertyIndex += 1) {
            var property = properties[propertyIndex];
            try {
                var raw = browser.get(property);
                item.properties.push({
                    name: property,
                    count: idsFrom(raw).length,
                    raw: String(raw).slice(0, 160)
                });
            } catch (error) {
                item.properties.push({
                    name: property,
                    error: error && error.message ? error.message : String(error)
                });
            }
        }
        diagnostics.push(item);
    }
    diagnostics.push(parentObjectDiagnostics("live_app", ["browser", "view"]));
    diagnostics.push(parentObjectDiagnostics("live_app view", ["browser", "selected_track", "highlighted_clip_slot"]));
    return diagnostics;
}


function parentObjectDiagnostics(path, properties) {
    var api = new LiveAPI(function () {}, path);
    var item = {path: path, id: 0, info: "", properties: []};
    try {
        item.id = Number(api.id || 0);
    } catch (_idError) {
    }
    try {
        item.info = String(api.info || "").slice(0, 600);
    } catch (_infoError) {
    }
    for (var index = 0; index < properties.length; index += 1) {
        try {
            var raw = api.get(properties[index]);
            item.properties.push({name: properties[index], count: idsFrom(raw).length, raw: String(raw).slice(0, 160)});
        } catch (error) {
            item.properties.push({name: properties[index], error: error && error.message ? error.message : String(error)});
        }
    }
    return item;
}


function browserItemInfo(itemId) {
    var item = new LiveAPI(function () {}, "id " + itemId);
    var name = String(valueOf(item.get("name"), ""));
    var uri = "";
    var path = "";
    var isLoadable = false;
    try {
        uri = String(valueOf(item.get("uri"), ""));
    } catch (_uriError) {
    }
    try {
        path = String(valueOf(item.get("path"), ""));
    } catch (_pathError) {
    }
    try {
        isLoadable = Boolean(Number(valueOf(item.get("is_loadable"), 0)));
    } catch (_loadableError) {
    }
    return {api: item, id: itemId, name: name, uri: uri, path: path, is_loadable: isLoadable};
}


function browserItemChildren(item) {
    try {
        return idsFrom(item.api.get("children"));
    } catch (_error) {
        return [];
    }
}


function itemMatches(info, samplePath, sampleName) {
    var wantedPath = normalizePath(samplePath);
    var wantedName = sampleName.toLowerCase();
    var candidatePath = normalizePath(info.path + " " + info.uri);
    var candidateName = String(info.name || "").toLowerCase();
    return candidatePath.indexOf(wantedPath) >= 0 ||
        candidatePath.indexOf(wantedName) >= 0 ||
        candidateName === wantedName;
}


function findBrowserItem(samplePath, scanLimit) {
    var browsers = browserApis();
    var limit = Number(scanLimit || DEFAULT_BROWSER_SCAN_LIMIT);
    if (!isFinite(limit) || limit < 1) {
        limit = DEFAULT_BROWSER_SCAN_LIMIT;
    }
    var totalScanned = 0;
    for (var browserIndex = 0; browserIndex < browsers.length; browserIndex += 1) {
        var roots = browserRootIds(browsers[browserIndex]);
        var queue = roots.slice(0);
        var visited = {};
        var sampleName = basename(samplePath);
        var scanned = 0;
        while (queue.length && totalScanned < limit) {
            var itemId = queue.shift();
            if (!itemId || visited[itemId]) {
                continue;
            }
            visited[itemId] = true;
            scanned += 1;
            totalScanned += 1;
            var info = browserItemInfo(itemId);
            if (itemMatches(info, samplePath, sampleName)) {
                info.scanned_count = totalScanned;
                info.browser_path = browserIndex === 0 ? "live_app browser" : "live_app view browser";
                return info;
            }
            var children = browserItemChildren(info);
            for (var childIndex = 0; childIndex < children.length; childIndex += 1) {
                if (!visited[children[childIndex]]) {
                    queue.push(children[childIndex]);
                }
            }
        }
        if (totalScanned >= limit) {
            break;
        }
    }
    return {id: 0, name: "", uri: "", path: "", is_loadable: false, scanned_count: totalScanned};
}


function loadBrowserItem(itemId) {
    var browser = new LiveAPI(function () {}, "live_app browser");
    browser.call("load_item", "id " + itemId);
}


function loadSample(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var samplePath = validateSamplePath(payload.sample_path || payload.path);
        var target = String(payload.target || "simpler");
        var selector = payload.track_index !== undefined ? payload.track_index : payload.track;
        if (selector === undefined || selector === null || selector === "") {
            selector = payload.track_name || "selected";
        }
        var trackRef = resolveTrack(selector);
        var trackName = String(valueOf(trackRef.api.get("name"), ""));
        if (payload.debug_browser) {
            emit("load_sample", requestId, {
                ok: true,
                script_version: SCRIPT_VERSION,
                dry_run: true,
                loaded: false,
                track_index: trackRef.index,
                track_name: trackName,
                target: target,
                sample_path: samplePath,
                browser_diagnostics: browserRootDiagnostics()
            });
            return;
        }
        var scanBrowser = Boolean(payload.scan_browser || !dryRun);
        var item = scanBrowser ? findBrowserItem(samplePath, payload.scan_limit) : {
            id: 0,
            name: "",
            uri: "",
            path: "",
            is_loadable: false,
            scanned_count: 0
        };
        var found = Boolean(item.id);

        if (!dryRun) {
            if (!found) {
                throw new Error("Sample was not found in Live Browser: " + samplePath);
            }
            selectTrack(trackRef);
            var ensuredDevice = ensureTargetDevice(trackRef, target);
            loadBrowserItem(item.id);
            emit("load_sample", requestId, {
                ok: true,
                script_version: SCRIPT_VERSION,
                dry_run: false,
                loaded: true,
                track_index: trackRef.index,
                track_name: trackName,
                target: target,
                ensured_device: ensuredDevice,
                sample_path: samplePath,
                browser_item: {
                    id: item.id,
                    name: item.name,
                    uri: item.uri,
                    path: item.path,
                    is_loadable: item.is_loadable
                },
                scanned_count: item.scanned_count,
                message: "Sample load requested through Live Browser"
            });
            return;
        }

        emit("load_sample", requestId, {
            ok: true,
            script_version: SCRIPT_VERSION,
            dry_run: true,
            loaded: false,
            track_index: trackRef.index,
            track_name: trackName,
            target: target,
            sample_path: samplePath,
            found: found,
            scan_browser: scanBrowser,
            browser_item: found ? {
                id: item.id,
                name: item.name,
                uri: item.uri,
                path: item.path,
                is_loadable: item.is_loadable
            } : null,
            scanned_count: item.scanned_count,
            message: found ? "Ready to load sample; rerun with commit to change the Set" : "Sample path was not found in Live Browser"
        });
    } catch (error) {
        emit("load_sample", requestId, {
            ok: false,
            script_version: SCRIPT_VERSION,
            dry_run: dryRun,
            loaded: false,
            error: error && error.message ? error.message : String(error)
        });
    }
}

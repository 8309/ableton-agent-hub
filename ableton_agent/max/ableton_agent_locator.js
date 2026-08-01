autowatch = 1;
inlets = 1;
outlets = 1;


function list() {
    var args = arrayfromargs(arguments);
    handleLocator(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleLocator(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
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


function emit(requestId, payload) {
    outlet(0, [requestId, JSON.stringify(payload)]);
}


function readLocators(song) {
    var ids = idsFrom(song.get("cue_points"));
    var locators = [];
    for (var index = 0; index < ids.length; index += 1) {
        var cue = new LiveAPI(function () {}, "id " + ids[index]);
        locators.push({
            id: ids[index],
            name: String(valueOf(cue.get("name"), "")),
            beat: Number(valueOf(cue.get("time"), 0))
        });
    }
    locators.sort(function (left, right) {
        return left.beat - right.beat || left.name.localeCompare(right.name);
    });
    return locators;
}


function findLocator(song, payload) {
    var locators = readLocators(song);
    var wantedName = payload.name === undefined ? "" : String(payload.name);
    var wantedId = payload.id === undefined ? 0 : Number(payload.id);
    for (var index = 0; index < locators.length; index += 1) {
        if (wantedId && locators[index].id === wantedId) {
            return locators[index];
        }
        if (wantedName && locators[index].name === wantedName) {
            return locators[index];
        }
    }
    return null;
}


function findLocatorAtBeat(song, beat) {
    var locators = readLocators(song);
    var target = Number(beat);
    for (var index = 0; index < locators.length; index += 1) {
        if (Math.abs(Number(locators[index].beat) - target) < 0.0001) {
            return locators[index];
        }
    }
    return null;
}


function requiredBeat(payload) {
    var beat = payload.beat !== undefined ? payload.beat : payload.time;
    if (beat === undefined || beat === null || beat === "") {
        throw new Error("beat is required");
    }
    var value = Number(beat);
    if (!isFinite(value) || value < 0) {
        throw new Error("beat must be a non-negative number");
    }
    return value;
}


function requiredName(payload) {
    var name = String(payload.name || "").replace(/^\s+|\s+$/g, "");
    if (!name) {
        throw new Error("name is required");
    }
    return name;
}


function jumpToBeat(song, beat) {
    var current = Number(valueOf(song.get("current_song_time"), 0));
    song.call("jump_by", Number(beat) - current);
}


function createLocator(song, payload, dryRun, useCurrentPosition) {
    var name = requiredName(payload);
    var beat = useCurrentPosition ? Number(valueOf(song.get("current_song_time"), 0)) : requiredBeat(payload);
    var existing = findLocator(song, {name: name});
    if (existing) {
        return {created: false, updated: false, locator: existing, message: "Locator already exists"};
    }
    var existingAtBeat = findLocatorAtBeat(song, beat);
    if (dryRun) {
        return {
            created: false,
            updated: false,
            locator: existingAtBeat || {name: name, beat: beat},
            message: existingAtBeat ? "Locator at beat would be renamed" : "Locator create validated"
        };
    }
    if (existingAtBeat && existingAtBeat.id) {
        var existingCue = new LiveAPI(function () {}, "id " + existingAtBeat.id);
        existingCue.set("name", name);
        return {
            created: false,
            updated: true,
            locator: findLocator(song, {id: existingAtBeat.id}) || existingAtBeat,
            message: "Locator at beat renamed"
        };
    }
    if (!useCurrentPosition) {
        jumpToBeat(song, beat);
    }
    song.call("set_or_delete_cue");
    var created = findLocatorAtBeat(song, beat);
    if (created && created.id) {
        var cue = new LiveAPI(function () {}, "id " + created.id);
        cue.set("name", name);
        created = findLocator(song, {id: created.id}) || created;
    }
    return {created: true, updated: false, locator: created, message: "Locator created"};
}


function handleLocator(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    var song = new LiveAPI(function () {}, "live_set");
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var action = String(payload.action || "list").toLowerCase();
        var before = readLocators(song);
        var result = {};

        if (action === "list") {
            result = {changed: false, message: "Locators read"};
        } else if (action === "create" || action === "create_current") {
            result = createLocator(song, payload, dryRun, action === "create_current");
            result.changed = !dryRun && (result.created || result.updated);
        } else if (action === "jump") {
            var jumpTarget = findLocator(song, payload);
            if (!jumpTarget) {
                throw new Error("locator not found");
            }
            if (!dryRun) {
                song.set("current_song_time", jumpTarget.beat);
            }
            result = {changed: !dryRun, locator: jumpTarget, message: "Locator jump applied"};
        } else if (action === "delete") {
            var deleteTarget = findLocator(song, payload);
            if (!deleteTarget) {
                throw new Error("locator not found");
            }
            if (!dryRun) {
                song.call("delete_cue_point", "id " + deleteTarget.id);
            }
            result = {changed: !dryRun, locator: deleteTarget, message: "Locator delete applied"};
        } else {
            throw new Error("action must be list, create, create_current, jump, or delete");
        }

        emit(requestId, {
            ok: true,
            dry_run: dryRun,
            action: action,
            before: before,
            after: dryRun ? before : readLocators(song),
            result: result
        });
    } catch (error) {
        emit(requestId, {
            ok: false,
            dry_run: dryRun,
            changed: false,
            error: error && error.message ? error.message : String(error)
        });
    }
}

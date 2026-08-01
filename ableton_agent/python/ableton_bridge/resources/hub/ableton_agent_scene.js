autowatch = 1;
inlets = 1;
outlets = 1;


function list() {
    var args = arrayfromargs(arguments);
    handleScene(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleScene(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
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


function sceneIds() {
    var song = new LiveAPI(function () {}, "live_set");
    return idsFrom(song.get("scenes"));
}


function sceneInfo(index, id) {
    var scene = new LiveAPI(function () {}, "id " + id);
    return {
        scene_index: index,
        scene_id: id,
        scene_name: String(valueOf(scene.get("name"), "")),
        color: Number(valueOf(safeGet(scene, "color", 0), 0))
    };
}


function listScenes() {
    var ids = sceneIds();
    var scenes = [];
    for (var index = 0; index < ids.length; index += 1) {
        scenes.push(sceneInfo(index, ids[index]));
    }
    return scenes;
}


function coerceSceneIndex(value, fallback, allowEnd) {
    if (value === undefined || value === null || value === "" || (allowEnd && value === "end")) {
        return fallback;
    }
    var numeric = Number(value);
    if (!isFinite(numeric) || Math.floor(numeric) !== numeric || numeric < 0) {
        throw new Error("scene_index must be a non-negative integer");
    }
    if (numeric > fallback) {
        throw new Error("scene_index is outside the scene list");
    }
    return numeric;
}


function resolveExistingScene(payload) {
    var ids = sceneIds();
    var index = coerceSceneIndex(payload.scene_index !== undefined ? payload.scene_index : payload.index, ids.length - 1, false);
    if (index < 0 || index >= ids.length) {
        throw new Error("scene_index is outside the scene list");
    }
    return sceneInfo(index, ids[index]);
}


function createScene(payload, dryRun) {
    var song = new LiveAPI(function () {}, "live_set");
    var beforeCount = sceneIds().length;
    var index = coerceSceneIndex(payload.scene_index !== undefined ? payload.scene_index : payload.index, beforeCount, true);
    var name = String(payload.name || payload.scene_name || "");
    var created = null;
    if (!dryRun) {
        song.call("create_scene", index);
        var ids = sceneIds();
        created = sceneInfo(index, ids[index]);
        if (name) {
            var scene = new LiveAPI(function () {}, "id " + created.scene_id);
            scene.set("name", name);
            created.scene_name = name;
        }
    }
    return {
        before_count: beforeCount,
        index: index,
        name: name,
        scene: created
    };
}


function duplicateScene(payload, dryRun) {
    var song = new LiveAPI(function () {}, "live_set");
    var target = resolveExistingScene(payload);
    var name = String(payload.name || payload.scene_name || "");
    var duplicated = null;
    if (!dryRun) {
        song.call("duplicate_scene", target.scene_index);
        var ids = sceneIds();
        var duplicateIndex = Math.min(target.scene_index + 1, ids.length - 1);
        duplicated = sceneInfo(duplicateIndex, ids[duplicateIndex]);
        if (name) {
            var scene = new LiveAPI(function () {}, "id " + duplicated.scene_id);
            scene.set("name", name);
            duplicated.scene_name = name;
        }
    }
    return {
        source: {
            scene_index: target.scene_index,
            scene_id: target.scene_id,
            scene_name: target.scene_name
        },
        target_index: target.scene_index + 1,
        name: name,
        scene: duplicated
    };
}


function renameScene(payload, dryRun) {
    var target = resolveExistingScene(payload);
    var newName = String(payload.name || payload.new_name || "");
    if (!newName) {
        throw new Error("Missing scene name");
    }
    var beforeName = target.scene_name;
    if (!dryRun) {
        var scene = new LiveAPI(function () {}, "id " + target.scene_id);
        scene.set("name", newName);
        target.scene_name = newName;
    }
    return {
        target: {
            scene_index: target.scene_index,
            scene_id: target.scene_id,
            before_name: beforeName,
            after_name: newName
        }
    };
}


function captureMidi(payload, dryRun) {
    var song = new LiveAPI(function () {}, "live_set");
    var name = String(payload.name || payload.scene_name || "");
    var beforeCount = sceneIds().length;
    if (!dryRun) {
        song.call("capture_midi");
        var ids = sceneIds();
        var index = Math.max(0, ids.length - 1);
        if (name && ids.length) {
            var scene = new LiveAPI(function () {}, "id " + ids[index]);
            scene.set("name", name);
        }
    }
    return {
        before_count: beforeCount,
        name: name,
        captured: !dryRun,
        note: "Live capture_midi uses Live's current capture state and may create or update a scene depending on Live state"
    };
}


function fireScene(payload, dryRun) {
    var target = resolveExistingScene(payload);
    if (!dryRun) {
        var scene = new LiveAPI(function () {}, "id " + target.scene_id);
        scene.call("fire");
    }
    return {
        target: {
            scene_index: target.scene_index,
            scene_id: target.scene_id,
            scene_name: target.scene_name
        },
        fired: !dryRun
    };
}


function handleScene(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var action = String(payload.action || "list");
        var allowed = ["list", "create", "duplicate", "rename", "capture_midi", "fire"];
        if (allowed.indexOf(action) < 0) {
            throw new Error("action must be list, create, duplicate, rename, capture_midi, or fire");
        }
        if (action === "list") {
            var scenes = listScenes();
            outlet(0, [requestId, JSON.stringify({
                ok: true,
                dry_run: true,
                applied: false,
                action: action,
                scene_count: scenes.length,
                scenes: scenes,
                message: "Scenes listed; choose scene_index before editing or firing"
            })]);
            return;
        }
        var result = action === "create"
            ? createScene(payload, dryRun)
            : action === "duplicate"
                ? duplicateScene(payload, dryRun)
                : action === "rename"
                    ? renameScene(payload, dryRun)
                    : action === "capture_midi"
                        ? captureMidi(payload, dryRun)
                        : fireScene(payload, dryRun);
        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: dryRun,
            applied: !dryRun,
            action: action,
            plan: result,
            message: dryRun ? "Ready to apply scene action" : "Scene action applied"
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

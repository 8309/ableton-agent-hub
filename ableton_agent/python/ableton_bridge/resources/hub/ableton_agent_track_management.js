autowatch = 1;
inlets = 1;
outlets = 1;

include("ableton_agent_read_core.js");

var MAX_BOUNDED_TRACKS = 512;


function list() {
    var args = arrayfromargs(arguments);
    handleTrackManagement(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
}


function anything() {
    var args = arrayfromargs(arguments);
    args.unshift(messagename);
    handleTrackManagement(String(args[0] || ""), String(args[1] || "{}"), String(args[2] || "dry_run"));
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


function normalize(value) {
    return String(value || "").toLowerCase().replace(/^\s+|\s+$/g, "");
}


function trackIdsForSection(song, section) {
    if (section === "return") {
        return idsFrom(song.get("return_tracks"));
    }
    return idsFrom(song.get("tracks"));
}


function trackInfo(section, index, id) {
    var track = new LiveAPI(function () {}, "id " + id);
    var isFoldable = Boolean(Number(valueOf(safeGet(track, "is_foldable", 0), 0)));
    var isGrouped = Boolean(Number(valueOf(safeGet(track, "is_grouped", 0), 0)));
    var parentGroupId = idFrom(safeGet(track, "group_track", []));
    return {
        section: section,
        track_index: index,
        track_id: id,
        track_name: String(valueOf(track.get("name"), "")),
        has_midi_input: Boolean(Number(valueOf(safeGet(track, "has_midi_input", 0), 0))),
        has_audio_input: Boolean(Number(valueOf(safeGet(track, "has_audio_input", 0), 0))),
        color: Number(valueOf(safeGet(track, "color", 0), 0)),
        is_grouped: isGrouped,
        is_foldable: isFoldable,
        is_visible: Boolean(Number(valueOf(safeGet(track, "is_visible", 1), 1))),
        fold_state: isFoldable ? Number(valueOf(safeGet(track, "fold_state", 0), 0)) : null,
        parent_group_id: parentGroupId,
        parent_group_name: "",
        depth: 0,
        group_path_ids: [],
        group_path_names: [],
        child_track_ids: []
    };
}


function specialTrackInfo(section, index, id, selectedTrackId) {
    var info = trackInfo(section, index, id);
    var track = new LiveAPI(function () {}, "id " + id);
    info.is_selected = id === selectedTrackId;
    info.device_count = idsFrom(safeGet(track, "devices", [])).length;
    var letter = String.fromCharCode(65 + index);
    var hasReturnPrefix = new RegExp("^" + letter + "(?:\\s*[-:]\\s*|\\s+)", "i").test(info.track_name);
    info.display_name = section === "return" && !hasReturnPrefix
        ? letter + "-" + info.track_name
        : info.track_name;
    return info;
}


function scanSpecialTracks() {
    var song = new LiveAPI(function () {}, "live_set");
    var view = new LiveAPI(function () {}, "live_set view");
    var selectedTrackId = idFrom(safeGet(view, "selected_track", []));
    var returnIds = trackIdsForSection(song, "return");
    var returns = [];
    for (var index = 0; index < returnIds.length; index += 1) {
        returns.push(specialTrackInfo("return", index, returnIds[index], selectedTrackId));
    }
    var mainId = idFrom(safeGet(song, "master_track", []));
    return {
        selected_track_id: selectedTrackId,
        return_tracks: returns,
        main_track: mainId ? specialTrackInfo("main", 0, mainId, selectedTrackId) : null
    };
}


function hierarchySnapshot(payload) {
    var song = new LiveAPI(function () {}, "live_set");
    var ordinaryIds = trackIdsForSection(song, "track");
    var returnIds = trackIdsForSection(song, "return");
    var tracks = [];
    var returns = [];
    var byId = {};
    var index;

    for (index = 0; index < ordinaryIds.length; index += 1) {
        var info = trackInfo("track", index, ordinaryIds[index]);
        tracks.push(info);
        byId[String(info.track_id)] = info;
    }
    for (index = 0; index < returnIds.length; index += 1) {
        returns.push(trackInfo("return", index, returnIds[index]));
    }

    for (index = 0; index < tracks.length; index += 1) {
        var item = tracks[index];
        var parent = byId[String(item.parent_group_id)];
        if (parent) {
            item.parent_group_name = parent.track_name;
            parent.child_track_ids.push(item.track_id);
        }
        var cursor = item;
        var seen = {};
        while (cursor.parent_group_id && byId[String(cursor.parent_group_id)]) {
            if (seen[String(cursor.parent_group_id)]) {
                break;
            }
            seen[String(cursor.parent_group_id)] = true;
            cursor = byId[String(cursor.parent_group_id)];
            item.group_path_ids.unshift(cursor.track_id);
            item.group_path_names.unshift(cursor.track_name);
            item.depth += 1;
        }
    }

    function treeNode(trackItem) {
        var children = [];
        for (var childIndex = 0; childIndex < trackItem.child_track_ids.length; childIndex += 1) {
            var child = byId[String(trackItem.child_track_ids[childIndex])];
            if (child) {
                children.push(treeNode(child));
            }
        }
        return {
            track_id: trackItem.track_id,
            track_name: trackItem.track_name,
            is_group: trackItem.is_foldable,
            fold_state: trackItem.fold_state,
            child_track_ids: trackItem.child_track_ids.slice(),
            children: children
        };
    }

    var hierarchy = [];
    var rootTrackIds = [];
    var groupCount = 0;
    for (index = 0; index < tracks.length; index += 1) {
        if (tracks[index].is_foldable) {
            groupCount += 1;
        }
        if (!tracks[index].parent_group_id || !byId[String(tracks[index].parent_group_id)]) {
            rootTrackIds.push(tracks[index].track_id);
            hierarchy.push(treeNode(tracks[index]));
        }
    }

    return {
        ordinary_track_count: tracks.length,
        return_track_count: returns.length,
        group_track_count: groupCount,
        root_track_ids: rootTrackIds,
        tracks: tracks,
        return_tracks: payload && payload.include_returns === false ? [] : returns,
        hierarchy: hierarchy
    };
}


function orderSummary(snapshot) {
    var order = [];
    for (var index = 0; index < snapshot.tracks.length; index += 1) {
        var track = snapshot.tracks[index];
        order.push({
            track_id: track.track_id,
            track_name: track.track_name,
            parent_group_id: track.parent_group_id,
            depth: track.depth,
            is_group: track.is_foldable
        });
    }
    return order;
}


function findOrdinaryTrackById(snapshot, rawId, label) {
    var trackId = Number(rawId);
    if (!isFinite(trackId) || Math.floor(trackId) !== trackId || trackId <= 0) {
        throw new Error((label || "track_id") + " must be a positive Live track id");
    }
    for (var index = 0; index < snapshot.tracks.length; index += 1) {
        if (Number(snapshot.tracks[index].track_id) === trackId) {
            return snapshot.tracks[index];
        }
    }
    throw new Error((label || "track_id") + " was not found in ordinary tracks: " + trackId);
}


function directMemberIds(snapshot, groupTrackId) {
    var members = [];
    for (var index = 0; index < snapshot.tracks.length; index += 1) {
        if (Number(snapshot.tracks[index].parent_group_id) === Number(groupTrackId)) {
            members.push(snapshot.tracks[index].track_id);
        }
    }
    return members;
}


function descendantIds(snapshot, groupTrackId) {
    var descendants = [];
    var pending = directMemberIds(snapshot, groupTrackId);
    while (pending.length) {
        var trackId = pending.shift();
        descendants.push(trackId);
        var children = directMemberIds(snapshot, trackId);
        for (var index = 0; index < children.length; index += 1) {
            pending.push(children[index]);
        }
    }
    return descendants;
}


function parseTrackIdList(raw, label) {
    if (!(raw instanceof Array) || !raw.length) {
        throw new Error((label || "member_track_ids") + " must be a non-empty array of track ids");
    }
    var result = [];
    var seen = {};
    for (var index = 0; index < raw.length; index += 1) {
        var trackId = Number(raw[index]);
        if (!isFinite(trackId) || Math.floor(trackId) !== trackId || trackId <= 0) {
            throw new Error((label || "member_track_ids") + " contains an invalid track id");
        }
        if (!seen[String(trackId)]) {
            seen[String(trackId)] = true;
            result.push(trackId);
        }
    }
    return result;
}


function hashText(text) {
    var hash = 2166136261;
    for (var index = 0; index < text.length; index += 1) {
        hash ^= text.charCodeAt(index);
        hash += (hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24);
    }
    var hex = (hash >>> 0).toString(16);
    return ("00000000" + hex).slice(-8);
}


function makePlanToken(action, beforeOrder, desired) {
    return hashText(JSON.stringify({action: action, before_order: beforeOrder, desired: desired}));
}


function parseColor(value) {
    if (value === undefined || value === null || value === "") {
        throw new Error("Missing color value");
    }
    if (typeof value === "number") {
        if (!isFinite(value) || value < 0 || value > 16777215 || Math.floor(value) !== value) {
            throw new Error("color must be an integer between 0 and 16777215");
        }
        return Number(value);
    }
    var text = String(value).replace(/^\s+|\s+$/g, "");
    if (/^#[0-9a-fA-F]{6}$/.test(text)) {
        return parseInt(text.slice(1), 16);
    }
    if (/^0x[0-9a-fA-F]{6}$/.test(text)) {
        return parseInt(text.slice(2), 16);
    }
    if (/^[0-9]+$/.test(text)) {
        var numeric = Number(text);
        if (numeric >= 0 && numeric <= 16777215 && Math.floor(numeric) === numeric) {
            return numeric;
        }
    }
    throw new Error("color must be an integer, #RRGGBB, or 0xRRGGBB");
}


function scanTracks(payload) {
    var song = new LiveAPI(function () {}, "live_set");
    var includeReturns = payload.include_returns === undefined ? true : Boolean(payload.include_returns);
    var ordinaryIds = trackIdsForSection(song, "track");
    var tracks = [];
    for (var index = 0; index < ordinaryIds.length; index += 1) {
        tracks.push(trackInfo("track", index, ordinaryIds[index]));
    }
    if (includeReturns) {
        var returnIds = trackIdsForSection(song, "return");
        for (var returnIndex = 0; returnIndex < returnIds.length; returnIndex += 1) {
            tracks.push(trackInfo("return", returnIndex, returnIds[returnIndex]));
        }
    }
    return tracks;
}


function boundedTrackType(section, track, isFoldable) {
    if (section === "return" || section === "main") {
        return section;
    }
    if (isFoldable) {
        return "group";
    }
    if (Boolean(Number(valueOf(safeGet(track, "has_midi_input", 0), 0)))) {
        return "midi";
    }
    if (Boolean(Number(valueOf(safeGet(track, "has_audio_input", 0), 0)))) {
        return "audio";
    }
    return "unknown";
}


function boundedTrackRecord(reference, read) {
    var track = new LiveAPI(function () {}, "id " + reference.id);
    var result = {};
    var isFoldable = Boolean(Number(valueOf(safeGet(track, "is_foldable", 0), 0)));
    if (AbletonAgentReadCore.has(read, "identity")) {
        result.section = reference.section;
        result.track_index = reference.index;
        result.track_id = reference.id;
        result.track_name = String(valueOf(safeGet(track, "name", ""), ""));
        result.track_type = boundedTrackType(reference.section, track, isFoldable);
    }
    if (AbletonAgentReadCore.has(read, "hierarchy")) {
        result.parent_group_id = reference.section === "track"
            ? idFrom(safeGet(track, "group_track", []))
            : 0;
    }
    if (AbletonAgentReadCore.has(read, "color")) {
        result.color = Number(valueOf(safeGet(track, "color", 0), 0));
    }
    if (AbletonAgentReadCore.has(read, "fold")) {
        result.is_foldable = isFoldable;
        result.is_grouped = Boolean(Number(valueOf(safeGet(track, "is_grouped", 0), 0)));
        result.is_visible = Boolean(Number(valueOf(safeGet(track, "is_visible", 1), 1)));
        result.fold_state = isFoldable ? Number(valueOf(safeGet(track, "fold_state", 0), 0)) : null;
    }
    if (AbletonAgentReadCore.has(read, "device_count")) {
        result.device_count = idsFrom(safeGet(track, "devices", [])).length;
    }
    return result;
}


function boundedTrackCollection(payload) {
    var song = new LiveAPI(function () {}, "live_set");
    var ordinaryIds = trackIdsForSection(song, "track");
    var returnIds = payload.include_returns === false ? [] : trackIdsForSection(song, "return");
    var references = [];
    var tokenIds = [];
    var index;
    for (index = 0; index < ordinaryIds.length; index += 1) {
        references.push({section: "track", index: index, id: ordinaryIds[index]});
        tokenIds.push(ordinaryIds[index]);
    }
    for (index = 0; index < returnIds.length; index += 1) {
        references.push({section: "return", index: index, id: returnIds[index]});
        tokenIds.push(returnIds[index]);
    }
    var mainId = payload.include_main === false ? 0 : idFrom(safeGet(song, "master_track", []));
    if (mainId) {
        references.push({section: "main", index: 0, id: mainId});
        tokenIds.push(mainId);
    }
    return {
        references: references.slice(0, MAX_BOUNDED_TRACKS),
        token_ids: tokenIds.slice(0, MAX_BOUNDED_TRACKS),
        ordinary_track_count: ordinaryIds.length,
        return_track_count: returnIds.length,
        main_track_count: mainId ? 1 : 0
    };
}


function scanTracksBounded(payload) {
    var read = AbletonAgentReadCore.parse(payload, {
        max_limit: 64,
        max_cursor: MAX_BOUNDED_TRACKS,
        allowed_projection: ["identity", "hierarchy", "color", "fold", "device_count"],
        default_projection: ["identity", "hierarchy"]
    });
    var collection = boundedTrackCollection(payload);
    var token = AbletonAgentReadCore.collectionToken(collection.token_ids);
    AbletonAgentReadCore.verifyCollection(read, token);
    if (read.cursor > collection.references.length) {
        throw new Error("read.cursor is outside the track collection");
    }
    var items = [];
    var scanned = 0;
    var partial = false;
    while (read.cursor + scanned < collection.references.length && scanned < read.limit) {
        if (scanned > 0 && AbletonAgentReadCore.budgetExceeded(read)) {
            partial = true;
            break;
        }
        items.push(boundedTrackRecord(collection.references[read.cursor + scanned], read));
        scanned += 1;
    }
    var nextCursor = read.cursor + scanned;
    var hasMore = nextCursor < collection.references.length;
    return {
        items: items,
        ordinary_track_count: collection.ordinary_track_count,
        return_track_count: collection.return_track_count,
        main_track_count: collection.main_track_count,
        total_item_count: collection.references.length,
        read: AbletonAgentReadCore.metadata(read, {
            next_cursor: nextCursor,
            scanned_count: scanned,
            returned_count: items.length,
            has_more: hasMore,
            partial: partial,
            collection_token: token,
            warnings: []
        })
    };
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
        return trackInfo(resolvedSection, requestedIndex, ids[requestedIndex]);
    }

    var wanted = normalize(selector);
    for (var index = 0; index < ids.length; index += 1) {
        var info = trackInfo(resolvedSection, index, ids[index]);
        if (normalize(info.track_name) === wanted) {
            return info;
        }
    }
    throw new Error("Track not found: " + selector);
}


function coerceInsertIndex(value, fallback) {
    if (value === undefined || value === null || value === "" || value === "end") {
        return fallback;
    }
    var numeric = Number(value);
    if (!isFinite(numeric) || Math.floor(numeric) !== numeric || numeric < 0 || numeric > fallback) {
        throw new Error("index must be an integer between 0 and the current track count");
    }
    return numeric;
}


function createdTrackInfo(song, section, index) {
    var ids = trackIdsForSection(song, section);
    if (index < 0 || index >= ids.length) {
        throw new Error("created track could not be resolved");
    }
    return trackInfo(section, index, ids[index]);
}


function trackIsEmpty(trackInfoItem) {
    var track = new LiveAPI(function () {}, "id " + trackInfoItem.track_id);
    if (idsFrom(safeGet(track, "devices", [])).length) {
        return {empty: false, reason: "track has devices"};
    }
    if (idsFrom(safeGet(track, "arrangement_clips", [])).length) {
        return {empty: false, reason: "track has Arrangement clips"};
    }
    var slots = idsFrom(safeGet(track, "clip_slots", []));
    for (var index = 0; index < slots.length; index += 1) {
        var slot = new LiveAPI(function () {}, "id " + slots[index]);
        if (Boolean(Number(valueOf(safeGet(slot, "has_clip", 0), 0)))) {
            return {empty: false, reason: "track has Session clips"};
        }
    }
    return {empty: true, reason: ""};
}


function createTrack(payload, kind, dryRun) {
    var song = new LiveAPI(function () {}, "live_set");
    var ids = trackIdsForSection(song, "track");
    var index = coerceInsertIndex(payload.index !== undefined ? payload.index : payload.track_index, ids.length);
    var name = String(payload.name || payload.track_name || "");
    var created = null;
    if (!dryRun) {
        if (kind === "audio") {
            song.call("create_audio_track", index);
        } else {
            song.call("create_midi_track", index);
        }
        created = createdTrackInfo(song, "track", index);
        if (name) {
            var track = new LiveAPI(function () {}, "id " + created.track_id);
            track.set("name", name);
            created.track_name = name;
        }
        if (payload.select) {
            var view = new LiveAPI(function () {}, "live_set view");
            view.set("selected_track", "id " + created.track_id);
        }
    }
    return {
        index: index,
        name: name,
        kind: kind,
        track: created
    };
}


function createReturnTrack(payload, dryRun) {
    var song = new LiveAPI(function () {}, "live_set");
    var ids = trackIdsForSection(song, "return");
    var index = ids.length;
    if (payload.index !== undefined || payload.track_index !== undefined) {
        var requestedIndex = coerceInsertIndex(payload.index !== undefined ? payload.index : payload.track_index, ids.length);
        if (requestedIndex !== ids.length) {
            throw new Error("Live can only append Return Tracks; requested index must equal the current Return count");
        }
    }
    var requestedName = String(payload.name || payload.track_name || "");
    var letter = String.fromCharCode(65 + index);
    var duplicatePrefix = new RegExp("^" + letter + "(?:\\s*[-:]\\s*|\\s+)", "i");
    var name = requestedName.replace(duplicatePrefix, "");
    var color = payload.color === undefined ? null : parseColor(payload.color);
    var created = null;
    var afterIds = ids.slice(0);
    if (!dryRun) {
        var expectedIds = payload.expected_return_ids;
        if (!(expectedIds instanceof Array)) {
            throw new Error("Commit requires expected_return_ids from the preceding dry-run");
        }
        if (expectedIds.length !== ids.length) {
            throw new Error("Return Track list changed since dry-run; scan again before commit");
        }
        for (var expectedIndex = 0; expectedIndex < ids.length; expectedIndex += 1) {
            if (Number(expectedIds[expectedIndex]) !== ids[expectedIndex]) {
                throw new Error("Return Track identity changed since dry-run; scan again before commit");
            }
        }
        song.call("create_return_track");
        afterIds = trackIdsForSection(song, "return");
        var createdIds = [];
        for (var afterIndex = 0; afterIndex < afterIds.length; afterIndex += 1) {
            if (ids.indexOf(afterIds[afterIndex]) < 0) {
                createdIds.push(afterIds[afterIndex]);
            }
        }
        if (afterIds.length !== ids.length + 1 || createdIds.length !== 1) {
            throw new Error("Return Track creation was not observable as exactly one new stable track_id");
        }
        var resolvedIndex = afterIds.indexOf(createdIds[0]);
        created = createdTrackInfo(song, "return", resolvedIndex);
        var track = new LiveAPI(function () {}, "id " + created.track_id);
        if (name) {
            track.set("name", name);
            created.track_name = String(valueOf(track.get("name"), ""));
        }
        if (color !== null) {
            track.set("color", color);
            created.color = Number(valueOf(track.get("color"), 0));
        }
        if (payload.select) {
            var view = new LiveAPI(function () {}, "live_set view");
            view.set("selected_track", "id " + created.track_id);
        }
    }
    return {
        index: index,
        requested_name: requestedName,
        stored_name: name,
        display_name: letter + "-" + name,
        kind: "return",
        color: color,
        before_return_ids: ids,
        after_return_ids: afterIds,
        expected_return_ids: ids,
        track: created,
        verified_created: Boolean(created)
    };
}


function deleteReturnPlanToken(trackId, trackName, deviceIds, returnIds) {
    return hashText(JSON.stringify({
        action: "delete_return_track",
        track_id: trackId,
        track_name: trackName,
        device_ids: deviceIds,
        return_ids: returnIds
    }));
}


function deleteReturnTrack(payload, dryRun) {
    var song = new LiveAPI(function () {}, "live_set");
    var beforeIds = trackIdsForSection(song, "return");
    var trackId = Number(payload.track_id);
    if (!isFinite(trackId) || trackId <= 0 || Math.floor(trackId) !== trackId) {
        throw new Error("delete_return_track requires a positive stable track_id");
    }
    var index = beforeIds.indexOf(trackId);
    if (index < 0) {
        throw new Error("track_id is not a current Return Track");
    }
    var track = new LiveAPI(function () {}, "id " + trackId);
    var trackName = String(valueOf(track.get("name"), ""));
    var expectedName = String(payload.expected_track_name || "");
    if (expectedName && normalize(expectedName) !== normalize(trackName)) {
        throw new Error("Return Track name changed since selection: " + trackName);
    }
    var deviceIds = idsFrom(safeGet(track, "devices", []));
    var token = deleteReturnPlanToken(trackId, trackName, deviceIds, beforeIds);
    var afterIds = beforeIds.slice(0);
    var verifiedDeleted = false;
    if (!dryRun) {
        if (String(payload.plan_token || "") !== token) {
            throw new Error("plan_token does not match current Return Track identity or contents; dry-run again");
        }
        if (deviceIds.length && !Boolean(payload.allow_nonempty)) {
            throw new Error("Return Track has devices; commit requires allow_nonempty=true after review");
        }
        song.call("delete_return_track", index);
        afterIds = trackIdsForSection(song, "return");
        var expectedAfterIds = [];
        for (var beforeIndex = 0; beforeIndex < beforeIds.length; beforeIndex += 1) {
            if (beforeIds[beforeIndex] !== trackId) {
                expectedAfterIds.push(beforeIds[beforeIndex]);
            }
        }
        if (afterIds.length !== expectedAfterIds.length) {
            throw new Error("Return Track deletion was not observable as exactly one removed track_id");
        }
        for (var afterIndex = 0; afterIndex < afterIds.length; afterIndex += 1) {
            if (afterIds[afterIndex] !== expectedAfterIds[afterIndex]) {
                throw new Error("Unexpected Return Track identity/order change after deletion");
            }
        }
        verifiedDeleted = true;
    }
    return {
        section: "return",
        track_index: index,
        track_id: trackId,
        track_name: trackName,
        device_count: deviceIds.length,
        device_ids: deviceIds,
        before_return_ids: beforeIds,
        after_return_ids: afterIds,
        plan_token: token,
        requires_allow_nonempty: deviceIds.length > 0,
        verified_deleted: verifiedDeleted
    };
}


function deleteEmptyTrack(payload, dryRun) {
    var song = new LiveAPI(function () {}, "live_set");
    var target = resolveTrack(song, payload);
    if (target.section !== "track") {
        throw new Error("delete_empty_track only supports ordinary tracks");
    }
    var safety = trackIsEmpty(target);
    if (!safety.empty) {
        throw new Error("Refusing to delete non-empty track: " + safety.reason);
    }
    if (!dryRun) {
        song.call("delete_track", target.track_index);
    }
    return {
        target: {
            section: target.section,
            track_index: target.track_index,
            track_id: target.track_id,
            track_name: target.track_name
        },
        empty: true,
        deleted: !dryRun
    };
}


function colorTrack(payload, dryRun) {
    var song = new LiveAPI(function () {}, "live_set");
    var target = resolveTrack(song, payload);
    var color = parseColor(payload.color);
    var beforeColor = target.color;
    if (!dryRun) {
        var track = new LiveAPI(function () {}, "id " + target.track_id);
        track.set("color", color);
        target.color = color;
    }
    return {
        target: {
            section: target.section,
            track_index: target.track_index,
            track_id: target.track_id,
            track_name: target.track_name,
            before_color: beforeColor,
            after_color: color
        }
    };
}


function renameTrack(payload, dryRun) {
    var song = new LiveAPI(function () {}, "live_set");
    var target = resolveTrack(song, payload);
    var newName = String(payload.name || payload.new_name || "");
    if (!newName) {
        throw new Error("Missing new track name");
    }
    var beforeName = target.track_name;
    if (!dryRun) {
        var track = new LiveAPI(function () {}, "id " + target.track_id);
        track.set("name", newName);
        target.track_name = newName;
    }
    return {
        target: {
            section: target.section,
            track_index: target.track_index,
            track_id: target.track_id,
            before_name: beforeName,
            after_name: newName
        }
    };
}


function cloneOrder(order) {
    return JSON.parse(JSON.stringify(order));
}


function orderIndexById(order, trackId) {
    for (var index = 0; index < order.length; index += 1) {
        if (String(order[index].track_id) === String(trackId)) {
            return index;
        }
    }
    return -1;
}


function setGroupProperties(payload, dryRun) {
    var snapshotBefore = hierarchySnapshot({include_returns: true});
    var target = findOrdinaryTrackById(
        snapshotBefore,
        payload.group_track_id !== undefined ? payload.group_track_id : payload.track_id,
        "group_track_id"
    );
    if (!target.is_foldable) {
        throw new Error("group_track_id does not resolve to a Group Track");
    }

    var desired = {};
    if (payload.name !== undefined || payload.new_name !== undefined) {
        desired.name = String(payload.name !== undefined ? payload.name : payload.new_name);
        if (!desired.name) {
            throw new Error("Group Track name cannot be empty");
        }
    }
    if (payload.color !== undefined) {
        desired.color = parseColor(payload.color);
    }
    if (payload.fold_state !== undefined) {
        desired.fold_state = Number(payload.fold_state);
        if (desired.fold_state !== 0 && desired.fold_state !== 1) {
            throw new Error("fold_state must be 0 or 1");
        }
    }
    if (desired.name === undefined && desired.color === undefined && desired.fold_state === undefined) {
        throw new Error("Provide at least one of name, color, or fold_state");
    }

    var beforeOrder = orderSummary(snapshotBefore);
    var token = makePlanToken("set_group_properties", beforeOrder, {
        group_track_id: target.track_id,
        current_name: target.track_name,
        current_color: target.color,
        current_fold_state: target.fold_state,
        desired: desired
    });
    var directMembers = directMemberIds(snapshotBefore, target.track_id);
    var allMembers = descendantIds(snapshotBefore, target.track_id);

    if (dryRun) {
        return {
            supported: true,
            can_commit: true,
            plan_token: token,
            target_group: target,
            direct_member_track_ids: directMembers,
            member_track_ids: allMembers,
            requested: desired,
            before_order: beforeOrder,
            after_order: cloneOrder(beforeOrder),
            hierarchy_before: snapshotBefore.hierarchy
        };
    }
    if (!payload.plan_token) {
        throw new Error("set_group_properties commit requires plan_token from a preceding dry-run");
    }
    if (String(payload.plan_token) !== token) {
        throw new Error("plan_token is stale; track ids, order, hierarchy, or group properties changed. Run dry-run again");
    }

    var groupApi = new LiveAPI(function () {}, "id " + target.track_id);
    if (desired.name !== undefined) {
        groupApi.set("name", desired.name);
    }
    if (desired.color !== undefined) {
        groupApi.set("color", desired.color);
    }
    if (desired.fold_state !== undefined) {
        groupApi.set("fold_state", desired.fold_state);
    }

    var snapshotAfter = hierarchySnapshot({include_returns: true});
    var readback = findOrdinaryTrackById(snapshotAfter, target.track_id, "group_track_id");
    var nameVerified = desired.name === undefined || readback.track_name === desired.name;
    var foldVerified = desired.fold_state === undefined || readback.fold_state === desired.fold_state;
    return {
        supported: true,
        can_commit: true,
        plan_token: token,
        target_group: target,
        direct_member_track_ids: directMembers,
        member_track_ids: allMembers,
        requested: desired,
        before_order: beforeOrder,
        after_order: orderSummary(snapshotAfter),
        readback: readback,
        verified: nameVerified && foldVerified,
        color_exact: desired.color === undefined || readback.color === desired.color,
        hierarchy_after: snapshotAfter.hierarchy
    };
}


function validateLeafTrack(track, label) {
    if (track.is_foldable) {
        throw new Error((label || "track_id") + " currently resolves to a Group Track; nested group movement is not planned automatically");
    }
}


function buildGroupProjection(snapshot, groups) {
    if (!(groups instanceof Array) || !groups.length) {
        throw new Error("groups must be a non-empty array");
    }
    var before = orderSummary(snapshot);
    var assigned = {};
    var normalizedGroups = [];
    for (var groupIndex = 0; groupIndex < groups.length; groupIndex += 1) {
        var rawGroup = groups[groupIndex] || {};
        var groupName = String(rawGroup.name || rawGroup.group_name || "");
        if (!groupName) {
            throw new Error("Each group requires a name");
        }
        var memberIds = parseTrackIdList(rawGroup.member_track_ids, "member_track_ids");
        var members = [];
        var sharedParent = null;
        for (var memberIndex = 0; memberIndex < memberIds.length; memberIndex += 1) {
            var member = findOrdinaryTrackById(snapshot, memberIds[memberIndex], "member_track_id");
            validateLeafTrack(member, "member_track_id");
            if (assigned[String(member.track_id)]) {
                throw new Error("A track id cannot be assigned to more than one target group: " + member.track_id);
            }
            assigned[String(member.track_id)] = true;
            if (sharedParent === null) {
                sharedParent = member.parent_group_id;
            } else if (Number(sharedParent) !== Number(member.parent_group_id)) {
                throw new Error("All members of a planned group must currently share the same parent group");
            }
            members.push(member);
        }
        var plannedFoldState = rawGroup.fold_state === undefined ? 0 : Number(rawGroup.fold_state);
        if (plannedFoldState !== 0 && plannedFoldState !== 1) {
            throw new Error("Each planned group fold_state must be 0 or 1");
        }
        normalizedGroups.push({
            name: groupName,
            color: rawGroup.color === undefined ? null : parseColor(rawGroup.color),
            fold_state: plannedFoldState,
            member_track_ids: memberIds,
            members: members
        });
    }

    var after = [];
    for (groupIndex = 0; groupIndex < normalizedGroups.length; groupIndex += 1) {
        var planned = normalizedGroups[groupIndex];
        var pseudoId = "new_group:" + planned.name;
        after.push({
            track_id: pseudoId,
            track_name: planned.name,
            parent_group_id: 0,
            depth: 0,
            is_group: true
        });
        for (var orderIndex = 0; orderIndex < before.length; orderIndex += 1) {
            var entry = before[orderIndex];
            if (planned.member_track_ids.indexOf(Number(entry.track_id)) >= 0) {
                var projected = cloneOrder([entry])[0];
                projected.parent_group_id = pseudoId;
                projected.depth = 1;
                after.push(projected);
            }
        }
    }
    for (var remainingIndex = 0; remainingIndex < before.length; remainingIndex += 1) {
        if (!assigned[String(before[remainingIndex].track_id)]) {
            after.push(cloneOrder([before[remainingIndex]])[0]);
        }
    }
    return {
        groups: normalizedGroups,
        before_order: before,
        after_order: after
    };
}


function structuralPlan(action, payload) {
    var snapshot = hierarchySnapshot({include_returns: true});
    var before = orderSummary(snapshot);
    var after = cloneOrder(before);
    var targetGroup = null;
    var memberTrackIds = [];
    var targetTrack = null;
    var targetGroups = [];

    if (action === "plan_groups" || action === "create_group") {
        var requestedGroups = action === "plan_groups"
            ? payload.groups
            : [{
                name: payload.name || payload.group_name,
                color: payload.color,
                fold_state: payload.fold_state,
                member_track_ids: payload.member_track_ids
            }];
        var projection = buildGroupProjection(snapshot, requestedGroups);
        before = projection.before_order;
        after = projection.after_order;
        for (var groupIndex = 0; groupIndex < projection.groups.length; groupIndex += 1) {
            targetGroups.push({
                name: projection.groups[groupIndex].name,
                color: projection.groups[groupIndex].color,
                fold_state: projection.groups[groupIndex].fold_state,
                member_track_ids: projection.groups[groupIndex].member_track_ids
            });
            memberTrackIds = memberTrackIds.concat(projection.groups[groupIndex].member_track_ids);
        }
    } else if (action === "move_track_to_group") {
        targetTrack = findOrdinaryTrackById(snapshot, payload.track_id, "track_id");
        validateLeafTrack(targetTrack, "track_id");
        targetGroup = findOrdinaryTrackById(snapshot, payload.group_track_id, "group_track_id");
        if (!targetGroup.is_foldable) {
            throw new Error("group_track_id does not resolve to a Group Track");
        }
        var movingIndex = orderIndexById(after, targetTrack.track_id);
        var movingEntry = after.splice(movingIndex, 1)[0];
        var groupIndexInOrder = orderIndexById(after, targetGroup.track_id);
        var descendantList = descendantIds(snapshot, targetGroup.track_id);
        var insertIndex = groupIndexInOrder + 1;
        for (var descendantIndex = 0; descendantIndex < descendantList.length; descendantIndex += 1) {
            var candidateIndex = orderIndexById(after, descendantList[descendantIndex]);
            if (candidateIndex >= insertIndex) {
                insertIndex = candidateIndex + 1;
            }
        }
        movingEntry.parent_group_id = targetGroup.track_id;
        movingEntry.depth = targetGroup.depth + 1;
        after.splice(insertIndex, 0, movingEntry);
        memberTrackIds = directMemberIds(snapshot, targetGroup.track_id).concat([targetTrack.track_id]);
    } else if (action === "move_track_out_of_group") {
        targetTrack = findOrdinaryTrackById(snapshot, payload.track_id, "track_id");
        validateLeafTrack(targetTrack, "track_id");
        if (!targetTrack.parent_group_id) {
            throw new Error("track_id is not currently inside a Group Track");
        }
        targetGroup = findOrdinaryTrackById(snapshot, targetTrack.parent_group_id, "parent_group_id");
        var removeIndex = orderIndexById(after, targetTrack.track_id);
        var removed = after.splice(removeIndex, 1)[0];
        var requestedIndex = payload.target_index === undefined ? after.length : Number(payload.target_index);
        if (!isFinite(requestedIndex) || Math.floor(requestedIndex) !== requestedIndex || requestedIndex < 0 || requestedIndex > after.length) {
            throw new Error("target_index must be between 0 and the projected ordinary track count");
        }
        removed.parent_group_id = 0;
        removed.depth = 0;
        after.splice(requestedIndex, 0, removed);
        memberTrackIds = directMemberIds(snapshot, targetGroup.track_id).filter(function (id) {
            return Number(id) !== Number(targetTrack.track_id);
        });
    } else if (action === "reorder_track") {
        targetTrack = findOrdinaryTrackById(snapshot, payload.track_id, "track_id");
        validateLeafTrack(targetTrack, "track_id");
        var targetIndex = Number(payload.target_index);
        if (!isFinite(targetIndex) || Math.floor(targetIndex) !== targetIndex || targetIndex < 0 || targetIndex >= after.length) {
            throw new Error("target_index must be an existing projected ordinary track index");
        }
        var originalIndex = orderIndexById(after, targetTrack.track_id);
        var reordered = after.splice(originalIndex, 1)[0];
        after.splice(targetIndex, 0, reordered);
        memberTrackIds = [targetTrack.track_id];
    } else {
        throw new Error("Unsupported structural planning action: " + action);
    }

    var desired = {
        action: action,
        target_track_id: targetTrack ? targetTrack.track_id : null,
        target_group_id: targetGroup ? targetGroup.track_id : null,
        member_track_ids: memberTrackIds,
        target_groups: targetGroups,
        after_order: after
    };
    return {
        supported: false,
        can_commit: false,
        blocked_by_live_api: true,
        api_limitation: "The public Live Object Model exposes Group Track hierarchy for reading, but has no create-group or move/reorder-track function",
        plan_token: makePlanToken(action, before, desired),
        target_track: targetTrack,
        target_group: targetGroup,
        target_groups: targetGroups,
        member_track_ids: memberTrackIds,
        before_order: before,
        after_order: after,
        return_track_ids_excluded: snapshot.return_tracks.map(function (track) { return track.track_id; }),
        manual_steps: [
            "Resolve every target by track_id and confirm its current name in scan_hierarchy",
            "Perform the grouping or drag operation manually in Ableton Live",
            "Run scan_hierarchy again and compare parent_group_id plus ordinary track order"
        ]
    };
}


function handleTrackManagement(requestId, payloadText, mode) {
    var dryRun = String(mode || "dry_run") !== "commit";
    try {
        var payload = JSON.parse(String(payloadText || "{}"));
        var action = String(payload.action || "scan_tracks");
        var allowed = ["scan_tracks", "scan_hierarchy", "scan_special_tracks", "create_midi_track", "create_audio_track", "create_return_track", "delete_return_track", "rename_track", "color_track", "delete_empty_track", "set_group_properties", "create_group", "move_track_to_group", "move_track_out_of_group", "reorder_track", "plan_groups"];
        if (allowed.indexOf(action) < 0) {
            throw new Error("Unsupported track_management action: " + action);
        }

        if (action === "scan_special_tracks") {
            var special = scanSpecialTracks();
            outlet(0, [requestId, JSON.stringify({
                ok: true,
                dry_run: true,
                applied: false,
                action: action,
                selected_track_id: special.selected_track_id,
                return_track_count: special.return_tracks.length,
                return_tracks: special.return_tracks,
                main_track: special.main_track,
                message: "Return and Main tracks scanned without traversing ordinary tracks"
            })]);
            return;
        }

        if (action === "scan_tracks" || action === "scan_hierarchy") {
            if (payload.read && typeof payload.read === "object") {
                var bounded = scanTracksBounded(payload);
                outlet(0, [requestId, JSON.stringify({
                    ok: true,
                    dry_run: true,
                    applied: false,
                    action: action,
                    track_count: bounded.ordinary_track_count + bounded.return_track_count,
                    ordinary_track_count: bounded.ordinary_track_count,
                    return_track_count: bounded.return_track_count,
                    main_track_count: bounded.main_track_count,
                    total_item_count: bounded.total_item_count,
                    read: bounded.read,
                    items: bounded.items,
                    tracks: bounded.items,
                    message: "Bounded flat track records scanned; rebuild hierarchy after all pages are collected"
                })]);
                return;
            }
            var snapshot = hierarchySnapshot(payload);
            outlet(0, [requestId, JSON.stringify({
                ok: true,
                dry_run: true,
                applied: false,
                action: action,
                track_count: snapshot.tracks.length + snapshot.return_tracks.length,
                ordinary_track_count: snapshot.ordinary_track_count,
                return_track_count: snapshot.return_track_count,
                group_track_count: snapshot.group_track_count,
                tracks: snapshot.tracks.concat(snapshot.return_tracks),
                hierarchy: action === "scan_hierarchy" ? snapshot.hierarchy : undefined,
                root_track_ids: action === "scan_hierarchy" ? snapshot.root_track_ids : undefined,
                message: action === "scan_hierarchy"
                    ? "Track hierarchy scanned; use session-stable track_id values for group planning"
                    : "Tracks scanned; choose track_id for hierarchy-sensitive operations"
            })]);
            return;
        }

        var structuralActions = ["create_group", "move_track_to_group", "move_track_out_of_group", "reorder_track", "plan_groups"];
        if (structuralActions.indexOf(action) >= 0) {
            var blockedPlan = structuralPlan(action, payload);
            outlet(0, [requestId, JSON.stringify({
                ok: dryRun,
                dry_run: dryRun,
                applied: false,
                action: action,
                blocked_by_live_api: true,
                plan: blockedPlan,
                error: dryRun ? undefined : "Commit refused: public Live API cannot create Group Tracks or move/reorder tracks",
                message: dryRun
                    ? "Manual Group Track plan prepared; commit is unavailable through the public Live API"
                    : "No Live state changed"
            })]);
            return;
        }

        var result = action === "set_group_properties"
            ? setGroupProperties(payload, dryRun)
            : action === "rename_track"
            ? renameTrack(payload, dryRun)
            : action === "color_track"
                ? colorTrack(payload, dryRun)
                : action === "delete_empty_track"
                    ? deleteEmptyTrack(payload, dryRun)
                    : action === "create_return_track"
                        ? createReturnTrack(payload, dryRun)
                        : action === "delete_return_track"
                            ? deleteReturnTrack(payload, dryRun)
                        : createTrack(payload, action === "create_audio_track" ? "audio" : "midi", dryRun);

        outlet(0, [requestId, JSON.stringify({
            ok: true,
            dry_run: dryRun,
            applied: !dryRun,
            action: action,
            plan: result,
            message: dryRun ? "Ready to apply track management action" : "Track management action applied"
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

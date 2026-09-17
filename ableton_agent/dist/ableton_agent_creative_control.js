// Private compatibility adapter for MCP creative calls on existing Hub routes.
var AgentCreative = (function () {
    var plans = {};
    var order = [];
    var serial = 0;
    function api(id) { return new LiveAPI(function () {}, "id " + id); }
    function song() { return new LiveAPI(function () {}, "live_set"); }
    function value(raw) { return raw instanceof Array ? raw[0] : raw; }
    function ids(raw) {
        var out = [];
        for (var i = 0; i < raw.length - 1; i += 1) {
            if (raw[i] === "id") { out.push(Number(raw[i + 1])); i += 1; }
        }
        return out;
    }
    function positive(id) {
        if (typeof id !== "number" || !isFinite(id) || id <= 0 || Math.floor(id) !== id) {
            throw new Error("A positive stable Live ID is required");
        }
        return id;
    }
    function track(payload) {
        var section = payload.section || "track";
        if (["track", "return", "main"].indexOf(section) < 0) { throw new Error("Invalid track section"); }
        var s = song();
        var list = section === "main" ? ids(s.get("master_track")) :
            ids(s.get(section === "return" ? "return_tracks" : "tracks"));
        var id = positive(payload.track_id);
        var index = list.indexOf(id);
        if (index < 0) { throw new Error("track_id does not belong to requested section"); }
        var a = api(id);
        return {id: id, index: index, api: a, section: section,
            name: String(value(a.get("name")))};
    }
    function device(t, id) {
        id = positive(id);
        var list = ids(t.api.get("devices"));
        var index = list.indexOf(id);
        if (index < 0) { throw new Error("device_id is not a direct device of this track; nested targets are not supported by this tool"); }
        return {id: id, index: index, api: api(id)};
    }
    function scene(id) {
        var list = ids(song().get("scenes"));
        var index = list.indexOf(positive(id));
        if (index < 0) { throw new Error("scene_id is not in the current Set"); }
        return {id: id, index: index, api: api(id)};
    }
    function clip(t, id, arrangementOnly) {
        id = positive(id);
        var arr = ids(t.api.get("arrangement_clips"));
        if (arr.indexOf(id) >= 0) { return api(id); }
        if (!arrangementOnly) {
            var slots = ids(t.api.get("clip_slots"));
            for (var i = 0; i < slots.length; i += 1) {
                var slot = api(slots[i]);
                if (Number(value(slot.get("has_clip"))) && ids(slot.get("clip"))[0] === id) {
                    return api(id);
                }
            }
        }
        throw new Error("clip_id does not belong to target track/location");
    }
    function emptyRange(t, start, length) {
        var list = ids(t.api.get("arrangement_clips"));
        var state = [];
        for (var i = 0; i < list.length; i += 1) {
            var c = api(list[i]);
            var begin = Number(value(c.get("start_time")));
            var end = Number(value(c.get("end_time")));
            if (begin < start + length && end > start) {
                throw new Error("Target range overlaps an existing Clip; no replacement allowed");
            }
            state.push([list[i], begin, end]);
        }
        return state;
    }
    function handle(family, requestId, payload, mode, prepare, emit) {
        var dry = String(mode || "dry_run") !== "commit";
        var attempted = false;
        var s = null;
        var undo = false;
        try {
            s = song();
            if (payload.mcp_safe !== 1) { throw new Error("Unsupported creative protocol version"); }
            if (!payload.creative || typeof payload.creative !== "object") { throw new Error("Missing private creative payload"); }
            payload = payload.creative;
            var work = prepare(payload);
            if (unescape(encodeURIComponent(JSON.stringify(work.plan))).length > 14000) {
                throw new Error("Impact result too large; narrow the target/page before applying");
            }
            var clean = {};
            for (var key in payload) { if (key !== "plan_token") { clean[key] = payload[key]; } }
            var signature = JSON.stringify([s.id, family, clean, work.state]);
            var token = null;
            if (work.read_only) {
                if (!dry) { throw new Error("Read-only action cannot apply"); }
            } else if (dry) {
                serial += 1;
                token = "creative-" + new Date().getTime() + "-" + serial;
                plans[token] = {signature: signature, expires: new Date().getTime() + 120000};
                order.push(token);
                while (order.length > 32) { delete plans[order.shift()]; }
            } else {
                token = String(payload.plan_token || "");
                var stored = plans[token];
                delete plans[token];
                if ((token || payload.direct_apply !== true) &&
                    (!stored || stored.expires < new Date().getTime() || stored.signature !== signature)) {
                    throw new Error("stale_plan: inspect again; request, target, or before-state changed");
                }
                s.call("begin_undo_step");
                undo = true;
                attempted = true;
            }
            var result = dry || work.read_only ? work.plan : work.apply();
            if (undo) { undo = false; s.call("end_undo_step"); }
            emit(requestId, {ok: true, mcp_protocol: 1, dry_run: dry,
                applied: attempted, plan_token: token, plan_expires_in_ms: dry && !work.read_only ? 120000 : null,
                plan: work.read_only ? null : work.plan, result: dry && !work.read_only ? null : result,
                message: dry ? "Impact inspected; no Live changes" : "Applied; inspect result for verification scope"});
        } catch (error) {
            emit(requestId, {ok: false, mcp_protocol: 1, dry_run: dry,
                applied: attempted ? null : false, mutation_attempted: attempted,
                recovery: attempted ? "State may have changed. Inspect the target; do not retry automatically. Live Undo is available." : null,
                error: error && error.message ? error.message : String(error)});
        } finally {
            if (undo) { try { s.call("end_undo_step"); } catch (_cleanupError) {} }
        }
    }
    function notes(c) {
        if (!Number(value(c.get("is_midi_clip")))) { throw new Error("MIDI Clip required"); }
        var raw = c.call("get_all_notes_extended");
        var parsed;
        if (raw instanceof Dict) { parsed = JSON.parse(raw.stringify()); }
        else if (raw instanceof Array && raw[0] === "dictionary") { parsed = JSON.parse(new Dict(raw[1]).stringify()); }
        else if (typeof raw === "string") { parsed = JSON.parse(raw); }
        if (!parsed || !(parsed.notes instanceof Array)) { throw new Error("Invalid note readback"); }
        if (parsed.notes.length > 512) { throw new Error("Creative note operation limited to 512 notes; use a smaller Clip"); }
        return parsed.notes;
    }
    function writeNotes(c, ns, method) {
        var d = new Dict();
        d.setparse("wrapper", JSON.stringify({notes: ns}));
        c.call(method, d.get("wrapper"));
    }
    function checkNotes(expected, actual, byId) {
        if (expected.length !== actual.length) { throw new Error("Note count readback mismatch"); }
        function key(n) { return byId ? Number(n.note_id) : Number(n.start_time) * 128 + Number(n.pitch); }
        expected = expected.slice().sort(function(a,b) { return key(a)-key(b); });
        actual = actual.slice().sort(function(a,b) { return key(a)-key(b); });
        var fields = ["pitch", "start_time", "duration", "velocity", "mute", "probability", "velocity_deviation", "release_velocity"];
        if (byId) { fields.push("note_id"); }
        for (var i = 0; i < expected.length; i += 1) {
            for (var j = 0; j < fields.length; j += 1) {
                var f = fields[j];
                if (expected[i][f] !== undefined && (actual[i][f] === undefined || !isFinite(Number(actual[i][f])) || Math.abs(Number(expected[i][f])-Number(actual[i][f])) > 0.0001)) {
                    throw new Error("Note readback mismatch: " + f);
                }
            }
        }
    }
    function newClip(t, p, ns) {
        if (t.section !== "track" || !Number(value(t.api.get("has_midi_input")))) { throw new Error("Ordinary MIDI track required"); }
        if (p.replace) { throw new Error("Replacement is not supported"); }
        if (!isFinite(p.length) || p.length <= 0 || p.length > 256 || ns.length > 512) { throw new Error("Invalid Clip size"); }
        for(var ni=0;ni<ns.length;ni+=1) {
            var n=ns[ni];
            if(!isFinite(n.start_time) || n.start_time<0 || n.start_time>=p.length ||
               !isFinite(n.duration) || n.duration<=0 || n.start_time+n.duration>p.length+0.0001) {
                throw new Error("Variation notes must fit the new Clip; crop source explicitly first");
            }
        }
        var slot = null, state;
        if (p.location === "arrangement") {
            if (!isFinite(p.start) || p.start < 0) { throw new Error("Invalid target beat"); }
            state = emptyRange(t, p.start, p.length);
        } else {
            var sc = scene(p.scene_id);
            var sid = ids(t.api.get("clip_slots"))[sc.index];
            slot = api(sid);
            if (Number(value(slot.get("has_clip")))) { throw new Error("Session slot is occupied"); }
            state = [sc.id, sid];
        }
        var plan = {track_id:t.id, track_name:t.name, location:p.location, scene_id:p.scene_id,
            start:p.start, length:p.length, name:p.name, note_count:ns.length};
        return {state:state, plan:plan, apply:function() {
            var before = slot ? [] : ids(t.api.get("arrangement_clips"));
            if (slot) { slot.call("create_clip", p.length); }
            else { t.api.call("create_midi_clip", p.start, p.length); }
            var cid;
            if (slot) { cid = ids(slot.get("clip"))[0]; }
            else {
                var created = ids(t.api.get("arrangement_clips")).filter(function(id) { return before.indexOf(id)<0; });
                if (created.length !== 1) { throw new Error("Expected exactly one new Clip"); }
                cid = created[0];
            }
            var c = api(positive(cid));
            c.set("loop_start", 0); c.set("loop_end", p.length); c.set("looping", 1);
            if (p.name) { c.set("name", p.name); }
            if (ns.length) { writeNotes(c, ns, "add_new_notes"); }
            checkNotes(ns, notes(c), false);
            if (Math.abs(Number(value(c.get("length")))-p.length)>0.0001 ||
                (p.name && String(value(c.get("name")))!==p.name)) { throw new Error("Clip metadata readback mismatch"); }
            if (!slot && Math.abs(Number(value(c.get("start_time")))-p.start)>0.0001) { throw new Error("Clip position readback mismatch"); }
            return {clip_id:cid, track_id:t.id, note_count:ns.length, verified:true};
        }};
    }
    return {api: api, song: song, value: value, ids: ids, track: track, device: device,
        scene: scene, clip: clip, emptyRange: emptyRange, handle: handle,
        notes:notes, writeNotes:writeNotes, checkNotes:checkNotes, newClip:newClip};
}());

function agentCreativeEmit(requestId, result) {
    outlet(0, [requestId, JSON.stringify(result)]);
}

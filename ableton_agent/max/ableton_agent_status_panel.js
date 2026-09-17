autowatch = 0;
inlets = 2;
outlets = 4;

// Passive wire observer. It never forwards commands, sends UDP, or accesses LOM.
var current = null;
var history = [];
var probes = {};
var songId = null;
function requestInfo(command, args) {
    var payload = {};
    try { payload = JSON.parse(String(args[1] || "{}")); } catch (ignore) {}
    if (!payload || typeof payload !== "object") { payload = {}; }
    var action = String(payload.action || "");
    var mode = String(args[args.length - 1] || "");
    var type = mode === "commit" ? "WRITE" : "INSPECT";
    if (command === "ping" || /^(get|read|scan|list|search|summary)/.test(action) ||
            /^(parameter_summary|snapshot|meter_monitor)$/.test(command)) { type = "READ"; }
    if (action === "health" || action === "_module_health") { type = "PROBE"; }
    var target = [];
    ["track_id", "device_id", "parameter_id", "clip_id"].forEach(function (key) {
        if (payload[key] !== undefined) { target.push(key.replace("_id", "") + " " + payload[key]); }
    });
    return {action: shortText(action, 64), type: type, target: shortText(target.join(" / "), 140)};
}
function shortText(value, limit) {
    var text = String(value === undefined ? "" : value).replace(/[\r\n\t]/g, " ");
    return text.length > limit ? text.slice(0, limit - 3) + "..." : text;
}
function render() {
    if (!current) { return; }
    outlet(0, "set", shortText(current.command, 28) + " | " + current.state +
        (current.elapsed_ms === null ? "" : " | " + current.elapsed_ms + " ms"));
    outlet(1, "set", "Request: " + shortText(current.request_id, 62));
    outlet(2, "set", shortText(current.error || current.note, 48));
    outlet(3, "model", JSON.stringify({current: current, history: history, probes: probes}));
}
function observe(selector, args, input) {
    var command = shortText(String(selector).replace(/^\//, ""), 96);
    var id = shortText(args[0], 128);
    if (input === 0) {
        var info = requestInfo(command, args);
        if (current && current.state === "WAITING") {
            current.state = "UNKNOWN";
            current.note = "No final reply observed before next request.";
        }
        current = {command: command, request_id: id, started: Date.now(),
            action: info.action, type: info.type, target: info.target,
            elapsed_ms: null, state: "WAITING", error: "",
            note: "Request received; outcome not yet known."};
        history.unshift(current);
        if (history.length > 32) { history.pop(); }
        render();
        return;
    }
    if (!current || current.request_id !== id) { return; }
    if (command === "parameter_summary_progress") { return; }
    if (command !== current.command && !(command === "pong" && current.command === "ping")) { return; }
    var result = null;
    if (command !== "pong") {
        try {
            result = JSON.parse(args.slice(1).join(" "));
            if (!result || typeof result !== "object" || result instanceof Array) { throw new Error("Not an object"); }
        }
        catch (error) {
            result = null;
            current.state = "UNKNOWN";
            current.error = "Reply is not valid JSON; outcome unknown.";
        }
    }
    if (result && result.kind === "progress") { return; }
    current.elapsed_ms = Math.max(0, Date.now() - current.started);
    if (command === "pong") {
        current.state = "REPLIED";
        current.note = "Ping only; module readiness unknown.";
    } else if (result) {
        current.state = result.ok === true ? "OK" : result.ok === false ? "FAILED" : "UNKNOWN";
        current.error = result.error ? shortText(typeof result.error === "string" ? result.error : JSON.stringify(result.error), 2048) : "";
        current.applied = result.applied;
        current.verified = result.verified;
        if (result.health_protocol === 1 && result.module) {
            current.type = "PROBE";
            if (songId !== null && result.song_id && songId !== result.song_id) { probes = {}; }
            if (result.song_id) { songId = result.song_id; }
            if (/^(tracks|parameters|clips|insertion)$/.test(result.module)) {
                probes[result.module] = {ok: result.ok === true, at: Date.now(), build: shortText(result.running_build || "unknown", 80)};
            }
        }
        current.note = result.ok === true ? "Module replied; client delivery not verified." : "Check structured client reply for details.";
    }
    render();
}
function anything() {
    observe(messagename, arrayfromargs(arguments), inlet);
}
// An explicit bang prints the full last diagnostic, not an unbounded log stream.
function bang() {
    post("Hub last operation: " + JSON.stringify(current) + "\n");
}

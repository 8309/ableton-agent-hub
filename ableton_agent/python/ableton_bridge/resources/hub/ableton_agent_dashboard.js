autowatch = 0;
inlets = 1;
outlets = 0;
mgraphics.init();
mgraphics.relative_coords = 0;
mgraphics.autofill = 0;
var build = "dev-6ce97b799d0e";
var data = {current: null, history: [], probes: {}};
var tab = 0, page = 0, detailPage = 0, selected = null;
var bg = [0.065, 0.07, 0.075, 1], line = [0.22, 0.24, 0.25, 1];
var ink = [0.9, 0.92, 0.92, 1], muted = [0.59, 0.63, 0.65, 1];
var cyan = [0.05, 0.83, 0.87, 1], amber = [1, 0.75, 0.12, 1], red = [1, 0.36, 0.32, 1];
function model(text) {
    try { data = JSON.parse(text); } catch (ignore) { return; }
    page = Math.min(page, Math.max(0, Math.ceil(data.history.length / 5) - 1));
    mgraphics.redraw();
}
function fill(x, y, w, h, color) {
    mgraphics.set_source_rgba(color);
    mgraphics.rectangle(x, y, w, h); mgraphics.fill();
}
function label(text, x, y, width, color, size) {
    text = String(text === undefined ? "unknown" : text).replace(/[\r\n\t]/g, " ");
    mgraphics.select_font_face("Arial"); mgraphics.set_font_size(size || 10);
    if (mgraphics.text_measure(text)[0] > width) {
        while (text.length && mgraphics.text_measure(text + "...")[0] > width) { text = text.slice(0, -1); }
        text += "...";
    }
    mgraphics.set_source_rgba(color || ink); mgraphics.move_to(x, y); mgraphics.show_text(text);
}
function tone(state) {
    return state === "FAILED" ? red : state === "WAITING" ? amber : state === "OK" || state === "REPLIED" ? cyan : muted;
}
function row(index) { return data.history[index] || null; }
function detail() {
    for (var i = 0; i < data.history.length; i++) {
        if (data.history[i].request_id === selected) { return data.history[i]; }
    }
    return data.current;
}
function wrap(text, width) {
    mgraphics.select_font_face("Arial"); mgraphics.set_font_size(10);
    var lines = [], currentLine = "";
    String(text).split("").forEach(function (c) {
        if (c === "\n" || mgraphics.text_measure(currentLine + c)[0] > width) {
            lines.push(currentLine); currentLine = c === "\n" ? "" : c;
        } else { currentLine += c; }
    });
    lines.push(currentLine); return lines;
}
function diagnosticLines(item) {
    if (!item) { return ["No request observed."]; }
    return wrap("Request: " + item.request_id + "\n" + item.command + " / " + (item.action || "-") +
        " / " + item.type + " / " + item.state + "\n" + (item.target || "Target not included in request") +
        "\nApplied: " + (item.applied === undefined ? "unknown" : item.applied) +
        "   Verified: " + (item.verified === undefined ? "unknown" : item.verified) +
        "\n" + (item.error || item.note), 586);
}
function paint() {
    fill(0, 0, 620, 148, bg);
    fill(0, 0, 3, 24, cyan);
    label("ABLETON AGENT", 12, 17, 160, ink, 12);
    var c = data.current;
    label(c ? c.state : "IDLE", 185, 17, 85, tone(c ? c.state : "IDLE"));
    ["OVERVIEW", "HISTORY", "DIAGNOSTICS"].forEach(function (name, i) {
        var x = 316 + i * 98;
        if (tab === i) { fill(x, 22, 92, 2, cyan); }
        label(name, x + 5, 16, 90, tab === i ? ink : muted, 10);
    });
    fill(10, 27, 600, 1, line);
    if (tab === 0) {
        label("TRANSPORT", 12, 43, 166, muted, 9);
        label("UDP 7400  >  7401", 12, 62, 174, ink, 12);
        label("MCP version: unknown", 12, 84, 174, muted);
        label("Disk version: unknown", 12, 101, 174, muted);
        label("Sequential requests", 12, 119, 174, muted);
        fill(196, 36, 1, 86, line);
        label("LAST OPERATION", 208, 43, 264, muted, 9);
        label(c ? c.command : "No request yet", 208, 63, 258, ink, 13);
        label(c ? c.type + " / " + (c.action || "-") : "-", 208, 81, 260, cyan);
        label(c ? c.target || "Target not included" : "", 208, 99, 260, muted);
        label(c ? c.state + " / " + (c.elapsed_ms === null ? "pending" : c.elapsed_ms + " ms") : "IDLE", 208, 119, 260, tone(c ? c.state : "IDLE"));
        fill(480, 36, 1, 86, line);
        label("LAST PROBES", 492, 43, 115, muted, 9);
        ["tracks", "parameters", "clips", "insertion"].forEach(function (name, i) {
            var p = data.probes[name];
            label(name, 492, 62 + i * 18, 68, ink);
            label(p ? p.ok ? "OK" : "FAIL" : "?", 566, 62 + i * 18, 42, p ? p.ok ? cyan : red : muted);
        });
    } else if (tab === 1) {
        if (!data.history.length) { label("No requests recorded", 14, 58, 560, muted); }
        for (var i = 0; i < 5; i++) {
            var item = row(page * 5 + i);
            if (!item) { break; }
            var y = 34 + i * 18;
            if (i % 2 === 0) { fill(10, y, 600, 18, [0.1, 0.11, 0.12, 1]); }
            label(item.type, 16, y + 13, 58, cyan, 9);
            label(item.command + (item.action ? " / " + item.action : ""), 80, y + 13, 275, ink);
            label(item.state, 370, y + 13, 70, tone(item.state));
            label(item.elapsed_ms === null ? "-" : item.elapsed_ms + " ms", 454, y + 13, 70, muted);
            label(item.request_id.slice(0, 8), 538, y + 13, 65, muted, 9);
        }
    } else {
        var lines = diagnosticLines(detail());
        detailPage = Math.min(detailPage, Math.max(0, Math.ceil(lines.length / 5) - 1));
        for (var n = 0; n < 5 && detailPage * 5 + n < lines.length; n++) {
            label(lines[detailPage * 5 + n], 14, 46 + n * 17, 588, ink);
        }
    }
    fill(10, 128, 600, 1, line);
    label(build, 12, 142, 264, muted, 9);
    if (tab === 0) { label("Reply observed != client delivery", 304, 142, 300, muted, 9); }
    else {
        var total = tab === 1 ? Math.max(1, Math.ceil(data.history.length / 5)) : Math.max(1, Math.ceil(diagnosticLines(detail()).length / 5));
        label((tab === 1 ? data.history.length + "/32 requests" : "Selected request") + "  |  " + ((tab === 1 ? page : detailPage) + 1) + "/" + total, 300, 142, 240, muted, 9);
        label("<", 552, 142, 18, ink, 12); label(">", 589, 142, 18, ink, 12);
    }
}
function onclick(x, y) {
    if (y < 27 && x >= 316 && x < 610) { tab = Math.floor((x - 316) / 98); detailPage = 0; }
    else if (tab === 1 && y >= 34 && y < 124) {
        var item = row(page * 5 + Math.floor((y - 34) / 18));
        if (item) { selected = item.request_id; tab = 2; detailPage = 0; }
    } else if (tab !== 0 && y >= 129 && x >= 540) {
        var step = x < 578 ? -1 : 1;
        if (tab === 1) { page = Math.max(0, Math.min(page + step, Math.ceil(data.history.length / 5) - 1)); }
        else { detailPage = Math.max(0, Math.min(detailPage + step, Math.ceil(diagnosticLines(detail()).length / 5) - 1)); }
    }
    mgraphics.redraw();
}

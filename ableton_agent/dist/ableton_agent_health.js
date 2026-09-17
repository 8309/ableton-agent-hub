// Build substitution identifies the shared helper actually executing in Max.
var AgentHealth = (function () {
    var build = "dev-6ce97b799d0e";
    function reply(requestId, module, mode, send) {
        var result = {ok: false, read_only: true, dry_run: true,
            request_id: requestId, health_protocol: 1, module: module,
            running_build: build, evidence: "module_handler_and_shared_helper"};
        try {
            if (String(mode || "dry_run") !== "dry_run") {
                result.error_code = "client_validation_failed";
                throw new Error("Module health is read-only");
            }
            var song = new LiveAPI(function () {}, "live_set");
            if (!Number(song.id)) { throw new Error("Live Set unavailable"); }
            result.song_id = Number(song.id);
            result.ok = true;
        } catch (error) {
            result.error_code = result.error_code || "lom_read_failed";
            result.error = String(error.message || error);
        }
        if (send) { send(requestId, result); }
        else { outlet(0, [requestId, JSON.stringify(result)]); }
    }
    return {reply: reply};
}());

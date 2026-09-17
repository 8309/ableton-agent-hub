"""Explicit, bounded module probes; a pong is not module readiness."""
import hashlib
from pathlib import Path

MODULES = {"tracks": "/track_management", "parameters": "/parameter_summary",
           "clips": "/write_clip", "insertion": "/insert_effect"}


def mcp_build_id():
    digest = hashlib.sha256()
    for name in ("mcp_server.py", "mcp_tools.py", "mcp_creative.py", "module_health.py"):
        source = Path(__file__).with_name(name)
        digest.update(name.encode() + source.read_bytes())
    return "dev-" + digest.hexdigest()[:12]


def module_status(request, connection, *, probe=False):
    results = {name: {"state": "unknown"} for name in MODULES}
    if probe:
        for name, route in MODULES.items():
            try:
                reply = request(route, {"action": "_module_health"}, commit=False, **connection)
                valid = (reply.get("health_protocol") == 1 and reply.get("module") == name
                         and reply.get("read_only") is True and reply.get("dry_run") is True)
                ready = valid and reply.get("ok") is True and bool(reply.get("running_build"))
                results[name] = {"state": "ready" if ready else "failed", "reply": reply,
                                 "error_category": None if ready else
                                 ("lom_read_failed" if valid else "unsupported_health_protocol")}
            except Exception as error:
                timeout = isinstance(error, TimeoutError) or "Timeout" in type(error).__name__
                results[name] = {"state": "unknown" if timeout else "failed",
                                 "error_category": "module_no_reply" if timeout else "probe_failed",
                                 "error": str(error), "error_type": type(error).__name__}
                # Stop at the first unanswered probe instead of stacking timeouts.
                break
    builds = {r["reply"]["running_build"] for r in results.values() if r["state"] == "ready"}
    return {"modules": results, "running_hub_build": next(iter(builds)) if len(builds) == 1 else None,
            "build_consistent": len(builds) == 1 if builds else None,
            "all_probed_ready": all(r["state"] == "ready" for r in results.values()) if probe else None,
            "scope": "handler/shared-helper load and Live Set identity only; not write acceptance"}


def error_category(result):
    code = str(result.get("error_code", ""))
    message = str(result.get("error", "")).lower()
    if result.get("applied", False) is None:
        return "write_result_unknown"
    if "stale" in code or "stale" in message:
        return "stale_state"
    if "readback" in message:
        return "readback_failed"
    if "timeout" in code or "Timeout" in str(result.get("error_type", "")):
        return "module_no_reply"
    if "validation" in code:
        return "client_validation_failed"
    if "target_not_found" in code or "not found" in message:
        return "target_not_found"
    if code.startswith("lom_"):
        return "lom_read_failed"
    return "operation_failed"

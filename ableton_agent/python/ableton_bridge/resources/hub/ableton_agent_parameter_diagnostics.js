var AbletonAgentParameterDiagnostics = (function () {
    function now() {
        return Date.now();
    }

    function create(requestId) {
        return {
            request_id: String(requestId || ""),
            started_ms: now(),
            stage: "hub_received",
            operation: null,
            parameter: null,
            property: null,
            stage_timings_ms: {hub_received: 0}
        };
    }

    function mark(state, stage, details) {
        state.stage = stage;
        state.stage_timings_ms[stage] = Math.max(0, now() - state.started_ms);
        if (details) {
            if (details.operation !== undefined) {
                state.operation = details.operation;
            }
            if (details.parameter !== undefined) {
                state.parameter = details.parameter;
            }
            if (details.property !== undefined) {
                state.property = details.property;
            }
        }
        emitProgress(state);
        return state;
    }

    function configure(state, level, emitter, cursor) {
        level = level || "none";
        if (["none", "page", "parameter", "field"].indexOf(level) < 0) {
            throw new Error("trace_level must be none, page, parameter, or field");
        }
        state.trace_level = level;
        state.emitter = emitter;
        state.cursor = cursor;
        state.progress_sequence = 0;
        mark(state, "hub_received");
    }

    function emitProgress(state) {
        if (!state.emitter || !state.trace_level || state.trace_level === "none") { return; }
        var field = state.stage.indexOf("parameter_field_") === 0;
        var parameter = state.stage === "parameter_started" || state.stage === "parameter_completed";
        if (field && state.trace_level !== "field") { return; }
        if (parameter && state.trace_level === "page") { return; }
        state.progress_sequence += 1;
        var checkpoint = {stage: state.stage, operation: state.operation,
            parameter: state.parameter, property: state.property, cursor: state.cursor,
            hub_elapsed_ms: Math.max(0, now() - state.started_ms)};
        // Keep each UDP checkpoint small; failure to emit must not break a read.
        if (checkpoint.parameter && checkpoint.parameter.name) {
            checkpoint.parameter = {id: checkpoint.parameter.id, index: checkpoint.parameter.index,
                name: String(checkpoint.parameter.name).slice(0, 96)};
        }
        try { state.emitter({kind: "progress", request_id: state.request_id,
            sequence: state.progress_sequence, checkpoint: checkpoint}); } catch (_error) {}
    }

    function snapshot(state) {
        return {
            request_id: state.request_id,
            stage: state.stage,
            operation: state.operation,
            parameter: state.parameter,
            property: state.property,
            trace_level: state.trace_level || "none",
            progress_emitted: state.progress_sequence || 0,
            hub_elapsed_ms: Math.max(0, now() - state.started_ms),
            stage_timings_ms: state.stage_timings_ms
        };
    }

    function failure(code, message, state, cause) {
        var error = new Error(message);
        error.diagnostic_code = code;
        error.diagnostic = snapshot(state);
        error.cause_message = cause && cause.message ? cause.message : null;
        return error;
    }

    function classify(state, error) {
        if (error && error.diagnostic_code) {
            return error.diagnostic_code;
        }
        if (state.stage === "payload_validated" || state.stage === "hub_received") {
            return "hub_route_failed";
        }
        if (state.stage === "track_resolving" || state.stage === "device_resolving") {
            return "target_not_found";
        }
        if (state.stage === "parameter_collection_loading") {
            return "lom_collection_read_failed";
        }
        if (state.stage === "collection_token_verifying") {
            return "stale_collection";
        }
        if (state.stage === "page_started" && String(error && error.message || "").indexOf("cursor") >= 0) {
            return "cursor_out_of_range";
        }
        if (state.stage === "parameter_started" || state.stage === "parameter_field_started") {
            return "lom_property_read_failed";
        }
        if (state.stage === "reply_serializing") {
            return "response_serialization_failed";
        }
        return "hub_route_failed";
    }

    function structuredError(state, error) {
        var diagnostic = error && error.diagnostic ? error.diagnostic : snapshot(state);
        return {
            ok: false,
            kind: "final",
            request_id: state.request_id,
            error_code: classify(state, error),
            error_layer: "hub",
            error: error && error.message ? error.message : String(error),
            cause: error && error.cause_message ? error.cause_message : null,
            diagnostics: diagnostic
        };
    }

    function readProperty(api, propertyName, state, operation, parameter) {
        mark(state, "parameter_field_started", {
            operation: operation,
            parameter: parameter,
            property: propertyName
        });
        try {
            var value = api.get(propertyName);
            mark(state, "parameter_field_completed", {
                operation: operation,
                parameter: parameter,
                property: propertyName
            });
            return value;
        } catch (error) {
            throw failure(
                "lom_property_read_failed",
                "LiveAPI parameter property read failed: " + propertyName,
                state,
                error
            );
        }
    }

    function runField(state, operation, parameter, propertyName, callback) {
        mark(state, "parameter_field_started", {
            operation: operation,
            parameter: parameter,
            property: propertyName
        });
        try {
            var value = callback();
            mark(state, "parameter_field_completed", {
                operation: operation,
                parameter: parameter,
                property: propertyName
            });
            return value;
        } catch (error) {
            if (error && error.diagnostic_code) {
                throw error;
            }
            throw failure(
                "lom_property_read_failed",
                "LiveAPI parameter field read failed: " + operation,
                state,
                error
            );
        }
    }

    function tracedApi(api, state, operation, parameter) {
        if (state.trace_level !== "field") { return api; }
        return {
            get: function (property) {
                return readProperty(api, property, state, operation, parameter);
            },
            call: function (method, value) {
                return runField(state, operation, parameter, method, function () {
                    return api.call(method, value);
                });
            }
        };
    }

    return {
        configure: configure,
        tracedApi: tracedApi,
        create: create,
        mark: mark,
        snapshot: snapshot,
        failure: failure,
        structuredError: structuredError,
        readProperty: readProperty,
        runField: runField
    };
})();

if (typeof module !== "undefined" && module.exports) {
    module.exports = AbletonAgentParameterDiagnostics;
}

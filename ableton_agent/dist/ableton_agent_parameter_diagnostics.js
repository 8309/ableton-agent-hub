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
        return state;
    }

    function snapshot(state) {
        return {
            request_id: state.request_id,
            stage: state.stage,
            operation: state.operation,
            parameter: state.parameter,
            property: state.property,
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

    return {
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

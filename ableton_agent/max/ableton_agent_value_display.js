var AbletonAgentValueDisplay = (function () {
    function valueOf(raw, fallback) {
        if (raw instanceof Array) {
            return raw.length ? raw[0] : fallback;
        }
        return raw === undefined || raw === null ? fallback : raw;
    }

    function textForValue(parameter, value) {
        try {
            return String(valueOf(parameter.call("str_for_value", value), ""));
        } catch (_error) {
            return "";
        }
    }

    function currentDisplayNumber(parameter) {
        try {
            var raw = valueOf(parameter.get("display_value"), null);
            var numeric = Number(raw);
            if (raw === null || raw === "" || !isFinite(numeric)) {
                return {available: false, value: null};
            }
            return {available: true, value: numeric};
        } catch (_error) {
            return {available: false, value: null};
        }
    }

    function current(parameter, value) {
        var direct = currentDisplayNumber(parameter);
        var text = textForValue(parameter, value);
        return {
            display_value: text,
            display_text: text,
            display_numeric_value: direct.available ? direct.value : null,
            display_value_source: direct.available ? "lom_display_value" : "str_for_value_fallback"
        };
    }

    function target(parameter, value) {
        var text = textForValue(parameter, value);
        return {
            display_value: text,
            display_text: text,
            display_numeric_value: null,
            display_value_source: "str_for_value_target"
        };
    }

    function attach(result, fields) {
        result.display_value = fields.display_value;
        result.display_text = fields.display_text;
        result.display_numeric_value = fields.display_numeric_value;
        result.display_value_source = fields.display_value_source;
        return result;
    }

    function attachCurrent(result, parameter, value) {
        return attach(result, current(parameter, value));
    }

    function attachTarget(result, parameter, value) {
        return attach(result, target(parameter, value));
    }

    function valuePayload(info) {
        return {
            value: info.value,
            display_value: info.display_value,
            display_text: info.display_text,
            display_numeric_value: info.display_numeric_value,
            display_value_source: info.display_value_source
        };
    }

    return {
        textForValue: textForValue,
        current: current,
        target: target,
        attachCurrent: attachCurrent,
        attachTarget: attachTarget,
        valuePayload: valuePayload
    };
}());

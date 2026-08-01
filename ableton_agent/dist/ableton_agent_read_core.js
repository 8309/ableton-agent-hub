var AbletonAgentReadCore = (function () {
    var DEFAULT_LIMIT = 16;
    var DEFAULT_BUDGET_MS = 1000;
    var MAX_LIMIT = 64;
    var MAX_BUDGET_MS = 5000;

    function integer(value, fallback, minimum, maximum, name) {
        var number = value === undefined || value === null ? fallback : Number(value);
        if (!isFinite(number) || Math.floor(number) !== number || number < minimum || number > maximum) {
            throw new Error(name + " must be an integer from " + minimum + " to " + maximum);
        }
        return number;
    }

    function uniqueProjection(raw, allowed, defaults) {
        var source = raw instanceof Array ? raw : defaults;
        var result = [];
        for (var index = 0; index < source.length; index += 1) {
            var field = String(source[index]);
            if (allowed.indexOf(field) < 0) {
                throw new Error("Unsupported read projection: " + field);
            }
            if (result.indexOf(field) < 0) {
                result.push(field);
            }
        }
        if (!result.length) {
            throw new Error("read.projection must contain at least one supported field");
        }
        return result;
    }

    function parse(payload, options) {
        if (!payload.read || typeof payload.read !== "object") {
            return null;
        }
        var raw = payload.read;
        var maximumLimit = options.max_limit || MAX_LIMIT;
        return {
            cursor: integer(raw.cursor, 0, 0, options.max_cursor || 1000000, "read.cursor"),
            limit: integer(raw.limit, options.default_limit || DEFAULT_LIMIT, 1, maximumLimit, "read.limit"),
            projection: uniqueProjection(raw.projection, options.allowed_projection, options.default_projection),
            budget_ms: integer(raw.budget_ms, options.default_budget_ms || DEFAULT_BUDGET_MS, 1, options.max_budget_ms || MAX_BUDGET_MS, "read.budget_ms"),
            expected_collection_token: raw.expected_collection_token === undefined || raw.expected_collection_token === null
                ? null
                : String(raw.expected_collection_token),
            started_ms: Date.now()
        };
    }

    function collectionToken(ids) {
        var hash = 2166136261;
        var text = ids.join(",");
        for (var index = 0; index < text.length; index += 1) {
            hash ^= text.charCodeAt(index);
            hash += (hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24);
        }
        return "fnv1a-" + (hash >>> 0).toString(16) + "-" + ids.length;
    }

    function verifyCollection(config, token) {
        if (config.expected_collection_token !== null && config.expected_collection_token !== token) {
            throw new Error(
                "stale_collection: expected token " + config.expected_collection_token + " but current token is " + token
            );
        }
    }

    function has(config, field) {
        return config.projection.indexOf(field) >= 0;
    }

    function budgetExceeded(config) {
        return Date.now() - config.started_ms >= config.budget_ms;
    }

    function metadata(config, details) {
        var partial = Boolean(details.partial);
        var hasMore = Boolean(details.has_more);
        return {
            complete: !partial && !hasMore,
            partial: partial,
            cursor: config.cursor,
            next_cursor: details.next_cursor,
            limit: config.limit,
            scanned_count: details.scanned_count,
            returned_count: details.returned_count,
            has_more: hasMore,
            collection_token: details.collection_token,
            elapsed_ms: Math.max(0, Date.now() - config.started_ms),
            warnings: details.warnings || []
        };
    }

    return {
        parse: parse,
        collectionToken: collectionToken,
        verifyCollection: verifyCollection,
        has: has,
        budgetExceeded: budgetExceeded,
        metadata: metadata
    };
})();

if (typeof module !== "undefined" && module.exports) {
    module.exports = AbletonAgentReadCore;
}

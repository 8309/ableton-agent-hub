var AbletonAgentDeviceTree = (function () {
    function valueOf(raw, fallback) {
        if (raw instanceof Array) {
            return raw.length ? raw[0] : fallback;
        }
        return raw === undefined || raw === null ? fallback : raw;
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

    function integer(value, fallback, minimum, maximum, name) {
        var number = value === undefined || value === null ? fallback : Number(value);
        if (!isFinite(number) || Math.floor(number) !== number || number < minimum || number > maximum) {
            throw new Error(name + " must be an integer from " + minimum + " to " + maximum);
        }
        return number;
    }

    function options(raw) {
        raw = raw || {};
        return {
            max_depth: integer(raw.max_depth, 6, 0, 12, "max_depth"),
            max_devices: integer(raw.max_devices, 128, 1, 512, "max_devices"),
            budget_ms: raw.budget_ms === undefined || raw.budget_ms === null
                ? null
                : integer(raw.budget_ms, null, 1, 5000, "budget_ms")
        };
    }

    function elapsedMs(state) {
        return new Date().getTime() - state.started_at;
    }

    function addReason(state, reason) {
        state.truncated = true;
        if (state.truncation_reasons.indexOf(reason) < 0) {
            state.truncation_reasons.push(reason);
        }
    }

    function budgetExceeded(state) {
        return state.options.budget_ms !== null && elapsedMs(state) >= state.options.budget_ms;
    }

    function copyRecord(record) {
        var result = {};
        for (var key in record) {
            if (record.hasOwnProperty(key)) {
                result[key] = record[key];
            }
        }
        return result;
    }

    function chainRecords(device, deviceId, parentPath) {
        var result = [];
        var kinds = [
            {property: "chains", kind: "chain"},
            {property: "return_chains", kind: "return_chain"}
        ];
        for (var kindIndex = 0; kindIndex < kinds.length; kindIndex += 1) {
            var spec = kinds[kindIndex];
            var chainIds = idsFrom(safeGet(device, spec.property, []));
            for (var chainIndex = 0; chainIndex < chainIds.length; chainIndex += 1) {
                var chain = new LiveAPI(function () {}, "id " + chainIds[chainIndex]);
                result.push({
                    id: chainIds[chainIndex],
                    api: chain,
                    name: String(valueOf(safeGet(chain, "name", ""), "")),
                    kind: spec.kind,
                    index: chainIndex,
                    rack_device_id: deviceId,
                    path: parentPath.concat([{
                        rack_device_id: deviceId,
                        chain_id: chainIds[chainIndex],
                        chain_index: chainIndex,
                        chain_kind: spec.kind,
                        chain_name: String(valueOf(safeGet(chain, "name", ""), ""))
                    }])
                });
            }
        }
        return result;
    }

    function deviceRecord(deviceId, device, deviceIndex, depth, parentChain, path) {
        var canHaveChains = Boolean(Number(valueOf(safeGet(device, "can_have_chains", 0), 0)));
        return {
            device_id: deviceId,
            device_index: deviceIndex,
            name: String(valueOf(safeGet(device, "name", ""), "")),
            class_name: String(valueOf(safeGet(device, "class_name", ""), "")),
            class_display_name: String(valueOf(safeGet(device, "class_display_name", ""), "")),
            type: Number(valueOf(safeGet(device, "type", 0), 0)),
            depth: depth,
            parent_chain_id: parentChain ? parentChain.id : null,
            parent_chain_name: parentChain ? parentChain.name : null,
            parent_rack_device_id: parentChain ? parentChain.rack_device_id : null,
            chain_path: path,
            can_have_chains: canHaveChains,
            has_macro_mappings: canHaveChains
                ? Boolean(Number(valueOf(safeGet(device, "has_macro_mappings", 0), 0)))
                : false,
            parameter_count: idsFrom(safeGet(device, "parameters", [])).length
        };
    }

    function walkDeviceIds(deviceIds, depth, parentChain, path, state) {
        for (var index = 0; index < deviceIds.length; index += 1) {
            if (state.records.length >= state.options.max_devices) {
                addReason(state, "max_devices");
                return;
            }
            if (budgetExceeded(state)) {
                addReason(state, "budget_ms");
                return;
            }
            var deviceId = deviceIds[index];
            if (state.seen[String(deviceId)]) {
                continue;
            }
            state.seen[String(deviceId)] = true;
            var device = new LiveAPI(function () {}, "id " + deviceId);
            var record = deviceRecord(deviceId, device, index, depth, parentChain, path);
            record.relative_depth = depth;
            record.absolute_depth = state.absolute_depth_offset + depth;
            state.records.push(record);
            if (!record.can_have_chains || depth >= state.options.max_depth) {
                if (record.can_have_chains && depth >= state.options.max_depth) {
                    addReason(state, "max_depth");
                }
                continue;
            }
            var chains = chainRecords(device, deviceId, path);
            for (var chainIndex = 0; chainIndex < chains.length; chainIndex += 1) {
                var chain = chains[chainIndex];
                walkDeviceIds(
                    idsFrom(safeGet(chain.api, "devices", [])),
                    depth + 1,
                    chain,
                    chain.path,
                    state
                );
                if (state.truncated && (
                    state.truncation_reasons.indexOf("max_devices") >= 0 ||
                    state.truncation_reasons.indexOf("budget_ms") >= 0
                )) {
                    return;
                }
            }
        }
    }

    function scanTrack(track, rawOptions) {
        var state = {
            options: options(rawOptions),
            records: [],
            seen: {},
            truncated: false,
            truncation_reasons: [],
            started_at: new Date().getTime(),
            absolute_depth_offset: 0
        };
        walkDeviceIds(idsFrom(safeGet(track, "devices", [])), 0, null, [], state);
        return {
            devices: state.records,
            device_count: state.records.length,
            truncated: state.truncated,
            truncation_reasons: state.truncation_reasons,
            max_depth: state.options.max_depth,
            max_devices: state.options.max_devices,
            budget_ms: state.options.budget_ms,
            elapsed_ms: elapsedMs(state),
            root_device_id: null,
            selectable_child_rack_ids: childRackIds(state.records, null)
        };
    }

    function childRackIds(records, rootDeviceId) {
        var result = [];
        for (var index = 0; index < records.length; index += 1) {
            if (records[index].can_have_chains && records[index].device_id !== rootDeviceId) {
                result.push(records[index].device_id);
            }
        }
        return result;
    }

    function scanSubtree(track, rootDeviceId, rawOptions) {
        var found = findDevice(track, rootDeviceId, {max_depth: 12, max_devices: 512});
        if (!found.record.can_have_chains) {
            throw new Error("root_device_id must identify a Rack-capable device");
        }
        var state = {
            options: options(rawOptions),
            records: [],
            seen: {},
            truncated: false,
            truncation_reasons: [],
            started_at: new Date().getTime(),
            absolute_depth_offset: found.record.depth
        };
        var rootRecord = copyRecord(found.record);
        rootRecord.depth = 0;
        rootRecord.relative_depth = 0;
        rootRecord.absolute_depth = found.record.depth;
        state.records.push(rootRecord);
        state.seen[String(found.id)] = true;

        if (state.options.max_depth === 0) {
            addReason(state, "max_depth");
        } else if (!budgetExceeded(state)) {
            var chains = chainRecords(found.api, found.id, found.record.chain_path);
            for (var chainIndex = 0; chainIndex < chains.length; chainIndex += 1) {
                var chain = chains[chainIndex];
                walkDeviceIds(
                    idsFrom(safeGet(chain.api, "devices", [])),
                    1,
                    chain,
                    chain.path,
                    state
                );
                if (state.truncated && (
                    state.truncation_reasons.indexOf("max_devices") >= 0 ||
                    state.truncation_reasons.indexOf("budget_ms") >= 0
                )) {
                    break;
                }
            }
        } else {
            addReason(state, "budget_ms");
        }

        return {
            devices: state.records,
            device_count: state.records.length,
            truncated: state.truncated,
            truncation_reasons: state.truncation_reasons,
            max_depth: state.options.max_depth,
            max_devices: state.options.max_devices,
            budget_ms: state.options.budget_ms,
            elapsed_ms: elapsedMs(state),
            root_device_id: found.id,
            root_device_name: rootRecord.name,
            root_absolute_depth: found.record.depth,
            root_chain_path: found.record.chain_path,
            selectable_child_rack_ids: childRackIds(state.records, found.id)
        };
    }

    function findInDeviceIds(deviceIds, depth, parentChain, path, state, wanted) {
        var level = [];
        for (var index = 0; index < deviceIds.length; index += 1) {
            if (state.visited >= state.options.max_devices) {
                state.truncated = true;
                return null;
            }
            var deviceId = deviceIds[index];
            if (state.seen[String(deviceId)]) {
                continue;
            }
            state.seen[String(deviceId)] = true;
            state.visited += 1;
            var device = new LiveAPI(function () {}, "id " + deviceId);
            var record = deviceRecord(deviceId, device, index, depth, parentChain, path);
            if (deviceId === wanted) {
                return {id: deviceId, api: device, record: record};
            }
            level.push({id: deviceId, api: device, record: record});
        }

        for (var levelIndex = 0; levelIndex < level.length; levelIndex += 1) {
            var entry = level[levelIndex];
            if (!entry.record.can_have_chains) {
                continue;
            }
            if (depth >= state.options.max_depth) {
                state.truncated = true;
                continue;
            }
            var chains = chainRecords(entry.api, entry.id, path);
            for (var chainIndex = 0; chainIndex < chains.length; chainIndex += 1) {
                var chain = chains[chainIndex];
                var found = findInDeviceIds(
                    idsFrom(safeGet(chain.api, "devices", [])),
                    depth + 1,
                    chain,
                    chain.path,
                    state,
                    wanted
                );
                if (found) {
                    return found;
                }
                if (state.visited >= state.options.max_devices) {
                    state.truncated = true;
                    return null;
                }
            }
        }
        return null;
    }

    function findDevice(track, deviceId, rawOptions) {
        var wanted = Number(deviceId);
        if (!isFinite(wanted) || wanted <= 0 || Math.floor(wanted) !== wanted) {
            throw new Error("device_id must be a positive integer");
        }
        var state = {
            options: options(rawOptions),
            seen: {},
            visited: 0,
            truncated: false
        };
        var found = findInDeviceIds(
            idsFrom(safeGet(track, "devices", [])),
            0,
            null,
            [],
            state,
            wanted
        );
        if (found) {
            return found;
        }
        if (state.truncated) {
            throw new Error("device_id was not found before the recursive device scan limit");
        }
        throw new Error("device_id is not in the target track device tree");
    }

    // Page one container, not a truncated depth-first prefix. Rack IDs identify
    // the next containers; ordered collection tokens reject changed siblings.
    function scanChildren(track, payload) {
        var read = AbletonAgentReadCore.parse({read: {
            cursor: payload.cursor === undefined ? 0 : payload.cursor,
            limit: payload.limit === undefined ? 4 : payload.limit,
            budget_ms: payload.budget_ms === undefined ? 1000 : payload.budget_ms,
            expected_collection_token: payload.expected_collection_token,
            projection: ["identity"]
        }}, {max_limit: 32, max_cursor: 65536, default_limit: 4,
            allowed_projection: ["identity"], default_projection: ["identity"]});
        var entries = [];
        var signature = [Number(track.id)];
        var rootId = payload.root_device_id;
        var containers = [{api: track, chain: null, path: []}];
        if (rootId !== undefined && rootId !== null) {
            var found = findDevice(track, rootId, {max_depth: 12, max_devices: 512});
            if (!found.record.can_have_chains) { throw new Error("root_device_id must identify a Rack-capable device"); }
            signature.push(Number(rootId));
            containers = [];
            var kinds = ["chains", "return_chains"];
            for (var k = 0; k < kinds.length; k += 1) {
                var chainIds = idsFrom(found.api.get(kinds[k]));
                signature.push(k, chainIds.length);
                for (var c = 0; c < chainIds.length; c += 1) {
                    signature.push(chainIds[c]);
                    var chain = {id: chainIds[c], name: null, rack_device_id: Number(rootId)};
                    var path = found.record.chain_path.concat([{rack_device_id: Number(rootId),
                        chain_id: chainIds[c], chain_index: c, chain_kind: kinds[k]}]);
                    containers.push({api: new LiveAPI(function () {}, "id " + chainIds[c]), chain: chain, path: path});
                }
            }
        }
        for (var ci = 0; ci < containers.length; ci += 1) {
            var container = containers[ci];
            var ids = idsFrom(container.api.get("devices"));
            signature.push(ids.length);
            signature = signature.concat(ids);
            for (var i = 0; i < ids.length; i += 1) {
                entries.push({id: ids[i], index: i, chain: container.chain, path: container.path});
            }
        }
        var token = AbletonAgentReadCore.collectionToken(signature);
        AbletonAgentReadCore.verifyCollection(read, token);
        if (read.cursor > entries.length) { throw new Error("cursor outside device collection"); }
        var records = [];
        while (read.cursor + records.length < entries.length && records.length < read.limit) {
            if (records.length && AbletonAgentReadCore.budgetExceeded(read)) { break; }
            var entry = entries[read.cursor + records.length];
            var api = new LiveAPI(function () {}, "id " + entry.id);
            // Discovery does not read parameter collections or format values.
            records.push({device_id: entry.id, device_index: entry.index,
                name: String(valueOf(api.get("name"), "")),
                can_have_chains: Boolean(Number(valueOf(api.get("can_have_chains"), 0))),
                parent_chain_id: entry.chain ? entry.chain.id : null,
                parent_rack_device_id: entry.chain ? entry.chain.rack_device_id : null,
                chain_path: entry.path});
        }
        var next = read.cursor + records.length;
        var more = next < entries.length;
        return {devices: records, device_count: records.length, container_device_count: entries.length,
            root_device_id: rootId === undefined ? null : rootId,
            selectable_child_rack_ids: childRackIds(records, null),
            scope: "direct_children", read: AbletonAgentReadCore.metadata(read, {
                next_cursor: next, scanned_count: records.length, returned_count: records.length,
                has_more: more, partial: more && records.length < read.limit,
                collection_token: token, warnings: []})};
    }

    return {
        scanChildren: scanChildren,
        idsFrom: idsFrom,
        safeGet: safeGet,
        scanTrack: scanTrack,
        scanSubtree: scanSubtree,
        findDevice: findDevice
    };
}());

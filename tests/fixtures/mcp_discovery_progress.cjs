const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');
const root = path.resolve(__dirname, '../../ableton_agent/max');
const sandbox = vm.createContext({assert, console});
sandbox.include = name => vm.runInContext(fs.readFileSync(path.join(root, name), 'utf8'), sandbox);
vm.runInContext(`
var packets = [], calls = [], failProperty = null;
var registry = {
  1: {tracks: ['id', 10], return_tracks: ['id', 20], master_track: ['id', 30]},
  10: {name: 'Track', devices: ['id', 100]},
  20: {name: 'A Return', devices: ['id', 200, 'id', 201, 'id', 202, 'id', 203, 'id', 204]},
  30: {name: 'Main', devices: ['id', 300]},
  100: {name: 'Rack', can_have_chains: 1, chains: ['id', 400], return_chains: ['id', 401]},
  200: {name: 'Reverb', can_have_chains: 0, parameters: ['id', 500]},
  201: {name: 'Delay', can_have_chains: 0},
  202: {name: 'EQ', can_have_chains: 0},
  203: {name: 'Utility', can_have_chains: 0},
  204: {name: 'Last', can_have_chains: 0},
  300: {name: 'Limiter', can_have_chains: 0},
  400: {name: 'Chain', devices: ['id', 201]},
  401: {name: 'Return chain', devices: ['id', 203]},
  500: {name: 'Device On', value: 1, min: 0, max: 1, is_quantized: 1, is_enabled: 1, automation_state: 0, display_value: 1}
};
function LiveAPI(callback, path) {
  this.id = path === 'live_set' ? 1 : Number(path.split(' ')[1]);
  if (!registry[this.id]) throw new Error('missing id ' + this.id);
}
LiveAPI.prototype.get = function(property) {
  calls.push([this.id, property]);
  if (property === failProperty) throw new Error('simulated property failure');
  if (/routing|mute/.test(property)) throw new Error('forbidden special-track getter');
  if (property === 'name' && this.id === 500 && expectProgress) {
    assert(packets.some(p => p.outlet === 1 && p.value.checkpoint.property === 'name'));
  }
  return registry[this.id][property] === undefined ? [] : registry[this.id][property];
};
LiveAPI.prototype.call = function(method, value) {
  if (method !== 'str_for_value') throw new Error('unexpected call');
  return value ? 'On' : 'Off';
};
LiveAPI.prototype.set = function() { throw new Error('read-only test attempted write'); };
function outlet(index, args) { packets.push({outlet: index, id: args[0], value: JSON.parse(args[1])}); }
var expectProgress = false;
`, sandbox);
sandbox.include('ableton_agent_device_chain.js');
vm.runInContext(`
function scan(payload) {
  packets = [];
  handleDeviceChain('scan', JSON.stringify(payload), 'dry_run');
  return packets[packets.length - 1].value;
}
for (var section of ['return', 'main', 'master', 'track']) {
  var id = section === 'return' ? 20 : section === 'track' ? 10 : 30;
  var result = scan({action:'scan_children', section:section, track_id:id});
  assert.equal(result.ok, true);
  assert.equal(result.tree.track_id, id);
}
assert.equal(scan({action:'scan_children', section:'return', track_id:10}).ok, false);
var page = scan({action:'scan_children', section:'return', track_id:20, limit:4}).tree;
assert.equal(page.read.next_cursor, 4);
var next = scan({action:'scan_children', section:'return', track_id:20, limit:4, cursor:4,
  expected_collection_token:page.read.collection_token}).tree;
assert.deepEqual(page.devices.concat(next.devices).map(d => d.device_id), [200,201,202,203,204]);
assert.equal(next.read.complete, true);
registry[20].devices.push('id', 300);
assert.equal(scan({action:'scan_children', section:'return', track_id:20, cursor:4,
  expected_collection_token:page.read.collection_token}).ok, false);
var nested = scan({action:'scan_children', track_id:10, root_device_id:100, limit:1}).tree;
assert.equal(nested.devices[0].parent_chain_id, 400);
var nested2 = scan({action:'scan_children', track_id:10, root_device_id:100, limit:1,
  cursor:1, expected_collection_token:nested.read.collection_token}).tree;
assert.equal(nested2.devices[0].parent_chain_id, 401);
assert.equal(scan({action:'scan_children', section:'return', track_id:20, cursor:50}).ok, false);
assert.equal(scan({action:'scan_children', track_id:10, limit:0}).ok, false);
var saved = registry[20].devices;
registry[20].devices = [];
for (var n=0; n<70; n++) {
  registry[20].devices.push('id', 1000+n);
  registry[1000+n]={name:'Device '+n,can_have_chains:0};
}
var collected=[], cursor=0, token=null;
do {
  var many=scan({action:'scan_children',section:'return',track_id:20,cursor:cursor,
    limit:4,expected_collection_token:token}).tree;
  collected=collected.concat(many.devices.map(d=>d.device_id));
  cursor=many.read.next_cursor; token=many.read.collection_token;
} while (many.read.has_more);
assert.equal(collected.length,70);
assert.equal(new Set(collected).size,70);
var realNow=Date.now, tick=0;
Date.now=function(){return ++tick;};
var partial=scan({action:'scan_children',section:'return',track_id:20,limit:4,budget_ms:1}).tree;
Date.now=realNow;
assert.equal(partial.read.partial,true);
assert.equal(partial.read.next_cursor,1);
registry[20].devices=saved;
packets=[];
handleDeviceChain('write', JSON.stringify({action:'apply_template', section:'return', track_id:20}), 'commit');
assert.equal(packets[0].value.ok, false);
`, sandbox);
sandbox.include('ableton_agent_parameter_summary.js');
vm.runInContext(`
for (var level of ['none', 'page', 'parameter', 'field']) {
  packets = []; expectProgress = level === 'field';
  readParameterSummary('read-' + level, JSON.stringify({action:'list_parameters', section:'return',
    track_id:20, device_id:200, trace_level:level,
    read:{cursor:0,limit:4,projection:['identity','internal_value','metadata','display_value','enum_values']}}), 'dry_run');
  expectProgress = false;
  var finals = packets.filter(p => p.outlet === 0);
  assert.equal(finals.length, 1);
  assert.equal(finals[0].value.ok, true, JSON.stringify(finals[0]));
  assert.equal(finals[0].value.parameters[0].display_text, 'On');
  var progress = packets.filter(p => p.outlet === 1);
  assert.equal(progress.length > 0, level !== 'none');
  if (level === 'page') assert(!progress.some(p => /^parameter_(started|completed|field)/.test(p.value.checkpoint.stage)));
  if (level === 'parameter') {
    assert(progress.some(p => p.value.checkpoint.stage === 'parameter_started'));
    assert(!progress.some(p => p.value.checkpoint.stage === 'parameter_field_started'));
  }
  if (level === 'field') {
    assert(progress.some(p => p.value.checkpoint.property === 'display_value'));
    assert(progress.some(p => p.value.checkpoint.property === 'str_for_value'));
  }
  assert(progress.every(p => p.id === 'read-' + level && p.value.request_id === p.id && p.value.kind === 'progress'));
}
packets = []; failProperty = 'value';
readParameterSummary('fail', JSON.stringify({action:'list_parameters', section:'return', track_id:20,
  device_id:200, trace_level:'field', read:{cursor:0,limit:1,projection:['internal_value']}}), 'dry_run');
var failed = packets.filter(p => p.outlet === 0)[0].value;
assert.equal(failed.error_code, 'lom_property_read_failed');
assert.equal(failed.diagnostics.parameter.id, 500);
assert.equal(failed.diagnostics.property, 'value');
failProperty = null;
calls=[]; packets=[];
readParameterSummary('metadata-cost', JSON.stringify({action:'list_parameters', section:'return', track_id:20,
  device_id:200, read:{cursor:0,limit:4,projection:['identity','metadata']}}), 'dry_run');
assert.equal(calls.filter(c=>c[0]===500).length, 6);
calls=[]; packets=[];
readParameterSummary('automation-only', JSON.stringify({action:'list_parameters', section:'return', track_id:20,
  device_id:200, read:{cursor:0,limit:4,projection:['identity','automation_state']}}), 'dry_run');
assert.equal(packets[0].value.ok, true);
assert.equal(packets[0].value.items[0].automation_state, 0);
assert.deepEqual(calls.filter(c=>c[0]===500).map(c=>c[1]), ['name','automation_state']);
assert(!('min' in packets[0].value.items[0]));
assert(!('value' in packets[0].value.items[0]));
assert(!('display_text' in packets[0].value.items[0]));
delete registry[500].automation_state; packets=[];
readParameterSummary('missing-state', JSON.stringify({action:'list_parameters', section:'return', track_id:20,
  device_id:200, read:{cursor:0,limit:4,projection:['identity','automation_state']}}), 'dry_run');
assert.equal(packets[0].value.ok, false);
registry[500].automation_state=0;
registry[200].parameters=[];
for (var i=0;i<513;i++) registry[200].parameters.push('id',500);
packets=[];
readParameterSummary('capped', JSON.stringify({action:'list_parameters', section:'return', track_id:20,
  device_id:200, read:{cursor:0,limit:4,projection:['identity','automation_state']}}), 'dry_run');
assert(packets[0].value.read.warnings.length>0);
registry[200].parameters=['id',500];
packets=[];
readParameterSummary('legacy', JSON.stringify({action:'list_parameters', section:'return', track_id:20, device_id:200}), 'dry_run');
assert.equal(packets.filter(p => p.outlet === 1).length, 0);
assert.equal(packets[0].value.ok, true);
`, sandbox);
sandbox.include('ableton_agent_track_management.js');
vm.runInContext(`
calls=[];
var a=lookupRevision();
assert.equal(a,lookupRevision());
assert(calls.every(c => ['tracks','return_tracks','master_track'].includes(c[1])));
registry[1].tracks.push('id', 40);
assert.notEqual(a,lookupRevision());
`, sandbox);
console.log('Max mocks: sections, pages, stale tokens, trace levels, field failure, legacy and revision OK');

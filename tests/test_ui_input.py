import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch

from ableton_bridge.ui_input import validate_value_input
from ableton_bridge.mcp_tools import AbletonMcpService, McpOperations
from ableton_bridge.mcp_server import MixChange, ParameterChange


class UiInputTests(unittest.TestCase):
    def test_cli_and_wire_payload(self):
        from ableton_bridge import mixer_control, multi_parameter_control
        for module, literal in ((mixer_control, "1|pan|ui:10R"), (multi_parameter_control, "1|EQ Eight|2 Freq A|ui:350 Hz")):
            change = module.parse_change(literal)
            self.assertIn("ui_value", change)
            self.assertNotIn("value", change)
            with patch.object(module, "encode_message", side_effect=RuntimeError("capture before UDP")) as encoder:
                setter = module.set_mix if module is mixer_control else module.set_parameters
                with self.assertRaisesRegex(RuntimeError, "capture before UDP"):
                    setter([change])
                payload = json.loads(encoder.call_args.args[1][1])
                self.assertEqual(payload["changes"], [change])

    def test_exclusive_and_numeric_compatibility(self):
        for value in ({"value": 0}, {"ui_value": "-6 dB"}):
            validate_value_input(value)
        for value in ({}, {"value": 0, "ui_value": "C"}, {"ui_value": ""}, {"ui_value": 3}, {"value": float("nan")}):
            with self.assertRaises(ValueError):
                validate_value_input(value)
        self.assertEqual(MixChange(track_id=1, field="pan", ui_value="10R").model_dump(exclude_none=True)["ui_value"], "10R")
        with self.assertRaises(ValueError):
            ParameterChange(track_id=1, device_id=2, parameter_id=3, value=1, ui_value="On")

    def test_batch_forwards_ui_without_conversion_or_extra_requests(self):
        mix, params = Mock(return_value={"ok": True}), Mock(return_value={"ok": True})
        service = AbletonMcpService(operations=McpOperations(set_mix=mix, set_parameters=params))
        a = [{"track_id": 1, "field": "pan", "ui_value": "10R"}]
        b = [{"track_id": 1, "device_id": 2, "parameter_id": 3, "ui_value": "350 Hz"}]
        result = service.apply_batch(mix_changes=a, parameter_changes=b)
        self.assertTrue(result["ok"])
        self.assertEqual(mix.call_args.args[0], a)
        self.assertEqual(params.call_args.args[0], b)
        self.assertEqual(mix.call_count, 1)
        self.assertEqual(params.call_count, 1)

    def test_max_adapters_never_write_during_conversion(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        root = Path(__file__).resolve().parents[1]
        path = root / "ableton_agent/max/ableton_agent_ui_input.js"
        program = """
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const c={};vm.createContext(c);vm.runInContext(fs.readFileSync(PATH,'utf8'),c);
vm.runInContext(`
function api(fn,labels){return {call:function(op,v){if(op!=='str_for_value')throw Error('unexpected');return fn(v);},get:function(){return labels;},set:function(){throw Error('conversion wrote state');}};}
function cv(s,a,info,ctx){return AgentUiInput.resolve({ui_value:s},a,info,ctx);}
var pan=api(function(v){return v===0?'C':Math.round(Math.abs(v)*50)+(v<0?'L':'R');});
if(cv('10R',pan,{min:-1,max:1},{field:'pan'})!==0.2)throw Error('pan');
if(cv('50L',pan,{min:-1,max:1},{field:'pan'})!==-1)throw Error('pan endpoint');
var vol=api(function(v){return v===0?'-inf dB':(20*Math.log(v)/Math.LN10).toFixed(2)+' dB';});
var v=cv('-6 dB',vol,{min:0,max:1},{field:'volume'});
if(Math.abs(20*Math.log(v)/Math.LN10+6)>0.006)throw Error('volume');
if(cv('-inf dB',vol,{min:0,max:1},{field:'volume'})!==0)throw Error('mute');
var hz=api(function(v){return (10*Math.pow(2200,v)).toFixed(1)+' Hz';});
if(Math.abs(cv('350 Hz',hz,{min:0,max:1,name:'2 Freq A'},{device_class:'Eq8'})-Math.log(35)/Math.log(2200))>1e-9)throw Error('hz');
if(Math.abs(cv('350 Hz',hz,{min:0,max:1,name:'2 Frequency A'},{device_class:'Eq8'})-Math.log(35)/Math.log(2200))>1e-9)throw Error('live frequency name');
var gain=api(function(v){return v.toFixed(2)+' dB';});
if(cv('-6 dB',gain,{min:-15,max:15,name:'2 Gain A'},{device_class:'Eq8'})!==-6)throw Error('gain');
var q=api(function(v){return v.toFixed(2);});
if(cv('0.71 Q',q,{min:0.1,max:18,name:'2 Q A'},{device_class:'Eq8'})!==0.71)throw Error('Q');
var e=api(function(v){return ['Off','On'][v];},['Off','On']);
if(cv('On',e,{min:0,max:1,is_quantized:true},{})!==1)throw Error('enum');
var rejected=0;
var invalid=[function(){cv('51R',pan,{min:-1,max:1},{field:'pan'});},function(){cv('350 dB',hz,{min:0,max:1,name:'2 Freq A'},{device_class:'Eq8'});},function(){cv('2 dB',gain,{min:0,max:1,name:'Mystery'},{device_class:'Other'});},function(){cv('On',api(function(){return 'On';},['On','On']),{min:0,max:1,is_quantized:true},{});},function(){cv('16 dB',gain,{min:-15,max:15,name:'2 Gain A'},{device_class:'Eq8'});}];
invalid.forEach(function(f){try{f();}catch(e){rejected++;}});
if(rejected!==invalid.length)throw Error('invalid accepted');
if(AgentUiInput.resolve({value:0.123},null,{}, {})!==0.123)throw Error('legacy');
`,c);
""".replace("PATH", json.dumps(str(path)))
        subprocess.run([node, "-e", program], check=True, capture_output=True, text=True)

    def test_builder_and_handlers_include_helper(self):
        root = Path(__file__).resolve().parents[1] / "ableton_agent"
        self.assertIn('"ableton_agent_ui_input.js"', (root / "build_hub_device.py").read_text())
        for module in ("mixer_control", "multi_parameter_control"):
            source = (root / "max" / ("ableton_agent_" + module + ".js")).read_text()
            self.assertIn('include("ableton_agent_ui_input.js")', source)
            self.assertIn("AgentUiInput.resolve", source)
            self.assertIn("requested_ui_value", source)

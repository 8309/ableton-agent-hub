import json
from pathlib import Path
import shutil
import subprocess
import unittest

from ableton_bridge.module_health import MODULES, module_status, error_category
from ableton_bridge.mcp_tools import AbletonMcpService, McpOperations


class ModuleHealthTests(unittest.TestCase):
    def test_default_does_not_probe(self):
        def forbidden(*args, **kwargs):
            self.fail("unexpected module probe")
        result = module_status(forbidden, {})
        self.assertIsNone(result["running_hub_build"])
        self.assertTrue(all(x["state"] == "unknown" for x in result["modules"].values()))

    def test_sequential_probe_and_mixed_builds(self):
        called = []
        def request(route, payload, **kwargs):
            self.assertFalse(kwargs["commit"])
            self.assertEqual(payload, {"action": "_module_health"})
            called.append(route)
            return {"ok": True, "health_protocol": 1, "read_only": True, "dry_run": True,
                    "module": next(k for k, v in MODULES.items() if v == route),
                    "running_build": "one" if len(called) < 3 else "two"}
        result = module_status(request, {}, probe=True)
        self.assertEqual(called, list(MODULES.values()))
        self.assertTrue(result["all_probed_ready"])
        self.assertFalse(result["build_consistent"])
        self.assertIsNone(result["running_hub_build"])

    def test_timeout_stops_and_does_not_claim_missing_file(self):
        calls = []
        def request(*args, **kwargs):
            calls.append(args)
            raise TimeoutError("no reply")
        result = module_status(request, {}, probe=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["modules"]["tracks"]["error_category"], "module_no_reply")
        self.assertEqual(result["modules"]["parameters"]["state"], "unknown")

    def test_old_protocol_not_ready(self):
        result = module_status(lambda *a, **k: {"ok": True}, {}, probe=True)
        self.assertFalse(result["all_probed_ready"])

    def test_handler_probes_precede_business_actions(self):
        root = Path(__file__).resolve().parents[1] / "ableton_agent/max"
        for module in ("track_management", "parameter_summary", "clip_writer", "inserter"):
            text = (root / ("ableton_agent_" + module + ".js")).read_text(encoding="utf-8")
            self.assertIn('include("ableton_agent_health.js")', text)
            self.assertIn('payload.action === "_module_health"', text)
            self.assertIn('AgentHealth.reply(requestId,', text)

    def test_error_categories(self):
        for fields, category in [({"applied": None}, "write_result_unknown"),
                                 ({"error_code": "stale_collection"}, "stale_state"),
                                 ({"error": "readback mismatch"}, "readback_failed"),
                                 ({"error_code": "client_validation_failed"}, "client_validation_failed"),
                                 ({"error_code": "target_not_found"}, "target_not_found"),
                                 ({"error_code": "lom_property_read_failed"}, "lom_read_failed")]:
            self.assertEqual(error_category(fields), category)

    def test_service_exposes_build_and_unknown_modules(self):
        service = AbletonMcpService(operations=McpOperations(ping=lambda **k: {"request_id": "p"}))
        result = service.status()
        self.assertTrue(result["ok"])
        self.assertRegex(result["mcp_build"], r"^dev-[0-9a-f]{12}$")
        self.assertIsNone(result["health"]["all_probed_ready"])

    def test_max_health_never_calls_mutation(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node runtime unavailable")
        path = Path(__file__).resolve().parents[1] / "ableton_agent/max/ableton_agent_health.js"
        program = """
const vm=require('vm'),fs=require('fs'),assert=require('assert');
let replies=[],reads=0;
let context={LiveAPI:function(){reads++;this.id=1;},outlet:(n,args)=>replies.push(JSON.parse(args[1]))};
vm.createContext(context);vm.runInContext(fs.readFileSync(PATH,'utf8'),context);
context.AgentHealth.reply('r','tracks','dry_run');
assert.equal(replies[0].request_id,'r');assert.equal(replies[0].ok,true);assert.equal(reads,1);
context.AgentHealth.reply('w','tracks','commit');
assert.equal(replies[1].ok,false);assert.equal(reads,1);
context.LiveAPI=function(){throw Error('unavailable');};
context.AgentHealth.reply('f','tracks','dry_run');
assert.equal(replies[2].error_code,'lom_read_failed');
""".replace("PATH", json.dumps(str(path)))
        subprocess.run([node, "-e", program], check=True, capture_output=True, text=True)

    def test_inserter_health_preserves_reply_selector(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node runtime unavailable")
        root = Path(__file__).resolve().parents[1] / "ableton_agent/max"
        program = """
const vm=require('vm'),fs=require('fs'),assert=require('assert');
let packets=[],reads=0;
let context={LiveAPI:function(){reads++;this.id=1;},outlet:(n,args)=>packets.push(args),include:()=>{}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(ROOT+'/ableton_agent_health.js','utf8'),context);
vm.runInContext(fs.readFileSync(ROOT+'/ableton_agent_inserter.js','utf8'),context);
context.insertEffect('probe',JSON.stringify({action:'_module_health'}),'dry_run');
assert.equal(packets.length,1);assert.equal(packets[0][0],'insert_effect');
assert.equal(packets[0][1],'probe');assert.equal(reads,1);
let result=JSON.parse(packets[0][2]);assert.equal(result.ok,true);assert.equal(result.module,'insertion');
context.insertEffect('reject',JSON.stringify({action:'_module_health'}),'commit');
assert.equal(packets[1][0],'insert_effect');assert.equal(packets[1][1],'reject');
assert.equal(JSON.parse(packets[1][2]).ok,false);assert.equal(reads,1);
""".replace("ROOT", json.dumps(str(root)))
        subprocess.run([node, "-e", program], check=True, capture_output=True, text=True)

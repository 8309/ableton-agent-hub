import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ableton_agent"))
from build_hub_device import build_hub_amxd
from amxd_container import extract_patch_json


class StatusPanelTests(unittest.TestCase):
    def test_build_taps_preserve_routes_and_fit_presentation(self):
        with tempfile.TemporaryDirectory() as folder:
            patch = extract_patch_json(build_hub_amxd(Path(folder) / "Hub.amxd"))["patcher"]
        original = json.loads((ROOT / "ableton_agent/max/agent_hub.maxpat.json").read_text())["patcher"]
        route = lambda p: next(x["box"]["text"] for x in p["boxes"] if x["box"]["id"] == "obj-route")
        self.assertEqual(route(original), route(patch))
        edges = lambda p: {(tuple(x["patchline"]["source"]), tuple(x["patchline"]["destination"])) for x in p["lines"]}
        self.assertTrue(edges(original).issubset(edges(patch)))
        self.assertIn((("obj-udp-receive", 0), ("obj-status-panel", 0)), edges(patch))
        for item in patch["boxes"]:
            box = item["box"]
            if box.get("presentation"):
                x, y, w, h = box["presentation_rect"]
                self.assertLessEqual(x + w, 620)
                self.assertLessEqual(y + h, 148)
        rects = sorted(x["box"]["presentation_rect"] for x in patch["boxes"] if x["box"].get("presentation"))
        for previous, following in zip(rects, rects[1:]):
            self.assertLessEqual(previous[1] + previous[3], following[1])

    def test_events_correlation_errors_progress_and_recovery(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        source = ROOT / "ableton_agent/max/ableton_agent_status_panel.js"
        program = r'''
const vm=require('vm'),fs=require('fs'),assert=require('assert');
let output=[],logs=[];
const c={outlet:(...a)=>output.push(a),post:s=>logs.push(s),Date};
vm.createContext(c);vm.runInContext(fs.readFileSync(PATH,'utf8'),c);
c.observe('/parameter_summary',['a','{}','dry_run'],0);
assert.equal(c.current.state,'WAITING');
c.observe('parameter_summary',['other','{"ok":true}'],1);
assert.equal(c.current.state,'WAITING');
c.observe('parameter_summary_progress',['a','{}'],1);
assert.equal(c.current.state,'WAITING');
c.observe('parameter_summary',['a','{"kind":"progress"}'],1);
assert.equal(c.current.state,'WAITING');
c.observe('parameter_summary',['a',JSON.stringify({ok:false,error:'x'.repeat(1000)})],1);
assert.equal(c.current.state,'FAILED');assert.equal(c.current.error.length,1000);
assert(output.filter(x=>x[0]===2).at(-1)[2].length<=82);c.bang();assert(logs[0].includes('x'.repeat(1000)));
c.observe('parameter_summary',['b'],0);
c.observe('parameter_summary',['b','bad json'],1);assert.equal(c.current.state,'UNKNOWN');
c.observe('parameter_summary',['c'],0);
c.observe('parameter_summary',['c','{"ok":true}'],1);
assert.equal(c.current.state,'OK');assert.equal(c.current.error,'');
c.observe('ping',['d'],0);c.observe('pong',['d'],1);
assert.equal(c.current.state,'REPLIED');assert(c.current.note.includes('unknown'));
assert(!('LiveAPI' in c));
c.observe('insert_effect',['h','{"action":"_module_health"}','dry_run'],0);
assert.equal(c.current.type,'PROBE');
c.observe('insert_effect',['h',JSON.stringify({ok:true,health_protocol:1,module:'insertion',song_id:1,running_build:'test'})],1);
assert.equal(c.current.type,'PROBE');assert(c.probes.insertion.ok);
for(let i=0;i<40;i++)c.observe('set_mix',['req'+i,'{"track_id":22}','commit'],0);
assert.equal(c.history.length,32);assert.equal(c.current.type,'WRITE');assert.equal(c.current.target,'track 22');
assert.equal(c.history[1].state,'UNKNOWN');
c.observe('parameter_summary',['bad','null'],0);
c.observe('parameter_summary',['bad','null'],1);assert.equal(c.current.state,'UNKNOWN');
'''.replace("PATH", json.dumps(str(source)))
        result = subprocess.run([node, "-e", program], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dashboard_tabs_selection_paging_and_text_bounds(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node unavailable")
        source = ROOT / "ableton_agent/max/ableton_agent_dashboard.js"
        program = r'''
const vm=require('vm'),fs=require('fs'),assert=require('assert');
let size=10,pos=[0,0],texts=[];
const g={init(){},redraw(){},set_source_rgba(){},rectangle(){},fill(){},select_font_face(){},set_font_size(n){size=n;},
text_measure(t){return [t.length*size*0.6,size];},move_to(x,y){pos=[x,y];},show_text(t){assert(pos[0]+g.text_measure(t)[0]<=620);assert(pos[1]<=148);texts.push(t);}};
const c={mgraphics:g};vm.createContext(c);vm.runInContext(fs.readFileSync(PATH,'utf8'),c);c.paint();
let history=Array.from({length:32},(_,i)=>({request_id:'req'+i,command:'set_parameters',type:'WRITE',state:'FAILED',elapsed_ms:6,error:'long error '.repeat(190),target:'track 1',note:''}));
c.model(JSON.stringify({current:history[0],history,probes:{}}));c.paint();
c.onclick(430,12);assert.equal(c.tab,1);c.paint();
c.onclick(596,139);assert.equal(c.page,1);c.paint();
c.onclick(120,41);assert.equal(c.selected,'req5');assert.equal(c.tab,2);c.paint();
c.onclick(596,139);assert.equal(c.detailPage,1);c.paint();
c.onclick(330,12);assert.equal(c.tab,0);c.paint();
assert(texts.includes('PROBE')===false);assert(texts.includes('MCP version: unknown'));
'''.replace("PATH", json.dumps(str(source)))
        result = subprocess.run([node, "-e", program], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

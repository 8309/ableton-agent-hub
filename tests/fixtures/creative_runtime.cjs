const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert');
const dir = path.resolve('ableton_agent/max');
let checks = 0;
function runtime(module) {
    const context = vm.createContext({});
    context.include = name => vm.runInContext(fs.readFileSync(path.join(dir, name), 'utf8'), context);
    vm.runInContext(`
      var db={1:{tracks:[11,12],return_tracks:[13],master_track:[14],scenes:[21,22]},
        11:{name:"MIDI",color:0,is_foldable:0,is_grouped:0,has_midi_input:1,has_audio_input:0,devices:[31],arrangement_clips:[41],clip_slots:[51,52]},
        12:{name:"Other",color:0,is_foldable:0,is_grouped:0,has_midi_input:1,has_audio_input:0,devices:[],arrangement_clips:[],clip_slots:[53,54]},
        13:{name:"Return",color:0,has_audio_input:0,devices:[]},14:{name:"Main",color:0,has_audio_input:0,devices:[]},
        21:{name:"A",color:0},22:{name:"B",color:0},31:{name:"EQ Eight",class_name:"Eq8",parameters:[]},
        41:{name:"Source",is_midi_clip:1,length:4,start_time:0,end_time:4,loop_start:0,loop_end:4,start_marker:0,
          notes:[{note_id:9,pitch:60,start_time:1,duration:0.25,velocity:80,mute:0,probability:0.8,velocity_deviation:5,release_velocity:64}]},
        51:{has_clip:0},52:{has_clip:0},53:{has_clip:0},54:{has_clip:0},91:{canonical_parent:[12]}};
      var mutations=[],nextId=100,out=[],failReadback=false;
      function refs(ids){var r=[];ids.forEach(function(id){r.push("id",id);});return r;}
      function LiveAPI(callback,target){this.id=target==="live_set"?1:target==="this_device"?91:Number(target.split(" ")[1]);if(!db[this.id])throw Error("missing API "+target);}
      LiveAPI.prototype.get=function(k){if(!(k in db[this.id]))throw Error("unknown property "+k);var x=db[this.id][k];return x instanceof Array?refs(x):[x];};
      LiveAPI.prototype.set=function(k,v){mutations.push([this.id,"set",k,v]);db[this.id][k]=v;if(k==="loop_end")db[this.id].length=v;};
      function makeClip(length,start){var id=nextId++;db[id]={name:"",is_midi_clip:1,length:length,loop_start:0,loop_end:length,start_marker:0,start_time:start||0,end_time:(start||0)+length,notes:[]};return id;}
      LiveAPI.prototype.call=function(method,a,b){
        var item=db[this.id];
        if(method==="get_all_notes_extended" || method==="get_notes_extended")return JSON.stringify({notes:item.notes});
        mutations.push([this.id,method,a,b]);
        if(method==="delete_track"){if(!failReadback)item.tracks.splice(a,1);return;}
        if(method==="create_audio_track" || method==="create_midi_track"){
          var id=nextId++;db[id]={name:"New",color:0,has_audio_input:method==="create_audio_track"?1:0};item.tracks.push(id);return;
        }
        if(method==="create_scene" || method==="duplicate_scene"){
          var id=nextId++;db[id]={name:"New Scene",color:0};item.scenes.push(id);return;
        }
        if(method==="create_clip"){item.clip=[makeClip(a,0)];item.has_clip=1;return;}
        if(method==="create_midi_clip"){item.arrangement_clips.push(makeClip(b,a));return;}
        if(method==="duplicate_clip_to_arrangement"){
          var source=db[Number(a.split(" ")[1])],id=nextId++;
          db[id]=JSON.parse(JSON.stringify(source));db[id].start_time=b;db[id].end_time=b+source.length;
          item.arrangement_clips.push(id);return;
        }
        if(method==="delete_clip"){var id=Number(a.split(" ")[1]);item.arrangement_clips=item.arrangement_clips.filter(function(x){return x!==id;});delete db[id];return;}
        if(method==="add_new_notes"){item.notes=a.notes.map(function(n,i){n.note_id=1000+i;return n;});return;}
        if(method==="apply_note_modifications"){
          if(!failReadback)item.notes=item.notes.map(function(n){return a.notes.filter(function(x){return x.note_id===n.note_id;})[0]||n;});return;
        }
        if(method==="insert_device"){var id=nextId++;db[id]={name:a};item.devices.push(id);return;}
      };
      function Dict(){}
      Dict.prototype.setparse=function(k,s){this.data=JSON.parse(s);};
      Dict.prototype.get=function(){return this.data;};
      var outlet=function(a,b){out.push(b);};
      function invoke(f,p,mode){var r;AgentCreative.handle("fixture","req",{mcp_safe:1,creative:p},mode,f,function(id,x){r=x;});return r;}
    `, context);
    context.include('ableton_agent_' + module + '.js');
    return context;
}
function run(c, code) { return vm.runInContext(code, c); }
function ok(value, label) { assert(value, label); checks++; }

let c = runtime('track_management');
ok(run(c, `var p={action:"rename_track",track_id:11,name:"Bass"};var r=invoke(prepareCreativeTrackManagement,p,"dry_run");r.ok && mutations.length===0`), 'inspect never mutates');
ok(run(c, `db[1].tracks=[12,11];p.plan_token=r.plan_token;r=invoke(prepareCreativeTrackManagement,p,"commit");r.ok && db[11].name==="Bass" && db[12].name==="Other"`), 'stable ID survives reorder');
ok(run(c, `r=invoke(prepareCreativeTrackManagement,p,"commit");!r.ok && !r.mutation_attempted`), 'token cannot replay');
ok(run(c, `delete p.plan_token;r=invoke(prepareCreativeTrackManagement,p,"dry_run");db[11].name="Manual";p.plan_token=r.plan_token;!invoke(prepareCreativeTrackManagement,p,"commit").ok`), 'stale state rejects');
ok(run(c, `p={action:"create_audio_track",name:"Texture"};r=invoke(prepareCreativeTrackManagement,p,"dry_run");p.plan_token=r.plan_token;r=invoke(prepareCreativeTrackManagement,p,"commit");r.ok && r.result.has_audio_input && !mutations.some(function(x){return x[2]==="arm";})`), 'create type readback without arm');
ok(run(c, `!invoke(prepareCreativeTrackManagement,{action:"rename_track",track_id:13,name:"Bad"},"dry_run").ok`), 'section mismatch');
ok(run(c, `var originalSet=LiveAPI.prototype.set;LiveAPI.prototype.set=function(k,v){originalSet.call(this,k,k==="color" && v===8421504?8092539:v);};p={action:"create_midi_track",name:"Palette test",color:8421504};r=invoke(prepareCreativeTrackManagement,p,"dry_run");p.plan_token=r.plan_token;r=invoke(prepareCreativeTrackManagement,p,"commit");r.ok && r.result.color===8092539 && r.result.requested_color===8421504 && r.result.color_exact_match===false && r.result.color_policy==="nearest_live_palette"`), 'native nearest-palette mapping is reported, not rejected');

c=runtime('track_management');
ok(run(c, `db[51].has_clip=1;db[51].clip=[41];var p={action:"delete_track",track_id:11};var r=invoke(prepareCreativeTrackManagement,p,"dry_run");r.ok && r.plan.direct_devices[0].device_id===31 && r.plan.arrangement_clip_count===1 && r.plan.session_clip_count===1 && r.plan.before_track_ids.join() === "11,12" && r.plan.after_track_ids.join() === "12" && mutations.length===0`), 'nonempty deletion impact is read-only');
ok(run(c, `p.plan_token=r.plan_token;r=invoke(prepareCreativeTrackManagement,p,"commit");r.ok && r.result.deleted && r.result.verified && db[1].tracks.join()==="12" && db[1].return_tracks.join()==="13" && mutations.filter(function(x){return x[1]==="delete_track";}).length===1 && mutations.some(function(x){return x[1]==="begin_undo_step";}) && mutations.some(function(x){return x[1]==="end_undo_step";})`), 'delete exactly inspected target with Undo grouping and readback');
ok(run(c, `!invoke(prepareCreativeTrackManagement,p,"commit").ok && mutations.filter(function(x){return x[1]==="delete_track";}).length===1`), 'delete token cannot repeat mutation');

for (const change of [
    'db[1].tracks.reverse()', 'db[11].devices=[]', 'db[11].arrangement_clips=[]',
    'db[51].has_clip=1;db[51].clip=[41]', 'db[11].name="Changed"',
    'db[41].start_time=2', 'db[11].is_grouped=1;db[11].group_track=[12]'
]) {
    c=runtime('track_management');
    run(c, 'var p={action:"delete_track",track_id:11};var r=invoke(prepareCreativeTrackManagement,p,"dry_run");p.plan_token=r.plan_token;');
    run(c, change);
    ok(run(c, `r=invoke(prepareCreativeTrackManagement,p,"commit");!r.ok && r.error.indexOf("stale_plan")>=0 && mutations.length===0`), 'delete rejects stale impact: '+change);
}
for (const [change, fields] of [
    ['db[11].is_foldable=1', '{track_id:11}'],
    ['', '{track_id:13,section:"return"}'], ['', '{track_id:14,section:"main"}'],
    ['', '{track_id:12}'], ['db[91].canonical_parent=[92];db[92]={canonical_parent:[11]}', '{track_id:11}'],
    ['db[91].canonical_parent=[91]', '{track_id:11}'],
    ['delete db[91].canonical_parent', '{track_id:11}'],
    ['db[1].tracks=[11]', '{track_id:11}'], ['', '{track_id:999}'],
    ['db[11].devices=Array(65).fill(31)', '{track_id:11}'],
    ['delete db[11].is_foldable', '{track_id:11}']
]) {
    c=runtime('track_management');run(c, change);
    ok(run(c, `var p=${fields};p.action="delete_track";var r=invoke(prepareCreativeTrackManagement,p,"dry_run");!r.ok && !r.plan_token && mutations.length===0`), 'protected or unreadable deletion rejects: '+change+fields);
}
c=runtime('track_management');
ok(run(c, `var p={action:"delete_track",track_id:11};var r=invoke(prepareCreativeTrackManagement,p,"dry_run");p.plan_token=r.plan_token;failReadback=true;r=invoke(prepareCreativeTrackManagement,p,"commit");!r.ok && r.applied===null && r.mutation_attempted && r.error.indexOf("readback mismatch")>=0 && mutations.filter(function(x){return x[1]==="delete_track";}).length===1`), 'delete readback failure never claims rollback');
c=runtime('track_management');
ok(run(c, `var ticks=0;Date=function(){return {getTime:function(){ticks+=1600;return ticks;}}};!invoke(prepareCreativeTrackManagement,{action:"delete_track",track_id:11},"dry_run").ok && mutations.length===0`), 'inspection budget failure prevents token and mutation');
c=runtime('track_management');
ok(run(c, `var p={action:"delete_track",track_id:11,plan_token:"missing"};var r=invoke(prepareCreativeTrackManagement,p,"commit");!r.ok && mutations.length===0`), 'delete apply without inspected token rejected');

c=runtime('clip_writer');
ok(run(c, `var p={track_id:11,location:"arrangement",start:3,length:4,notes:[]};!invoke(prepareCreativeClipWriter,p,"dry_run").ok && mutations.length===0`), 'partial overlaps reject');
ok(run(c, `p={track_id:11,location:"session",scene_id:21,length:4,name:"Test",notes:[{pitch:60,start_time:0,duration:1,velocity:90}]};var r=invoke(prepareCreativeClipWriter,p,"dry_run");p.plan_token=r.plan_token;r=invoke(prepareCreativeClipWriter,p,"commit");r.ok && r.result.verified && db[51].has_clip===1`), 'new Session Clip verification');
ok(run(c, `!invoke(prepareCreativeClipWriter,p,"dry_run").ok`), 'occupied slot rejects');
ok(run(c, `p={track_id:11,location:"arrangement",start:8,length:4,name:"New",notes:[]};r=invoke(prepareCreativeClipWriter,p,"dry_run");p.plan_token=r.plan_token;r=invoke(prepareCreativeClipWriter,p,"commit");r.ok && db[r.result.clip_id].start_time===8`), 'Arrangement creation');

c=runtime('clip_note_tools');
ok(run(c, `var p={action:"shift_notes",track_id:11,clip_id:41,beats:0.25};var r=invoke(prepareCreativeClipNoteTools,p,"dry_run");p.plan_token=r.plan_token;r=invoke(prepareCreativeClipNoteTools,p,"commit");r.ok && db[41].notes[0].note_id===9 && db[41].notes[0].start_time===1.25 && db[41].notes[0].velocity_deviation===5 && !mutations.some(function(x){return x[1]==="remove_notes_extended";})`), 'note IDs and extended fields preserved');
ok(run(c, `delete p.plan_token;r=invoke(prepareCreativeClipNoteTools,p,"dry_run");p.plan_token=r.plan_token;failReadback=true;r=invoke(prepareCreativeClipNoteTools,p,"commit");!r.ok && r.mutation_attempted && r.applied===null`), 'readback failure does not claim rollback');
ok(run(c, `p.track_id=12;!invoke(prepareCreativeClipNoteTools,p,"dry_run").ok`), 'foreign Clip rejects');
ok(run(c, `p.track_id=11;p.beats=-2;!invoke(prepareCreativeClipNoteTools,p,"dry_run").ok`), 'negative shifted note rejects');

c=runtime('clip_variation');
ok(run(c, `var p={action:"make_fill",track_id:11,clip_id:41,target_start:8,name:"Fill"};var r=invoke(prepareCreativeClipVariation,p,"dry_run");p.plan_token=r.plan_token;r=invoke(prepareCreativeClipVariation,p,"commit");r.ok && db[41].notes.length===1 && r.result.note_count===2`), 'variation leaves source');

c=runtime('scene');
ok(run(c, `var r=invoke(prepareCreativeScene,{action:"list",limit:1},"dry_run");r.ok && r.result.next_cursor===1 && mutations.length===0`), 'bounded scene list');
ok(run(c, `var p={action:"create",name:"Audition"};r=invoke(prepareCreativeScene,p,"dry_run");p.plan_token=r.plan_token;r=invoke(prepareCreativeScene,p,"commit");r.ok && r.result.scene_name==="Audition"`), 'scene creation readback');
ok(run(c, `p={action:"fire",scene_id:21};r=invoke(prepareCreativeScene,p,"dry_run");p.plan_token=r.plan_token;r=invoke(prepareCreativeScene,p,"commit");r.ok && r.result.fire_requested && !r.result.playback_verified`), 'fire avoids false playback verification');

c=runtime('sample_confirm');
ok(run(c, `confirmLoadedSample=function(p){return {track_index:p.track_index,device_index:p.device_index,loaded:true};};var r=invoke(prepareCreativeSampleConfirm,{track_id:11,device_id:31,target:"simpler"},"dry_run");r.ok && r.result.device_index===0 && mutations.length===0`), 'sample stable target adapter');
ok(run(c, `!invoke(prepareCreativeSampleConfirm,{track_id:12,device_id:31},"dry_run").ok`), 'foreign device rejects');

c=runtime('inserter');
ok(run(c, `var p={track_id:11,kind:"effect",device:"Utility"};var r=invoke(prepareCreativeInserter,p,"dry_run");p.plan_token=r.plan_token;r=invoke(prepareCreativeInserter,p,"commit");r.ok && r.result.after_device_ids.length===2`), 'whitelisted effect insert readback');
ok(run(c, `p.device="Unverified Third Party";!invoke(prepareCreativeInserter,p,"dry_run").ok`), 'whitelist rejects');
ok(run(c, `p={track_id:11,kind:"effect",device:"Utility"};r=invoke(prepareCreativeInserter,p,"dry_run");p.plan_token=r.plan_token;p.device="Reverb";!invoke(prepareCreativeInserter,p,"commit").ok`), 'changed intent invalidates token');
ok(run(c, `var old=Date;Date=function(){return {getTime:function(){return 1;}}};p={track_id:11,kind:"effect",device:"Utility"};r=invoke(prepareCreativeInserter,p,"dry_run");p.plan_token=r.plan_token;Date=function(){return {getTime:function(){return 120002;}}};r=invoke(prepareCreativeInserter,p,"commit");Date=old;!r.ok && !r.mutation_attempted`), 'expired token rejects');

c=runtime('eq_tools');
ok(run(c, `db[61]={value:0.2,is_enabled:1};applyMoves=function(){return {skipped_count:0,changes:[{parameter:{id:61,index:0,name:"Gain"},before:{value:db[61].value},after:{value:0.4}}]};};parameterInfo=function(a){return {value:db[a.id].value,display_text:"Test"};};var p={action:"apply_preset",track_id:11,device_id:31,preset:"lead_presence_soft"};var r=invoke(prepareCreativeEqTools,p,"dry_run");p.plan_token=r.plan_token;r=invoke(prepareCreativeEqTools,p,"commit");r.ok && r.result.changes[0].after.value===0.4`), 'EQ writes verified parameter IDs');
ok(run(c, `db[61].is_enabled=0;!invoke(prepareCreativeEqTools,p,"dry_run").ok`), 'disabled EQ rejects before mutation');

c=runtime('arrangement_tools');
ok(run(c, `var p={action:"copy_midi_clip",track_id:11,clip_id:41,target_start:8};var r=invoke(prepareCreativeArrangement,p,"dry_run");r.ok && mutations.length===0`), 'Arrangement copy inspect');
ok(run(c, `p.plan_token=r.plan_token;r=invoke(prepareCreativeArrangement,p,"commit");r.ok && r.result.verified && db[r.result.clip_id].start_time===8 && db[41].notes[0].note_id===9 && db[r.result.clip_id].notes[0].probability===0.8`), 'Arrangement MIDI copy reuses note-preserving writer');
ok(run(c, `p.target_start=3;!invoke(prepareCreativeArrangement,p,"dry_run").ok`), 'copy overlap rejected');
ok(run(c, `p.target_start=16;p.track_id=12;!invoke(prepareCreativeArrangement,p,"dry_run").ok`), 'copy target membership');
ok(run(c, `p.track_id=11;db[41].start_marker=1;!invoke(prepareCreativeArrangement,p,"dry_run").ok`), 'copy unsupported clip origin explicit');

c=runtime('arrangement_tools');
run(c, `db[41].is_midi_clip=0;db[41].is_audio_clip=1;db[41].file_path="test.wav";db[41].gain=0.75;db[41].warping=1;`);
ok(run(c, `var p={action:"move_audio_clip",track_id:11,clip_id:41,target_start:2};var r=invoke(prepareCreativeArrangement,p,"dry_run");r.ok && mutations.length===0`), 'audio move inspect reuses existing mover');
ok(run(c, `p.plan_token=r.plan_token;r=invoke(prepareCreativeArrangement,p,"commit");r.ok && r.result.verified && r.result.clip_id!==41 && db[11].arrangement_clips.length===1 && !db[41] && db[r.result.clip_id].start_time===2 && db[r.result.clip_id].gain===0.75 && db[r.result.clip_id].file_path==="test.wav"`), 'overlapping audio move preserves sample through native duplicate');
ok(run(c, `p.clip_id=r.result.clip_id;delete p.plan_token;r=invoke(prepareCreativeArrangement,p,"dry_run");p.plan_token=r.plan_token;var before=mutations.length;r=invoke(prepareCreativeArrangement,p,"commit");r.ok && r.result.no_op && r.result.clip_id===p.clip_id && !mutations.slice(before).some(function(x){return x[1]==="delete_clip";})`), 'no-op move does not delete');
ok(run(c, `db[42]={start_time:10,end_time:14,length:4,is_audio_clip:1};db[11].arrangement_clips.push(42);p.target_start=9;!invoke(prepareCreativeArrangement,p,"dry_run").ok`), 'audio collision uses existing mover check');

c=runtime('track_management');
ok(run(c, `var p={action:"create_audio_track",name:"Direct",direct_apply:true};var r=invoke(prepareCreativeTrackManagement,p,"commit");r.ok && r.applied`), 'direct apply without prior token');
c=runtime('track_management');
ok(run(c, `var p={action:"create_audio_track",name:"Direct",direct_apply:true,plan_token:"bad"};var r=invoke(prepareCreativeTrackManagement,p,"commit");!r.ok && mutations.length===0`), 'explicit stale token remains enforced');

console.log('Creative Max runtime: ' + checks + ' checks passed');

// Strip only the new private dispatch branch, then run the real legacy handlers.
for (const [module, handler] of [
    ['clip_writer','writeClip'], ['clip_note_tools','handleClipNoteTools'],
    ['clip_variation','handleClipVariation'], ['scene','handleScene'],
    ['track_management','handleTrackManagement'], ['eq_tools','handleEqTools'],
    ['sample_confirm','handleSampleConfirm'], ['inserter','insertEffect'],
    ['arrangement_tools','handleArrangementTools']
]) {
    c=runtime(module);
    let source=fs.readFileSync(path.join(dir,'ableton_agent_'+module+'.js'),'utf8');
    const regex=/if\s*\(payload\.mcp_safe\s*!==\s*undefined\)\s*\{/;
    let match;
    while ((match=regex.exec(source))) {
        let end=match.index+match[0].length, depth=1;
        while(depth && end<source.length) {
            if(source[end]==='{') depth++;
            if(source[end]==='}') depth--;
            end++;
        }
        source=source.slice(0,match.index)+source.slice(end);
    }
    vm.runInContext(source,c);
    run(c, `${handler}("request",JSON.stringify({mcp_safe:1,action:"mcp_creative_v1",creative:{track_id:11,device:"Utility",kind:"effect",action:"create_audio_track",notes:[]}}),"commit")`);
    ok(run(c,'mutations.length===0 && out.length>0'), 'legacy '+module+' fails closed');
}
console.log('Including legacy rejection: ' + checks + ' checks passed');

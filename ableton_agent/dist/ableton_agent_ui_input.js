// Only named, known monotonic controls may use formatter inversion. Never probe by writing.
var AgentUiInput = (function () {
    function fail(message) { throw new Error("unsupported_ui_value: " + message); }
    function text(raw) { return String(raw instanceof Array ? raw.join(" ") : raw).replace(/^\s+|\s+$/g, ""); }
    function format(api, value) { return text(api.call("str_for_value", value)); }
    function scalar(raw) { return Number(raw instanceof Array ? raw[0] : raw); }
    function exclusive(change) {
        var numeric = change.value !== undefined && change.value !== null;
        var ui = change.ui_value !== undefined && change.ui_value !== null;
        if (numeric === ui) { fail("provide exactly one of value or ui_value"); }
        if (ui && (typeof change.ui_value !== "string" || !text(change.ui_value))) { fail("ui_value must be a nonempty string"); }
    }
    function number(raw, kind) {
        var s = text(raw), match, scale = 1;
        if (kind === "db" && /^-(inf|infinity|\u221e)\s*dB$/i.test(s)) { return {value:-Infinity, tolerance:0}; }
        if (kind === "pan") {
            if (/^C$/i.test(s)) { return {value:0,tolerance:0}; }
            match = /^(\d+(?:\.\d+)?)\s*([LR])$/i.exec(s);
            if (!match) { fail("pan requires C, nL or nR"); }
            return {value:Number(match[1]) * (match[2].toUpperCase()==="L"?-1:1), tolerance:0};
        }
        match = /^([+-]?\d+(?:\.\d+)?)\s*(kHz|Hz|dB|Q)?$/i.exec(s);
        if (!match) { fail("invalid unit or number: " + s); }
        var unit = (match[2] || "").toLowerCase();
        if ((kind==="hz" && unit!=="hz" && unit!=="khz") || (kind==="db" && unit!=="db") || (kind==="q" && unit!=="" && unit!=="q")) { fail("wrong unit: " + s); }
        if (unit==="khz") { scale=1000; }
        var decimals = match[1].indexOf(".")<0 ? 0 : match[1].split(".")[1].length;
        return {value:Number(match[1])*scale, tolerance:Math.pow(10,-decimals)*scale/2};
    }
    function resolve(change, api, info, context) {
        exclusive(change);
        if (change.ui_value === undefined || change.ui_value === null) { return Number(change.value); }
        var requested=text(change.ui_value), min=info.min, max=info.max, value, kind;
        if (info.is_quantized) {
            var labels=api.get("value_items"), matches=[];
            if (!(labels instanceof Array)) { labels=[labels]; }
            if (labels.length>128 || labels.length!==max-min+1 || min!==Math.round(min)) { fail("unsupported enumeration"); }
            for(var i=0;i<labels.length;i++) { if(text(labels[i]).toLowerCase()===requested.toLowerCase()) { matches.push(min+i); } }
            if(matches.length!==1) { fail("unknown or ambiguous enum label"); }
            value=matches[0];
            if(format(api,value).toLowerCase()!==requested.toLowerCase()) { fail("enum formatter mismatch"); }
            return value;
        }
        if(context.field==="pan" && min===-1 && max===1) {
            var pan=number(requested,"pan").value;
            if(Math.abs(pan)>50) { fail("pan outside 50L..50R"); }
            value=pan/50;
            if(number(format(api,value),"pan").value!==pan) { fail("pan formatter mismatch"); }
            return value;
        }
        if(context.field==="volume") { kind="db"; }
        else if(context.device_class==="Eq8") {
            if(/^\d+ (Freq|Frequency) [AB]$/.test(info.name)) { kind="hz"; }
            else if(/^\d+ Gain [AB]$/.test(info.name)) { kind="db"; }
            else if(/^\d+ Q [AB]$/.test(info.name)) { kind="q"; }
        }
        if(!kind) { fail("no verified adapter for this parameter"); }
        var target=number(requested,kind).value;
        var low=number(format(api,min),kind), high=number(format(api,max),kind);
        if(target<low.value || target>high.value) { fail("outside displayed range"); }
        if(target===low.value) { return min; }
        if(target===high.value) { return max; }
        // Prefer existing EQ numeric/log-frequency mappings, verified by the formatter.
        value=target;
        if(kind==="hz" && min===0 && max===1) { value=Math.log(target/10)/Math.log(22000/10); }
        function matches(v) {
            var shown=number(format(api,v),kind);
            return isFinite(shown.value) && Math.abs(shown.value-target)<=shown.tolerance+1e-9;
        }
        if(context.device_class==="Eq8" && value>=min && value<=max && matches(value)) { return value; }
        var deadline=new Date().getTime()+200;
        for(var step=0;step<24;step++) {
            if(new Date().getTime()>deadline) { fail("formatter conversion budget exceeded"); }
            value=(min+max)/2;
            var shown=number(format(api,value),kind);
            if(isFinite(shown.value) && Math.abs(shown.value-target)<=shown.tolerance+1e-9) { return value; }
            if(shown.value<target) { min=value; } else { max=value; }
        }
        fail("cannot confirm requested display value");
    }
    return {resolve:resolve, exclusive:exclusive};
}());

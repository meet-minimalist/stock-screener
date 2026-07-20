"""Static CSS + vanilla-JS for the interactive screener site (no external libs)."""

STYLE = """
:root {
  --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --surface:#fcfcfb;
  --card:#ffffff; --line:#e6e5df; --line2:#efeee9; --accent:#2a78d6;
  --pos:#0a7a0a; --neg:#c0392b; --chip-bg:rgba(12,163,12,.12); --chip-line:rgba(12,163,12,.35);
}
@media (prefers-color-scheme: dark) {
  :root { --ink:#f4f4f2; --ink2:#c3c2b7; --muted:#8f8e88; --surface:#141413;
    --card:#1c1c1a; --line:#2c2c2a; --line2:#232321; --accent:#3987e5;
    --pos:#28b528; --neg:#e26d5c; --chip-bg:rgba(40,181,40,.14); --chip-line:rgba(40,181,40,.4); }
}
:root[data-theme="light"] { --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --surface:#fcfcfb;
  --card:#ffffff; --line:#e6e5df; --line2:#efeee9; --accent:#2a78d6; --pos:#0a7a0a; --neg:#c0392b;
  --chip-bg:rgba(12,163,12,.12); --chip-line:rgba(12,163,12,.35); }
:root[data-theme="dark"] { --ink:#f4f4f2; --ink2:#c3c2b7; --muted:#8f8e88; --surface:#141413;
  --card:#1c1c1a; --line:#2c2c2a; --line2:#232321; --accent:#3987e5; --pos:#28b528; --neg:#e26d5c;
  --chip-bg:rgba(40,181,40,.14); --chip-line:rgba(40,181,40,.4); }

* { box-sizing:border-box; }
.app { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color:var(--ink);
  max-width:1280px; margin:0 auto; padding:24px 20px 72px; }
.app h1 { font-size:1.5rem; margin:0 0 2px; }
.meta { color:var(--ink2); font-size:.85rem; margin-bottom:18px; }
.nav { display:flex; flex-wrap:wrap; gap:4px; margin:0 0 16px; }
.navlink { font-size:.82rem; color:var(--ink2); text-decoration:none; padding:5px 10px;
  border-radius:8px; border:1px solid var(--line); }
.navlink:hover { background:var(--line2); color:var(--ink); }
.navlink.active { color:var(--ink); border-color:var(--accent); font-weight:600; }
.tiles { display:flex; flex-wrap:wrap; gap:12px; margin-bottom:16px; }
.tile { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:10px 16px; min-width:118px; }
.tile .k { font-size:1.45rem; font-weight:650; font-variant-numeric:tabular-nums; }
.tile .l { font-size:.7rem; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
.chips { margin:0 0 18px; font-size:.8rem; }
.chip { display:inline-block; background:var(--chip-bg); color:var(--ink); border:1px solid var(--chip-line);
  border-radius:999px; padding:2px 10px; margin:0 6px 6px 0; }
details.rrg { margin:0 0 20px; border:1px solid var(--line); border-radius:12px; background:var(--card); }
details.rrg > summary { cursor:pointer; padding:12px 16px; font-weight:600; }
details.rrg img { display:block; width:100%; height:auto; border-radius:0 0 12px 12px; }
details.method { margin:0 0 18px; border:1px solid var(--line); border-radius:12px; background:var(--card); }
details.method > summary { cursor:pointer; padding:11px 16px; font-weight:600; font-size:.9rem; }
details.method p { margin:0 16px 10px; color:var(--ink2); font-size:.86rem; }
details.method ul { margin:0 16px 10px; padding-left:20px; color:var(--ink2); font-size:.86rem; }
details.method li { margin:3px 0; }
details.method li b { color:var(--ink); }

.tabs { display:flex; flex-wrap:wrap; gap:6px; border-bottom:1px solid var(--line); margin-bottom:14px; }
.tab { appearance:none; background:none; border:0; border-bottom:2px solid transparent; color:var(--ink2);
  padding:8px 12px; font-size:.86rem; cursor:pointer; border-radius:6px 6px 0 0; }
.tab:hover { background:var(--line2); color:var(--ink); }
.tab[aria-selected="true"] { color:var(--ink); border-bottom-color:var(--accent); font-weight:600; }
.tab .n { display:inline-block; margin-left:6px; min-width:20px; padding:0 6px; font-size:.72rem;
  color:var(--muted); background:var(--line2); border-radius:999px; font-variant-numeric:tabular-nums; }

.tabdesc { color:var(--ink2); font-size:.85rem; margin:0 0 12px; }
.controls { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:12px; }
.controls input[type="search"], .controls select { background:var(--card); color:var(--ink);
  border:1px solid var(--line); border-radius:8px; padding:7px 10px; font-size:.85rem; font-family:inherit; }
.controls input[type="search"] { min-width:180px; }
.controls label { font-size:.78rem; color:var(--muted); display:inline-flex; gap:6px; align-items:center; }
.controls .spacer { flex:1; }
.btn { background:var(--accent); color:#fff; border:0; border-radius:8px; padding:7px 12px; font-size:.82rem;
  cursor:pointer; font-family:inherit; }
.btn:hover { filter:brightness(1.06); }
.count { color:var(--muted); font-size:.8rem; }

.tablewrap { border:1px solid var(--line); border-radius:12px; overflow-x:auto; background:var(--card); }
table { border-collapse:collapse; width:100%; font-size:.85rem; }
th, td { padding:8px 10px; text-align:right; border-bottom:1px solid var(--line2); white-space:nowrap; }
th { position:sticky; top:0; background:var(--card); color:var(--muted); font-weight:600; font-size:.7rem;
  text-transform:uppercase; letter-spacing:.03em; cursor:pointer; user-select:none; }
th.left, td.left { text-align:left; }
th.has-desc { cursor:help; border-bottom:1px dotted var(--muted); }
th.has-desc[aria-sort] { cursor:pointer; }
th[aria-sort="ascending"]::after { content:" \\2191"; color:var(--accent); }
th[aria-sort="descending"]::after { content:" \\2193"; color:var(--accent); }
td.num { font-variant-numeric:tabular-nums; }
.tag { display:inline-block; padding:1px 8px; border-radius:999px; font-size:.72rem; font-weight:600;
  border:1px solid var(--line); color:var(--ink2); background:var(--line2); }
.tag.t-mega, .tag.t-large { color:var(--accent); border-color:var(--chip-line); background:var(--chip-bg); }
.tag.t-mid { color:#b07400; border-color:rgba(176,116,0,.35); background:rgba(176,116,0,.12); }
tbody tr:hover { background:var(--line2); }
.rank { color:var(--muted); }
.tk { font-weight:650; }
.score { display:inline-block; min-width:34px; text-align:center; color:#fff; border-radius:7px;
  padding:2px 7px; font-weight:650; font-variant-numeric:tabular-nums; }
.why { color:var(--ink2); white-space:normal; min-width:220px; text-align:left; }
.pos { color:var(--pos); } .neg { color:var(--neg); } .muted { color:var(--muted); }
.fbars { display:inline-flex; align-items:flex-end; gap:2px; height:18px; }
.fbar { position:relative; width:5px; height:100%; background:var(--line); border-radius:2px; overflow:hidden; }
.fbar > span { position:absolute; bottom:0; left:0; width:100%; border-radius:2px; }
.empty { padding:28px; text-align:center; color:var(--muted); }
:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
@media (prefers-reduced-motion: reduce) { * { transition:none !important; } }
"""

# The table engine reads three globals injected by site.py: RECORDS, SCREENS,
# COLUMNS. It keeps predicates server-side (each record carries its `screens`
# membership) and only filters/sorts/renders here.
SCRIPT = r"""
(function () {
  var state = { tab: SCREENS[0].key, q: "", sector: "", minScore: 0, sortKey: null, sortDir: -1 };
  var FCOLORS = { sector:"#2a78d6", trend:"#1baf7a", rel_strength:"#eda100",
                  volatility:"#4a3aa7", trigger:"#eb6834", fundamental:"#e34948" };
  var $ = function (s, r) { return (r || document).querySelector(s); };

  function tierColor(v) {
    return v >= 80 ? "#0ca30c" : v >= 65 ? "#2a78d6" : v >= 50 ? "#fab219" : "#898781";
  }
  function num(v) { return (typeof v === "number") ? v : null; }
  function screenByKey(k) { for (var i=0;i<SCREENS.length;i++) if (SCREENS[i].key===k) return SCREENS[i]; }

  function fmt(col, v) {
    if (v === null || v === undefined || v === "") return col.type === "text" ? "" : "–";
    switch (col.type) {
      case "score": return '<span class="score" style="background:' + tierColor(v) + '">' + v.toFixed(0) + "</span>";
      case "pct": return (typeof v === "number") ? v.toFixed(0) + "%" : v;
      case "ret": { var c = v > 0 ? "pos" : v < 0 ? "neg" : "muted"; return '<span class="' + c + '">' + (v>0?"+":"") + v.toFixed(0) + "%</span>"; }
      case "money": return (typeof CURRENCY === "undefined" ? "$" : CURRENCY) + Number(v).toLocaleString(undefined, {maximumFractionDigits:2});
      case "mcap": {
        if (typeof v !== "number") return "–";
        var cur = (typeof CURRENCY === "undefined" ? "$" : CURRENCY);
        if (cur === "₹") return "₹" + Math.round(v).toLocaleString("en-IN") + " Cr";
        var a = Math.abs(v);
        if (a >= 1e12) return "$" + (v/1e12).toFixed(2) + "T";
        if (a >= 1e9)  return "$" + (v/1e9).toFixed(2) + "B";
        if (a >= 1e6)  return "$" + (v/1e6).toFixed(0) + "M";
        return "$" + Math.round(v).toLocaleString();
      }
      case "tag": return '<span class="tag t-' + String(v).toLowerCase() + '">' + v + "</span>";
      case "num": return (typeof v === "number") ? v.toFixed(col.dp==null?1:col.dp) : v;
      case "factors": {
        var out = '<span class="fbars">', keys = ["sector","trend","rel_strength","volatility","trigger","fundamental"];
        for (var i=0;i<keys.length;i++){ var p=Math.round((v&&v[keys[i]]!=null?v[keys[i]]:0)*100);
          out += '<span class="fbar" title="'+keys[i]+' '+p+'%"><span style="height:'+p+'%;background:'+FCOLORS[keys[i]]+'"></span></span>'; }
        return out + "</span>";
      }
      default: return String(v);
    }
  }

  function currentRows() {
    var q = state.q.toLowerCase();
    var rows = RECORDS.filter(function (r) {
      if (r.screens.indexOf(state.tab) < 0) return false;
      if (state.sector && r.sector !== state.sector) return false;
      if (num(r.score) !== null && r.score < state.minScore) return false;
      if (q && (r.ticker.toLowerCase().indexOf(q) < 0) && ((r.sector||"").toLowerCase().indexOf(q) < 0)) return false;
      return true;
    });
    var sc = screenByKey(state.tab);
    var key = state.sortKey || sc.sort_by, dir = state.sortKey ? state.sortDir : (sc.sort_desc ? -1 : 1);
    rows.sort(function (a, b) {
      var x = a[key], y = b[key];
      x = (typeof x === "number") ? x : -Infinity; y = (typeof y === "number") ? y : -Infinity;
      return x < y ? -dir : x > y ? dir : 0;
    });
    return rows;
  }

  function render() {
    var sc = screenByKey(state.tab);
    $("#tabdesc").textContent = sc.description;
    document.querySelectorAll(".tab").forEach(function (t) {
      t.setAttribute("aria-selected", t.dataset.key === state.tab ? "true" : "false");
    });
    var rows = currentRows();
    $("#count").textContent = rows.length + " stocks";

    var head = "<tr>";
    for (var i=0;i<COLUMNS.length;i++){ var c=COLUMNS[i];
      var sortKey = state.sortKey || sc.sort_by, dir = state.sortKey ? state.sortDir : (sc.sort_desc?-1:1);
      var aria = (c.key===sortKey && c.sortable!==false) ? (dir===1?"ascending":"descending") : "none";
      var titleAttr = c.desc ? ' title="'+String(c.desc).replace(/"/g,"&quot;")+'"' : '';
      head += '<th'+titleAttr+' class="'+(c.align==="left"?"left":"num")+(c.desc?" has-desc":"")+'" data-key="'+c.key+'" aria-sort="'+aria+'">'+c.label+"</th>"; }
    head += "</tr>";

    var body = "";
    if (!rows.length) body = '<tr><td class="empty" colspan="'+COLUMNS.length+'">No stocks match this screen and filters.</td></tr>';
    for (var r=0;r<rows.length;r++){ var rec=rows[r]; body += "<tr>";
      for (var j=0;j<COLUMNS.length;j++){ var col=COLUMNS[j];
        var val;
        if (col.key==="rank") val = r+1;
        else if (col.key==="reason") val = (rec.signal_notes && rec.signal_notes[state.tab]) || rec.reason;
        else val = rec[col.key];
        var cls = col.align==="left" ? "left" : "num"; if (col.key==="ticker") cls+=" tk"; if (col.key==="rank") cls+=" rank"; if (col.key==="reason") cls="why";
        body += '<td class="'+cls+'">'+fmt(col, val)+"</td>"; }
      body += "</tr>"; }
    $("#thead").innerHTML = head; $("#tbody").innerHTML = body;
  }

  function toCsv() {
    var rows = currentRows(), cols = COLUMNS.filter(function(c){return c.key!=="factors"&&c.key!=="rank";});
    var lines = [cols.map(function(c){return c.label;}).join(",")];
    rows.forEach(function (rec) {
      lines.push(cols.map(function (c) {
        var v = rec[c.key]; if (v===null||v===undefined) return "";
        if (typeof v === "string" && (v.indexOf(",")>=0||v.indexOf('"')>=0)) return '"'+v.replace(/"/g,'""')+'"';
        return v;
      }).join(","));
    });
    var blob = new Blob([lines.join("\n")], {type:"text/csv"});
    var a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = "screener-" + state.tab + ".csv"; a.click(); URL.revokeObjectURL(a.href);
  }

  function buildTabs() {
    var bar = $("#tabs"); bar.innerHTML = "";
    SCREENS.forEach(function (s) {
      var b = document.createElement("button");
      b.className = "tab"; b.dataset.key = s.key; b.setAttribute("role","tab");
      b.innerHTML = s.name + '<span class="n">' + s.count + "</span>";
      b.onclick = function () { state.tab = s.key; state.sortKey = null; render(); };
      bar.appendChild(b);
    });
  }

  function buildSectorOptions() {
    var seen = {}; RECORDS.forEach(function (r) { if (r.sector) seen[r.sector] = 1; });
    var sel = $("#sector"); Object.keys(seen).sort().forEach(function (s) {
      var o = document.createElement("option"); o.value = s; o.textContent = s; sel.appendChild(o); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    buildTabs(); buildSectorOptions();
    $("#search").addEventListener("input", function (e) { state.q = e.target.value; render(); });
    $("#sector").addEventListener("change", function (e) { state.sector = e.target.value; render(); });
    var slider = $("#minscore");
    slider.addEventListener("input", function (e) { state.minScore = +e.target.value; $("#minscoreval").textContent = e.target.value; render(); });
    $("#export").addEventListener("click", toCsv);
    $("#thead").addEventListener("click", function (e) {
      var th = e.target.closest("th"); if (!th) return; var key = th.dataset.key;
      var col = COLUMNS.filter(function(c){return c.key===key;})[0]; if (!col || col.sortable===false) return;
      if (state.sortKey === key) state.sortDir = -state.sortDir; else { state.sortKey = key; state.sortDir = -1; }
      render();
    });
    render();
  });
})();
"""

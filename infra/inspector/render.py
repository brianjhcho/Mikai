"""Inspector HTML template.

Single-file light-theme inspection surface. Companion to the dark
cockpit; matches the enterprise-brain reference (cream ground, dark
ink, faint pink accents, delicate serif titling). The state dict from
``build_state()`` is embedded as ``window.__INSPECTOR__`` and the page
renders entirely from that — no network calls beyond the
``/ask/stream`` EventSource on the canned-query panels.

Deliberate design choices, so future edits stay honest to the brief:

  * The Inspector never asks the user to act. Every panel is a
    read-only lens on what MIKAI has noticed.
  * The bottom bar reuses the cockpit's ask contract exactly — same
    endpoint, same event shape — so we do not fork the streaming
    surface for a second UI.
  * Cream palette lives in CSS custom properties on ``:root``. When
    palette drift becomes a problem, retune here — component code
    reads colors from tokens.
"""

from __future__ import annotations

import json


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MIKAI — inspector</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600&family=IBM+Plex+Mono:ital,wght@0,400;0,500;1,400&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&display=swap" rel="stylesheet">
<style>
  :root{
    --ground:#F4F1EA;      /* cream */
    --ground-2:#EEEAE0;
    --ink:#1B2430;         /* dark ink */
    --ink-soft:#3C4653;
    --faint:#8A8577;
    --rule:#D9D3C4;
    --pink:#D4816F;
    --pink-soft:rgba(212,129,111,.32);
    --card:#FBF8F2;
    --card-hover:#F7F3EA;
    --dot:#D4816F;
    --serif:"Newsreader",Georgia,serif;
    --sans:"Archivo",system-ui,sans-serif;
    --mono:"IBM Plex Mono",ui-monospace,monospace;
    --topbar-h:52px;
    --bottombar-h:56px;
    --rail-w:220px;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%}
  body{
    background:var(--ground);
    color:var(--ink);
    font-family:var(--serif);
    font-size:15px;
    line-height:1.55;
    overflow:hidden;
  }
  button{font:inherit;color:inherit;background:none;border:none;cursor:pointer}
  button:focus-visible{outline:1px solid var(--pink);outline-offset:3px;border-radius:2px}
  a{color:inherit}

  /* ── top bar ────────────────────────────────────────────────── */
  #topbar{
    position:fixed;top:0;left:0;right:0;height:var(--topbar-h);z-index:50;
    display:flex;align-items:center;justify-content:space-between;
    padding:0 24px;
    border-bottom:1px solid var(--rule);
    background:rgba(244,241,234,.92);
    backdrop-filter:blur(8px);
  }
  #topbar .wordmark{
    font-family:var(--sans);font-weight:600;font-size:11px;
    letter-spacing:.42em;text-transform:uppercase;color:var(--ink);
  }
  #topbar .wordmark .dot{color:var(--pink);margin-left:2px}
  #topbar .ts{
    font-family:var(--mono);font-size:10px;letter-spacing:.12em;
    color:var(--faint);
  }

  /* toggle switch — cockpit · inspector */
  .toggle{
    display:flex;align-items:center;gap:10px;
    font-family:var(--mono);font-size:10px;letter-spacing:.22em;
    text-transform:uppercase;color:var(--faint);
  }
  .toggle .track{
    position:relative;width:64px;height:22px;
    border:1px solid var(--rule);border-radius:12px;
    background:var(--ground-2);
    cursor:pointer;
    transition:background .18s ease;
  }
  .toggle .knob{
    position:absolute;top:1px;left:1px;
    width:30px;height:18px;border-radius:10px;
    background:var(--ink);
    transition:transform .22s ease;
  }
  .toggle .track[data-mode="inspector"] .knob{
    transform:translateX(32px);
    background:var(--pink);
  }
  .toggle .lbl{color:var(--faint)}
  .toggle .lbl.on{color:var(--ink)}

  /* ── layout ─────────────────────────────────────────────────── */
  main{
    position:fixed;
    top:var(--topbar-h);left:0;right:0;bottom:var(--bottombar-h);
    display:grid;
    grid-template-columns:var(--rail-w) 1fr;
  }
  /* ── left rail ──────────────────────────────────────────────── */
  #rail{
    border-right:1px solid var(--rule);
    padding:24px 18px 20px;
    display:flex;flex-direction:column;
    overflow-y:auto;
  }
  #rail .rail-header{
    font-family:var(--mono);font-size:9px;letter-spacing:.28em;
    text-transform:uppercase;color:var(--faint);
    margin-bottom:14px;
  }
  #rail ul{list-style:none}
  #rail li{
    display:flex;align-items:center;gap:10px;
    padding:8px 8px;margin:2px -8px;border-radius:3px;
    font-family:var(--sans);font-size:11px;letter-spacing:.22em;
    text-transform:uppercase;color:var(--ink-soft);
    cursor:pointer;
    transition:background .12s ease, color .12s ease;
  }
  #rail li:hover{background:var(--card-hover);color:var(--ink)}
  #rail li.on{
    color:var(--ink);background:var(--card);
    box-shadow:inset 3px 0 0 var(--pink);
  }
  #rail li .glyph{
    width:14px;height:14px;flex:0 0 14px;color:var(--ink);opacity:.86;
  }
  #rail .hint{
    margin-top:auto;padding-top:22px;
    font-family:var(--serif);font-style:italic;
    font-size:12px;color:var(--faint);line-height:1.5;
  }

  /* ── content ────────────────────────────────────────────────── */
  #content{
    overflow-y:auto;
    padding:36px 44px 60px;
  }
  .panel-header{
    display:flex;align-items:baseline;gap:16px;
    padding-bottom:14px;margin-bottom:22px;
    border-bottom:1px solid var(--rule);
  }
  .panel-header .h{
    font-family:var(--serif);font-style:italic;
    font-size:34px;font-weight:500;
    letter-spacing:.02em;color:var(--ink);
  }
  .panel-header .sub{
    font-family:var(--mono);font-size:10px;letter-spacing:.24em;
    text-transform:uppercase;color:var(--faint);
  }
  .panel-header .count{
    margin-left:auto;
    font-family:var(--mono);font-size:10px;letter-spacing:.18em;
    color:var(--faint);
  }

  /* ── tensions cards ─────────────────────────────────────────── */
  .tensions{display:flex;flex-direction:column;gap:10px}
  .tcard{
    position:relative;
    background:var(--card);
    border:1px solid var(--rule);
    border-radius:2px;
    padding:16px 20px 16px 24px;
    cursor:pointer;
    transition:background .12s ease, border-color .12s ease;
  }
  .tcard:hover{background:var(--card-hover);border-color:#C6BFAD}
  .tcard::before{
    content:"";position:absolute;left:0;top:14px;bottom:14px;width:3px;
    background:var(--pink-soft);
  }
  .tcard.released::before{background:#B6C7B4}
  .tcard-head{
    display:flex;align-items:baseline;gap:14px;
  }
  .tcard-title{
    font-family:var(--serif);font-weight:500;
    font-size:17px;color:var(--ink);line-height:1.3;
    flex:1;
  }
  .tcard-chips{
    display:flex;gap:6px;flex-shrink:0;
  }
  .chip{
    display:inline-flex;align-items:center;padding:2px 8px;
    border:1px solid var(--rule);border-radius:2px;
    font-family:var(--mono);font-size:8.5px;letter-spacing:.2em;
    text-transform:uppercase;color:var(--faint);
    background:var(--ground);
  }
  .chip.status-holding{color:var(--pink);border-color:var(--pink-soft)}
  .chip.status-released{color:#4d7a4b;border-color:#B6C7B4}
  .chip.dot::before{
    content:"";display:inline-block;width:4px;height:4px;
    border-radius:50%;background:currentColor;margin-right:6px;
  }
  .tcard-body{
    display:none;
    margin-top:12px;padding-top:12px;
    border-top:1px dotted var(--rule);
    color:var(--ink-soft);
    font-family:var(--serif);font-size:14.5px;line-height:1.62;
  }
  .tcard.open .tcard-body{display:block}
  .tcard-meta{
    display:flex;gap:16px;margin-top:10px;
    font-family:var(--mono);font-size:9px;letter-spacing:.14em;
    color:var(--faint);text-transform:uppercase;
  }
  .tcard-notes{
    margin-top:10px;padding:10px 12px;
    background:var(--ground-2);border-left:2px solid var(--pink-soft);
    font-family:var(--mono);font-size:11px;color:var(--ink-soft);
    line-height:1.55;
  }
  .tcard-notes .n{margin-bottom:4px}

  /* ── user model panel ───────────────────────────────────────── */
  .um-column{
    max-width:720px;
    font-family:var(--serif);font-size:15.5px;line-height:1.7;color:var(--ink);
  }
  .um-column h2{
    font-family:var(--serif);font-style:italic;font-weight:500;
    font-size:22px;margin:22px 0 10px;color:var(--ink);
  }
  .um-column ul{padding-left:20px;margin:8px 0 14px}
  .um-column li{margin:4px 0}
  .um-column em{color:var(--pink)}
  .um-footer{
    margin-top:32px;padding-top:14px;border-top:1px solid var(--rule);
    font-family:var(--mono);font-size:10px;letter-spacing:.14em;
    color:var(--faint);
  }

  /* ── query panel ────────────────────────────────────────────── */
  .q-wrap{max-width:820px;display:flex;flex-direction:column;gap:12px}
  .q-shell{
    display:flex;flex-direction:column;gap:10px;
    background:var(--card);border:1px solid var(--rule);border-radius:2px;
    padding:14px 16px;
  }
  .q-textarea{
    width:100%;min-height:82px;
    background:transparent;border:none;outline:none;resize:vertical;
    font-family:var(--serif);font-size:15px;line-height:1.55;color:var(--ink);
  }
  .q-actions{display:flex;align-items:center;gap:10px}
  .q-run{
    padding:6px 16px;border:1px solid var(--ink);
    font-family:var(--mono);font-size:10px;letter-spacing:.22em;
    text-transform:uppercase;color:var(--ink);
    background:var(--ground);
  }
  .q-run:hover{background:var(--ink);color:var(--ground)}
  .q-regen{
    font-family:var(--mono);font-size:9.5px;letter-spacing:.18em;
    text-transform:uppercase;color:var(--faint);
    text-decoration:underline;text-decoration-color:var(--pink-soft);
  }
  .q-cache-note{
    margin-left:auto;
    font-family:var(--mono);font-size:9px;letter-spacing:.16em;
    color:var(--faint);text-transform:uppercase;
  }
  .q-answer{
    background:var(--card);border:1px solid var(--rule);
    padding:20px 24px;font-family:var(--serif);font-size:15px;
    line-height:1.7;color:var(--ink);
    white-space:pre-wrap;
    min-height:120px;
  }
  .q-answer.empty{color:var(--faint);font-style:italic}

  /* ── substrate panel ────────────────────────────────────────── */
  .stat-grid{
    display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
    gap:14px;
  }
  .stat{
    background:var(--card);border:1px solid var(--rule);
    padding:16px 18px;border-radius:2px;
  }
  .stat .lbl{
    font-family:var(--mono);font-size:9px;letter-spacing:.24em;
    text-transform:uppercase;color:var(--faint);margin-bottom:6px;
  }
  .stat .val{
    font-family:var(--serif);font-style:italic;font-size:26px;color:var(--ink);
    line-height:1.1;
  }
  .stat .sub{
    margin-top:6px;font-family:var(--mono);font-size:9.5px;color:var(--faint);
    letter-spacing:.06em;
  }
  .launchd-list{
    margin-top:20px;background:var(--card);border:1px solid var(--rule);
    padding:14px 16px;font-family:var(--mono);font-size:11px;color:var(--ink-soft);
    line-height:1.55;
  }
  .launchd-list .lbl{
    font-size:9px;letter-spacing:.24em;text-transform:uppercase;
    color:var(--faint);margin-bottom:6px;
  }

  /* ── bottom ask bar ─────────────────────────────────────────── */
  #bottombar{
    position:fixed;left:0;right:0;bottom:0;height:var(--bottombar-h);z-index:40;
    display:flex;align-items:center;gap:12px;padding:0 24px;
    border-top:1px solid var(--rule);
    background:rgba(244,241,234,.94);
    backdrop-filter:blur(8px);
  }
  #bottombar .bmark{
    font-family:var(--mono);font-size:9px;letter-spacing:.24em;
    text-transform:uppercase;color:var(--faint);
  }
  #ask-input{
    flex:1;height:34px;padding:0 12px;
    border:1px solid var(--rule);background:var(--ground);
    font-family:var(--serif);font-size:14px;color:var(--ink);
    outline:none;
  }
  #ask-input:focus{border-color:var(--pink)}
  #ask-submit{
    padding:6px 16px;border:1px solid var(--ink);
    font-family:var(--mono);font-size:10px;letter-spacing:.22em;
    text-transform:uppercase;color:var(--ink);
  }
  #ask-submit:hover{background:var(--ink);color:var(--ground)}

  /* ── ask overlay (result of bottom bar submit) ─────────────── */
  #ask-overlay{
    display:none;
    position:absolute;top:0;left:0;right:0;bottom:0;
    background:rgba(244,241,234,.96);
    padding:36px 44px;overflow-y:auto;z-index:20;
  }
  #ask-overlay.open{display:block}
  #ask-overlay .oh{
    display:flex;align-items:baseline;gap:12px;margin-bottom:14px;
  }
  #ask-overlay .ot{
    font-family:var(--serif);font-style:italic;font-size:22px;color:var(--ink);
  }
  #ask-overlay .oc{
    margin-left:auto;font-family:var(--mono);font-size:12px;
    color:var(--ink);cursor:pointer;padding:2px 8px;
  }
  #ask-overlay .oc:hover{color:var(--pink)}
  #ask-overlay .oa{
    background:var(--card);border:1px solid var(--rule);
    padding:20px 24px;font-family:var(--serif);font-size:15px;
    line-height:1.7;color:var(--ink);white-space:pre-wrap;
  }
</style>
</head>
<body>

<div id="topbar">
  <div class="wordmark">MIKAI<span class="dot">·</span>INSPECTOR</div>
  <div class="toggle" role="tablist" aria-label="surface toggle">
    <span class="lbl" id="lbl-cockpit">cockpit</span>
    <button class="track" id="surface-toggle" data-mode="inspector" aria-label="switch to cockpit">
      <span class="knob"></span>
    </button>
    <span class="lbl on" id="lbl-inspector">inspector</span>
  </div>
  <div class="ts" id="asof">as of —</div>
</div>

<main>
  <nav id="rail" aria-label="Inspector panels">
    <div class="rail-header">Panels</div>
    <ul id="rail-list"></ul>
    <div class="hint">Diagnostic surface — for tuning, not for acting.</div>
  </nav>

  <section id="content-wrap" style="position:relative;overflow:hidden">
    <div id="content" role="main"></div>
    <div id="ask-overlay" aria-live="polite">
      <div class="oh">
        <div class="ot" id="overlay-title">Ask</div>
        <div class="oc" id="overlay-close" title="close">×</div>
      </div>
      <div class="oa" id="overlay-answer">…</div>
    </div>
  </section>
</main>

<div id="bottombar">
  <div class="bmark">ASK</div>
  <input id="ask-input" type="text" placeholder="Ask something grounded in the substrate…" autocomplete="off" />
  <button id="ask-submit">Run</button>
</div>

<script>
window.__INSPECTOR__ = __STATE__;

(function(){
  var STATE = window.__INSPECTOR__ || {};
  var ASK_URL = (STATE.endpoints && STATE.endpoints.ask_stream)
              || "http://localhost:8210/ask/stream";

  // ── panel registry ────────────────────────────────────────────
  var PANELS = [
    {id:"tensions",  label:"Tensions",  glyph:svgGlyph("dot")},
    {id:"user",      label:"User Model",glyph:svgGlyph("book")},
    {id:"obsessions",label:"Obsessions",glyph:svgGlyph("spiral")},
    {id:"aphorisms", label:"Aphorisms", glyph:svgGlyph("quote")},
    {id:"ideas",     label:"Ideas",     glyph:svgGlyph("bulb")},
    {id:"expertise", label:"Expertise", glyph:svgGlyph("book")},
    {id:"substrate", label:"Substrate", glyph:svgGlyph("hex")},
  ];

  // Minimal inline SVG glyphs — dark filled circles / marks per brief.
  function svgGlyph(kind){
    var c = 'fill="currentColor"';
    var base = '<svg viewBox="0 0 14 14" width="14" height="14" xmlns="http://www.w3.org/2000/svg">';
    var shapes = {
      dot   : '<circle cx="7" cy="7" r="4" '+c+'/>',
      book  : '<rect x="3" y="2.5" width="8" height="9" rx="0.7" '+c+'/><rect x="6.6" y="2.5" width="0.6" height="9" fill="#F4F1EA"/>',
      spiral: '<path d="M7 2c-2.5 0-4 2-4 4s2 3.5 4 3.5 3-1.5 3-3-1-2.5-2.5-2.5S5 5.2 5 6.5 6 8 7 8" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>',
      quote : '<path d="M3.5 4h3v3l-1.5 3H3.5V7h1.5V5.5h-1.5zM8 4h3v3l-1.5 3H8V7h1.5V5.5H8z" '+c+'/>',
      bulb  : '<path d="M7 2.4a3.4 3.4 0 013.4 3.4c0 1.3-.7 2.3-1.6 2.9v1.1H5.2V8.7c-.9-.6-1.6-1.6-1.6-2.9A3.4 3.4 0 017 2.4z" '+c+'/><rect x="5.4" y="10.4" width="3.2" height="1" rx="0.4" '+c+'/><rect x="5.8" y="11.7" width="2.4" height="0.7" rx="0.3" '+c+'/>',
      hex   : '<path d="M7 2.2l4 2.3v4.6l-4 2.3-4-2.3V4.5z" '+c+'/>',
    };
    return base + (shapes[kind]||shapes.dot) + '</svg>';
  }

  // ── boot: rail + as-of + toggle ───────────────────────────────
  var rail = document.getElementById("rail-list");
  PANELS.forEach(function(p){
    var li = document.createElement("li");
    li.dataset.id = p.id;
    li.innerHTML = '<span class="glyph">'+p.glyph+'</span><span>'+p.label+'</span>';
    li.addEventListener("click", function(){ selectPanel(p.id); });
    rail.appendChild(li);
  });

  document.getElementById("asof").textContent =
      "as of " + (STATE.generated_at_human || STATE.generated_at || "—");

  var toggle = document.getElementById("surface-toggle");
  toggle.addEventListener("click", function(){
    // Redirect within the same brain directory.
    var here = window.location.pathname;
    if (here.indexOf("inspector.html") >= 0){
      window.location.href = here.replace("inspector.html","cockpit.html");
    } else {
      window.location.href = "cockpit.html";
    }
  });
  document.getElementById("lbl-cockpit").addEventListener("click", function(){
    toggle.click();
  });

  // ── panel selection ───────────────────────────────────────────
  var CACHE_PREFIX = "mikai.inspector.answer.";
  var CACHE_TS = "mikai.inspector.ts.";
  var current = "tensions";
  function selectPanel(id){
    current = id;
    Array.prototype.forEach.call(rail.children, function(li){
      li.classList.toggle("on", li.dataset.id === id);
    });
    closeOverlay();
    renderPanel(id);
  }

  function renderPanel(id){
    var c = document.getElementById("content");
    c.innerHTML = "";
    if (id === "tensions") return renderTensions(c);
    if (id === "user")     return renderUserModel(c);
    if (id === "substrate")return renderSubstrate(c);
    return renderQueryPanel(c, id);
  }

  // ── TENSIONS ──────────────────────────────────────────────────
  function renderTensions(c){
    var tens = STATE.tensions || [];
    var header = document.createElement("div");
    header.className = "panel-header";
    header.innerHTML =
      '<div class="h">Tensions</div>'+
      '<div class="sub">what MIKAI is holding open</div>'+
      '<div class="count">'+tens.length+' parsed · from wiki.md</div>';
    c.appendChild(header);
    var list = document.createElement("div"); list.className="tensions";
    tens.forEach(function(t){ list.appendChild(tensionCard(t)); });
    c.appendChild(list);
  }

  function tensionCard(t){
    var card = document.createElement("div");
    card.className = "tcard" + (t.status === "released" ? " released" : "");
    var chips = '<span class="chip dot status-'+(t.status||"holding")+'">'
              + (t.status||"holding") + '</span>';
    if (t.section) chips += '<span class="chip">'+esc(t.section)+'</span>';
    card.innerHTML =
      '<div class="tcard-head">'+
        '<div class="tcard-title">'+esc(t.title||"untitled")+'</div>'+
        '<div class="tcard-chips">'+chips+'</div>'+
      '</div>'+
      '<div class="tcard-body">'+
        '<div>'+esc(t.body||"(no body)")+'</div>'+
        '<div class="tcard-meta">'+
          '<span>slug: '+esc(t.slug)+'</span>'+
          (t.first_seen_date ? '<span>first seen: '+esc(t.first_seen_date)+'</span>':'')+
          (t.provenance ? '<span>prov: '+esc(truncate(t.provenance, 60))+'</span>':'')+
        '</div>'+
        (t.notes && t.notes.length
          ? '<div class="tcard-notes">'+ t.notes.map(function(n){
              return '<div class="n">· '+esc((n.at||"")+" — "+(n.text||""))+'</div>';
            }).join("") +'</div>'
          : '');
    card.addEventListener("click", function(){ card.classList.toggle("open"); });
    return card;
  }

  // ── USER MODEL ────────────────────────────────────────────────
  function renderUserModel(c){
    var um = STATE.user_model || {text:""};
    var header = document.createElement("div");
    header.className = "panel-header";
    header.innerHTML =
      '<div class="h">User Model</div>'+
      '<div class="sub">what MIKAI thinks it knows about Brian</div>'+
      '<div class="count">'+(um.bytes||0)+' B</div>';
    c.appendChild(header);

    var col = document.createElement("div");
    col.className = "um-column";
    col.innerHTML = markdownLite(um.text||"(USER_MODEL.md is empty)");
    c.appendChild(col);

    var foot = document.createElement("div");
    foot.className = "um-footer";
    foot.textContent = "compiled by dream-weekly at " +
        (um.mtime||"—") + " · regenerate via `make user-model`";
    c.appendChild(foot);
  }

  // ── CANNED QUERY PANEL ────────────────────────────────────────
  function renderQueryPanel(c, id){
    var q = (STATE.queries||{})[id];
    if (!q){
      c.innerHTML = "<div class='panel-header'><div class='h'>—</div></div>";
      return;
    }
    var header = document.createElement("div");
    header.className = "panel-header";
    header.innerHTML =
      '<div class="h">'+esc(q.title)+'</div>'+
      '<div class="sub">'+esc(q.subtitle||"")+'</div>';
    c.appendChild(header);

    var wrap = document.createElement("div"); wrap.className="q-wrap";
    var shell = document.createElement("div"); shell.className="q-shell";
    var ta = document.createElement("textarea");
    ta.className = "q-textarea";
    ta.value = q.query;
    shell.appendChild(ta);

    var actions = document.createElement("div"); actions.className="q-actions";
    var runBtn = document.createElement("button");
    runBtn.className="q-run"; runBtn.textContent="Run";
    actions.appendChild(runBtn);
    var regen = document.createElement("button");
    regen.className="q-regen"; regen.textContent="regenerate";
    actions.appendChild(regen);
    var cacheNote = document.createElement("span");
    cacheNote.className="q-cache-note";
    actions.appendChild(cacheNote);
    shell.appendChild(actions);
    wrap.appendChild(shell);

    var ans = document.createElement("div");
    ans.className="q-answer empty";
    ans.textContent = "not run yet — press Run.";
    wrap.appendChild(ans);
    c.appendChild(wrap);

    // hydrate from localStorage
    var cached = localStorage.getItem(CACHE_PREFIX + id);
    var cachedTs = localStorage.getItem(CACHE_TS + id);
    if (cached){
      ans.classList.remove("empty");
      ans.textContent = cached;
      cacheNote.textContent = "cached · " + (cachedTs||"—");
    }

    function run(){
      ans.classList.remove("empty");
      ans.textContent = "";
      cacheNote.textContent = "streaming…";
      streamAsk(ta.value, function(chunk){
        ans.textContent += chunk;
      }, function(err){
        if (err){ ans.textContent += "\n\n[stream error: "+err+"]"; }
        var ts = new Date().toISOString().slice(0,19).replace("T"," ");
        localStorage.setItem(CACHE_PREFIX+id, ans.textContent);
        localStorage.setItem(CACHE_TS+id, ts);
        cacheNote.textContent = "cached · " + ts;
      });
    }
    runBtn.addEventListener("click", run);
    regen.addEventListener("click", run);
  }

  // ── SUBSTRATE ─────────────────────────────────────────────────
  function renderSubstrate(c){
    var s = STATE.substrate || {};
    var att = s.attention_last || {};
    var header = document.createElement("div");
    header.className = "panel-header";
    header.innerHTML =
      '<div class="h">Substrate</div>'+
      '<div class="sub">vanity metrics · health audit</div>'+
      '<div class="count">'+(s.wiki_bytes ? (s.wiki_bytes/1e6).toFixed(1)+' MB wiki' : '—')+'</div>';
    c.appendChild(header);

    var grid = document.createElement("div");
    grid.className = "stat-grid";
    grid.innerHTML =
      stat("episodes", (s.episode_count||0), "wiki-episodes.log lines") +
      stat("entities", (s.entity_count||0), "entities/*.md") +
      stat("tensions", (s.tensions_count||0), "parsed from wiki.md") +
      stat("threads",  (s.thread_count||0), "brain/threads/") +
      stat("dismiss·7d",
           s.dismiss_rate_7d!=null ? (s.dismiss_rate_7d*100).toFixed(0)+"%":"—",
           "of " + (s.dismiss_responded_7d||0) + " responded") +
      stat("last ask", s.last_ask||"—", "progress.jsonl") +
      stat("attention",
           att.ts||"—",
           (att.did||"—").slice(0,40)) +
      stat("narrative", s.wiki_narrative_mtime||"—", "dream-nightly") +
      stat("ontology",  s.wiki_ontology_mtime||"—",  "dream-weekly");
    c.appendChild(grid);

    var jobs = (s.launchd_jobs||[]);
    var jobBox = document.createElement("div");
    jobBox.className = "launchd-list";
    jobBox.innerHTML =
      '<div class="lbl">launchd · mikai jobs</div>' +
      (jobs.length
        ? jobs.map(function(j){ return "· "+esc(j); }).join("<br>")
        : '<span style="color:var(--faint)">no mikai jobs found in launchctl list</span>');
    c.appendChild(jobBox);
  }
  function stat(lbl, val, sub){
    return '<div class="stat"><div class="lbl">'+esc(lbl)+
           '</div><div class="val">'+esc(String(val))+
           '</div><div class="sub">'+esc(sub||"")+'</div></div>';
  }

  // ── streaming ask helper (SSE) ────────────────────────────────
  function streamAsk(query, onChunk, onDone){
    var url = ASK_URL + "?q=" + encodeURIComponent(query);
    try{
      var es = new EventSource(url);
      es.addEventListener("token", function(ev){
        try{ var d = JSON.parse(ev.data); if(d.text) onChunk(d.text); }
        catch(_){ onChunk(ev.data); }
      });
      es.addEventListener("message", function(ev){
        // fallback for servers that don't tag events
        try{ var d = JSON.parse(ev.data); if(d.text) onChunk(d.text); }
        catch(_){ onChunk(ev.data); }
      });
      es.addEventListener("done", function(){ es.close(); onDone(null); });
      es.addEventListener("error", function(){
        es.close(); onDone("connection lost");
      });
    } catch (e){ onDone(String(e)); }
  }

  // ── bottom ask bar ────────────────────────────────────────────
  var askInput = document.getElementById("ask-input");
  var askSubmit = document.getElementById("ask-submit");
  var overlay = document.getElementById("ask-overlay");
  var overlayTitle = document.getElementById("overlay-title");
  var overlayAnswer = document.getElementById("overlay-answer");
  document.getElementById("overlay-close").addEventListener("click", closeOverlay);
  function closeOverlay(){ overlay.classList.remove("open"); overlayAnswer.textContent=""; }
  function submitAsk(){
    var q = askInput.value.trim();
    if (!q) return;
    overlayTitle.textContent = "Ask · " + q.slice(0,60) + (q.length>60?"…":"");
    overlayAnswer.textContent = "";
    overlay.classList.add("open");
    streamAsk(q, function(chunk){ overlayAnswer.textContent += chunk; },
      function(err){ if (err) overlayAnswer.textContent += "\n\n["+err+"]"; });
  }
  askSubmit.addEventListener("click", submitAsk);
  askInput.addEventListener("keydown", function(e){
    if (e.key === "Enter") { e.preventDefault(); submitAsk(); }
  });
  document.addEventListener("keydown", function(e){
    if (e.key === "Escape") closeOverlay();
  });

  // ── util ──────────────────────────────────────────────────────
  function esc(s){
    return String(s==null?"":s)
      .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;");
  }
  function truncate(s, n){
    s = String(s||""); return s.length > n ? s.slice(0,n-1)+"…" : s;
  }
  function markdownLite(md){
    // Deliberately tiny renderer — the file is short + hand-authored.
    // Preserves paragraphs, ## headings, - lists, *italics*, `code`.
    md = esc(md);
    md = md.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    md = md.replace(/^# (.+)$/gm, '<h2>$1</h2>');
    var lines = md.split(/\n/);
    var out = []; var inList = false;
    lines.forEach(function(l){
      if (/^- /.test(l)){
        if (!inList){ out.push("<ul>"); inList = true; }
        out.push("<li>" + l.slice(2) + "</li>");
      } else {
        if (inList){ out.push("</ul>"); inList = false; }
        if (l.trim() === "") out.push("");
        else if (/^<h2>/.test(l)) out.push(l);
        else out.push("<p>" + l + "</p>");
      }
    });
    if (inList) out.push("</ul>");
    var html = out.join("\n");
    html = html.replace(/\*([^\n*]+)\*/g, "<em>$1</em>");
    html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    return html;
  }

  // boot
  selectPanel("tensions");
})();
</script>
</body>
</html>
"""


def render_html(state: dict) -> str:
    payload = json.dumps(state, ensure_ascii=False, indent=None)
    return _TEMPLATE.replace("__STATE__", payload)

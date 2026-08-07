"""Inspector HTML template.

Single-file light-theme inspection surface. Companion to the dark
cockpit; matches the enterprise-brain reference (cream ground, dark
ink, faint pink accents, delicate serif titling). The state dict from
``build_state()`` is embedded as ``window.__INSPECTOR__`` and the page
renders entirely from that — no network calls beyond the
``/ask/stream`` EventSource used by the bottom ASK bar.

Deliberate design choices, so future edits stay honest to the brief:

  * The Inspector never asks the user to act. Every panel is a
    read-only lens on what MIKAI has noticed.
  * Five panels — TENSIONS, USER MODEL, L4 SIGNALS, WIKI, SUBSTRATE —
    each backed by real, parsed data. The over-taxonomy of canned-query
    panels (obsessions / aphorisms / ideas / expertise) was deleted:
    the bottom ASK bar covers those asks without dressing them as tabs.
  * L4 SIGNALS absorbs the standalone ~/.mikai/brain/surfacing.html —
    same sections, one diagnostic surface. WIKI is an in-page browser
    over ~/.mikai/wiki/* with client-side substring search.
  * Tensions cards have a Release button that toggles holding ↔
    released. State persists in localStorage as a client-side overlay
    (no HTTP endpoint exists yet for writing back to
    ~/.mikai/console/tensions.json; when one lands, wire it in
    releaseTension()).
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
  /* #content-wrap is a grid item; give it a definite height and
     min-height:0 so its scrollable child can actually shrink and
     scroll (grid items default to min-height:auto → content size,
     which is the classic "scroll doesn't work" bug). */
  #content-wrap{
    position:relative;
    overflow:hidden;
    height:100%;
    min-height:0;
  }
  #content{
    position:absolute;
    inset:0;
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
  .tcard-actions{
    display:flex;align-items:center;gap:12px;
    margin-top:12px;padding-top:10px;
    border-top:1px dotted var(--rule);
  }
  .release-btn{
    padding:4px 12px;border:1px solid var(--ink);
    font-family:var(--mono);font-size:9px;letter-spacing:.22em;
    text-transform:uppercase;color:var(--ink);
    background:var(--ground);border-radius:2px;
  }
  .release-btn:hover{background:var(--ink);color:var(--ground)}
  .tcard.released .release-btn{
    border-color:#4d7a4b;color:#4d7a4b;
  }
  .tcard.released .release-btn:hover{
    background:#4d7a4b;color:var(--ground);
  }
  .release-note{
    font-family:var(--mono);font-size:8.5px;letter-spacing:.14em;
    color:var(--faint);text-transform:uppercase;
  }

  /* ── L4 SIGNALS panel ───────────────────────────────────────── */
  .signals-stamp{
    font-family:var(--mono);font-size:10px;letter-spacing:.16em;
    color:var(--faint);text-transform:uppercase;
    margin-bottom:20px;
  }
  .signals-wrap{display:flex;flex-direction:column;gap:24px;max-width:940px}
  .signals-section{
    background:var(--card);border:1px solid var(--rule);
    padding:16px 20px;border-radius:2px;
  }
  .signals-section h3{
    font-family:var(--mono);font-size:10px;letter-spacing:.24em;
    text-transform:uppercase;color:var(--faint);
    font-weight:500;
    padding-bottom:8px;margin-bottom:10px;
    border-bottom:1px dotted var(--rule);
  }
  .signals-body{
    font-family:var(--serif);font-size:14.5px;color:var(--ink);
    line-height:1.6;
  }
  /* Rehome surfacing.html's inline classes into our theme. */
  .signals-body .head-line{
    font-family:var(--serif);font-style:italic;
    font-size:22px;line-height:1.35;margin:4px 0;
  }
  .signals-body .head-meta{
    font-family:var(--mono);font-size:11px;color:var(--faint);
    letter-spacing:.06em;
  }
  .signals-body .head-quiet{
    font-family:var(--serif);font-style:italic;color:var(--faint);
    font-size:18px;
  }
  .signals-body table{
    border-collapse:collapse;width:100%;
    font-family:var(--mono);font-size:11.5px;
  }
  .signals-body th, .signals-body td{
    text-align:left;padding:6px 12px 6px 0;vertical-align:top;
    border-bottom:1px dotted var(--rule);
  }
  .signals-body th{
    color:var(--faint);font-weight:500;font-size:9px;
    letter-spacing:.14em;text-transform:uppercase;
  }
  .signals-body td.wrap, .signals-body th.wrap{white-space:normal}
  .signals-body td.num, .signals-body th.num{text-align:right;padding-right:14px}
  .signals-body .muted{color:var(--faint)}
  .signals-body .warm{color:var(--pink)}
  .signals-body .cool{color:#4d7a4b}
  .signals-body .quiet-list .item{
    display:inline-block;margin-right:16px;
    font-family:var(--mono);font-size:11px;color:var(--ink-soft);
  }
  .signals-body table.mini{font-size:11px}
  .signals-empty{
    padding:24px;font-style:italic;color:var(--faint);
    background:var(--card);border:1px dashed var(--rule);
  }

  /* ── WIKI panel ─────────────────────────────────────────────── */
  .wiki-shell{
    display:grid;grid-template-columns:220px 1fr;gap:20px;
    align-items:start;
  }
  .wiki-side{
    display:flex;flex-direction:column;gap:2px;
    border:1px solid var(--rule);background:var(--card);
    border-radius:2px;padding:6px;
  }
  .wiki-file{
    display:flex;flex-direction:column;align-items:flex-start;
    padding:8px 10px;border-radius:2px;
    text-align:left;cursor:pointer;
    transition:background .12s ease;
  }
  .wiki-file:hover{background:var(--card-hover)}
  .wiki-file.on{
    background:var(--ground-2);
    box-shadow:inset 2px 0 0 var(--pink);
  }
  .wf-name{
    font-family:var(--mono);font-size:11.5px;color:var(--ink);
  }
  .wf-meta{
    margin-top:2px;font-family:var(--mono);font-size:9px;
    letter-spacing:.1em;color:var(--faint);
  }
  .wiki-main{
    display:flex;flex-direction:column;gap:12px;min-width:0;
  }
  .wiki-search input{
    width:100%;padding:8px 12px;
    border:1px solid var(--rule);background:var(--card);
    font-family:var(--serif);font-size:14px;color:var(--ink);
    outline:none;border-radius:2px;
  }
  .wiki-search input:focus{border-color:var(--pink)}
  .wiki-hint{
    margin-top:6px;font-family:var(--mono);font-size:9px;
    letter-spacing:.12em;color:var(--faint);text-transform:uppercase;
  }
  .wiki-body{
    background:var(--card);border:1px solid var(--rule);
    padding:20px 24px;border-radius:2px;overflow-x:auto;
  }
  .wiki-file-head{margin-bottom:14px;padding-bottom:10px;border-bottom:1px dotted var(--rule)}
  .wfh-name{
    font-family:var(--serif);font-style:italic;
    font-size:20px;color:var(--ink);
  }
  .wfh-meta{
    margin-top:4px;font-family:var(--mono);font-size:10px;
    color:var(--faint);letter-spacing:.08em;
  }
  .wiki-log{
    font-family:var(--mono);font-size:11px;line-height:1.55;
    color:var(--ink-soft);white-space:pre;overflow-x:auto;
  }
  .wiki-md{max-width:none}
  .wiki-results{
    background:var(--card);border:1px solid var(--rule);
    padding:12px 16px;border-radius:2px;
    max-height:none;
  }
  .wiki-results-head{
    font-family:var(--mono);font-size:10px;letter-spacing:.14em;
    color:var(--faint);text-transform:uppercase;
    margin-bottom:10px;padding-bottom:8px;
    border-bottom:1px dotted var(--rule);
  }
  .wiki-hit{
    padding:8px 0;border-bottom:1px dotted var(--rule);cursor:pointer;
  }
  .wiki-hit:last-child{border-bottom:none}
  .wiki-hit:hover{background:var(--card-hover)}
  .wh-file{
    font-family:var(--mono);font-size:10px;letter-spacing:.1em;
    color:var(--pink);text-transform:uppercase;margin-bottom:4px;
  }
  .wh-snip{
    font-family:var(--mono);font-size:11.5px;color:var(--ink-soft);
    white-space:pre-wrap;line-height:1.5;
  }
  .wh-snip mark{
    background:var(--pink-soft);color:var(--ink);padding:0 2px;
    border-radius:2px;
  }
  .wiki-noresults{
    padding:16px;font-style:italic;color:var(--faint);
  }

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

  <section id="content-wrap">
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
  // Only three panels — each backed by real, parsed data. The
  // over-taxonomy of canned-query panels (obsessions / aphorisms /
  // ideas / expertise) was deleted; the bottom ASK bar covers those
  // asks without dressing them as tabs.
  var PANELS = [
    {id:"tensions",  label:"Tensions",  glyph:svgGlyph("dot")},
    {id:"user",      label:"User Model",glyph:svgGlyph("book")},
    {id:"signals",   label:"L4 Signals",glyph:svgGlyph("wave")},
    {id:"wiki",      label:"Wiki",      glyph:svgGlyph("stack")},
    {id:"substrate", label:"Substrate", glyph:svgGlyph("hex")},
  ];

  // Minimal inline SVG glyphs — dark filled circles / marks per brief.
  function svgGlyph(kind){
    var c = 'fill="currentColor"';
    var base = '<svg viewBox="0 0 14 14" width="14" height="14" xmlns="http://www.w3.org/2000/svg">';
    var shapes = {
      dot  : '<circle cx="7" cy="7" r="4" '+c+'/>',
      book : '<rect x="3" y="2.5" width="8" height="9" rx="0.7" '+c+'/><rect x="6.6" y="2.5" width="0.6" height="9" fill="#F4F1EA"/>',
      hex  : '<path d="M7 2.2l4 2.3v4.6l-4 2.3-4-2.3V4.5z" '+c+'/>',
      wave : '<path d="M2 8 Q4 4 7 7 T12 6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
      stack: '<rect x="2.5" y="3" width="9" height="1.6" '+c+'/><rect x="2.5" y="6.2" width="9" height="1.6" '+c+'/><rect x="2.5" y="9.4" width="9" height="1.6" '+c+'/>',
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
    if (id === "signals")  return renderSignals(c);
    if (id === "wiki")     return renderWiki(c);
    if (id === "substrate")return renderSubstrate(c);
    // Unknown panel id (should not happen — rail is closed vocabulary)
    c.innerHTML = "<div class='panel-header'><div class='h'>—</div></div>";
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

  // Tension-status override: released/holding toggle persists in
  // localStorage. When a real POST endpoint against
  // ~/.mikai/console/tensions.json lands, replace the localStorage
  // write in releaseTension() with a fetch to it — the UI contract
  // (button toggles class, chip flips) stays the same.
  var TENSION_OVERRIDES_KEY = "mikai.inspector.tensionOverrides.v1";
  function loadTensionOverrides(){
    try { return JSON.parse(localStorage.getItem(TENSION_OVERRIDES_KEY) || "{}"); }
    catch(_){ return {}; }
  }
  function saveTensionOverrides(o){
    try { localStorage.setItem(TENSION_OVERRIDES_KEY, JSON.stringify(o)); }
    catch(_){ /* quota/private mode — ignore */ }
  }
  function effectiveStatus(t){
    var o = loadTensionOverrides();
    return (o[t.slug] && o[t.slug].status) || t.status || "holding";
  }
  function toggleTensionStatus(slug){
    var o = loadTensionOverrides();
    var current = (o[slug] && o[slug].status) || null;
    // If no override yet, default flips FROM whatever the card carried.
    // We stash the flip target only — the render layer resolves.
    var next = current === "released" ? "holding" : "released";
    o[slug] = {status: next, at: new Date().toISOString()};
    saveTensionOverrides(o);
    return next;
  }

  function tensionCard(t){
    var card = document.createElement("div");
    var status = effectiveStatus(t);
    card.className = "tcard" + (status === "released" ? " released" : "");
    var chips = '<span class="chip dot status-'+status+'" data-role="chip">'
              + status + '</span>';
    if (t.section) chips += '<span class="chip">'+esc(t.section)+'</span>';
    var releaseLabel = status === "released" ? "reopen" : "release";
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
          : '')+
        '<div class="tcard-actions">'+
          '<button class="release-btn" data-role="release">'+releaseLabel+'</button>'+
          '<span class="release-note">local override · not yet synced to console/tensions.json</span>'+
        '</div>'+
      '</div>';
    card.addEventListener("click", function(ev){
      // Ignore clicks on interactive descendants — the button owns them.
      if (ev.target.closest("[data-role=release]")) return;
      card.classList.toggle("open");
    });
    var btn = card.querySelector("[data-role=release]");
    btn.addEventListener("click", function(ev){
      ev.stopPropagation();
      var next = toggleTensionStatus(t.slug);
      // Repaint chip + card class + button label in place — no full
      // re-render (keeps the card open + scroll position stable).
      card.classList.toggle("released", next === "released");
      var chip = card.querySelector("[data-role=chip]");
      chip.className = "chip dot status-" + next;
      chip.textContent = next;
      btn.textContent = next === "released" ? "reopen" : "release";
    });
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

  // ── L4 SIGNALS ────────────────────────────────────────────────
  // Absorbs the former standalone ~/.mikai/brain/surfacing.html.
  // Two code paths:
  //   1. state.l4_signals.sections has raw HTML per section
  //      (parsed from surfacing.html) — render it wrapped in our chrome
  //      so themes align with the rest of the Inspector.
  //   2. state.l4_signals.deliveries/ticks — the fallback path when
  //      surfacing.html is gone; render a small ledger + tick table.
  function renderSignals(c){
    var s = STATE.l4_signals || {};
    var header = document.createElement("div");
    header.className = "panel-header";
    header.innerHTML =
      '<div class="h">L4 Signals</div>'+
      '<div class="sub">what MIKAI is surfacing · Sumimasen ledger</div>'+
      '<div class="count">'+esc(s.source||"—")+
        (s.mtime ? ' · '+esc(s.mtime.slice(0,19).replace("T"," ")) : '')+
        '</div>';
    c.appendChild(header);

    if (s.stamp){
      var stamp = document.createElement("div");
      stamp.className = "signals-stamp";
      stamp.textContent = s.stamp;
      c.appendChild(stamp);
    }

    var wrap = document.createElement("div");
    wrap.className = "signals-wrap";

    var sections = s.sections || {};
    var order = ["attention-head","scored","deliveries",
                 "transitions","engine","quiet"];
    var titles = {
      "attention-head":"Attention head",
      "scored":"Also scoring above zero",
      "deliveries":"Recent deliveries (Sumimasen ledger)",
      "transitions":"Recent state transitions",
      "engine":"Attention Engine — last ticks",
      "quiet":"What MIKAI is choosing to be silent about",
    };
    var rendered = 0;
    order.forEach(function(id){
      if (!sections[id]) return;
      var sec = document.createElement("section");
      sec.className = "signals-section";
      sec.innerHTML =
        '<h3>'+esc(titles[id]||id)+'</h3>'+
        '<div class="signals-body">'+ sections[id] +'</div>';
      wrap.appendChild(sec);
      rendered++;
    });

    // Fallback (source=logs) — render mini tables when we don't have
    // surfacing.html HTML to hand back.
    if (rendered === 0){
      var dels = (s.deliveries||[]);
      var ticks = (s.ticks||[]);
      if (dels.length){
        var d = document.createElement("section");
        d.className = "signals-section";
        d.innerHTML = '<h3>Recent deliveries</h3>' +
          '<div class="signals-body"><table class="mini"><thead>'+
          '<tr><th>ts</th><th>thread</th><th>verdict</th><th>note</th></tr>'+
          '</thead><tbody>'+
          dels.map(function(row){
            var v = row.verdict || row.outcome || "—";
            return '<tr><td class="mono">'+esc((row.ts||"").slice(5,16))+
              '</td><td>'+esc(row.thread||row.slug||"—")+
              '</td><td>'+esc(v)+
              '</td><td>'+esc(truncate(row.note||row.next_step||"",90))+'</td></tr>';
          }).join("") + '</tbody></table></div>';
        wrap.appendChild(d);
      }
      if (ticks.length){
        var e = document.createElement("section");
        e.className = "signals-section";
        e.innerHTML = '<h3>Attention Engine ticks</h3>' +
          '<div class="signals-body"><table class="mini"><thead>'+
          '<tr><th>ts</th><th>mode</th><th>surf</th><th>summary</th></tr>'+
          '</thead><tbody>'+
          ticks.map(function(row){
            return '<tr><td class="mono">'+esc((row.ts||"").slice(5,16))+
              '</td><td>'+esc(row.mode||"")+
              '</td><td>'+esc(String(row.surfaced||0))+
              '</td><td>'+esc(truncate(row.did||"",90))+'</td></tr>';
          }).join("") + '</tbody></table></div>';
        wrap.appendChild(e);
      }
      if (!dels.length && !ticks.length){
        var empty = document.createElement("div");
        empty.className = "signals-empty";
        empty.textContent = "no signals — surfacing.html missing and "+
          "no delivery/progress log entries yet.";
        wrap.appendChild(empty);
      }
    }

    c.appendChild(wrap);
  }

  // ── WIKI ──────────────────────────────────────────────────────
  // File browser + client-side substring search over the wiki dir.
  // Content is pre-inlined at build time; the sidecar's FTS index is
  // ignored here (it needs a live HTTP endpoint — not this static page).
  function renderWiki(c){
    var w = STATE.wiki || {files:[]};
    var files = w.files || [];
    var header = document.createElement("div");
    header.className = "panel-header";
    header.innerHTML =
      '<div class="h">Wiki</div>'+
      '<div class="sub">'+esc(w.dir||"~/.mikai/wiki")+'</div>'+
      '<div class="count">'+files.length+' file(s)</div>';
    c.appendChild(header);

    if (!files.length){
      var e = document.createElement("div");
      e.className = "signals-empty";
      e.textContent = "no wiki files discovered.";
      c.appendChild(e);
      return;
    }

    var shell = document.createElement("div");
    shell.className = "wiki-shell";

    // File list
    var side = document.createElement("nav");
    side.className = "wiki-side";
    files.forEach(function(f, i){
      var li = document.createElement("button");
      li.className = "wiki-file" + (i===0 ? " on" : "");
      li.dataset.idx = String(i);
      li.innerHTML =
        '<span class="wf-name">'+esc(f.name)+'</span>'+
        '<span class="wf-meta">'+
          (f.bytes>1e6 ? (f.bytes/1e6).toFixed(1)+" MB"
                       : (f.bytes/1024).toFixed(0)+" KB")+
          (f.truncated ? " · truncated" : "")+
        '</span>';
      side.appendChild(li);
    });
    shell.appendChild(side);

    // Main pane
    var main = document.createElement("div");
    main.className = "wiki-main";
    var search = document.createElement("div");
    search.className = "wiki-search";
    search.innerHTML =
      '<input id="wiki-q" type="text" placeholder="substring search across all files (case-insensitive)…" autocomplete="off"/>'+
      '<div class="wiki-hint">note: this searches the embedded slices only — full FTS requires the sidecar.</div>';
    main.appendChild(search);
    var results = document.createElement("div");
    results.className = "wiki-results";
    results.id = "wiki-results";
    results.style.display = "none";
    main.appendChild(results);
    var body = document.createElement("div");
    body.className = "wiki-body";
    body.id = "wiki-body";
    main.appendChild(body);
    shell.appendChild(main);
    c.appendChild(shell);

    function showFile(idx){
      var f = files[idx];
      if (!f) return;
      Array.prototype.forEach.call(side.children, function(el, i){
        el.classList.toggle("on", i === idx);
      });
      var head = '<div class="wiki-file-head">'+
        '<div class="wfh-name">'+esc(f.name)+'</div>'+
        '<div class="wfh-meta">'+
          esc(f.path)+
          ' · '+ (f.bytes/1024).toFixed(0) +' KB · mtime '+esc(f.mtime||"—")+
          (f.truncated ? ' · showing '+((f.shown_bytes||0)/1024).toFixed(0)+' KB (head+tail slice)' : '')+
        '</div></div>';
      var content;
      if (f.kind === "log"){
        content = '<pre class="wiki-log">'+esc(f.text||"")+'</pre>';
      } else {
        // Reuse the tiny markdown-lite pass. For wiki.md (large), this
        // is still lightweight — no async parsing library needed.
        content = '<div class="um-column wiki-md">'+markdownLite(f.text||"")+'</div>';
      }
      body.innerHTML = head + content;
      results.style.display = "none";
      body.style.display = "block";
    }
    Array.prototype.forEach.call(side.children, function(el){
      el.addEventListener("click", function(){
        showFile(parseInt(el.dataset.idx, 10));
      });
    });

    var q = search.querySelector("#wiki-q");
    var searchTimer;
    q.addEventListener("input", function(){
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function(){ runSearch(q.value); }, 120);
    });
    function runSearch(needle){
      needle = String(needle||"").trim();
      if (needle.length < 2){
        results.style.display = "none";
        body.style.display = "block";
        return;
      }
      var lower = needle.toLowerCase();
      var hits = [];
      files.forEach(function(f, idx){
        var text = f.text || "";
        var lc = text.toLowerCase();
        var pos = 0;
        while ((pos = lc.indexOf(lower, pos)) !== -1 && hits.length < 60){
          var start = Math.max(0, pos - 60);
          var end   = Math.min(text.length, pos + needle.length + 80);
          hits.push({
            file: f.name,
            idx: idx,
            snippet: (start>0?"…":"") + text.slice(start, end) + (end<text.length?"…":""),
            offset: pos,
          });
          pos = pos + needle.length;
        }
      });
      if (!hits.length){
        results.innerHTML = '<div class="wiki-noresults">no matches for '+esc(needle)+'</div>';
      } else {
        results.innerHTML = '<div class="wiki-results-head">'+hits.length+' match(es) · click to open file</div>' +
          hits.map(function(h){
            var snip = esc(h.snippet).replace(
              new RegExp("("+esc(needle).replace(/[-/\\^$*+?.()|[\]{}]/g,"\\$&")+")","gi"),
              "<mark>$1</mark>");
            return '<div class="wiki-hit" data-idx="'+h.idx+'">'+
              '<div class="wh-file">'+esc(h.file)+'</div>'+
              '<div class="wh-snip">'+snip+'</div></div>';
          }).join("");
        Array.prototype.forEach.call(
          results.querySelectorAll(".wiki-hit"), function(el){
            el.addEventListener("click", function(){
              showFile(parseInt(el.dataset.idx, 10));
            });
        });
      }
      results.style.display = "block";
      body.style.display = "none";
    }

    // First file selected by default
    showFile(0);
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

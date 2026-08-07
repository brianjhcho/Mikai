"""Cockpit HTML template — self-contained constellation view.

Single-file dark-theme instrument. No external assets beyond the
Google Fonts <link>. The dashboard dict is embedded inline as
window.__DASHBOARD__ (T1 snapshot); on load the page attempts
fetch('./state/dashboard.json') and re-renders if newer (T2).
No polling — refresh happens on page load and on the manual reload
button only.

Layout (2026-08-06 refactor, ref: Alassafi enterprise-brain):
  ┌ topbar ──────────────────────────────────────────────────────┐
  │ MIKAI · MAP                                    [loud|all]    │
  ├─────────────┬────────────────────────────────────────────────┤
  │             │                                                │
  │  detail     │        full-height constellation               │
  │  panel      │        (right pane)                            │
  │  (persistent│                                                │
  │   ~380px)   │                                                │
  │             │                                                │
  │             │             ┌ ask bar ┐                       │
  │             │             └─────────┘  ⟳ as of 12:34        │
  └─────────────┴────────────────────────────────────────────────┘

The detail panel is always visible. Default state shows the attention
head + delta strip + "hover a node for details" hint. Hovering a node
(or clicking a hub, center) fills the panel with structured chip-based
fields for the selected item. Escape or clicking empty stage returns
the panel to its default state.
"""

from __future__ import annotations

import json

# NOTE (light theme): this pass ships dark-only, deliberately — the
# constellation is designed as a night instrument. When a light theme
# lands, define the palette as CSS custom properties on :root and add a
# `:root[data-theme="light"]` token block right below the :root block in
# the CSS; components already read colors from one place.

_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MIKAI — cockpit</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600&family=IBM+Plex+Mono:ital,wght@0,400;0,500;1,400&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400;1,6..72,500&display=swap" rel="stylesheet">
<style>
  :root{
    --ground0:#06080D; --ground1:#0A0F1A;
    --ink:#ECEEF2; --faint:#7B8790; --rule:#22282F;
    --warm:#E4A776; --cool:#5EBFA9;
    --panel:#0B111Bf2;
    --panel-w:380px;
    --topbar-h:44px;
    --serif:"Newsreader",Georgia,serif;
    --sans:"Archivo",system-ui,sans-serif;
    --mono:"IBM Plex Mono",ui-monospace,monospace;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%}
  body{
    background:radial-gradient(120% 90% at 62% 42%, var(--ground1) 0%, var(--ground0) 78%);
    color:var(--ink); font-family:var(--serif);
    overflow:hidden;
  }
  button{font:inherit;color:inherit;background:none;border:none;cursor:pointer}
  button:focus-visible{outline:1px solid var(--warm);outline-offset:3px;border-radius:2px}

  /* faint star grain — over stage only, not under the panel */
  #grain{
    position:fixed;top:var(--topbar-h);left:var(--panel-w);right:0;bottom:0;
    pointer-events:none;opacity:.45;z-index:1;
  }

  /* ── top bar ────────────────────────────────────────────────── */
  #topbar{
    position:fixed;top:0;left:0;right:0;height:var(--topbar-h);z-index:50;
    display:flex;align-items:center;justify-content:space-between;
    padding:0 22px;
    border-bottom:1px solid var(--rule);
    background:rgba(6,8,13,.72);
    backdrop-filter:blur(10px);
  }
  #topbar .brand{display:flex;align-items:baseline;gap:14px}
  #topbar .wordmark{
    font-family:var(--sans);font-weight:600;font-size:12px;
    letter-spacing:.42em;text-transform:uppercase;color:var(--ink);
  }
  #topbar .wordmark .dot{color:var(--warm);margin-left:2px}
  #topbar .nav{
    display:flex;gap:18px;
    font-family:var(--mono);font-size:9.5px;letter-spacing:.2em;
    text-transform:uppercase;color:var(--faint);
  }
  #topbar .nav span{padding:4px 0;border-bottom:1px solid transparent}
  #topbar .nav span.on{color:var(--ink);border-bottom-color:var(--warm)}
  #salience-toggle{
    display:inline-flex;gap:2px;font-family:var(--mono);font-size:9px;
    letter-spacing:.14em;text-transform:uppercase;color:var(--faint);
    border:1px solid var(--rule);border-radius:999px;padding:2px;
    background:rgba(11,17,27,.55);
  }
  #salience-toggle button{
    padding:4px 10px;border-radius:999px;color:var(--faint);
    transition:color .2s,background .2s;
  }
  #salience-toggle button:hover{color:var(--ink)}
  #salience-toggle button.on{color:var(--ink);background:rgba(228,167,118,.14)}

  /* ── detail panel (left, persistent) ────────────────────────── */
  #panel{
    position:fixed;top:var(--topbar-h);left:0;bottom:0;width:var(--panel-w);z-index:40;
    background:var(--panel);border-right:1px solid var(--rule);
    backdrop-filter:blur(10px);
    padding:26px 24px 30px;overflow-y:auto;
    scrollbar-width:thin;scrollbar-color:var(--rule) transparent;
  }
  #panel::-webkit-scrollbar{width:6px}
  #panel::-webkit-scrollbar-thumb{background:var(--rule);border-radius:3px}
  #panel-body[hidden]{display:none}
  #panel-default[hidden]{display:none}

  .eyebrow{
    font-family:var(--mono);font-size:8.5px;letter-spacing:.24em;
    text-transform:uppercase;color:var(--faint);margin:22px 0 8px;
  }
  .eyebrow:first-child{margin-top:0}
  #panel h2{
    font-family:var(--serif);font-weight:500;font-style:italic;
    font-size:24px;line-height:1.2;letter-spacing:-.005em;
    text-wrap:balance;margin:6px 0 14px;
  }
  #panel h2.hub{
    font-style:normal;font-size:20px;letter-spacing:.16em;
    text-transform:uppercase;font-weight:500;
  }
  #panel h2 em{font-style:italic}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:4px}
  .chip{
    font-family:var(--mono);font-size:9px;letter-spacing:.12em;text-transform:uppercase;
    border:1px solid var(--rule);border-radius:999px;padding:3.5px 9px;color:var(--faint);
    white-space:nowrap;
  }
  .chip.tint{border-color:color-mix(in srgb,currentColor 45%,transparent);color:currentColor}
  .chip.warm{border-color:#E4A77666;color:var(--warm)}
  .chip.cool{border-color:#5EBFA966;color:var(--cool)}
  #panel p{font-size:14px;line-height:1.55;color:var(--ink)}
  #panel p.soft{color:var(--faint);font-size:13px}
  #panel p.next{
    font-family:var(--serif);font-style:italic;font-size:15.5px;line-height:1.5;
    color:var(--ink);margin:2px 0 4px;
  }
  #panel .log{list-style:none;border-left:1px solid var(--rule);padding-left:14px;
    display:flex;flex-direction:column;gap:9px}
  #panel .log li{font-family:var(--mono);font-size:10.5px;line-height:1.5;color:var(--faint)}
  #panel .log li b{color:var(--ink);font-weight:500}
  #panel .reason{
    border-left:2px solid var(--warm);padding:2px 0 2px 12px;
    font-style:italic;color:var(--ink);font-size:13.5px;line-height:1.5;
  }
  #panel .stat{font-family:var(--mono);font-size:11px;color:var(--ink);line-height:1.7}
  #panel .stat b{font-size:20px;font-weight:500}
  #panel hr{border:0;border-top:1px solid var(--rule);margin:18px 0 0}

  /* do-next card — the one operator affordance; deliberately modest */
  #panel .donext{
    border:1px solid color-mix(in srgb,var(--warm) 28%,var(--rule));
    border-radius:8px;padding:13px 15px 12px;margin:14px 0 2px;
    background:rgba(228,167,118,.045);
  }
  #panel .donext .eyebrow{margin-top:0}
  #panel .donext p.step{font-size:15.5px;line-height:1.45;margin:2px 0 11px;font-family:var(--serif);font-style:italic}
  #panel .did-it{
    font-family:var(--mono);font-size:9px;letter-spacing:.14em;text-transform:uppercase;
    border:1px solid #E4A77666;border-radius:999px;padding:5px 12px;color:var(--warm);
    transition:color .2s,border-color .2s;
  }
  #panel .did-it:hover{color:var(--ink);border-color:var(--warm)}
  #panel .did-it.queued{
    border-color:var(--rule);color:var(--faint);cursor:default;
    text-transform:none;letter-spacing:.03em;
  }
  #panel .did-hint{font-family:var(--mono);font-size:8.5px;color:var(--faint);
    letter-spacing:.04em;margin-top:8px;line-height:1.5}

  /* timeline micro-strip */
  #panel .tl{display:block;width:100%;height:auto;margin-top:2px}

  /* log show-older toggle */
  #panel .log-toggle{
    font-family:var(--mono);font-size:8.5px;letter-spacing:.14em;text-transform:uppercase;
    color:var(--faint);margin:9px 0 0 15px;padding:2px 0;
    border-bottom:1px dotted var(--rule);transition:color .2s;
  }
  #panel .log-toggle:hover{color:var(--ink)}
  #panel .log.older{margin-top:9px}

  /* linked decisions & entangled list */
  #panel .dec{list-style:none;display:flex;flex-direction:column;gap:8px}
  #panel .dec li{font-size:12.5px;line-height:1.5;color:var(--faint)}
  #panel .dec li b{font-family:var(--mono);font-size:10px;color:var(--ink);font-weight:500}

  /* ── default panel: attention head + delta strip ─────────────
     The parallel Opus's attention/delta feed lives here, rendered
     as a vertical stack inside the persistent panel. The rendering
     functions still target #attnhead and #deltastrip verbatim; only
     the CSS layout differs from a floating pill. */
  #attnhead{
    display:block;padding:14px 16px 13px;margin:6px 0 12px;
    border:1px solid var(--rule);border-radius:8px;
    background:rgba(11,17,27,.55);cursor:pointer;
    transition:border-color .2s,background .2s;
  }
  #attnhead:hover{border-color:color-mix(in srgb,var(--warm) 30%,var(--rule));background:rgba(228,167,118,.045)}
  #attnhead[hidden]{display:none}
  #attnhead .caret{
    display:inline-block;font-family:var(--mono);font-size:10px;color:var(--warm);
    letter-spacing:.16em;text-transform:uppercase;margin-bottom:6px;
  }
  #attnhead .title{
    display:block;font-family:var(--serif);font-style:italic;font-weight:500;
    font-size:17px;line-height:1.35;letter-spacing:0;text-transform:none;
    color:var(--ink);margin:2px 0 6px;
  }
  #attnhead .meta{
    display:inline-block;font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;
    color:var(--faint);text-transform:uppercase;
  }
  #attnhead .next{
    display:block;font-family:var(--serif);font-size:13.5px;line-height:1.5;
    color:var(--ink);margin-top:8px;font-style:normal;letter-spacing:0;
  }
  #attnhead[data-mood="warm"] .caret{color:var(--warm)}
  #attnhead[data-mood="cool"] .caret{color:var(--cool)}
  #attnhead[data-mood="muted"]{opacity:.72}
  #attnhead[data-mood="muted"] .caret,
  #attnhead[data-mood="muted"] .title{color:var(--faint)}
  #attnhead[data-quiet="1"]{cursor:default}
  #attnhead[data-quiet="1"]:hover{border-color:var(--rule);background:rgba(11,17,27,.55)}

  #deltastrip{
    display:flex;flex-direction:column;gap:6px;margin:8px 0 4px;
    font-family:var(--mono);font-size:10.5px;line-height:1.5;color:var(--faint);
  }
  #deltastrip[hidden]{display:none}
  #deltastrip .lbl{
    font-family:var(--mono);font-size:8.5px;letter-spacing:.24em;
    text-transform:uppercase;color:var(--faint);margin-bottom:2px;
  }
  #deltastrip .sep{display:none}
  #deltastrip .item{
    display:block;padding-left:10px;border-left:1px solid var(--rule);
    color:var(--faint);cursor:pointer;transition:color .2s,border-left-color .2s;
  }
  #deltastrip .item:hover{color:var(--ink);border-left-color:var(--warm)}
  #deltastrip .item b{font-weight:500;color:var(--ink)}

  #panel .hint{
    font-family:var(--mono);font-size:9.5px;letter-spacing:.06em;
    color:var(--faint);margin-top:22px;padding-top:16px;
    border-top:1px dotted var(--rule);line-height:1.6;
  }

  /* ── constellation stage (right pane) ───────────────────────── */
  #stage{
    position:fixed;top:var(--topbar-h);left:var(--panel-w);right:0;bottom:0;
    z-index:2;
  }
  #wires{position:absolute;inset:0;width:100%;height:100%}

  .hub{position:absolute;transform:translate(-50%,-50%);text-align:center;z-index:5;width:150px}
  .hub .icon{
    width:46px;height:46px;border-radius:50%;
    display:inline-flex;align-items:center;justify-content:center;
    border:1.5px solid;position:relative;
    background:rgba(6,8,13,.55);
    transition:box-shadow .25s;
  }
  .hub[data-tier="secondary"] .icon,.hub[data-tier="misc"] .icon{
    width:38px;height:38px;border-width:1px;
  }
  .hub:hover .icon,.hub:focus-visible .icon{box-shadow:0 0 18px -4px currentColor}
  .hub .icon svg{width:17px;height:17px}
  .hub[data-tier="secondary"] .icon svg{width:14px;height:14px}
  .hub .name{
    display:block;margin-top:10px;
    font-family:var(--serif);font-weight:500;font-size:16px;
    letter-spacing:.24em;text-transform:uppercase;
  }
  .hub[data-tier="secondary"] .name,.hub[data-tier="misc"] .name{
    font-size:12px;letter-spacing:.26em;color:var(--faint);
  }
  .hub[data-tier="misc"] .name{font-style:italic;text-transform:none;letter-spacing:.12em}
  .hub .sub{
    display:block;margin-top:4px;
    font-family:var(--mono);font-size:8.5px;letter-spacing:.1em;
    color:var(--faint);opacity:.85;text-transform:uppercase;
  }

  /* center */
  #center{position:absolute;transform:translate(-50%,-50%);text-align:center;z-index:6}
  #center .icon{
    width:64px;height:64px;border-radius:50%;
    display:inline-flex;align-items:center;justify-content:center;
    border:1px solid var(--faint);color:var(--ink);
    background:rgba(10,15,26,.7);
    transition:box-shadow .25s;
  }
  #center:hover .icon,#center:focus-visible .icon{box-shadow:0 0 26px -6px var(--warm)}
  #center .icon svg{width:26px;height:26px}
  #center .name{
    display:block;margin-top:11px;font-family:var(--sans);font-weight:600;
    font-size:12.5px;letter-spacing:.42em;text-transform:uppercase;text-indent:.42em;
  }
  #center .sub{
    display:block;margin-top:3px;font-family:var(--serif);font-style:italic;
    font-size:11.5px;color:var(--faint);
  }

  /* sub-nodes (threads) */
  .node{position:absolute;transform:translate(-50%,-50%);z-index:8;
    display:flex;align-items:center;gap:7px}
  .node .dot{
    width:11px;height:11px;border-radius:50%;flex:none;position:relative;
    border:1.5px solid transparent;
  }
  .node[data-state="exploring"]  .dot{border-color:var(--faint);background:transparent}
  .node[data-state="evaluating"] .dot{border-color:currentColor;background:transparent}
  .node[data-state="decided"]    .dot{border-color:currentColor;background:currentColor}
  .node[data-state="acting"]     .dot{border-color:currentColor;background:currentColor}
  .node[data-state="stalled"]    .dot{border-color:#E4A776;background:#E4A776}
  .node[data-state="completed"]  .dot{border-color:#4A545E;background:#4A545E}
  .node[data-state="acting"] .dot::after{
    content:"";position:absolute;inset:-5px;border-radius:50%;
    border:1px solid currentColor;opacity:0;
    animation:pulse 2.8s ease-out infinite;
  }
  @keyframes pulse{
    0%{transform:scale(.45);opacity:.7}
    70%{transform:scale(1.15);opacity:0}
    100%{opacity:0}
  }
  .node .check{
    position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
    font-family:var(--mono);font-size:7px;color:var(--ground0);
  }
  .node .over{
    position:absolute;width:5px;height:5px;border-radius:50%;
    background:var(--warm);top:-2px;right:-3px;
    box-shadow:0 0 6px 0 var(--warm);
  }
  .node .lbl{
    font-family:var(--mono);font-size:9px;letter-spacing:.04em;
    color:var(--faint);max-width:120px;white-space:nowrap;
    overflow:hidden;text-overflow:ellipsis;transition:color .2s;
  }
  .node:hover .lbl,.node:focus-visible .lbl{color:var(--ink)}
  .node.flip{flex-direction:row-reverse}

  /* salience: dim = scenery, loud = default styling */
  .node.dim .dot{opacity:.35;filter:saturate(.35)}
  .node.dim .lbl{opacity:.4}
  .node.dim .over{opacity:.5}
  .node.dim[data-state="acting"] .dot::after{opacity:0;animation:none}
  #stage.loud-only .node:not(.loud){display:none}
  #stage.loud-only #wires line{opacity:.3}

  /* ── entity edges (ENTANGLED WITH) ──
     hidden until a node with shared entities is hovered/focused */
  #entity-edges path{
    fill:none;stroke:#5EBFA9;stroke-width:1;stroke-dasharray:4 3;
    opacity:0;transition:opacity .3s;
  }
  #entity-edges circle{fill:var(--warm);opacity:0;transition:opacity .3s}
  #entity-edges path.on{opacity:.28}
  #entity-edges circle.on{opacity:.7}
  .hub,#center,.node{transition:opacity .3s}
  #stage.entangled .hub,#stage.entangled #center,
  #stage.entangled .node:not(.lit){opacity:.4}

  /* ── ask bar (bottom of stage) ──────────────────────────────── */
  #askbar{
    position:fixed;left:calc(var(--panel-w) + 32px);right:220px;bottom:22px;z-index:35;
    max-width:640px;
  }
  #askform{
    display:flex;align-items:center;gap:8px;
    border:1px solid var(--rule);border-radius:999px;
    background:rgba(11,17,27,.82);backdrop-filter:blur(10px);
    padding:6px 8px 6px 18px;transition:border-color .2s;
  }
  #askform:focus-within{border-color:var(--faint)}
  #askq{
    flex:1;min-width:0;background:none;border:none;resize:none;outline:none;
    color:var(--ink);font-family:var(--serif);font-size:14px;line-height:1.4;
    height:20px;
  }
  #askq::placeholder{color:var(--faint);font-style:italic}
  #asksend{
    font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;
    color:var(--warm);border:1px solid #E4A77666;border-radius:999px;padding:6px 13px;
    transition:color .2s,border-color .2s;flex:none;
  }
  #asksend:hover{color:var(--ink);border-color:var(--warm)}
  #asksend:disabled{color:var(--faint);border-color:var(--rule);cursor:default}
  #askload{
    width:7px;height:7px;border-radius:50%;background:var(--warm);flex:none;
    animation:askpulse 1.1s ease-in-out infinite;
  }
  @keyframes askpulse{0%,100%{opacity:.25;transform:scale(.7)}50%{opacity:1;transform:scale(1)}}
  #askhelp{
    display:flex;gap:10px;align-items:flex-start;margin-top:7px;padding:0 18px;
    font-family:var(--mono);font-size:9px;line-height:1.6;color:var(--faint);
    letter-spacing:.03em;
  }
  #askhelp[hidden]{display:none}
  #askhelp button{color:var(--faint);font-family:var(--mono);font-size:11px;padding:0 4px;flex:none}
  #askhelp button:hover{color:var(--ink)}

  /* ask result in the detail panel */
  #panel .ask-answer{font-size:14px;line-height:1.6}
  #panel .ask-answer p{margin:0 0 10px}
  #panel .ask-answer ul{margin:0 0 10px 18px}
  #panel .ask-answer li{font-size:14px;line-height:1.55}
  #panel .ask-answer code{font-family:var(--mono);font-size:12px;color:var(--warm)}
  #panel .ask-foot{
    font-family:var(--mono);font-size:9px;color:var(--faint);line-height:1.7;
    border-top:1px solid var(--rule);padding-top:10px;margin-top:16px;
  }
  #panel .ask-err{
    border-left:2px solid #C96A5E;padding:2px 0 2px 12px;color:#C96A5E;
    font-size:13.5px;line-height:1.5;
  }

  /* ── bottom-right micro-controls (stamp + refresh) ─────────── */
  #corner{
    position:fixed;bottom:22px;right:22px;z-index:35;
    display:flex;align-items:center;gap:10px;
    font-family:var(--mono);font-size:9px;letter-spacing:.08em;
    color:var(--faint);
  }
  #corner #stamp{white-space:nowrap}
  #reload{
    display:inline-flex;align-items:center;gap:6px;
    font-family:var(--mono);font-size:9px;letter-spacing:.14em;
    text-transform:uppercase;color:var(--faint);
    border:1px solid var(--rule);border-radius:999px;padding:5px 10px;
    transition:color .2s,border-color .2s;
    background:rgba(11,17,27,.6);backdrop-filter:blur(6px);
  }
  #reload:hover{color:var(--ink);border-color:var(--faint)}
  #reload svg{width:10px;height:10px}
  #reload.spin svg{animation:spin .7s linear}
  @keyframes spin{to{transform:rotate(360deg)}}

  /* legend kept for a11y but off-screen — the constellation is
     largely self-explanatory once you know the primitives, and the
     footer chrome competed with the map. */
  #legend{position:fixed;left:-9999px;top:0}

  /* ── mobile: stacked cards ──────────────────────────────────── */
  #cards{display:none}
  @media (max-width:899px){
    :root{--panel-w:100%}
    body{overflow:auto}
    #grain{display:none}
    #stage{display:none}
    #topbar{padding:0 16px}
    #topbar .nav{display:none}
    #panel{
      position:static;width:100%;border-right:none;border-bottom:1px solid var(--rule);
      padding:22px 20px;max-height:none;
    }
    #cards{display:flex;flex-direction:column;gap:14px;padding:20px 20px 8px;max-width:640px;margin:0 auto}
    .card{border:1px solid var(--rule);border-radius:10px;padding:16px 18px;background:rgba(11,17,27,.6)}
    .card .head{display:flex;align-items:center;gap:12px;width:100%;text-align:left}
    .card .icon{width:32px;height:32px;border-radius:50%;border:1px solid;flex:none;
      display:inline-flex;align-items:center;justify-content:center}
    .card .icon svg{width:13px;height:13px}
    .card .cname{font-family:var(--sans);font-weight:600;font-size:12px;letter-spacing:.22em;text-transform:uppercase}
    .card .cbrk{font-family:var(--mono);font-size:9px;color:var(--faint);margin-top:3px}
    .card ul{list-style:none;margin-top:12px;display:flex;flex-direction:column;gap:2px}
    .card .row{display:flex;align-items:center;gap:10px;width:100%;text-align:left;
      padding:8px 4px;border-top:1px solid var(--rule)}
    .card .row .lbl{font-family:var(--serif);font-size:15px;flex:1;min-width:0;
      overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:none}
    .card .row .days{font-family:var(--mono);font-size:9px;color:var(--faint)}
    .node-inline{position:static;transform:none}
    #askbar{position:static;left:0;right:0;width:auto;max-width:640px;margin:18px auto 12px;padding:0 20px}
    #corner{position:static;justify-content:flex-end;padding:6px 20px 22px}
  }

  @media (prefers-reduced-motion:reduce){
    .node[data-state="acting"] .dot::after{animation:none;display:none}
    #reload.spin svg{animation:none}
    #askload{animation:none}
    #entity-edges path,#entity-edges circle,.hub,#center,.node{transition:none}
  }
</style>
</head>
<body>
<canvas id="grain" aria-hidden="true"></canvas>

<div id="topbar">
  <div class="brand">
    <div class="wordmark">MIKAI<span class="dot">·</span></div>
    <nav class="nav" aria-label="Views (map only shipped)">
      <span class="on">Map</span>
    </nav>
  </div>
  <div id="salience-toggle" role="group" aria-label="Salience mode">
    <button type="button" data-mode="show-all" class="on">show all</button>
    <button type="button" data-mode="loud-only">loud only</button>
  </div>
</div>

<aside id="panel" role="region" aria-live="polite" aria-label="Detail panel">
  <div id="panel-default">
    <div class="eyebrow">attention</div>
    <div id="attnhead" role="button" tabindex="0" hidden></div>
    <div id="deltastrip" hidden></div>
    <p class="hint">hover a node for details · escape returns here · ask below</p>
  </div>
  <div id="panel-body" hidden></div>
</aside>

<div id="stage" role="application" aria-label="Life constellation">
  <svg id="wires" aria-hidden="true"></svg>
</div>

<div id="cards"></div>

<div id="askbar">
  <form id="askform">
    <textarea id="askq" rows="1" placeholder="Ask MIKAI anything about your substrate…" aria-label="Ask MIKAI"></textarea>
    <span id="askload" hidden aria-hidden="true"></span>
    <button id="asksend" type="submit">ask</button>
  </form>
  <div id="askhelp" hidden>
    <span>answers are grounded in your own substrate — wiki sections (full-text search), entity files, active threads, BRAIN.md priorities, and PROFILE.md. needs the tap endpoint on localhost:8210; a real ask takes 30–60s.</span>
    <button type="button" id="askhelp-x" aria-label="Dismiss help">×</button>
  </div>
</div>

<div id="corner">
  <span id="stamp"></span>
  <button id="reload" type="button" aria-label="Refresh from latest snapshot">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
      <path d="M20 12a8 8 0 1 1-2.3-5.6M20 3v4h-4"/></svg>
    <span>refresh</span>
  </button>
</div>

<div id="legend" aria-hidden="true"></div>

<script>window.__DASHBOARD__ = __DASH_JSON__;</script>
<script>
(function(){
"use strict";

var TINT = {
  ai_work:"#5C7FBE", body:"#5EBFA9", domestic:"#7BB98F", love:"#D4816F",
  misc:"#7B8790"
};
var WARM = "#E4A776";
var COOL = "#5EBFA9";
var GLYPH = {
  ai_work:'<path d="M8 5l-5 7 5 7M16 5l5 7-5 7"/>',
  body:'<path d="M12 4v7M12 11c-2 1-5 3-5 7M12 11c2 1 5 3 5 7"/>',
  domestic:'<path d="M12 20C6.5 16 6.5 8 12 4c5.5 4 5.5 12 0 16zM12 8v10"/>',
  love:'<circle cx="12" cy="14.5" r="5.5"/><path d="M9.4 9.4L12 5l2.6 4.4"/>',
  misc:'<circle cx="12" cy="12" r="2.6"/>',
  center:'<circle cx="12" cy="12" r="3.2"/><circle cx="12" cy="12" r="8.5" stroke-dasharray="2.4 3.4"/>'
};
var STATE_LEGEND = [
  ["exploring","exploring"],["evaluating","evaluating"],["decided","decided"],
  ["acting","acting"],["stalled","stalled"],["completed","completed"]
];

var data = window.__DASHBOARD__;
var embeddedAt = data.generated_at;
var source = "snapshot";
var stage = document.getElementById("stage");
var wires = document.getElementById("wires");
var cards = document.getElementById("cards");
var panel = document.getElementById("panel");
var panelBody = document.getElementById("panel-body");
var panelDefault = document.getElementById("panel-default");

// current panel mode: "default" | "detail"
var panelMode = "default";

function h(tag, cls, html){
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}
function esc(s){
  return String(s == null ? "" : s).replace(/[&<>"]/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];
  });
}
function iconSVG(g){
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' + g + "</svg>";
}
function tintOf(id){ return TINT[id] || TINT.misc; }

/* ── panel ─────────────────────────────────────────────────────────── */
// The panel is persistent. openPanel/closePanel swap between the
// default view (attention head + delta strip) and the detail view.
function openPanel(html){
  panelBody.innerHTML = html;
  panelBody.hidden = false;
  panelDefault.hidden = true;
  panel.scrollTop = 0;
  panelMode = "detail";
}
function closePanel(){
  panelBody.hidden = true;
  panelDefault.hidden = false;
  panelMode = "default";
}
document.addEventListener("keydown", function(e){
  if (e.key === "Escape" && panelMode !== "default") closePanel();
});
// Click on empty stage returns to default. The panel itself, any
// opener, ask bar, reload, and top bar keep their meanings.
document.addEventListener("click", function(e){
  if (panelMode === "default") return;
  if (e.target.closest("#panel, .node, .hub, #center, .card, #reload, #askbar, #topbar")) return;
  closePanel();
});

function chip(txt, cls, color){
  return '<span class="chip ' + (cls||"") + '"' +
    (color ? ' style="color:' + color + '"' : "") + ">" + esc(txt) + "</span>";
}
function logLine(l){
  var m = /^-\s*(\d{4}-\d{2}-\d{2})\s*(\[[^\]]*\])?\s*(.*)$/.exec(l);
  if (m) return "<li><b>" + esc(m[1]) + "</b> " + esc(m[2]||"") + " " + esc(m[3]) + "</li>";
  return "<li>" + esc(l.replace(/^-\s*/, "")) + "</li>";
}
// Full log, newest first. First three visible; the rest behind a
// "show older" toggle — the path is the value, but on demand.
function logHTML(lines){
  if (!lines || !lines.length) return '<p class="soft">no log entries.</p>';
  var rev = lines.slice().reverse();
  var html = '<ul class="log">' + rev.slice(0, 3).map(logLine).join("") + "</ul>";
  var older = rev.slice(3);
  if (older.length){
    html += '<ul class="log older" hidden>' + older.map(logLine).join("") + "</ul>" +
      '<button type="button" class="log-toggle" data-n="' + older.length +
      '">show ' + older.length + " older ↓</button>";
  }
  return html;
}
function timelineHTML(t, tint){
  var entries = [];
  (t.log_full || t.log_recent || []).forEach(function(l){
    var m = /^-\s*(\d{4}-\d{2}-\d{2})\s*(?:\[([^\]]*)\])?/.exec(l);
    if (m){
      var ms = Date.parse(m[1] + "T00:00:00");
      if (!isNaN(ms)) entries.push({ms: ms, s: m[2] || ""});
    }
  });
  if (!entries.length) return "";
  var DAY = 86400000, now = Date.now();
  var lo = Math.min(entries[0].ms, now - 14 * DAY), hi = now;
  var due = t.next_step_due ? Date.parse(t.next_step_due + "T00:00:00") : NaN;
  if (!isNaN(due)){ lo = Math.min(lo, due); hi = Math.max(hi, due); }
  var W = 320, H = 34, P = 8, Y = 16;
  function X(ms){ return P + (ms - lo) / (hi - lo || 1) * (W - 2 * P); }
  var SC = {stalled: "#E4A776", completed: "#4A545E"};
  var s = '<svg class="tl" viewBox="0 0 ' + W + " " + H + '" aria-hidden="true">' +
    '<line x1="' + P + '" y1="' + Y + '" x2="' + (W - P) + '" y2="' + Y +
      '" stroke="var(--rule)" stroke-width="1"/>' +
    '<line x1="' + X(now) + '" y1="' + (Y - 7) + '" x2="' + X(now) + '" y2="' + (Y + 7) +
      '" stroke="var(--faint)" stroke-width="1" opacity=".55"/>';
  if (!isNaN(due) && t.state !== "completed")
    s += '<circle cx="' + X(due) + '" cy="' + Y + '" r="3.4" fill="' +
      (t.overdue ? WARM : "none") + '" stroke="' + WARM + '" stroke-width="1.1"/>';
  entries.forEach(function(e){
    s += '<circle cx="' + X(e.ms) + '" cy="' + Y + '" r="2.4" fill="' +
      (SC[e.s] || tint) + '" opacity=".92"/>';
  });
  var f = "font-family:IBM Plex Mono,monospace;font-size:7.5px;fill:var(--faint)";
  s += '<text x="' + P + '" y="' + (H - 3) + '" style="' + f + '">' +
      new Date(entries[0].ms).toISOString().slice(0, 10) + "</text>" +
    '<text x="' + (W - P) + '" y="' + (H - 3) + '" text-anchor="end" style="' + f + '">today</text></svg>';
  return '<div class="eyebrow">trajectory</div>' + s;
}
function decisionsHTML(t){
  if (!t.decisions || !t.decisions.length) return "";
  return '<div class="eyebrow">linked decisions</div><ul class="dec">' +
    t.decisions.map(function(d){
      return "<li><b>" + esc(d.id) + "</b> · " + esc(d.date) + " — " + esc(d.summary) + "</li>";
    }).join("") + "</ul>";
}
// "Mark done" queues an action for triage: browser JS cannot append to
// a file on disk, so the click copies a ready-to-run shell append
// targeting state/pending_actions.jsonl and remembers the queue in
// localStorage until triage advances the thread (next_step changes).
function doneKey(slug){ return "mikai.done." + slug; }
function queuedFor(t){
  try {
    var v = JSON.parse(localStorage.getItem(doneKey(t.slug)) || "null");
    if (v && v.next_step === t.next_step) return v;
    if (v) localStorage.removeItem(doneKey(t.slug));
  } catch (err) {}
  return null;
}
function doNextHTML(t){
  if (!t.next_step || t.state === "completed") return "";
  var q = queuedFor(t);
  return '<div class="donext"><div class="eyebrow">do next</div>' +
    '<p class="step">' + esc(t.next_step) +
    (t.next_step_due ? ' <span class="chip' + (t.overdue ? " warm" : "") +
      '" style="margin-left:6px">due ' + esc(t.next_step_due) + "</span>" : "") + "</p>" +
    '<button type="button" class="did-it' + (q ? " queued" : "") +
      '" data-slug="' + esc(t.slug) + '" data-step="' + esc(t.next_step) + '"' +
      (q ? " disabled" : "") + ">" +
      (q ? "queued " + esc((q.ts || "").slice(0, 10)) + " — awaiting triage" : "I did it") +
    "</button></div>";
}
panelBody.addEventListener("click", function(e){
  var tog = e.target.closest(".log-toggle");
  if (tog){
    var older = panelBody.querySelector(".log.older");
    if (older){
      older.hidden = !older.hidden;
      tog.textContent = older.hidden ? "show " + tog.dataset.n + " older ↓" : "hide older ↑";
    }
    return;
  }
  var did = e.target.closest(".did-it");
  if (did && !did.classList.contains("queued")){
    var act = JSON.stringify({
      ts: new Date().toISOString(), thread: did.dataset.slug,
      type: "next_step_done", next_step: did.dataset.step, source: "cockpit"
    });
    var path = (data.paths && data.paths.pending_actions) ||
      "$HOME/.mikai/brain/state/pending_actions.jsonl";
    var cmd = "printf '%s\\n' '" + act.replace(/'/g, "'\\''") + "' >> \"" + path + '"';
    var mark = function(copied){
      try { localStorage.setItem(doneKey(did.dataset.slug),
        JSON.stringify({ts: new Date().toISOString(), next_step: did.dataset.step})); } catch (err) {}
      did.classList.add("queued"); did.disabled = true;
      did.textContent = "queued — awaiting triage";
      var hint = h("p", "did-hint", copied
        ? "append command copied — paste in a terminal to queue it for triage."
        : "copy failed — run this to queue it: <code>" + esc(cmd) + "</code>");
      did.parentNode.appendChild(hint);
    };
    if (navigator.clipboard && navigator.clipboard.writeText)
      navigator.clipboard.writeText(cmd).then(
        function(){ mark(true); }, function(){ mark(false); });
    else mark(false);
  }
});
function entangledHTML(slug){
  var edges = (data.entity_edges || []).filter(function(e){
    return e.a === slug || e.b === slug;
  });
  if (!edges.length) return "";
  var titles = {};
  data.departments.forEach(function(d){
    d.threads.forEach(function(t){ titles[t.slug] = t.title; });
  });
  var items = edges.map(function(e){
    var other = e.a === slug ? e.b : e.a;
    return "<li>" + esc(titles[other] || other) +
      ' <span style="color:var(--faint);font-style:italic">via ' + esc(e.via[0]) + "</span></li>";
  });
  return '<div class="eyebrow">entangled with</div><ul class="dec">' + items.join("") + "</ul>";
}
function entitiesHTML(t){
  if (!t.entities || !t.entities.length) return "";
  return '<div class="eyebrow">entities</div><div class="chips">' +
    t.entities.map(function(e){ return chip(e); }).join("") + "</div>";
}
function threadPanel(t, dept){
  var tint = tintOf(dept.id);
  var stateColor = t.state === "stalled" ? WARM :
                   (t.state === "acting" || t.state === "completed") ? COOL : tint;
  var html = '<div class="eyebrow">thread · ' + esc(dept.name) + "</div>" +
    "<h2>" + esc(t.title) + "</h2>" +
    '<div class="chips">' +
      chip("state · " + t.state, "tint", stateColor) +
      (t.days_since != null ? chip("age · " + t.days_since + "d") : "") +
      (t.overdue ? chip("overdue" + (t.overdue_days ? " " + t.overdue_days + "d" : ""), "warm") : "") +
    "</div>";
  html += doNextHTML(t);
  if (t.next_step && t.state === "completed")
    html += '<div class="eyebrow">next step</div><p class="soft">' + esc(t.next_step) + "</p>";
  html += entitiesHTML(t);
  html += entangledHTML(t.slug);
  html += timelineHTML(t, tint);
  html += '<div class="eyebrow">recent log</div>' + logHTML(t.log_full || t.log_recent);
  html += decisionsHTML(t);
  if (t.reason)
    html += '<div class="eyebrow">reason</div><div class="reason">' + esc(t.reason) + "</div>";
  return html;
}
function deptPanel(d){
  var tint = tintOf(d.id);
  var html = '<div class="eyebrow">' + esc(d.tier) + " hub</div>" +
    '<h2 class="hub" style="color:' + tint + '">' + esc(d.name) + "</h2>" +
    '<p class="soft" style="font-family:var(--mono);font-size:9.5px;letter-spacing:.16em;text-transform:uppercase">' +
    esc(d.sub) + "</p>" +
    '<div class="eyebrow">threads</div>' +
    '<p><b style="font-weight:500">' + d.threads.length + "</b> — " + esc(d.breakdown) + "</p>";
  if (d.top_next_step)
    html += '<div class="eyebrow">top next step</div><p class="next">' + esc(d.top_next_step.next_step) +
      '</p><p class="soft" style="margin-top:2px;font-style:italic">— ' + esc(d.top_next_step.title) + "</p>";
  if (d.recent_decision)
    html += '<div class="eyebrow">recent decision</div><p class="soft"><b style="color:var(--ink);font-weight:500">' +
      esc(d.recent_decision.id) + "</b> · " + esc(d.recent_decision.date) + "<br>" +
      esc(d.recent_decision.summary) + "</p>";
  else
    html += '<div class="eyebrow">recent decision</div><p class="soft">none recorded for this hub.</p>';
  return html;
}
function centerPanel(c){
  var rate = Math.round((c.dismiss_rate || 0) * 100);
  var html = '<div class="eyebrow">surface · intervention gate</div>' +
    "<h2><em>Surface</em></h2>" +
    '<div class="chips">' + chip("mikai · noonchi") + chip(c.gate_status, "warm") + "</div>" +
    '<div class="eyebrow">dismiss rate · ' + c.window_days + 'd</div>' +
    '<p class="stat"><b>' + rate + "%</b> &nbsp;of " + c.responded + " responded surface(s)</p>" +
    '<p class="soft">pending responses: ' + c.pending + "</p>";
  if (c.last_surface){
    var ls = c.last_surface;
    html += '<div class="eyebrow">most recent surfaced</div>' +
      "<p>" + esc(ls.thread) + ' <span class="chip" style="margin-left:4px">' + esc(ls.kind) + "</span></p>" +
      (ls.note ? '<div class="reason" style="margin-top:8px">' + esc(ls.note) + "</div>" : "") +
      '<p class="soft" style="margin-top:8px">' + esc((ls.ts||"").slice(0,10)) +
      (ls.days_ago != null ? " · " + ls.days_ago + "d ago" : "") + " · " + esc(ls.response) + "</p>";
  } else {
    html += '<div class="eyebrow">most recent surfaced</div><p class="soft">nothing surfaced yet.</p>';
  }
  return html;
}

function bindOpen(el, fn){
  el.addEventListener("mouseenter", fn);
  el.addEventListener("focus", fn);
  el.addEventListener("click", fn);
}

/* ── attention head + delta strip + salience budget ────────────────── */
function loudSet(){
  var c = (data.center && data.center.loud_slugs) || [];
  var s = {};
  c.forEach(function(x){ s[x] = 1; });
  return s;
}
function threadIndex(){
  var idx = {};
  data.departments.forEach(function(d){
    d.threads.forEach(function(t){ idx[t.slug] = {t: t, d: d}; });
  });
  return idx;
}
function renderAttentionHead(){
  var el = document.getElementById("attnhead");
  var head = (data.center && data.center.attention_head) || null;
  if (!head){ el.hidden = true; return; }
  el.hidden = false;
  if (head.quiet || !head.slug){
    el.dataset.mood = "muted";
    el.dataset.quiet = "1";
    el.innerHTML = '<span class="caret">all quiet</span>' +
      '<span class="title">nothing owed</span>' +
      '<span class="meta">the sky is calm</span>';
    return;
  }
  el.dataset.quiet = "0";
  var st = head.state || "";
  var mood = "muted";
  if (st === "stalled" || (head.reason || "").indexOf("overdue") === 0) mood = "warm";
  else if (st === "acting") mood = "cool";
  el.dataset.mood = mood;
  var days = head.days_since_state || 0;
  var meta = st + (days ? " · " + days + "d" : "");
  var caret = head.reason || "attention";
  el.innerHTML =
    '<span class="caret">' + esc(caret) + "</span>" +
    '<span class="title">' + esc(head.title) + "</span>" +
    '<span class="meta">' + esc(meta) + "</span>" +
    (head.next_step ? '<span class="next">' + esc(head.next_step) + "</span>" : "");
  el.onclick = function(){
    var e = threadIndex()[head.slug];
    if (e) openPanel(threadPanel(e.t, e.d));
  };
  el.onkeydown = function(ev){
    if (ev.key === "Enter" || ev.key === " "){ ev.preventDefault(); el.click(); }
  };
}
function renderDeltaStrip(){
  var el = document.getElementById("deltastrip");
  var deltas = (data.center && data.center.delta_strip) || [];
  if (!deltas.length){ el.hidden = true; el.innerHTML = ""; return; }
  el.hidden = false;
  var parts = ['<span class="lbl">what changed</span>'];
  var idx = threadIndex();
  deltas.forEach(function(d){
    var slug = d.slug || "";
    var label = '<b>' + esc(slug) + "</b> — " + esc(d.desc || "");
    if (idx[slug]){
      parts.push('<span class="item" data-slug="' + esc(slug) + '">' + label + "</span>");
    } else {
      parts.push('<span class="item" style="cursor:default">' + label + "</span>");
    }
  });
  el.innerHTML = parts.join("");
  Array.prototype.forEach.call(el.querySelectorAll(".item[data-slug]"), function(node){
    node.addEventListener("click", function(){
      var e = threadIndex()[node.dataset.slug];
      if (e) openPanel(threadPanel(e.t, e.d));
    });
  });
}

/* ── constellation ─────────────────────────────────────────────────── */
function nodeButton(t, dept, isLoud){
  var tint = tintOf(dept.id);
  var b = h("button", "node" + (isLoud ? " loud" : " dim"));
  b.type = "button";
  b.dataset.state = t.state;
  b.dataset.slug = t.slug;
  b.style.color = tint;
  b.setAttribute("aria-label", t.title + " — " + t.state);
  var dot = h("span", "dot");
  if (t.state === "completed") dot.appendChild(h("span", "check", "✓"));
  if (t.overdue) dot.appendChild(h("span", "over"));
  b.appendChild(dot);
  var lbl = h("span", "lbl", esc(t.title.length > 26 ? t.title.slice(0, 25) + "…" : t.title));
  b.appendChild(lbl);
  bindOpen(b, function(){ openPanel(threadPanel(t, dept)); });
  return b;
}

function renderConstellation(){
  stage.querySelectorAll(".hub,.node,#center").forEach(function(e){ e.remove(); });
  var W = stage.clientWidth, H = stage.clientHeight;
  wires.setAttribute("viewBox", "0 0 " + W + " " + H);
  wires.innerHTML = "";
  var cx = W * 0.5, cy = H * 0.5;
  var rx = Math.min(W * 0.36, 460), ry = Math.min(H * 0.34, 310);

  // center node
  var c = h("button", null, null); c.id = "center"; c.type = "button";
  c.setAttribute("aria-label", "Surface — intervention gate");
  c.style.left = cx + "px"; c.style.top = cy + "px";
  c.innerHTML = '<span class="icon">' + iconSVG(GLYPH.center) + "</span>" +
    '<span class="name">Surface</span><span class="sub">MIKAI · noonchi</span>';
  bindOpen(c, function(){ openPanel(centerPanel(data.center)); });
  stage.appendChild(c);

  var nodePos = {};   // slug → {x,y} of the placed sub-node
  var nodeEls = {};   // slug → button element
  var loud = loudSet();

  var depts = data.departments;
  var n = depts.length;
  depts.forEach(function(d, i){
    var ang = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    var hx = cx + rx * Math.cos(ang), hy = cy + ry * Math.sin(ang);
    var tint = tintOf(d.id);

    // wire: center → hub, with warm flow dots
    line(cx, cy, hx, hy, "rgba(123,135,144,.16)", 1);
    [0.42, 0.68].forEach(function(t){
      dotAt(cx + (hx - cx) * t, cy + (hy - cy) * t, 1.4, "rgba(228,167,118,.55)");
    });

    var hub = h("button", "hub"); hub.type = "button";
    hub.dataset.tier = d.tier;
    hub.style.left = hx + "px"; hub.style.top = hy + "px";
    hub.style.color = tint;
    hub.setAttribute("aria-label", d.name + " — " + d.breakdown);
    hub.innerHTML =
      '<span class="icon" style="border-color:' + tint + (d.tier !== "primary" ? "99" : "") + ';color:' + tint + '">' +
        iconSVG(GLYPH[d.id] || GLYPH.misc) + "</span>" +
      '<span class="name" style="' + (d.tier === "primary" ? "color:var(--ink)" : "") + '">' + esc(d.name) + "</span>" +
      '<span class="sub">' + esc(d.sub) + "</span>";
    bindOpen(hub, function(){ openPanel(deptPanel(d)); });
    stage.appendChild(hub);

    // sub-nodes fan outward from the hub, away from center
    d.threads.forEach(function(t, k){
      var count = d.threads.length;
      var spread = Math.min(0.95, 0.5 * count);
      var off = count === 1 ? 0 : (k / (count - 1) - 0.5) * spread;
      var dist = 96 + (k % 2) * 26;
      var na = ang + off;
      var nx = hx + dist * Math.cos(na), ny = hy + dist * Math.sin(na);
      // keep on-stage
      nx = Math.max(30, Math.min(W - 30, nx));
      ny = Math.max(40, Math.min(H - 70, ny));
      line(hx, hy, nx, ny, "color-mix(in srgb," + tint + " 26%,transparent)", 1);
      var b = nodeButton(t, d, !!loud[t.slug]);
      b.style.left = nx + "px"; b.style.top = ny + "px";
      if (Math.cos(na) < -0.15) b.classList.add("flip"); // label toward outer edge
      nodePos[t.slug] = {x: nx, y: ny};
      nodeEls[t.slug] = b;
      b.addEventListener("mouseenter", function(){ focusEdges(t.slug); });
      b.addEventListener("focus", function(){ focusEdges(t.slug); });
      b.addEventListener("mouseleave", unfocusEdges);
      b.addEventListener("blur", unfocusEdges);
      stage.appendChild(b);
    });
  });

  // ── entity edges: shared-entity curves between threads ──
  var SVGNS = "http://www.w3.org/2000/svg";
  var edgesG = document.createElementNS(SVGNS, "g");
  edgesG.id = "entity-edges";
  wires.appendChild(edgesG);
  var edgeEls = [];
  (data.entity_edges || []).forEach(function(e){
    var A = nodePos[e.a], B = nodePos[e.b];
    if (!A || !B) return;
    var mx = (A.x + B.x) / 2, my = (A.y + B.y) / 2;
    var dx = mx - cx, dy = my - cy, dd = Math.sqrt(dx*dx + dy*dy);
    var span = Math.sqrt((B.x-A.x)*(B.x-A.x) + (B.y-A.y)*(B.y-A.y)) || 1;
    var lift = Math.min(130, 36 + span * 0.18);
    var ux, uy;
    if (dd < 24){
      ux = -(B.y - A.y) / span; uy = (B.x - A.x) / span;
      if (uy > 0){ ux = -ux; uy = -uy; }
    } else {
      ux = dx / dd; uy = dy / dd;
    }
    var qx = mx + ux * lift, qy = my + uy * lift;
    var p = document.createElementNS(SVGNS, "path");
    p.setAttribute("d", "M" + A.x + " " + A.y + " Q " + qx + " " + qy + " " + B.x + " " + B.y);
    edgesG.appendChild(p);
    var dot = document.createElementNS(SVGNS, "circle");
    dot.setAttribute("cx", 0.25*A.x + 0.5*qx + 0.25*B.x);
    dot.setAttribute("cy", 0.25*A.y + 0.5*qy + 0.25*B.y);
    dot.setAttribute("r", 1.7);
    edgesG.appendChild(dot);
    edgeEls.push({a: e.a, b: e.b, path: p, dot: dot});
  });

  function focusEdges(slug){
    var hit = false;
    edgeEls.forEach(function(e){
      var on = e.a === slug || e.b === slug;
      e.path.classList.toggle("on", on);
      e.dot.classList.toggle("on", on);
      if (on){
        hit = true;
        var other = nodeEls[e.a === slug ? e.b : e.a];
        if (other) other.classList.add("lit");
      }
    });
    if (hit){
      if (nodeEls[slug]) nodeEls[slug].classList.add("lit");
      stage.classList.add("entangled");
    }
  }
  function unfocusEdges(){
    stage.classList.remove("entangled");
    edgeEls.forEach(function(e){
      e.path.classList.remove("on"); e.dot.classList.remove("on");
    });
    Object.keys(nodeEls).forEach(function(s){ nodeEls[s].classList.remove("lit"); });
  }

  function line(x1, y1, x2, y2, stroke, w){
    var l = document.createElementNS("http://www.w3.org/2000/svg", "line");
    l.setAttribute("x1", x1); l.setAttribute("y1", y1);
    l.setAttribute("x2", x2); l.setAttribute("y2", y2);
    l.setAttribute("stroke", stroke); l.setAttribute("stroke-width", w);
    wires.appendChild(l);
  }
  function dotAt(x, y, r, fill){
    var d = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    d.setAttribute("cx", x); d.setAttribute("cy", y); d.setAttribute("r", r);
    d.setAttribute("fill", fill);
    wires.appendChild(d);
  }
}

/* ── mobile cards ──────────────────────────────────────────────────── */
function renderCards(){
  cards.innerHTML = "";
  // Surface card first
  var sc = h("div", "card");
  var sh = h("button", "head"); sh.type = "button";
  sh.innerHTML = '<span class="icon" style="border-color:var(--faint);color:var(--ink)">' +
    iconSVG(GLYPH.center) + '</span><span><div class="cname">Surface</div>' +
    '<div class="cbrk">' + esc(data.center.gate_status) + "</div></span>";
  bindOpen(sh, function(){ openPanel(centerPanel(data.center)); });
  sc.appendChild(sh); cards.appendChild(sc);

  data.departments.forEach(function(d){
    var tint = tintOf(d.id);
    var card = h("div", "card");
    var head = h("button", "head"); head.type = "button";
    head.innerHTML = '<span class="icon" style="border-color:' + tint + ";color:" + tint + '">' +
      iconSVG(GLYPH[d.id] || GLYPH.misc) + "</span>" +
      '<span><div class="cname" style="color:' + (d.tier === "primary" ? "var(--ink)" : "var(--faint)") + '">' +
      esc(d.name) + '</div><div class="cbrk">' + esc(d.breakdown) + "</div></span>";
    bindOpen(head, function(){ openPanel(deptPanel(d)); });
    card.appendChild(head);
    if (d.threads.length){
      var ul = h("ul");
      d.threads.forEach(function(t){
        var li = h("li");
        var row = h("button", "row node node-inline"); row.type = "button";
        row.dataset.state = t.state; row.style.color = tint;
        var dot = h("span", "dot");
        if (t.state === "completed") dot.appendChild(h("span", "check", "✓"));
        if (t.overdue) dot.appendChild(h("span", "over"));
        row.appendChild(dot);
        row.appendChild(h("span", "lbl", esc(t.title)));
        row.appendChild(h("span", "days", t.days_since != null ? t.days_since + "d" : ""));
        bindOpen(row, function(){ openPanel(threadPanel(t, d)); });
        li.appendChild(row); ul.appendChild(li);
      });
      card.appendChild(ul);
    }
    cards.appendChild(card);
  });
}

/* ── chrome ────────────────────────────────────────────────────────── */
function renderLegend(){
  // Kept as an off-screen a11y-only listing; the constellation UI
  // stopped shipping a visible legend row in the 2026-08-06 refactor.
  var lg = document.getElementById("legend");
  lg.innerHTML = STATE_LEGEND.map(function(s){
    return "<span>" + s[1] + "</span>";
  }).join("");
}
function renderStamp(){
  document.getElementById("stamp").textContent =
    "as of " + data.generated_at_human + " · " + source;
}
function renderAll(){
  renderAttentionHead();
  renderDeltaStrip();
  renderConstellation();
  renderCards();
  renderLegend();
  renderStamp();
  // If the panel was in default mode, keep it there; a re-render
  // shouldn't yank the user out of a detail view they were reading.
  if (panelMode === "default") closePanel();
}

/* ── salience toggle (show all · loud only), persisted in localStorage ── */
var SAL_KEY = "mikai.cockpit.salience";
function applySalienceMode(mode){
  stage.classList.toggle("loud-only", mode === "loud-only");
  var buttons = document.querySelectorAll("#salience-toggle button");
  Array.prototype.forEach.call(buttons, function(btn){
    btn.classList.toggle("on", btn.dataset.mode === mode);
  });
}
(function initSalience(){
  var stored = "show-all";
  try {
    var v = localStorage.getItem(SAL_KEY);
    if (v === "loud-only" || v === "show-all") stored = v;
  } catch (err){}
  document.querySelectorAll("#salience-toggle button").forEach(function(btn){
    btn.addEventListener("click", function(){
      var m = btn.dataset.mode;
      try { localStorage.setItem(SAL_KEY, m); } catch (err){}
      applySalienceMode(m);
    });
  });
  // apply after first render — renderAll runs at the bottom of this IIFE
  setTimeout(function(){ applySalienceMode(stored); }, 0);
})();

/* ── star grain ────────────────────────────────────────────────────── */
function grain(){
  var cv = document.getElementById("grain");
  var r = cv.getBoundingClientRect();
  cv.width = r.width || innerWidth;
  cv.height = r.height || innerHeight;
  var g = cv.getContext("2d");
  g.clearRect(0, 0, cv.width, cv.height);
  for (var i = 0; i < 120; i++){
    var x = Math.random() * cv.width, y = Math.random() * cv.height;
    g.fillStyle = "rgba(200,215,235," + (Math.random() * 0.16 + 0.03) + ")";
    g.beginPath(); g.arc(x, y, Math.random() * 0.9 + 0.2, 0, 7); g.fill();
  }
}

/* ── T2: refresh on load + manual reload (no polling) ──────────────── */
function tryRefresh(manual){
  var btn = document.getElementById("reload");
  if (manual) btn.classList.add("spin");
  return fetch("./state/dashboard.json", {cache: "no-store"})
    .then(function(r){ if (!r.ok) throw 0; return r.json(); })
    .then(function(j){
      if (j && j.generated_at && j.generated_at !== data.generated_at){
        data = j;
        renderAll();
      }
      source = j.generated_at === embeddedAt ? "snapshot · live" : "refreshed from state/";
      renderStamp();
    })
    .catch(function(){ /* file:// or missing state — embedded snapshot stands */ })
    .then(function(){ setTimeout(function(){ btn.classList.remove("spin"); }, 700); });
}
document.getElementById("reload").addEventListener("click", function(){ tryRefresh(true); });

/* ── ask bar → tap endpoint → detail panel ─────────────────────────── */
var ASK_BASE = "http://localhost:8210";
var ASK_STREAM_URL = ASK_BASE + "/ask/stream";
var askQ = document.getElementById("askq");
var askSend = document.getElementById("asksend");
var askLoad = document.getElementById("askload");
var askHelp = document.getElementById("askhelp");
var HELP_KEY = "mikai.askhelp.dismissed";
try { if (!localStorage.getItem(HELP_KEY)) askHelp.hidden = false; }
catch (err) { askHelp.hidden = false; }
document.getElementById("askhelp-x").addEventListener("click", function(){
  askHelp.hidden = true;
  try { localStorage.setItem(HELP_KEY, "1"); } catch (err) {}
});

// Tiny markdown-ish renderer: escape first, then bold / inline code /
// italics / headings / bullets / paragraphs. Not a parser — just enough
// for LLM prose.
function mdHTML(text){
  var out = [], para = [], list = null;
  function inline(s){
    return esc(s)
      .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/(^|[\s(])\*([^*\s][^*]*)\*(?=[\s).,;:!?]|$)/g, "$1<i>$2</i>");
  }
  function flushPara(){
    if (para.length){ out.push("<p>" + para.map(inline).join("<br>") + "</p>"); para = []; }
  }
  function flushList(){
    if (list){ out.push("<ul>" + list.join("") + "</ul>"); list = null; }
  }
  String(text || "").split(/\r?\n/).forEach(function(l){
    var t = l.trim();
    if (!t){ flushPara(); flushList(); return; }
    var mh = /^(#{1,4})\s+(.*)$/.exec(t);
    if (mh){
      flushPara(); flushList();
      out.push('<p style="font-weight:600;margin-top:4px">' + inline(mh[2]) + "</p>");
      return;
    }
    var mb = /^[-*]\s+(.*)$/.exec(t);
    if (mb){ flushPara(); (list = list || []).push("<li>" + inline(mb[1]) + "</li>"); return; }
    flushList(); para.push(t);
  });
  flushPara(); flushList();
  return out.join("");
}
function askFootHTML(r){
  r = r || {};
  var ents = (r.entities || []).join(", ") || "—";
  var thrs = (r.threads || []).join(", ") || "—";
  return 'Retrieved: ' + (r.wiki_hits != null ? r.wiki_hits : "?") +
    " wiki sections · entities: " + esc(ents) + " · threads: " + esc(thrs) +
    " · prompt: " + (r.prompt_chars != null ? r.prompt_chars.toLocaleString() : "?") +
    " chars";
}
function askSkeletonHTML(query){
  return '<div class="eyebrow">ask · grounded in your substrate</div>' +
    "<h2>" + esc(query) + "</h2>" +
    '<div id="ask-status" class="soft" style="font-family:var(--mono);font-size:10px;letter-spacing:.08em;margin:0 0 12px">' +
      '<span id="ask-status-dot" style="display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--warm);margin-right:6px;animation:askpulse 1.1s ease-in-out infinite;vertical-align:middle"></span>' +
      '<span id="ask-status-text">retrieving substrate…</span>' +
    "</div>" +
    '<div class="ask-answer" id="ask-answer-body"></div>' +
    '<div class="ask-foot" id="ask-foot">…</div>';
}
function askErrPanel(query, msg){
  return '<div class="eyebrow">ask · error</div>' +
    "<h2>" + esc(query) + "</h2>" +
    '<div class="ask-err">' + esc(msg) + "</div>" +
    '<p class="soft" style="margin-top:12px">is the tap endpoint up? ' +
    '<code style="font-family:var(--mono);font-size:10.5px">launchctl kickstart -k gui/$UID/com.mikai.tap-endpoint</code></p>';
}
var askBusy = false;
var askES = null;
function closeES(){
  if (askES){ try { askES.close(); } catch (e) {} askES = null; }
}
function submitAsk(){
  var q = askQ.value.trim();
  if (!q || askBusy) return;
  askBusy = true; askSend.disabled = true; askLoad.hidden = false;

  openPanel(askSkeletonHTML(q));
  var body = document.getElementById("ask-answer-body");
  var foot = document.getElementById("ask-foot");
  var statusText = document.getElementById("ask-status-text");
  var statusDot = document.getElementById("ask-status-dot");
  var raw = "";

  function stopUI(){
    askBusy = false; askSend.disabled = false; askLoad.hidden = true;
    if (statusDot) statusDot.style.animation = "none";
  }
  function finish(msg){
    if (statusText) statusText.textContent = msg;
    if (statusDot) statusDot.style.display = "none";
    stopUI();
    closeES();
  }
  function fail(msg){
    closeES();
    openPanel(askErrPanel(q, msg));
    stopUI();
  }

  if (!("EventSource" in window)){
    fail("this browser has no EventSource — streaming ask is unavailable");
    return;
  }

  closeES();
  var url = ASK_STREAM_URL + "?q=" + encodeURIComponent(q);
  try {
    askES = new EventSource(url);
  } catch (err){
    fail("could not open stream: " + (err && err.message ? err.message : err));
    return;
  }

  var watchdog = setTimeout(function(){
    if (askBusy) fail("no response from the ask endpoint after 30s");
  }, 30000);
  function ping(){ clearTimeout(watchdog); watchdog = setTimeout(function(){
    if (askBusy) fail("stream stalled — the LLM stopped emitting text");
  }, 60000); }

  askES.addEventListener("retrieved", function(ev){
    ping();
    try {
      var payload = JSON.parse(ev.data || "{}");
      if (foot) foot.innerHTML = askFootHTML(payload.data || {});
      if (statusText) statusText.textContent = "MIKAI is thinking…";
    } catch (err){}
  });
  askES.addEventListener("chunk", function(ev){
    ping();
    try {
      var payload = JSON.parse(ev.data || "{}");
      if (typeof payload.text === "string" && payload.text){
        raw += payload.text;
        if (body) body.innerHTML = mdHTML(raw);
      }
    } catch (err){}
  });
  askES.addEventListener("done", function(ev){
    clearTimeout(watchdog);
    try {
      var payload = JSON.parse(ev.data || "{}");
      if (typeof payload.answer === "string" && payload.answer){
        raw = payload.answer;
        if (body) body.innerHTML = mdHTML(raw);
      }
    } catch (err){}
    finish("done");
  });
  askES.addEventListener("error", function(ev){
    clearTimeout(watchdog);
    var msg = "";
    try { msg = (JSON.parse(ev.data || "{}") || {}).error || ""; } catch (e){}
    if (!msg) msg = "the stream ended unexpectedly (endpoint down, or CORS?)";
    fail(msg);
  });
}
document.getElementById("askform").addEventListener("submit", function(e){
  e.preventDefault(); submitAsk();
});
askQ.addEventListener("keydown", function(e){
  if (e.key === "Enter" && !e.shiftKey){ e.preventDefault(); submitAsk(); }
});

var resizeT;
window.addEventListener("resize", function(){
  clearTimeout(resizeT);
  resizeT = setTimeout(function(){ grain(); renderConstellation(); }, 150);
});

grain();
renderAll();
tryRefresh(false);
try { localStorage.setItem("mikai:last_open", String(Date.now())); }
catch (err) {}
})();
</script>
</body>
</html>
"""


def render_html(dashboard: dict) -> str:
    payload = json.dumps(dashboard, ensure_ascii=False)
    payload = payload.replace("</", "<\\/")  # never terminate the script tag
    return _TEMPLATE.replace("__DASH_JSON__", payload)

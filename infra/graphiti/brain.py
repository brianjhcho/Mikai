"""
brain.py — "search bar for your own brain."

A tiny local web app: type a concept ("3d ocean farming") and MIKAI returns what
YOU actually thought/wrote about it — the ontology wiki's cross-time synthesis on
top, then the source episodes as a dated timeline.

It reuses the live retrieval stack:
  - the sidecar's hybrid /search (vector + BM25 + RRF) to rank relevant edges,
  - Neo4j to fetch the raw source prose behind those edges (your own words),
  - the ontology wiki (~/.mikai/wiki/wiki-ontology-v1.md) for the synthesized take.

Served locally (not an Artifact) because it must reach localhost:8100 + Neo4j.

Run:
    python brain.py           # serves http://localhost:8200
Requires the sidecar (localhost:8100) + Neo4j up. Env from ~/.mikai/launchd.env.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from neo4j import GraphDatabase

MIKAI_DIR = Path.home() / ".mikai"
ENV_FILE = MIKAI_DIR / "launchd.env"
WIKI_PATH = MIKAI_DIR / "wiki" / "wiki-ontology-v1.md"
SIDECAR = "http://localhost:8100"
PORT = 8200


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


load_env()
_DRIVER = GraphDatabase.driver(
    os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
    auth=(os.environ.get("NEO4J_USER", "neo4j"),
          os.environ.get("NEO4J_PASSWORD", "mikai-local-dev")),
)

SOURCE_LABELS = {
    "claude-thread": "Claude", "claude-code": "Terminal",
    "apple-notes": "Note", "perplexity": "Perplexity", "mikai-default": "Archive",
}

# When MIKAI's own build sessions (claude-code / claude-thread) discuss a concept
# as a DATA POINT ("the graph split ocean farming across nodes"), that's meta-
# noise, not the user's genuine engagement with the concept. Tell: the concept
# co-occurs with system vocabulary. Such episodes are demoted below real traces.
_META_WORDS = re.compile(
    r"\b(graph|wiki|episode|node|dimension|mikai|neo4j|graphiti|consolidat|"
    r"ingest|embedding|deepseek|dream\.py|sidecar|schema|dedup|extraction)\b",
    re.I,
)


def _relevance(content: str, phrase: str, terms: list[str], group: str) -> float:
    """Higher = more genuinely about the query. Rewards exact-phrase and
    all-terms matches; penalizes single-loose-token hits and MIKAI meta-chatter."""
    low = content.lower()
    hits = [t for t in terms if t in low]
    if not hits:
        return 0.0
    score = len(hits) / max(len(terms), 1)          # coverage of query terms
    if len(phrase) > 3 and phrase in low:
        score += 1.0                                # exact phrase present
    if len(terms) > 1 and len(hits) == 1:
        score -= 0.5                                # only one loose token → likely false positive
    if group in ("claude-code", "claude-thread"):
        meta = len(_META_WORDS.findall(low))
        if meta >= 3:
            # Scale with density: light incidental mentions barely dip; a full
            # MIKAI-build transcript (meta ≫ 3) drops below the visibility floor.
            score -= min(2.2, 0.4 + 0.22 * meta)
    return score


def fetch_episodes(uuids: list[str]) -> dict[str, dict]:
    if not uuids:
        return {}
    q = """
    MATCH (e:Episodic) WHERE e.uuid IN $uuids
    RETURN e.uuid AS uuid, e.content AS content,
           toString(e.valid_at) AS valid_at, e.group_id AS group_id, e.name AS name
    """
    with _DRIVER.session() as s:
        return {r["uuid"]: r for r in s.run(q, uuids=uuids).data()}


def excerpt(content: str, terms: list[str], width: int = 460) -> str:
    content = re.sub(r"\s+", " ", content or "").strip()
    if not content:
        return ""
    low = content.lower()
    pos = min((low.find(t) for t in terms if t and t in low), default=-1)
    if pos < 0:
        return content[:width] + ("…" if len(content) > width else "")
    start = max(0, pos - width // 3)
    end = min(len(content), start + width)
    snip = content[start:end]
    return ("…" if start else "") + snip + ("…" if end < len(content) else "")


def wiki_synthesis(query: str) -> dict | None:
    """Find the wiki paragraph(s) most relevant to the query; return with the
    dimension heading as context. Graceful: None if no wiki / no match."""
    if not WIKI_PATH.exists():
        return None
    terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
    if not terms:
        return None
    text = WIKI_PATH.read_text()
    dim = "Synthesis"
    best = (0, "", "")
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b:
            continue
        if b.startswith("#"):
            dim = b.lstrip("# ").strip()
            continue
        low = b.lower()
        score = sum(low.count(t) for t in terms)
        if score > best[0]:
            best = (score, b, dim)
    if best[0] == 0:
        return None
    return {"dimension": best[2], "body": best[1][:1400]}


app = FastAPI()


@app.get("/api/search")
async def api_search(q: str):
    q = (q or "").strip()
    if not q:
        return JSONResponse({"query": q, "synthesis": None, "traces": []})
    terms = [t for t in re.split(r"\W+", q.lower()) if len(t) > 1]
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{SIDECAR}/search", json={"query": q, "num_results": 14})
            edges = r.json() if r.status_code == 200 else []
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"query": q, "error": f"search backend unreachable: {e}",
                             "synthesis": wiki_synthesis(q), "traces": []})

    # rank episode uuids by first appearance in the ranked edge list
    ordered, seen, fact_for = [], set(), {}
    for edge in edges:
        for ep in (edge.get("episodes") or []):
            if ep not in seen:
                seen.add(ep); ordered.append(ep); fact_for[ep] = edge.get("fact") or ""
    phrase = q.lower().strip()
    eps = fetch_episodes(ordered)
    traces = []
    for ep in ordered:
        row = eps.get(ep)
        content = (row or {}).get("content") or ""
        if not content.strip():
            continue
        group = row.get("group_id") or ""
        rel = _relevance(content, phrase, terms, group)
        if rel <= 0:
            continue                                # drop false positives / pure meta-noise
        traces.append({
            "date": (row.get("valid_at") or "")[:10],
            "source": SOURCE_LABELS.get(group, group or "?"),
            "group": group,
            "excerpt": excerpt(content, terms),
            "fact": fact_for.get(ep, ""),
            "rel": round(rel, 2),
        })
    # Strongest signal first, then most recent within equal strength.
    traces.sort(key=lambda t: (t["rel"], t["date"] or "0000"), reverse=True)
    return JSONResponse({"query": q, "synthesis": wiki_synthesis(q), "traces": traces})


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(PAGE)


PAGE = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>mikai · your mind, searchable</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,500;9..144,600&family=Newsreader:opsz@6..72&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#100d0b; --bg2:#161210; --ink:#ece5da; --muted:#938a7e; --dim:#6a6157;
  --line:#2a241f; --ember:#e08a3c; --ember-soft:rgba(224,138,60,.13);
  --serif:"Fraunces",Georgia,serif; --read:"Newsreader",Georgia,serif;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--bg);color:var(--ink);font-family:var(--read);
  -webkit-font-smoothing:antialiased;overflow-x:hidden}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(60% 45% at 50% 0%,rgba(224,138,60,.07),transparent 70%);}
.grain{position:fixed;inset:0;z-index:0;opacity:.35;pointer-events:none;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.5'/%3E%3C/svg%3E");}
.wrap{position:relative;z-index:1;max-width:760px;margin:0 auto;padding:0 26px}

/* search zone — centered until a query lands, then pins to top */
.stage{min-height:100vh;display:flex;flex-direction:column;justify-content:center;
  transition:min-height .5s cubic-bezier(.4,0,.1,1)}
body.searched .stage{min-height:auto;padding-top:46px}
.brand{font-family:var(--mono);font-size:11px;letter-spacing:.42em;text-transform:uppercase;
  color:var(--dim);margin-bottom:22px;transition:opacity .4s}
body.searched .brand{opacity:.6;margin-bottom:14px}
.lede{font-family:var(--serif);font-weight:300;font-size:clamp(30px,5vw,46px);line-height:1.05;
  letter-spacing:-.02em;color:var(--ink);margin-bottom:30px;max-width:16ch}
.lede em{font-style:italic;color:var(--ember)}
body.searched .lede{display:none}

.field{display:flex;align-items:baseline;gap:14px;border-bottom:1px solid var(--line);
  padding-bottom:14px;transition:border-color .3s}
.field:focus-within{border-color:var(--ember)}
.caret{font-family:var(--mono);color:var(--ember);font-size:20px;line-height:1;transform:translateY(-1px)}
#q{flex:1;background:transparent;border:0;outline:0;color:var(--ink);
  font-family:var(--serif);font-weight:300;font-size:clamp(22px,3.4vw,30px);letter-spacing:-.01em}
#q::placeholder{color:var(--dim);font-style:italic}
.hint{font-family:var(--mono);font-size:11px;color:var(--dim);margin-top:12px;letter-spacing:.04em}
.hint b{color:var(--muted);font-weight:400;cursor:pointer;border-bottom:1px dotted var(--line)}

/* results */
#out{padding:38px 0 120px}
.status{font-family:var(--mono);font-size:12px;color:var(--dim);letter-spacing:.06em;padding:8px 0}
.synth{border-left:2px solid var(--ember);padding:4px 0 4px 22px;margin:6px 0 46px;
  animation:rise .6s both}
.synth .kick{font-family:var(--mono);font-size:10.5px;letter-spacing:.24em;text-transform:uppercase;
  color:var(--ember);margin-bottom:12px}
.synth .body{font-family:var(--read);font-size:18px;line-height:1.62;color:#ded6ca}
.synth .body b{color:var(--ink);font-weight:600;background:var(--ember-soft);padding:0 2px;border-radius:2px}

.spinehead{display:flex;align-items:center;gap:14px;margin:0 0 26px}
.spinehead h2{font-family:var(--serif);font-weight:500;font-size:15px;letter-spacing:.02em;color:var(--muted)}
.spinehead .rule{flex:1;height:1px;background:var(--line)}

.trace{position:relative;padding:2px 0 30px 30px;border-left:1px solid var(--line);
  animation:rise .55s both}
.trace::before{content:"";position:absolute;left:-5px;top:6px;width:9px;height:9px;border-radius:50%;
  background:var(--bg);border:1.5px solid var(--dim);transition:.25s}
.trace:hover::before{border-color:var(--ember);box-shadow:0 0 0 4px var(--ember-soft)}
/* strongest match — the thread the search most surely landed on */
.trace.top{padding-left:30px}
.trace.top::before{background:var(--ember);border-color:var(--ember);
  box-shadow:0 0 0 5px var(--ember-soft)}
.trace.top .texcerpt{font-family:var(--serif);font-weight:300;font-size:20px;line-height:1.5;color:#efe7db}
.tmeta{display:flex;align-items:center;gap:12px;margin-bottom:9px}
.tdate{font-family:var(--mono);font-size:12px;color:var(--muted);letter-spacing:.02em}
.tsrc{font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--dim);border:1px solid var(--line);border-radius:999px;padding:3px 9px}
.ttop{font-family:var(--mono);font-size:9px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--ember);border:1px solid var(--ember);border-radius:999px;padding:3px 8px}
.tspan{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--dim);letter-spacing:.04em}
.texcerpt{font-family:var(--read);font-size:16.5px;line-height:1.6;color:#d7cfc4}
.texcerpt mark{background:var(--ember-soft);color:var(--ember);padding:0 1px;border-radius:2px}
.tfact{font-family:var(--mono);font-size:11px;color:var(--dim);margin-top:10px;line-height:1.5}
.empty{font-family:var(--read);font-style:italic;font-size:19px;color:var(--muted);padding:20px 0}

@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
</style></head>
<body>
<div class="grain"></div>
<div class="wrap"><div class="stage">
  <div class="brand">mikai · noonchi</div>
  <div class="lede">Search your <em>own</em> mind.</div>
  <div class="field">
    <span class="caret">&gt;</span>
    <input id="q" autocomplete="off" spellcheck="false" placeholder="a thought, a person, a half-finished idea…" autofocus>
  </div>
  <div class="hint">Enter to search · try
    <b onclick="run('3d ocean farming')">3d ocean farming</b> ·
    <b onclick="run('International Village')">International Village</b></div>
  <div id="out"></div>
</div></div>
<script>
const $=s=>document.querySelector(s), out=$('#out'), q=$('#q');
const esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function hl(t,terms){let h=esc(t);for(const w of terms){if(w.length<2)continue;
  h=h.replace(new RegExp('('+w.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi'),'<mark>$1</mark>');}return h;}
async function run(text){
  const query=(text!=null?text:q.value).trim(); if(!query)return;
  q.value=query; document.body.classList.add('searched');
  out.innerHTML='<div class="status">searching your mind…</div>';
  let d; try{ d=await (await fetch('/api/search?q='+encodeURIComponent(query))).json(); }
  catch(e){ out.innerHTML='<div class="empty">The mind is unreachable — is the sidecar running?</div>'; return; }
  const terms=query.toLowerCase().split(/\W+/).filter(x=>x.length>1);
  let html='';
  if(d.error) html+='<div class="status">⚠ '+esc(d.error)+'</div>';
  if(d.synthesis) html+=`<div class="synth"><div class="kick">Synthesis · ${esc(d.synthesis.dimension)}</div>`+
    `<div class="body">${hl(d.synthesis.body,terms)}</div></div>`;
  const T=d.traces||[];
  if(!T.length && !d.synthesis){ out.innerHTML='<div class="empty">Nothing surfaced for “'+esc(query)+'”. The trace may not be in the graph yet.</div>'; return; }
  if(T.length){
    const dates=T.map(t=>t.date).filter(Boolean).sort();
    const span=dates.length?(dates[0]===dates[dates.length-1]?dates[0]:dates[0]+' → '+dates[dates.length-1]):'';
    html+=`<div class="spinehead"><h2>${T.length} trace${T.length>1?'s':''} across time</h2>`+
      `<div class="rule"></div>${span?`<span class="tspan">${span}</span>`:''}</div>`;
    T.forEach((t,i)=>{ const top=i===0;
      html+=`<div class="trace${top?' top':''}" style="animation-delay:${i*45}ms">`+
      `<div class="tmeta"><span class="tdate">${t.date||'—'}</span><span class="tsrc">${esc(t.source)}</span>`+
      (top?'<span class="ttop">strongest</span>':'')+`</div>`+
      `<div class="texcerpt">${hl(t.excerpt,terms)}</div>`+
      (t.fact?`<div class="tfact">↳ ${esc(t.fact)}</div>`:'')+`</div>`; });
  }
  out.innerHTML=html;
}
q.addEventListener('keydown',e=>{if(e.key==='Enter')run();});
window.run=run;
</script></body></html>"""


if __name__ == "__main__":
    import uvicorn
    print(f"\n  🧠  mikai brain search  →  http://localhost:{PORT}\n")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")

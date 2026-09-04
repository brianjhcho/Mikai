"""Surface C — retrieval + composition over a nashsu-processed wiki vault.

Parallel to infra/mikai_ask/core.py but the substrate is a nashsu vault's
`wiki/` directory (concepts/entities/wisdom/journal/sources/…) instead of
the raw capture at ~/.mikai/wiki-raw/. Same compose-then-LLM pattern.

Retrieval pipeline:
  1. BM25-lite rank over title + first-500-chars body across the enumerated
     subdirs (title weighted 3x); take top 8.
  2. Wikilink expansion: for each top hit, follow [[wikilinks]] in its
     body, add unique linked pages (cap 5 extra).
  3. Related-frontmatter expansion: if hit has `related: [a, b, c]`, add
     those (cap 3 extra).

Prompt assembly (100k char cap):
  - Full body of top-3 hits (never trimmed).
  - First-1000-chars of the rest of the top-k.
  - Snippets for wikilink + related expansions.
  - Trim order when over budget: expanded-wikilinks → related-expansion →
    tail-of-topK. Top-3 full bodies are inviolate.

stdlib-only. LLM call is `subprocess.run(["claude", "-p"], input=prompt)`.
"""
from __future__ import annotations

import math
import re
import subprocess
from collections import Counter
from pathlib import Path

PROMPT_CHAR_CAP = 100_000
TOP_K = 8
WIKILINK_EXPAND_CAP = 5
RELATED_EXPAND_CAP = 3
TOP3_BODY_CAP = 8000
TAIL_BODY_CAP = 1000
INDEX_SNIPPET_CHARS = 500
SEP = "\n---\n"

RANK_SUBDIRS = ("concepts", "entities", "wisdom", "journal", "sources")
WIKI_SUBDIRS = RANK_SUBDIRS + (
    "queries", "goals", "habits", "reflections", "synthesis", "comparisons",
)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?(?:#[^\]]+)?\]\]")
TOKEN_RE = re.compile(r"[a-z][a-z0-9]{2,}")

STOP = frozenset("""
the this that these those my our your his her their its
a an and or but for nor so yet as if in on at by to of from with without
he she they we you it me us them him whom whose
is are was were be being been have has had do does did done
will would could should may might must shall can cannot also just more most
what who which how why when where about above below into like near onto over
now today tomorrow yesterday some such very much many any all each every
than then thus therefore however moreover otherwise
""".split())

PREAMBLE = (
    "You are answering from the nashsu-processed wiki pages assembled "
    "below. Ground every claim in these pages. Cite page slugs by name "
    "(e.g. `concepts/sumimasen`, `entities/openclaw`) when quoting or "
    "paraphrasing. If the substrate is silent on some part of the "
    "question, say so plainly — do not invent."
)


# ── Vault reading ────────────────────────────────────────────────────────

def _split_frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_raw, body = m.group(1), m.group(2)
    fm: dict = {}
    for line in fm_raw.splitlines():
        if not line or line.startswith(" ") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            fm[k] = [x.strip().strip('"').strip("'")
                     for x in inner.split(",") if x.strip()]
        else:
            fm[k] = v.strip('"').strip("'")
    return fm, body


def _page_title(fm: dict, path: Path) -> str:
    t = fm.get("title")
    if isinstance(t, str) and t.strip():
        return t.strip()
    return path.stem.replace("-", " ")


def _tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOP]


def _enumerate_vault(vault_path: Path) -> list[dict]:
    wiki_root = vault_path / "wiki"
    if not wiki_root.is_dir():
        return []
    pages: list[dict] = []
    for sub in WIKI_SUBDIRS:
        d = wiki_root / sub
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.suffix != ".md" or p.name in ("index.md", "log.md"):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            fm, body = _split_frontmatter(text)
            pages.append({
                "path": p,
                "type": sub,
                "slug": p.stem,
                "title": _page_title(fm, p),
                "fm": fm,
                "body": body,
                "text": text,
            })
    return pages


# ── BM25-lite ranking ────────────────────────────────────────────────────

def _bm25_rank(pages: list[dict], query: str, k: int = TOP_K,
               k1: float = 1.5, b: float = 0.75) -> list[dict]:
    """Rank pages by BM25 over (title×3 + first-500-chars body). Returns
    top-k with score attached (only positive scores)."""
    q_terms = _tokenize(query)
    if not q_terms or not pages:
        return []

    docs: list[list[str]] = []
    for p in pages:
        title_tokens = _tokenize(p["title"])
        body_tokens = _tokenize(p["body"][:INDEX_SNIPPET_CHARS])
        docs.append(title_tokens * 3 + body_tokens)

    doc_lens = [len(d) for d in docs]
    avgdl = sum(doc_lens) / max(1, len(doc_lens))
    N = len(docs)

    df: Counter[str] = Counter()
    for terms_set in ({t for t in d} for d in docs):
        for t in terms_set:
            df[t] += 1

    idf = {t: math.log(1 + (N - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))
           for t in set(q_terms)}

    scored: list[tuple[float, dict]] = []
    for i, doc in enumerate(docs):
        if not doc:
            continue
        tf = Counter(doc)
        dl = doc_lens[i]
        score = 0.0
        for t in q_terms:
            f = tf.get(t, 0)
            if f == 0:
                continue
            denom = f + k1 * (1 - b + b * dl / max(1, avgdl))
            score += idf[t] * (f * (k1 + 1)) / denom
        if score > 0:
            scored.append((score, pages[i]))

    scored.sort(key=lambda x: (-x[0], x[1]["path"].name))
    out: list[dict] = []
    for score, page in scored[:k]:
        page = dict(page)
        page["score"] = round(score, 3)
        out.append(page)
    return out


# ── Expansion ────────────────────────────────────────────────────────────

def _slug_index(pages: list[dict]) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for p in pages:
        idx.setdefault(p["slug"].lower(), p)
    return idx


def _resolve_link(target: str, slug_index: dict[str, dict]) -> dict | None:
    t = target.strip().lower()
    if "/" in t:
        t = t.rsplit("/", 1)[-1]
    if t.endswith(".md"):
        t = t[:-3]
    return slug_index.get(t)


def _expand_wikilinks(hits: list[dict], slug_index: dict[str, dict],
                      cap: int) -> list[dict]:
    seen = {h["path"] for h in hits}
    out: list[dict] = []
    for h in hits:
        if len(out) >= cap:
            break
        for m in WIKILINK_RE.finditer(h["body"]):
            if len(out) >= cap:
                break
            resolved = _resolve_link(m.group(1), slug_index)
            if not resolved or resolved["path"] in seen:
                continue
            add = dict(resolved)
            add["via"] = h["slug"]
            add["expand_kind"] = "wikilink"
            out.append(add)
            seen.add(resolved["path"])
    return out


def _expand_related(hits: list[dict], slug_index: dict[str, dict],
                    cap: int, already: list[dict]) -> list[dict]:
    seen = {h["path"] for h in hits} | {a["path"] for a in already}
    out: list[dict] = []
    for h in hits:
        if len(out) >= cap:
            break
        rel = h["fm"].get("related")
        if not isinstance(rel, list):
            continue
        for target in rel:
            if len(out) >= cap:
                break
            resolved = _resolve_link(str(target), slug_index)
            if not resolved or resolved["path"] in seen:
                continue
            add = dict(resolved)
            add["via"] = h["slug"]
            add["expand_kind"] = "related"
            out.append(add)
            seen.add(resolved["path"])
    return out


# ── Prompt assembly ──────────────────────────────────────────────────────

def _clip(s: str, n: int) -> str:
    s = s.strip()
    return s[:n] + ("…" if len(s) > n else "")


def _format_full(h: dict) -> str:
    body = _clip(h["body"], TOP3_BODY_CAP)
    return f"### {h['type']}/{h['slug']} — {h['title']}\n\n{body}"


def _format_tail(h: dict) -> str:
    body = _clip(h["body"], TAIL_BODY_CAP)
    return f"### {h['type']}/{h['slug']} — {h['title']}\n\n{body}"


def _format_expansion(h: dict) -> str:
    body = _clip(h["body"], TAIL_BODY_CAP)
    via = f" (via {h['via']}, {h.get('expand_kind', '?')})"
    return f"### {h['type']}/{h['slug']} — {h['title']}{via}\n\n{body}"


def _assemble(query: str, vault_path: Path, top3: list[dict],
              tail: list[dict], wikilink_exp: list[dict],
              related_exp: list[dict]) -> str:
    parts = [
        PREAMBLE,
        f"## Vault under test\n\n`{vault_path}`",
    ]
    if top3:
        parts.append("## Top hits (full bodies)\n\n"
                     + "\n\n---\n\n".join(_format_full(h) for h in top3))
    if tail:
        parts.append("## Additional hits (first 1000 chars)\n\n"
                     + "\n\n---\n\n".join(_format_tail(h) for h in tail))
    if related_exp:
        parts.append("## Related-page expansions\n\n"
                     + "\n\n---\n\n".join(_format_expansion(h)
                                           for h in related_exp))
    if wikilink_exp:
        parts.append("## Wikilink expansions\n\n"
                     + "\n\n---\n\n".join(_format_expansion(h)
                                           for h in wikilink_exp))
    parts.append("## Question\n\n" + query)
    return SEP.join(parts)


def compose(query: str, vault_dir: Path) -> tuple[str, dict]:
    """Build a Surface C prompt. Returns (prompt, stats)."""
    pages = _enumerate_vault(vault_dir)
    rankable = [p for p in pages if p["type"] in RANK_SUBDIRS]
    hits = _bm25_rank(rankable, query, k=TOP_K)
    slug_index = _slug_index(pages)

    wikilink_exp = _expand_wikilinks(hits, slug_index, WIKILINK_EXPAND_CAP)
    related_exp = _expand_related(hits, slug_index, RELATED_EXPAND_CAP,
                                  already=wikilink_exp)

    top3 = hits[:3]
    tail = list(hits[3:])
    wl = list(wikilink_exp)
    rel = list(related_exp)

    trimmed = {"wikilinks": 0, "related": 0, "tail": 0}
    prompt = _assemble(query, vault_dir, top3, tail, wl, rel)
    # Trim order: wikilink expansions → related expansions → tail-of-topK
    while len(prompt) > PROMPT_CHAR_CAP:
        if wl:
            wl.pop()
            trimmed["wikilinks"] += 1
        elif rel:
            rel.pop()
            trimmed["related"] += 1
        elif tail:
            tail.pop()
            trimmed["tail"] += 1
        else:
            break
        prompt = _assemble(query, vault_dir, top3, tail, wl, rel)

    stats = {
        "prompt_chars": len(prompt),
        "pages_indexed": len(pages),
        "pages_ranked": len(rankable),
        "hits": len(hits),
        "top_slugs": [f"{h['type']}/{h['slug']}" for h in hits],
        "top_scores": [h.get("score", 0.0) for h in hits],
        "wikilink_expansions": len(wl),
        "related_expansions": len(rel),
        "tail_kept": len(tail),
        "trimmed": trimmed,
    }
    return prompt, stats


# ── LLM invocation ───────────────────────────────────────────────────────

def ask(query: str, vault_dir: Path, timeout_s: int = 600) -> tuple[str, dict]:
    """Compose then call `claude -p` via subprocess. Returns (answer, stats).
    Errors bubble up as an `_ERROR:` string in answer with stats intact."""
    query = (query or "").strip()
    if not query:
        raise ValueError("empty query")
    prompt, stats = compose(query, vault_dir)
    try:
        result = subprocess.run(
            ["claude", "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return f"_ERROR: claude -p timed out after {timeout_s}s._", stats
    except FileNotFoundError:
        return "_ERROR: `claude` not on PATH._", stats
    if result.returncode != 0:
        return (f"_ERROR: claude exited {result.returncode}. "
                f"stderr: {result.stderr[:300].strip()}_"), stats
    answer = result.stdout.strip() or "_(empty response)_"
    return answer, stats

"""
full_corpus_dream.py — one-shot ontology-shaped wiki generation from the ENTIRE
corpus. Companion to dream.py (which processes only last-N-days). This is the
"seed the wiki" run: map-reduce over every episode in Neo4j, structured
against DIMENSIONS.md, produces ~/.mikai/wiki/wiki-ontology-v1.md.

Pattern (per MEMORY_ARCHITECTURE.md PART J's LLM policy layer and Karpathy's
LLM wiki):

  MAP phase — chunk corpus into ~60K-token pieces. For each chunk, ask the LLM
    to extract observations against Brian's 9 life dimensions. Return YAML.

  REDUCE phase — for each of the 9 dimensions, gather all observations across
    all chunks, then synthesize a wiki section. Nine dimension-scoped reduces
    keep each reduce input well under the model's context window.

  ASSEMBLE — combine dimension sections with a Who header and Themes footer.
    Write to a NEW file (wiki-ontology-v1.md) so we don't clobber the existing
    incrementally-maintained wiki.md.

Cost target (DeepSeek V3):
  Map:    ~170 chunks × (60K input + 3K output) = 10.2M in + 510K out ≈ $3.30
  Reduce: 9 × (~50K input + 3K output) = 450K in + 27K out ≈ $0.15
  Total:  ~$3.50

Wall clock with MAX_PARALLEL=8: ~10-15 minutes end-to-end.

Usage:
    python full_corpus_dream.py [--limit N] [--dry-run] [--out PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from neo4j import GraphDatabase
from openai import AsyncOpenAI

# ── Paths ─────────────────────────────────────────────────────────────

MIKAI_DIR = Path.home() / ".mikai"
WIKI_DIR = MIKAI_DIR / "wiki"
DEFAULT_OUT = WIKI_DIR / "wiki-ontology-v1.md"
LOG_PATH = WIKI_DIR / "log.md"

# DIMENSIONS.md lives in the pear-seashore worktree (source of truth). The
# runner sources ~/.mikai/launchd.env, so setting MIKAI_DIMENSIONS_PATH there
# would override.
DEFAULT_DIMENSIONS_PATH = Path.home() / ".superset" / "worktrees" / "MIKAI" / "pear-seashore" / "docs" / "DIMENSIONS.md"
ENV_FILE = MIKAI_DIR / "launchd.env"

# ── Chunking ──────────────────────────────────────────────────────────

CHUNK_CHARS = 240_000       # ~60K tokens per chunk (safely under 128K DeepSeek context)
MAX_PARALLEL = 8            # concurrent map calls (well within DeepSeek rate limits)
EPISODE_CAP_CHARS = 30_000  # per-episode truncation to keep pathological outliers bounded

# ── Prompts ───────────────────────────────────────────────────────────

MAP_SYSTEM_PROMPT = """\
You are MIKAI, mapping a chunk of Brian's personal corpus into his life-
dimensions ontology. Read the DIMENSIONS file below to understand the schema,
then extract observations from the chunk.

Rules:
1. Route every substantive observation to at least one dimension. Use the
   dimension's `concepts` list as a router — a mention of Nairobi routes to
   dimension 2 (Where to Live) AND dimension 3 (Business Opportunities).
2. IGNORE framework/tooling noise (Dimension 1's `concepts` list). Unless a
   chunk contains a concrete decision point in Dimension 1 (founder-vs-employee
   commitment, funding move, product launch), do NOT emit observations there.
3. Preserve QUOTES verbatim when the chunk contains a load-bearing statement
   Brian made or received.
4. Preserve DATES when they appear.
5. Preserve DECISION POINTS — sentences like "I need to X" or "I'll email Y" or
   "we should Z" — even without follow-through.
6. For Dimension 9 (Recurring Themes / self-messages), be alert to
   philosophical or self-directive statements — "life is composed of the journey
   not commencing after you've figured it out" style. These often appear as
   Apple Notes entries and rarely surface elsewhere.

Output STRICTLY valid JSON, no markdown code fence, no preamble:

{
  "dim_1_ai_career": [
    {"observation": "...", "quote": "..." (optional), "date": "YYYY-MM-DD" (optional)}
  ],
  "dim_2_where_to_live": [...],
  "dim_3_business_opportunities": [...],
  "dim_4_germaine": [...],
  "dim_5_family": [...],
  "dim_6_health": [...],
  "dim_7_craft_hobbies": [...],
  "dim_8_financial_trading": [...],
  "dim_9_recurring_themes": [...]
}

Empty arrays are fine for dimensions the chunk doesn't touch. If a chunk is
entirely framework noise, all arrays can be empty.
"""

REDUCE_SYSTEM_PROMPT = """\
You are MIKAI, synthesizing one dimension of Brian's life-wiki. You receive:
  - The DIMENSIONS file describing this dimension's goals, concepts, and notes
  - The full set of OBSERVATIONS extracted from the corpus for this dimension

Your job: write ONE markdown section for this dimension. Rules:

1. LEAD with concrete goals. Each goal gets a name, state (exploring, in_flight,
   blocked, on_hold, decided, acting, stalled, done), and the last observed
   pickup point (what needs to happen next, or what was left unresolved).
2. GROUND with evidence. Cite specific dates, quotes, or observation clusters.
   Do not invent — use only what's in the observations.
3. WEIGHT BY DEPTH, NOT VOLUME. A single detailed decision beat weighs more than
   fifty passing mentions of the same concept.
4. SURFACE TENSIONS. If the observations contain contradictions (Brian said X,
   then did Y), name it explicitly under a "Tensions" heading within this
   section.
5. TERSE. This is the LLM-native wiki — read whole, no fluff. Aim for
   200-800 words per dimension.
6. MARK MOVEMENT. If a goal changed state across the corpus timeline, say so.

Output ONLY the markdown for this dimension section. Start with `### N. <Dimension Name>`
(using the dimension's number and name). No preamble, no other sections.
"""


# ── Env loading ───────────────────────────────────────────────────────

def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


# ── Neo4j: fetch every episode ────────────────────────────────────────

def fetch_all_episodes(groups: list[str] | None = None) -> list[dict]:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ.get("NEO4J_PASSWORD", "mikai-local-dev")
    where_group = "AND e.group_id IN $groups" if groups else ""
    query = f"""
    MATCH (e:Episodic)
    WHERE e.content IS NOT NULL AND size(e.content) > 0
    {where_group}
    RETURN e.uuid AS uuid,
           e.name AS name,
           e.content AS content,
           e.group_id AS group_id,
           toString(e.valid_at) AS valid_at
    ORDER BY e.valid_at ASC
    """
    driver = GraphDatabase.driver(uri, auth=(user, pw))
    try:
        with driver.session() as session:
            return session.run(query, groups=groups).data()
    finally:
        driver.close()


# ── Chunking ──────────────────────────────────────────────────────────

def make_chunks(episodes: list[dict], max_chars: int = CHUNK_CHARS) -> list[str]:
    """Serialize episodes into text chunks of ~max_chars. Each chunk contains
    a stream of episodes in temporal order, delimited by episode headers."""
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for ep in episodes:
        content = (ep.get("content") or "").strip()
        if not content:
            continue
        if len(content) > EPISODE_CAP_CHARS:
            content = content[:EPISODE_CAP_CHARS] + " […truncated]"
        ts = (ep.get("valid_at") or "")[:10]
        name = ep.get("name") or ep.get("group_id") or ""
        group = ep.get("group_id") or ""
        header = f"\n\n=== [{ts}] ({group}) {name[:80]} ===\n"
        piece = header + content
        piece_len = len(piece)
        if buf_len + piece_len > max_chars and buf:
            chunks.append("".join(buf))
            buf = [piece]
            buf_len = piece_len
        else:
            buf.append(piece)
            buf_len += piece_len
    if buf:
        chunks.append("".join(buf))
    return chunks


# ── Map phase ─────────────────────────────────────────────────────────

async def map_chunk(
    client: AsyncOpenAI,
    chunk: str,
    dimensions_content: str,
    idx: int,
    total: int,
    sem: asyncio.Semaphore,
) -> dict | None:
    async with sem:
        user_prompt = (
            f"=== DIMENSIONS FILE ===\n{dimensions_content}\n\n"
            f"=== CORPUS CHUNK {idx + 1}/{total} ===\n{chunk}"
        )
        try:
            resp = await client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": MAP_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            print(f"  MAP {idx + 1}/{total} FAILED: {str(e)[:160]}", file=sys.stderr)
            return None

        raw = (resp.choices[0].message.content or "").strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  MAP {idx + 1}/{total} JSON parse failed", file=sys.stderr)
            return None
        print(f"  MAP {idx + 1}/{total} ok", file=sys.stderr)
        return data


async def map_all(
    client: AsyncOpenAI,
    chunks: list[str],
    dimensions_content: str,
) -> list[dict]:
    sem = asyncio.Semaphore(MAX_PARALLEL)
    tasks = [
        map_chunk(client, c, dimensions_content, i, len(chunks), sem)
        for i, c in enumerate(chunks)
    ]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


# ── Reduce phase ──────────────────────────────────────────────────────

DIMENSION_KEYS = [
    ("dim_1_ai_career",          "1. AI Career / MIKAI Build"),
    ("dim_2_where_to_live",      "2. Where to Live"),
    ("dim_3_business_opportunities", "3. Business Opportunities"),
    ("dim_4_germaine",           "4. Relationship with Germaine"),
    ("dim_5_family",             "5. Family Obligations"),
    ("dim_6_health",             "6. Health / Body"),
    ("dim_7_craft_hobbies",      "7. Craft / Hobbies"),
    ("dim_8_financial_trading",  "8. Financial / Trading"),
    ("dim_9_recurring_themes",   "9. Recurring Themes"),
]


def collect_by_dimension(map_outputs: list[dict]) -> dict[str, list[dict]]:
    by_dim: dict[str, list[dict]] = {k: [] for k, _ in DIMENSION_KEYS}
    for out in map_outputs:
        for key, _ in DIMENSION_KEYS:
            obs = out.get(key)
            if isinstance(obs, list):
                by_dim[key].extend(obs)
    return by_dim


async def reduce_dimension(
    client: AsyncOpenAI,
    dim_key: str,
    dim_label: str,
    observations: list[dict],
    dimensions_content: str,
    sem: asyncio.Semaphore,
) -> str:
    async with sem:
        if not observations:
            return f"### {dim_label}\n\n(no observations extracted from the corpus for this dimension)\n"

        # Serialize observations compactly to stay within context
        obs_text = "\n".join(
            f"- {json.dumps(o, ensure_ascii=False)}"
            for o in observations
        )
        # Cap to ~90K chars input observations to be safe
        if len(obs_text) > 90_000:
            obs_text = obs_text[:90_000] + "\n[…truncated at 90K chars]"

        user_prompt = (
            f"=== DIMENSIONS FILE (for context) ===\n{dimensions_content}\n\n"
            f"=== DIMENSION TO SYNTHESIZE ===\n{dim_label}\n\n"
            f"=== OBSERVATIONS ({len(observations)} entries) ===\n{obs_text}"
        )
        try:
            resp = await client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": REDUCE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text.startswith("###"):
                text = f"### {dim_label}\n\n" + text
            print(f"  REDUCE {dim_label[:40]} ok ({len(observations)} obs → {len(text)} chars)", file=sys.stderr)
            return text
        except Exception as e:
            print(f"  REDUCE {dim_label} FAILED: {str(e)[:160]}", file=sys.stderr)
            return f"### {dim_label}\n\n(reduce failed — {len(observations)} observations pending re-synthesis)\n"


async def reduce_all(
    client: AsyncOpenAI,
    by_dim: dict[str, list[dict]],
    dimensions_content: str,
) -> list[tuple[str, str]]:
    sem = asyncio.Semaphore(MAX_PARALLEL)
    tasks = [
        reduce_dimension(client, dim_key, dim_label, by_dim.get(dim_key, []), dimensions_content, sem)
        for dim_key, dim_label in DIMENSION_KEYS
    ]
    sections = await asyncio.gather(*tasks)
    return list(zip([label for _, label in DIMENSION_KEYS], sections))


# ── Assemble + write ──────────────────────────────────────────────────

def assemble_wiki(sections: list[tuple[str, str]], stats: dict) -> str:
    stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M UTC")
    parts = [
        f"# Brian — Ontology Wiki (v1)\n",
        f"*Generated {stamp} from full corpus ({stats['episodes']} episodes, "
        f"{stats['chars']:,} chars, {stats['chunks']} chunks).*\n\n",
        "## Frame\n",
        "This wiki is organized around Brian's 9 life dimensions (see `docs/DIMENSIONS.md`).\n"
        "Each dimension section carries current goals, evidence, and pickup points\n"
        "synthesized from the entire corpus — Apple Notes, Perplexity threads,\n"
        "Claude conversations, iMessage, Calendar, Gmail, and MIKAI-internal streams.\n\n",
        "## Dimensions\n\n",
    ]
    for _, section_md in sections:
        parts.append(section_md.strip() + "\n\n")
    return "".join(parts)


def write_wiki(text: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)


# ── Main ──────────────────────────────────────────────────────────────

async def main_async(args) -> int:
    load_env()
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("ERROR: DEEPSEEK_API_KEY not set", file=sys.stderr)
        return 1

    dims_path = Path(args.dimensions or DEFAULT_DIMENSIONS_PATH)
    if not dims_path.exists():
        print(f"ERROR: dimensions file not found: {dims_path}", file=sys.stderr)
        return 1
    dimensions_content = dims_path.read_text()
    print(f"Dimensions file: {dims_path} ({len(dimensions_content):,} chars)", file=sys.stderr)

    groups = [g.strip() for g in args.groups.split(",")] if args.groups else None
    t0 = time.time()
    if args.source == "raw":
        import raw_corpus
        print(f"Reading corpus from RAW sources (no Neo4j) · groups={groups or 'all'}...", file=sys.stderr)
        episodes = raw_corpus.fetch_raw_episodes(groups)
    else:
        print(f"Fetching episodes from Neo4j · groups={groups or 'all'}...", file=sys.stderr)
        episodes = fetch_all_episodes(groups)
    if args.limit:
        episodes = episodes[: args.limit]
    total_chars = sum(len(e.get("content") or "") for e in episodes)
    print(f"  {len(episodes):,} episodes  ·  {total_chars:,} content chars"
          f"  ·  {time.time() - t0:.1f}s", file=sys.stderr)

    print("Chunking...", file=sys.stderr)
    chunks = make_chunks(episodes)
    print(f"  {len(chunks)} chunks  ·  avg {int(sum(len(c) for c in chunks) / max(len(chunks), 1)):,} chars/chunk",
          file=sys.stderr)

    if args.dry_run:
        print("DRY-RUN: printing first chunk preview + exiting", file=sys.stderr)
        print("\n--- first chunk preview (first 2000 chars) ---")
        print(chunks[0][:2000])
        print(f"\n--- total chunks: {len(chunks)} ---")
        return 0

    client = AsyncOpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    print(f"MAP phase: {len(chunks)} chunks × ~{MAX_PARALLEL}-parallel...", file=sys.stderr)
    t1 = time.time()
    map_outputs = await map_all(client, chunks, dimensions_content)
    print(f"  MAP done: {len(map_outputs)}/{len(chunks)} chunks succeeded  ·  {(time.time() - t1) / 60:.1f} min",
          file=sys.stderr)

    print("Collecting observations by dimension...", file=sys.stderr)
    by_dim = collect_by_dimension(map_outputs)
    for k, label in DIMENSION_KEYS:
        print(f"  {label}: {len(by_dim[k])} observations", file=sys.stderr)

    print("REDUCE phase: 9 dimension-scoped synthesis calls...", file=sys.stderr)
    t2 = time.time()
    sections = await reduce_all(client, by_dim, dimensions_content)
    print(f"  REDUCE done: {(time.time() - t2):.1f}s", file=sys.stderr)

    print("Assembling and writing wiki...", file=sys.stderr)
    wiki_text = assemble_wiki(
        sections,
        stats={"episodes": len(episodes), "chars": total_chars, "chunks": len(chunks)},
    )
    out_path = Path(args.out or DEFAULT_OUT)
    write_wiki(wiki_text, out_path)
    total_min = (time.time() - t0) / 60
    print(f"\nWrote {out_path}  ·  {len(wiki_text):,} chars  ·  {total_min:.1f} min total",
          file=sys.stderr)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="One-shot ontology-shaped wiki from full corpus.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap number of episodes processed (for testing).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch + chunk + preview; do not call LLM.")
    parser.add_argument("--out", type=str, default=None,
                        help=f"Output path (default: {DEFAULT_OUT}).")
    parser.add_argument("--dimensions", type=str, default=None,
                        help=f"Path to DIMENSIONS.md (default: {DEFAULT_DIMENSIONS_PATH}).")
    parser.add_argument("--source", choices=["neo4j", "raw"], default="neo4j",
                        help="Corpus source: neo4j (needs the graph) or raw (graphless — reads sources directly).")
    parser.add_argument("--groups", type=str, default=None,
                        help="Comma-separated group_ids to include (e.g. claude-thread,apple-notes). Applies to both sources.")
    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()

"""dream_bootstrap — one-shot narrative + ontology bootstrap over the wiki.

The old `dream` process is frozen (it read Graphiti/Neo4j). This script
reads the 27MB Karpathy wiki (~/.mikai/wiki/wiki.md, 8,000+ sections
indexed by ~/.mikai/wiki/wiki.index) and produces the two derived files
the nightly/weekly dream jobs will later keep fresh incrementally:

- wiki-narrative.md  — first-person recent-activity summary (Pass A).
  Windowed read over the last N days (default 30), chunked by month /
  ~150K chars, one LLM call per chunk.
- wiki-ontology.md   — canonical entity list (Pass B). Full-corpus
  map-reduce: batches of sections -> per-batch JSON entity extraction ->
  merge on name. Follows docs/ENTITY_MODEL.md (person/org/thing/place
  only, kebab-case, singular, first-name people).

Scale note: the raw corpus is ~27MB, so naive 150KB batching would cost
~190 LLM calls. Both passes therefore excerpt each section (header line +
the first `cap` bytes of body) with `cap` sized so a batch of B sections
fits ~150K chars. Entity names and thread signals live overwhelmingly in
headers and openings, so excerpting is cheap for recall and keeps the
whole bootstrap under the call budget.

All LLM traffic goes through infra.mikai_llm.chat(tier="interactive")
(`claude -p`, Max sub, tools disabled). Rate-limited to 1 call / 2s;
hard call-budget cap (--max-calls, default 50). Per-batch ontology
results checkpoint to a JSONL so a crashed run resumes with --resume.

Usage (from repo root):

    python3 -m infra.graphiti.dream_bootstrap --dry-run
    python3 -m infra.graphiti.dream_bootstrap narrative --narrative-days 30
    python3 -m infra.graphiti.dream_bootstrap ontology --resume
    python3 -m infra.graphiti.dream_bootstrap            # both passes

Existing outputs are backed up as <file>.bak-bootstrap-<ts> before
overwrite. wiki-ontology-v1.md (hand-curated, July 22) is never touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from infra.mikai_llm import chat as llm_chat  # noqa: E402


def _load_wiki_index_cls():
    """Import WikiIndex without triggering sidecar.l3.__init__ (which
    pulls in graphiti_core — only installed in the sidecar venv).
    wiki_index.py itself is stdlib-only."""
    import importlib.util

    path = _REPO / "infra" / "graphiti" / "sidecar" / "l3" / "wiki_index.py"
    spec = importlib.util.spec_from_file_location("_wiki_index_standalone", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.WikiIndex


WikiIndex = _load_wiki_index_cls()

WIKI_DIR = Path.home() / ".mikai" / "wiki"
WIKI_MD = WIKI_DIR / "wiki.md"
WIKI_INDEX = WIKI_DIR / "wiki.index"
NARRATIVE_OUT = WIKI_DIR / "wiki-narrative.md"
ONTOLOGY_OUT = WIKI_DIR / "wiki-ontology.md"
CHECKPOINT = WIKI_DIR / ".dream-bootstrap-ontology.checkpoint.jsonl"

CHUNK_CHAR_BUDGET = 150_000   # safe LLM context margin per call
NARRATIVE_TARGET_CHUNKS = 5   # aim for <= this many Pass A calls
RATE_LIMIT_S = 2.0            # min seconds between LLM calls

_ALLOWED_TYPES = {"person", "org", "thing", "place"}


# ── LLM plumbing: rate limit + budget + failure isolation ─────────────────


class Budget:
    def __init__(self, max_calls: int) -> None:
        self.max_calls = max_calls
        self.calls = 0
        self.failures = 0
        self._last = 0.0

    def chat(self, prompt: str, label: str) -> str | None:
        """One rate-limited, budget-capped, failure-isolated LLM call.
        Returns the response text, or None if this call failed."""
        if self.calls >= self.max_calls:
            raise BudgetExceeded(
                f"call budget exhausted ({self.max_calls}) before {label}"
            )
        wait = RATE_LIMIT_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self.calls += 1
        self._last = time.monotonic()
        try:
            return llm_chat(prompt, tier="interactive")
        except Exception as exc:  # one failure never aborts the pass
            self.failures += 1
            digest = hashlib.sha256(prompt.encode()).hexdigest()[:12]
            print(
                f"[llm-fail] {label} (content-hash {digest}): {exc}",
                file=sys.stderr,
            )
            return None


class BudgetExceeded(RuntimeError):
    pass


# ── Shared helpers ────────────────────────────────────────────────────────


_INGESTED_RE = re.compile(r"^<!--\s*ingested=.*?-->\s*$", re.MULTILINE)


def excerpt(section_text: str, cap: int) -> str:
    """Header line + first `cap` chars of the body (ingested-comment
    stripped). Sections shorter than cap pass through whole."""
    lines = section_text.split("\n", 1)
    header = lines[0]
    body = _INGESTED_RE.sub("", lines[1] if len(lines) > 1 else "").strip()
    if len(body) > cap:
        body = body[:cap].rsplit(" ", 1)[0] + " …[truncated]"
    return header + "\n" + body


def parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def source_stream(source: str) -> str:
    """'apple-notes: Foo' -> 'apple-notes'."""
    return source.split(":")[0].strip()


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = path.with_name(path.name + f".bak-bootstrap-{ts}")
    bak.write_bytes(path.read_bytes())
    return bak


def load_index() -> WikiIndex:
    if WIKI_INDEX.exists():
        idx = WikiIndex.load(WIKI_INDEX)
    else:
        idx = WikiIndex.build(WIKI_MD)  # read-only fallback; never saved here
    if not idx.records:
        sys.exit("wiki.index is empty — nothing to bootstrap")
    return idx


def strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)
    # tolerate prose around a single JSON object
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return text


# ── Pass A — narrative ────────────────────────────────────────────────────


def plan_narrative(idx: WikiIndex, days: int) -> list[dict]:
    """Chunk plan: [{label, records, cap, chars}]. Month-grouped, then
    split so each chunk stays under CHUNK_CHAR_BUDGET chars."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    records = idx.sections_matching(since=since)
    if not records:
        return []
    # Per-section excerpt cap sized so the whole window targets
    # NARRATIVE_TARGET_CHUNKS chunks.
    cap = max(
        300,
        min(4000, NARRATIVE_TARGET_CHUNKS * CHUNK_CHAR_BUDGET // len(records)),
    )
    by_month: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_month[parse_ts(r["header_ts"]).strftime("%Y-%m")].append(r)

    chunks: list[dict] = []
    for month in sorted(by_month):
        cur: list[dict] = []
        cur_chars = 0
        part = 1
        for r in by_month[month]:
            est = min(r["byte_end"] - r["byte_start"], cap + 200)
            if cur and cur_chars + est > CHUNK_CHAR_BUDGET:
                chunks.append(
                    {"label": f"{month} (part {part})", "records": cur,
                     "cap": cap, "chars": cur_chars}
                )
                part += 1
                cur, cur_chars = [], 0
            cur.append(r)
            cur_chars += est
        if cur:
            label = month if part == 1 else f"{month} (part {part})"
            chunks.append(
                {"label": label, "records": cur, "cap": cap, "chars": cur_chars}
            )
    return chunks


_NARRATIVE_PROMPT = """\
You are writing Brian's private activity journal. Below are dated excerpts
from his personal knowledge wiki for the window {label} — notes, Claude
sessions, Perplexity research, messages. Each excerpt starts with a
`### <timestamp> — <source> — <title>` header.

Write a 400-800 word FIRST-PERSON narrative (Brian's voice, "I") of what
happened in this window: what I worked on, decided, researched, worried
about, and left unfinished. Name the specific threads, projects, people,
and decisions that actually appear in the excerpts — no generic filler.
Ground every claim in the excerpts; if something is ambiguous, hedge or
omit it. Never invent people, events, or decisions.

Output: the narrative prose only. No preamble, no headers, no bullet
lists.

EXCERPTS:
{body}
"""


def run_narrative(
    idx: WikiIndex, days: int, budget: Budget, dry_run: bool, verbose: bool
) -> None:
    chunks = plan_narrative(idx, days)
    n_sections = sum(len(c["records"]) for c in chunks)
    est_chars = sum(c["chars"] for c in chunks)
    print(
        f"[pass A] narrative: last {days}d -> {n_sections} sections, "
        f"{len(chunks)} chunk(s), ~{est_chars:,} prompt chars "
        f"(~{est_chars // 4:,} tokens), estimated LLM calls: {len(chunks)}"
    )
    if dry_run:
        print("[pass A] dry-run: no LLM calls, no writes")
        return
    if not chunks:
        print("[pass A] no sections in window — writing empty narrative")

    pieces: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        body = "\n\n".join(
            excerpt(WikiIndex.read_section(WIKI_MD, r), chunk["cap"])
            for r in chunk["records"]
        )
        prompt = _NARRATIVE_PROMPT.format(label=chunk["label"], body=body)
        if verbose:
            print(
                f"[{i}/{len(chunks)}] chunk {chunk['label']}: "
                f"{len(chunk['records'])} sections, {len(prompt):,} chars"
            )
        out = budget.chat(prompt, f"narrative chunk {chunk['label']}")
        status = "ok" if out else "FAILED"
        print(f"[{i}/{len(chunks)}] batch {chunk['label']}: {status}")
        if out:
            pieces.append(f"## {chunk['label']}\n\n{out.strip()}")

    today = datetime.now(timezone.utc).date().isoformat()
    header = (
        f"# Wiki Narrative — as of {today}\n\n"
        f"_Bootstrap run: covers last {days} days across {n_sections} "
        f"sections. Regenerated in full each nightly run once "
        f"dream_nightly ships._\n\n"
    )
    bak = backup(NARRATIVE_OUT)
    if bak:
        print(f"[pass A] backed up prior narrative -> {bak.name}")
    NARRATIVE_OUT.write_text(header + "\n\n".join(pieces) + "\n", encoding="utf-8")
    print(f"[pass A] wrote {NARRATIVE_OUT} ({NARRATIVE_OUT.stat().st_size:,} bytes)")


# ── Pass B — ontology (map-reduce) ────────────────────────────────────────


def plan_ontology(idx: WikiIndex, batch_sections: int) -> list[dict]:
    """Batch plan over ALL sections, ordered by source stream so each
    prompt is thematically bounded, then chronologically within it."""
    ordered = sorted(
        idx.records,
        key=lambda r: (source_stream(r["source"]), r["header_ts"]),
    )
    cap = max(250, CHUNK_CHAR_BUDGET // batch_sections)
    batches: list[dict] = []
    cur: list[dict] = []
    cur_chars = 0
    for r in ordered:
        est = min(r["byte_end"] - r["byte_start"], cap + 200)
        if cur and (
            len(cur) >= batch_sections or cur_chars + est > CHUNK_CHAR_BUDGET
        ):
            batches.append({"records": cur, "cap": cap, "chars": cur_chars})
            cur, cur_chars = [], 0
        cur.append(r)
        cur_chars += est
    if cur:
        batches.append({"records": cur, "cap": cap, "chars": cur_chars})
    return batches


_ONTOLOGY_PROMPT = """\
You are extracting a canonical entity list from excerpts of Brian's
personal knowledge wiki. Each excerpt starts with a
`### <timestamp> — <source> — <title>` header.

An entity is a specific, recurring PERSON, ORG, THING, or PLACE that
exists independently of any one note — a named person, a company or
team, a concrete object/product/project (software projects count as
"thing"), a physical place. NEVER an abstract concept, topic, state,
feeling, or judgment ("productivity", "anxiety", "planning" are NOT
entities).

Naming rules (strict):
- kebab-case slug, lowercase, singular: "moss-pole", not "Moss Poles"
- no prefixes or @: "germaine", not "person-germaine"
- people: first name only, unless two people share it

Return ONLY a JSON object, no prose, exactly this shape:
{{"entities": [{{"name": "kebab-slug", "type": "person|org|thing|place",
  "mentions": <approx count of appearances in THESE excerpts>,
  "sources": ["<source stream, e.g. apple-notes, claude-code>"],
  "confidence": <0.0-1.0 that this is a real recurring entity per the
  rules above>}}]}}

Only include entities actually present in the excerpts. Skip one-off
trivia (a restaurant mentioned once). 5-25 entities is typical.

EXCERPTS:
{body}
"""


def _load_checkpoint() -> dict[int, list[dict]]:
    done: dict[int, list[dict]] = {}
    if CHECKPOINT.exists():
        for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                done[int(row["batch"])] = row["entities"]
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return done


def _normalize_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
    return slug


def _parse_batch_json(raw: str) -> list[dict] | None:
    try:
        data = json.loads(strip_json_fences(raw))
    except json.JSONDecodeError:
        return None
    ents = data.get("entities")
    if not isinstance(ents, list):
        return None
    out = []
    for e in ents:
        if not isinstance(e, dict) or not e.get("name"):
            continue
        name = _normalize_name(e["name"])
        etype = str(e.get("type", "thing")).lower()
        if not name or etype not in _ALLOWED_TYPES:
            continue
        out.append(
            {
                "name": name,
                "type": etype,
                "mentions": max(1, int(e.get("mentions", 1) or 1)),
                "sources": [str(s) for s in e.get("sources", []) if s],
                "confidence": min(1.0, max(0.0, float(e.get("confidence", 0.5)))),
            }
        )
    return out


def run_ontology(
    idx: WikiIndex,
    batch_sections: int,
    budget: Budget,
    dry_run: bool,
    verbose: bool,
    resume: bool,
) -> None:
    batches = plan_ontology(idx, batch_sections)
    est_chars = sum(b["chars"] for b in batches)
    print(
        f"[pass B] ontology: {len(idx.records)} sections -> "
        f"{len(batches)} batches (<= {batch_sections} sections / "
        f"~{CHUNK_CHAR_BUDGET // 1000}K chars each), ~{est_chars:,} prompt "
        f"chars (~{est_chars // 4:,} tokens), estimated LLM calls: {len(batches)}"
    )
    print(
        "[pass B] WARNING: this is the expensive pass — "
        f"{len(batches)} interactive-tier calls."
    )
    if dry_run:
        print("[pass B] dry-run: no LLM calls, no writes")
        return

    done = _load_checkpoint() if resume else {}
    if not resume and CHECKPOINT.exists():
        CHECKPOINT.unlink()
    if done:
        print(f"[pass B] resume: {len(done)} batch(es) already checkpointed")

    # Map
    batch_meta: dict[int, dict] = {}
    for i, batch in enumerate(batches):
        tss = [r["header_ts"] for r in batch["records"]]
        batch_meta[i] = {"first": min(tss), "last": max(tss)}
        if i in done:
            continue
        body = "\n\n".join(
            excerpt(WikiIndex.read_section(WIKI_MD, r), batch["cap"])
            for r in batch["records"]
        )
        prompt = _ONTOLOGY_PROMPT.format(body=body)
        raw = budget.chat(prompt, f"ontology batch {i}")
        ents = _parse_batch_json(raw) if raw else None
        if ents is None:
            status = "FAILED" if raw is None else "PARSE-FAILED"
            print(f"[{i + 1}/{len(batches)}] batch {i}: {status}")
            if raw is not None and verbose:
                print(f"  first 200 chars: {raw[:200]!r}", file=sys.stderr)
            continue
        done[i] = ents
        with CHECKPOINT.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"batch": i, "entities": ents}) + "\n")
        print(f"[{i + 1}/{len(batches)}] batch {i}: ok ({len(ents)} entities)")

    # Reduce — merge on name (case-insensitive; names are normalized slugs)
    merged: dict[str, dict] = {}
    for i, ents in done.items():
        meta = batch_meta.get(i, {"first": "", "last": ""})
        for e in ents:
            m = merged.setdefault(
                e["name"],
                {
                    "name": e["name"], "mentions": 0, "sources": set(),
                    "confs": [], "best": (-1.0, e["type"]),
                    "first": meta["first"], "last": meta["last"],
                    "batches": 0,
                },
            )
            m["mentions"] += e["mentions"]
            m["sources"].update(e["sources"])
            m["confs"].append(e["confidence"])
            if e["confidence"] > m["best"][0]:
                m["best"] = (e["confidence"], e["type"])
            m["batches"] += 1
            if meta["first"] and (not m["first"] or meta["first"] < m["first"]):
                m["first"] = meta["first"]
            if meta["last"] and meta["last"] > m["last"]:
                m["last"] = meta["last"]

    kept: list[dict] = []
    for m in merged.values():
        avg_conf = sum(m["confs"]) / len(m["confs"])
        if avg_conf < 0.5:
            continue
        if m["batches"] == 1 and m["mentions"] < 3:
            continue
        kept.append(
            {
                "name": m["name"], "type": m["best"][1],
                "mentions": m["mentions"],
                "first": m["first"][:10], "last": m["last"][:10],
                "sources": sorted(m["sources"]),
                "conf": round(avg_conf, 2),
            }
        )
    kept.sort(key=lambda e: -e["mentions"])

    # Grounding check: flag entities whose name never literally appears
    # in the corpus (likely inferred/hallucinated — Brian triages).
    corpus = WIKI_MD.read_text(encoding="utf-8", errors="replace").lower()
    flagged = []
    for e in kept:
        variants = {e["name"], e["name"].replace("-", " "), e["name"].replace("-", "")}
        if not any(v in corpus for v in variants):
            e["flag"] = True
            flagged.append(e["name"])
        else:
            e["flag"] = False

    today = datetime.now(timezone.utc).date().isoformat()
    lines = [
        f"# Wiki Ontology — as of {today}",
        "",
        f"_Bootstrap: extracted from all {len(idx.records)} sections "
        f"({len(done)}/{len(batches)} batches succeeded). Rebuilt on "
        f"`dream_weekly`. Merge into existing entities/ via triage or "
        f"manual review._",
        "",
        "| entity | type | mentions | first_seen | last_seen | sources |",
        "|---|---|---|---|---|---|",
    ]
    for e in kept:
        name = e["name"] + (" ⚠" if e["flag"] else "")
        lines.append(
            f"| {name} | {e['type']} | {e['mentions']} | {e['first']} "
            f"| {e['last']} | {', '.join(e['sources'])} |"
        )
    if flagged:
        lines += [
            "",
            "## ⚠ Possibly inferred (name not found verbatim in wiki.md)",
            "",
            "Flagged, not stripped — triage manually: "
            + ", ".join(f"`{n}`" for n in flagged),
        ]
    lines += [
        "",
        f"_{len(kept)} entities kept of {len(merged)} extracted "
        f"(dropped: avg confidence < 0.5, or single-batch with < 3 "
        f"mentions)._",
        "",
    ]

    bak = backup(ONTOLOGY_OUT)
    if bak:
        print(f"[pass B] backed up prior ontology -> {bak.name}")
    ONTOLOGY_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"[pass B] wrote {ONTOLOGY_OUT} ({ONTOLOGY_OUT.stat().st_size:,} "
        f"bytes, {len(kept)} entities, {len(flagged)} flagged)"
    )


# ── CLI ───────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="dream_bootstrap",
        description="One-shot wiki narrative + ontology bootstrap.",
    )
    ap.add_argument(
        "which", nargs="?", default="all",
        choices=["all", "narrative", "ontology"],
        help="which pass to run (default: all)",
    )
    ap.add_argument("--narrative-days", type=int, default=30)
    ap.add_argument("--batch-sections", type=int, default=300,
                    help="max sections per ontology batch (default 300)")
    ap.add_argument("--max-calls", type=int, default=50,
                    help="hard cap on total LLM calls (default 50)")
    ap.add_argument("--resume", action="store_true",
                    help="skip ontology batches already checkpointed")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not WIKI_MD.exists():
        sys.exit(f"{WIKI_MD} not found")
    idx = load_index()
    budget = Budget(args.max_calls)
    t0 = time.monotonic()

    try:
        if args.which in ("all", "narrative"):
            run_narrative(idx, args.narrative_days, budget,
                          args.dry_run, args.verbose)
        if args.which in ("all", "ontology"):
            run_ontology(idx, args.batch_sections, budget,
                         args.dry_run, args.verbose, args.resume)
    except BudgetExceeded as exc:
        print(f"[stop] {exc}", file=sys.stderr)
        sys.exit(2)
    finally:
        mins = (time.monotonic() - t0) / 60
        print(
            f"[done] LLM calls: {budget.calls} "
            f"({budget.failures} failed), wall-clock: {mins:.1f} min"
        )


if __name__ == "__main__":
    main()

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
    python3 -m infra.graphiti.dream_bootstrap compact --dry-run
    python3 -m infra.graphiti.dream_bootstrap            # narrative+ontology

Scheduled runs (see docs/DREAM_CRONS.md): `ontology` weekly (Sunday
06:00, com.mikai.dream-weekly), `compact` monthly (1st 05:00,
com.mikai.dream-monthly). `compact` is zero-LLM: it drops retry/glitch
duplicate sections — same (source, content_bytes) and matching
normalized 256-char body prefix — keeping the oldest copy, rewrites
wiki.md (with backup), rebuilds the index + episode log, retires the
FTS db, and leaves a compact-report-<date>.md.

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
NARRATIVE_STATE = WIKI_DIR / ".narrative-state.json"

# Consolidation MVP (Pass E — promote):
CONCEPTS_DIR = WIKI_DIR / "concepts"
SALIENCE_LEDGER = WIKI_DIR / "wiki-salience.md"
USER_MODEL_MD = Path.home() / ".mikai" / "brain" / "USER_MODEL.md"

DECAY_RATE = 0.5              # ACT-R d = 0.5 (Anderson & Schooler 1991)
PROMOTE_DEFAULT_THRESHOLD = 4.0
PROMOTE_DEFAULT_CAP = 10
NGRAM_MIN_COUNT = 5
NGRAM_MIN_NONSTOP_CHARS = 8

# Build 1 (Fable's SALIENCE_MVP_DIAGNOSIS.md): case-blind extraction.
# Lowercase phrases need a higher frequency floor than capitalized ones
# because common English 1–3-grams flood the counter. 15 is the "posture
# has 723 mentions but graphiti has 591 and got promoted, so 15 leaves
# real signal without noise flood" threshold.
LOWERCASE_NGRAM_MIN_COUNT = 15
LOWERCASE_NGRAM_MIN_NONSTOP_CHARS = 5

# Self-corpus stoplist path. If missing, the pass auto-generates from
# repo file/dir names (things named as MIKAI infrastructure — sidecar,
# graphiti, wiki_index, cockpit, dream_bootstrap, etc. — are removed as
# candidates so the promotion pass doesn't reward "MIKAI ingests its own
# build sessions" self-referential vocabulary).
SELF_CORPUS_STOPLIST = Path.home() / ".mikai" / "brain" / "self-corpus-stoplist.txt"

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
    # A full rebuild covers everything up to now — reset the incremental
    # watermark so the next nightly delta starts from here (the rebuild
    # replaces any dated deltas the file previously carried).
    _save_narrative_state(datetime.now(timezone.utc).isoformat(timespec="seconds"))
    print(f"[pass A] reset incremental watermark ({NARRATIVE_STATE.name})")


# ── Pass A′ — incremental (nightly) narrative delta ───────────────────────


INCR_MIN_SECTIONS = 5          # fewer new sections than this -> nothing to say
INCR_CHAR_BUDGET = 300_000     # single-call prompt ceiling (~75K tokens)
INCR_RETENTION_DAYS = 30       # dated deltas older than this are truncated
INCR_DEFAULT_LOOKBACK_H = 24   # first run ever: cover the last day

_DELTA_HEADER_RE = re.compile(r"^## Δ (\d{4}-\d{2}-\d{2})", re.MULTILINE)


def _load_narrative_state() -> str | None:
    """-> last_run_ts (ISO) or None if no state yet."""
    if not NARRATIVE_STATE.exists():
        return None
    try:
        return json.loads(NARRATIVE_STATE.read_text(encoding="utf-8"))["last_run_ts"]
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def _save_narrative_state(last_run_ts: str) -> None:
    NARRATIVE_STATE.write_text(
        json.dumps(
            {
                "last_run_ts": last_run_ts,
                "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _split_deltas(text: str) -> tuple[str, list[tuple[str, str]]]:
    """-> (base_text, [(date, delta_block), ...]). base = everything
    before the first `## Δ YYYY-MM-DD` header (bootstrap/weekly body)."""
    matches = list(_DELTA_HEADER_RE.finditer(text))
    if not matches:
        return text, []
    base = text[: matches[0].start()]
    deltas: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        deltas.append((m.group(1), text[m.start():end].rstrip() + "\n"))
    return base, deltas


_INCR_PROMPT = """\
You are appending today's entry to Brian's private activity journal.
Below are dated excerpts from his personal knowledge wiki covering only
what is NEW since the last journal entry ({since}) — notes, Claude
sessions, research, messages. Each excerpt starts with a
`### <timestamp> — <source> — <title>` header.

Write a 200-500 word FIRST-PERSON delta narrative (Brian's voice, "I")
of what happened since then: what I worked on, decided, researched,
worried about, and left unfinished. Name the specific threads, projects,
people, and decisions that actually appear in the excerpts — no generic
filler. Ground every claim in the excerpts; if something is ambiguous,
hedge or omit it. Never invent people, events, or decisions.

Output: the narrative prose only. No preamble, no headers, no bullet
lists.

EXCERPTS:
{body}
"""


def run_narrative_incremental(
    idx: WikiIndex, budget: Budget, dry_run: bool, verbose: bool
) -> str:
    """Nightly delta: one LLM call over sections newer than the last run,
    APPENDED to wiki-narrative.md under a dated `## Δ` header. Dated
    deltas older than INCR_RETENTION_DAYS are truncated. Returns a
    one-line summary (for the ledger trace)."""
    last_ts = _load_narrative_state()
    if last_ts is None:
        since = datetime.now(timezone.utc) - timedelta(hours=INCR_DEFAULT_LOOKBACK_H)
        last_ts = since.isoformat(timespec="seconds")
        print(f"[pass A-incr] no state file — defaulting to last "
              f"{INCR_DEFAULT_LOOKBACK_H}h (since {last_ts})")
    records = [
        r for r in idx.sections_matching(since=last_ts)
        if r["header_ts"] > last_ts
    ]
    print(f"[pass A-incr] {len(records)} new section(s) since {last_ts}")

    if len(records) < INCR_MIN_SECTIONS:
        msg = (f"skipped: only {len(records)} new section(s) since {last_ts} "
               f"(< {INCR_MIN_SECTIONS}) — nothing to say")
        print(f"[pass A-incr] {msg}")
        # Watermark intentionally NOT advanced: the trickle accumulates
        # until there is enough to narrate.
        return msg

    cap = max(300, min(4000, INCR_CHAR_BUDGET // len(records)))
    if dry_run:
        est = sum(min(r["byte_end"] - r["byte_start"], cap + 200) for r in records)
        newest = max(r["header_ts"] for r in records)
        print(
            f"[pass A-incr] dry-run: would send 1 LLM call "
            f"(~{est:,} prompt chars, ~{est // 4:,} tokens, per-section "
            f"cap {cap}), append '## Δ "
            f"{datetime.now(timezone.utc).date().isoformat()}' to "
            f"{NARRATIVE_OUT.name}, advance watermark {last_ts} -> {newest}"
        )
        return "dry-run"

    body = "\n\n".join(
        excerpt(WikiIndex.read_section(WIKI_MD, r), cap) for r in records
    )
    if len(body) > INCR_CHAR_BUDGET:
        body = body[:INCR_CHAR_BUDGET] + "\n…[window truncated]"
    if verbose:
        print(f"[pass A-incr] prompt body: {len(body):,} chars, "
              f"per-section cap {cap}")
    out = budget.chat(
        _INCR_PROMPT.format(since=last_ts, body=body), "incremental narrative"
    )
    if not out:
        print("[pass A-incr] LLM call FAILED — no write, watermark unchanged")
        return "FAILED: LLM call returned nothing"

    today = datetime.now(timezone.utc).date().isoformat()
    existing = (
        NARRATIVE_OUT.read_text(encoding="utf-8")
        if NARRATIVE_OUT.exists()
        else f"# Wiki Narrative — as of {today}\n\n_(started by nightly "
             f"incremental dream — no full bootstrap narrative yet)_\n"
    )
    base, deltas = _split_deltas(existing)
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=INCR_RETENTION_DAYS)
    ).date().isoformat()
    kept = [(d, block) for d, block in deltas if d >= cutoff]
    dropped = len(deltas) - len(kept)
    if dropped:
        print(f"[pass A-incr] truncated {dropped} delta(s) older than {cutoff}")

    new_block = (
        f"## Δ {today} — nightly delta (since {last_ts}, "
        f"{len(records)} sections)\n\n{out.strip()}\n"
    )
    text = base.rstrip() + "\n\n" + "\n\n".join(
        [block.rstrip() for _, block in kept] + [new_block]
    ) + "\n"
    NARRATIVE_OUT.write_text(text, encoding="utf-8")
    print(f"[pass A-incr] appended '## Δ {today}' to {NARRATIVE_OUT} "
          f"({NARRATIVE_OUT.stat().st_size:,} bytes)")

    newest = max(r["header_ts"] for r in records)
    _save_narrative_state(newest)
    print(f"[pass A-incr] watermark -> {newest}")
    return (f"nightly delta: {len(records)} sections since {last_ts}, "
            f"{dropped} old delta(s) truncated")


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


# ── Pass C — compact (monthly, zero-LLM dedup) ────────────────────────────


EPISODE_LOG = WIKI_DIR / "wiki-episodes.log"
FTS_DB = WIKI_DIR / "wiki.fts.db"


def _body_prefix(section_text: str, n: int = 256) -> str:
    """Normalized first-n-chars of the section body (header + ingested
    comment stripped, lowercased, whitespace collapsed)."""
    lines = section_text.split("\n", 1)
    body = _INGESTED_RE.sub("", lines[1] if len(lines) > 1 else "")
    return re.sub(r"\s+", " ", body).strip().lower()[:n]


def _find_duplicates(idx: WikiIndex) -> tuple[list[dict], list[list[dict]]]:
    """Group sections by (source, content_bytes, normalized 256-char body
    prefix). Returns (survivors_in_file_order, duplicate_groups) where
    each group is [kept, dropped, dropped, ...] sorted oldest-first by
    reference_time (header_ts) — the OLDEST copy survives."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in idx.records:
        prefix = _body_prefix(WikiIndex.read_section(WIKI_MD, r))
        groups[(r["source"], r["content_bytes"], prefix)].append(r)

    drop_ids: set[int] = set()
    dup_groups: list[list[dict]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda r: r["header_ts"])
        dup_groups.append(members)
        drop_ids.update(id(r) for r in members[1:])

    survivors = [r for r in idx.records if id(r) not in drop_ids]
    return survivors, dup_groups


def run_compact(idx: WikiIndex, dry_run: bool, verbose: bool) -> None:
    snapshot_size = idx.scanned_bytes  # wiki.md size at index-build time
    survivors, dup_groups = _find_duplicates(idx)
    n_dropped = len(idx.records) - len(survivors)
    bytes_reclaimed = sum(
        r["byte_end"] - r["byte_start"]
        for g in dup_groups
        for r in g[1:]
    )
    print(
        f"[pass C] compact: {len(idx.records)} sections, "
        f"{len(dup_groups)} duplicate group(s), {n_dropped} section(s) to "
        f"drop, ~{bytes_reclaimed:,} bytes to reclaim"
    )
    if verbose:
        for g in dup_groups:
            k = g[0]
            print(
                f"  keep {k['header_ts']} — {k['source']} — {k['name']}; "
                f"drop {len(g) - 1} copy(ies) at "
                + ", ".join(r["header_ts"] for r in g[1:])
            )
    if dry_run:
        print("[pass C] dry-run: no writes")
        return

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    today = datetime.now(timezone.utc).date().isoformat()

    if n_dropped == 0:
        print("[pass C] no duplicates — wiki.md untouched")
        _write_compact_report(today, idx, dup_groups, 0, None)
        return

    # Rewrite wiki.md: preamble + surviving sections (verbatim byte
    # slices, file order), via temp file + atomic replace. If the wiki
    # grew while we worked (ingest race), carry the appended tail over.
    raw = WIKI_MD.read_bytes()
    preamble_end = idx.records[0]["byte_start"]
    parts = [raw[:preamble_end]]
    for r in survivors:
        parts.append(raw[r["byte_start"]:r["byte_end"]])
    if len(raw) > snapshot_size:
        print(
            f"[pass C] wiki.md grew during compaction "
            f"({len(raw):,} > {snapshot_size:,}) — preserving appended tail"
        )
        parts.append(raw[snapshot_size:])

    bak_md = WIKI_MD.with_name(f"wiki.md.pre-compact-{ts}")
    bak_md.write_bytes(raw)
    print(f"[pass C] backed up wiki.md -> {bak_md.name}")

    tmp = WIKI_MD.with_suffix(".md.compact-tmp")
    tmp.write_bytes(b"".join(parts))
    import os as _os
    _os.replace(tmp, WIKI_MD)
    print(f"[pass C] wrote {WIKI_MD} ({WIKI_MD.stat().st_size:,} bytes)")

    # Derived files: rebuild index, rewrite episode log from the new
    # index, retire the FTS db (disposable — adapter regrows it via
    # rebuild_if_stale on next access). All originals backed up first.
    if WIKI_INDEX.exists():
        WIKI_INDEX.with_name(f"wiki.index.pre-compact-{ts}").write_bytes(
            WIKI_INDEX.read_bytes()
        )
    new_idx = WikiIndex.build(WIKI_MD)
    new_idx.save(WIKI_INDEX)
    print(f"[pass C] rebuilt wiki.index ({len(new_idx.records)} sections)")

    if EPISODE_LOG.exists():
        EPISODE_LOG.with_name(
            f"wiki-episodes.log.pre-compact-{ts}"
        ).write_bytes(EPISODE_LOG.read_bytes())
    with EPISODE_LOG.open("w", encoding="utf-8") as f:
        for r in new_idx.records:
            f.write(f"{r['header_ts']} {r['source']} {r['content_bytes']}\n")
    print(f"[pass C] rewrote wiki-episodes.log ({len(new_idx.records)} lines)")

    if FTS_DB.exists():
        _os.replace(FTS_DB, FTS_DB.with_name(f"wiki.fts.db.pre-compact-{ts}"))
        for suffix in ("-wal", "-shm"):
            side = FTS_DB.with_name(FTS_DB.name + suffix)
            if side.exists():
                side.unlink()
        print("[pass C] retired wiki.fts.db (adapter rebuilds on next access)")

    _write_compact_report(today, idx, dup_groups, bytes_reclaimed, bak_md)


def _write_compact_report(
    today: str,
    idx: WikiIndex,
    dup_groups: list[list[dict]],
    bytes_reclaimed: int,
    bak_md: Path | None,
) -> None:
    n_dropped = sum(len(g) - 1 for g in dup_groups)
    lines = [
        f"# Wiki Compaction Report — {today}",
        "",
        f"- sections scanned: {len(idx.records)}",
        f"- duplicate groups: {len(dup_groups)}",
        f"- sections dropped: {n_dropped}",
        f"- bytes reclaimed: {bytes_reclaimed:,}",
        f"- backup: {bak_md.name if bak_md else '(none — nothing dropped)'}",
        "",
    ]
    if dup_groups:
        lines += ["## Sample duplicates (kept the oldest of each group)", ""]
        for g in dup_groups[:20]:
            k = g[0]
            lines.append(
                f"- **{k['name']}** ({k['source']}, {k['content_bytes']}B): "
                f"kept {k['header_ts']}, dropped "
                + ", ".join(r["header_ts"] for r in g[1:])
            )
        if len(dup_groups) > 20:
            lines.append(f"- … and {len(dup_groups) - 20} more group(s)")
        lines.append("")
    report = WIKI_DIR / f"compact-report-{today}.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"[pass C] report -> {report}")


# ── Ledger trace (health-check heartbeat) ─────────────────────────────────


def _ledger_trace(mode: str, did: str, budget: Budget) -> None:
    """Best-effort progress.jsonl row so infra.mikai_brain.health can see
    the scheduled job fired. Never allowed to fail the dream run."""
    try:
        from infra.mikai_brain import ledger

        ledger.run(mode=mode, did=did,
                   extra={"llm_calls": budget.calls,
                          "llm_failures": budget.failures})
        print(f"[ledger] trace written: mode={mode}")
    except Exception as exc:
        print(f"[ledger] trace failed (non-fatal): {exc}", file=sys.stderr)


# ── Pass D: user-model rebuild (weekly, 1 LLM call) ───────────────────────


def run_user_model(budget: Budget, dry_run: bool, verbose: bool) -> str:
    """Rebuild USER_MODEL.md via infra.mikai_brain.user_model.build().

    One interactive-tier LLM call. Counted against `budget` (weekly
    runner has plenty of headroom). Never nightly — see
    docs/USER_MODEL_RESEARCH.md for the weekly-cadence rationale."""
    from infra.mikai_brain import user_model as um_mod

    print("[pass D] rebuilding USER_MODEL.md from substrate")
    if dry_run:
        bundle = um_mod.collect_inputs()
        print(f"[pass D] dry-run — would send {len(bundle)}ch input to interactive tier")
        return "user-model dry-run"

    # Route the synthesizer call through the shared Budget so it
    # rate-limits and counts against --max-calls like every other pass.
    def _budget_chat(prompt: str) -> str:
        out = budget.chat(prompt, "user-model synthesizer")
        if out is None:
            raise RuntimeError("user-model synthesizer call failed (see stderr)")
        return out

    try:
        model = um_mod.build(chat_fn=_budget_chat)
    except RuntimeError as exc:
        print(f"[pass D] build failed: {exc}", file=sys.stderr)
        raise

    md_path, json_path = um_mod.save(model)
    if verbose:
        print(model.to_markdown())
    print(f"[pass D] wrote {md_path} ({md_path.stat().st_size}B)")
    print(f"[pass D] wrote {json_path}")
    return (
        f"user-model rebuild: {len(model.durable)} durable, "
        f"{len(model.current)} current"
    )


# ── Pass E: promote (Consolidation MVP) ───────────────────────────────────
#
# The magnum-opus formula (see docs/SALIENCE_FORMULA.md):
#     S(c, t) = w₁·ln(Σᵢ (t−tᵢ)⁻ᵈ) + w₂·spread(c) + w₃·goal_overlap(c)
#
# MVP form: all weights = 1, d = 0.5, hand-set threshold. The four LLM
# entry points Fable enumerated (E1 canonicalization, E2 goal inference,
# E3 importance rating I(c), E4 promotion gate) are DEFERRED — none run
# in the MVP. The only LLM call per pass is one 3-sentence summary per
# promoted concept (Budget-capped).
#
# "No taxonomy" per Brian's 2026-08-08 call: candidates come from BOTH
# wiki-ontology.md (entity-flavored) AND capitalized-phrase extraction
# over wiki.md (concept-flavored). One scoring loop, one output dir, one
# ledger. Entity vs concept is a v2 sort — the formula is agnostic.
#
# Output surfaces:
# - ~/.mikai/wiki/concepts/<slug>.md  — one page per promoted candidate
# - ~/.mikai/wiki/wiki-salience.md    — ranked audit ledger (every score,
#                                        every term, promoted marker)

_NGRAM_STOP = frozenset("""
the this that these those my our your his her their its
a an and or but for nor so yet as if in on at by to of from with
he she they we you it i me us them him her
is are was were be being been have has had do does did
will would could should may might must shall can
not no yes than then when where while why how what who whom whose
about above across after against along among around because before below
between during into like near off onto out over past since through
throughout under until upon within without also just more most other
some such very much many few little several own same each every any
here there now today yesterday tomorrow later earlier soon still already
""".split())

_NGRAM_RE = re.compile(
    r"\b(?:[A-Z][a-z0-9]+(?:-[A-Za-z0-9]+)?)"
    r"(?:\s+[A-Z][a-z0-9]+(?:-[A-Za-z0-9]+)?){1,3}\b"
)

# Lowercase 1–3 word token pattern (Build 1). Deliberately permissive
# because filtering happens after — _ngram_ok_lower drops leading/trailing
# stopwords and length-2 all-common phrases. Words are ≥3 chars to skip
# noise like "as", "is", "at" that _NGRAM_STOP might miss in some forms.
_NGRAM_RE_LOWER = re.compile(
    r"\b([a-z][a-z0-9]{2,}(?:-[a-z0-9]+)?"
    r"(?:\s+[a-z][a-z0-9]{2,}(?:-[a-z0-9]+)?){0,2})\b"
)


def _slugify(name: str) -> str:
    """Concept name → kebab-case filename slug."""
    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unknown"


def _ngram_ok(phrase: str) -> bool:
    """N-gram candidate filter: no leading stopword, enough real letters.
    Kills 'The System', 'This Approach', 'Next Step' — keeps 'Task State
    Awareness', 'Agent Memory', 'Attention Head'."""
    words = phrase.split()
    if not words:
        return False
    if words[0].lower() in _NGRAM_STOP:
        return False
    non_stop_chars = sum(len(w) for w in words if w.lower() not in _NGRAM_STOP)
    return non_stop_chars >= NGRAM_MIN_NONSTOP_CHARS


def _ngram_ok_lower(phrase: str) -> bool:
    """Lowercase-phrase filter (Build 1). Same shape as _ngram_ok but
    with a lower char threshold — single-word lowercase candidates like
    'posture' (7 chars) and 'workout' (7 chars) are the point of this
    pass and would fail an 8-char rule. Rejects candidates whose FIRST
    OR LAST word is a stopword, so 'posture correction' passes but
    'the posture' and 'posture is' don't."""
    words = phrase.split()
    if not words:
        return False
    if words[0] in _NGRAM_STOP or words[-1] in _NGRAM_STOP:
        return False
    non_stop_chars = sum(len(w) for w in words if w not in _NGRAM_STOP)
    return non_stop_chars >= LOWERCASE_NGRAM_MIN_NONSTOP_CHARS


def parse_ontology_candidates(path: Path) -> list[dict]:
    """Parse wiki-ontology.md's markdown table → [{name, kind, type}].
    Mentions/tᵢ recomputed at scan time (ontology counts can be stale)."""
    if not path.exists():
        return []
    out = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        # skip header/separator rows
        if line.startswith("|---") or line.lower().startswith("| entity"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 6:
            continue
        name, typ = cols[0], cols[1]
        if not name or typ not in _ALLOWED_TYPES:
            continue
        out.append({"name": name, "kind": "entity", "type": typ})
    return out


def extract_ngram_candidates(idx: WikiIndex, wiki_md: Path) -> list[dict]:
    """Scan every wiki.md section body once. Return capitalized 2-4 word
    phrases (per _NGRAM_RE) appearing >= NGRAM_MIN_COUNT times, filtered
    by _ngram_ok. These are the concept-flavored candidates that ontology
    extraction (proper-nouns-only) never surfaces."""
    from collections import Counter
    counter: Counter = Counter()
    for rec in idx.records:
        try:
            text = idx.read_section(wiki_md, rec)
        except Exception:  # noqa: BLE001 — one bad section shouldn't abort
            continue
        # skip header line + ingested-comment line
        body_start = text.find("\n") + 1
        body = _INGESTED_RE.sub("", text[body_start:])
        for m in _NGRAM_RE.finditer(body):
            phrase = m.group(0).strip()
            if _ngram_ok(phrase):
                counter[phrase] += 1
    return [{"name": name, "kind": "concept"}
            for name, count in counter.items()
            if count >= NGRAM_MIN_COUNT]


def extract_lowercase_ngram_candidates(idx: WikiIndex,
                                       wiki_md: Path) -> list[dict]:
    """Build 1: scan every wiki.md section body once for LOWERCASE 1-3
    word phrases. Same output shape as extract_ngram_candidates. Uses a
    higher frequency floor (LOWERCASE_NGRAM_MIN_COUNT=15) than the
    capitalized pass to keep noise bounded.

    Diagnosis 2026-08-08: 'posture' (~723 mentions), 'workout' (~256),
    'parents' (~185), 'startup' (~426), 'proposal spot' (~130) never
    became candidates because the capitalized-only regex excluded them.
    This function is the fix.

    De-duplication is per-section: a phrase that appears twice in one
    section counts once toward its frequency total (prevents dense-
    section outliers from inflating counts). Overlapping phrases within
    a section ('posture correction' + 'posture') each count for their
    own row."""
    from collections import Counter
    counter: Counter = Counter()
    for rec in idx.records:
        try:
            text = idx.read_section(wiki_md, rec)
        except Exception:  # noqa: BLE001
            continue
        body_start = text.find("\n") + 1
        body = _INGESTED_RE.sub("", text[body_start:]).lower()
        section_phrases: set[str] = set()
        for m in _NGRAM_RE_LOWER.finditer(body):
            phrase = m.group(1).strip()
            if _ngram_ok_lower(phrase):
                section_phrases.add(phrase)
        for p in section_phrases:
            counter[p] += 1
    return [{"name": name, "kind": "concept-lower"}
            for name, count in counter.items()
            if count >= LOWERCASE_NGRAM_MIN_COUNT]


def _build_self_corpus_stoplist() -> set[str]:
    """Build 1: identifiers appearing as file/dir names in MIKAI's own
    repo become an exclusion set. Counters the self-referential-corpus
    bias — 'dream_bootstrap', 'wiki_adapter', 'sidecar' should not
    compete for salience as if they were topics Brian thinks about.

    Uses a hand-maintained file if present (~/.mikai/brain/
    self-corpus-stoplist.txt, one term per line, comments ignored).
    Otherwise auto-generates from the repo the script lives in — file
    stems + directory names, kebab-cased.

    Never returns empty when the auto path runs: at minimum it seeds
    ['infra', 'sidecar', 'graphiti', 'wiki', 'cockpit', 'mikai'] so a
    first run without a hand-list still filters obvious infra
    vocabulary — the '.mikai/wiki/wiki.md' path itself would otherwise
    make 'wiki' rank high as a bare concept."""
    stoplist: set[str] = set()
    if SELF_CORPUS_STOPLIST.exists():
        for raw in SELF_CORPUS_STOPLIST.read_text().splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                stoplist.add(line.lower())
        return stoplist
    # Auto-generate from repo file/dir names.
    for p in _REPO.rglob("*"):
        if any(part.startswith(".") for part in p.parts[len(_REPO.parts):]):
            continue
        if p.is_file():
            stem = p.stem.lower().replace("_", "-")
            if len(stem) >= 3:
                stoplist.add(stem)
        for part in p.parts[len(_REPO.parts):]:
            norm = part.lower().replace("_", "-")
            if len(norm) >= 3 and "." not in norm:
                stoplist.add(norm)
    # Seed the obvious ones so tests + fresh runs behave.
    stoplist.update({
        "infra", "sidecar", "graphiti", "wiki", "cockpit", "mikai",
        "dream", "brain", "concepts",
    })
    return stoplist


# ── Build 2: deterministic alias folding (E1-lite) ───────────────────────


def _alias_key(name: str) -> str:
    """Normalize a candidate name into an alias-grouping key.
    'Claude Code', 'claude-code', 'Claude-Code', 'claude  code', 'Claude
    Codes' all fold to 'claude code'. Preserves multi-word structure so
    'Family Day' and 'Family Controls' stay separate — v0 does NOT do
    modifier-variant folding ('Mint Monstera' → 'monstera'); that
    requires embedding cosine (Fable's spec), deferred to v1."""
    s = name.lower().strip()
    s = re.sub(r"[-_/]+", " ", s)     # unify separators
    s = re.sub(r"\s+", " ", s).strip()
    words = s.split()
    # Strip trailing plural 's' from words >3 chars to fold 'threads'→'thread',
    # while leaving 'os', 'as', 'is' alone.
    words = [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words]
    return " ".join(words)


def _fold_aliases(candidates: list[dict]) -> list[dict]:
    """Group candidates by alias key. Each group produces ONE head
    candidate with an 'aliases' list of the other member names.

    Head selection rules:
    1. If any group member is an ontology entry (kind='entity'), it wins
       — ontology carries type (person/org/thing/place) that shouldn't be
       lost to a capitalized-phrase variant.
    2. Otherwise the SHORTEST name wins — 'monstera' beats 'monstera-adansonii'.
    3. Ties break alphabetically for determinism.

    Every returned candidate has an 'aliases' key (possibly empty list),
    so downstream code can uniformly pass the dict to find_mention_records.
    Ledger + concept-page writers use 'aliases' to show constituents."""
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in candidates:
        groups[_alias_key(c["name"])].append(c)
    out: list[dict] = []
    for _, group in groups.items():
        if len(group) == 1:
            group[0].setdefault("aliases", [])
            out.append(group[0])
            continue
        onto = [c for c in group if c.get("kind") == "entity"]
        pool = onto if onto else group
        head = min(pool, key=lambda c: (len(c["name"]), c["name"]))
        aliases = sorted({c["name"] for c in group if c is not head})
        head["aliases"] = aliases
        out.append(head)
    return out


def find_mention_records(candidate, records, wiki_md: Path) -> list[dict]:
    """Sections whose body contains the candidate as a WHOLE-WORD match
    (case-insensitive). Word boundaries are essential — plain substring
    matching would count 'mem' inside 'memory'/'member'/'remember', 'pri'
    inside 'priority', 'mark' inside 'market' — inflating short-name
    counts by 100x+ and flooding the ledger with fragment candidates.

    `records` is a list of WikiIndex record dicts (was WikiIndex before
    the 2026-08-09 multiprocessing refactor — records are pickleable,
    a full WikiIndex is not so cheaply). `candidate` may be either a
    str OR a dict with 'name' + 'aliases' — in the dict shape the
    returned mention set is the UNION over head + all aliases,
    deduplicated by byte_start.

    Returns [{header_ts, source_stream, byte_start, section_name}]."""
    if isinstance(candidate, dict):
        names = [candidate["name"]] + list(candidate.get("aliases") or [])
    else:
        names = [candidate]
    alts = "|".join(re.escape(n.lower()) for n in names if n)
    if not alts:
        return []
    pattern = re.compile(r"\b(?:" + alts + r")\b", re.IGNORECASE)
    seen: set[int] = set()
    out = []
    for rec in records:
        try:
            text = WikiIndex.read_section(wiki_md, rec)
        except Exception:  # noqa: BLE001
            continue
        if pattern.search(text):
            key = rec.get("byte_start", 0)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "header_ts": rec.get("header_ts", ""),
                "source_stream": source_stream(rec.get("source", "")),
                "byte_start": key,
                "section_name": rec.get("name", ""),
            })
    return out


# ── Build 2.5: multiprocessing scoring workers ────────────────────────────
# Pure-Python regex scoring over ~5000 candidates × 8000 sections was
# ~40 min single-threaded. multiprocessing.Pool over CPU cores drops
# that to ~5-10 min. Workers are initialized once per process with the
# index records list, wiki path, goals text, and reference timestamp —
# all pickleable — via `initializer`. Each `_promote_worker_score(cand)`
# call is stateless w.r.t. the pool (writes only to its own return
# value); the parent aggregates.

_PROMOTE_WORKER_CTX: dict = {}


def _promote_worker_init(records: list, wiki_md_str: str,
                         goals_text: str, now_iso: str) -> None:
    """One-time per-worker setup. Runs in each Pool worker on startup."""
    _PROMOTE_WORKER_CTX["records"] = records
    _PROMOTE_WORKER_CTX["wiki_md"] = Path(wiki_md_str)
    _PROMOTE_WORKER_CTX["goals_text"] = goals_text
    _PROMOTE_WORKER_CTX["now"] = datetime.fromisoformat(now_iso)


def _promote_worker_score(cand: dict):
    """Per-candidate work unit. Returns (cand, score, mentions) or None.
    None when the candidate has zero mentions (dropped from the ledger)."""
    ctx = _PROMOTE_WORKER_CTX
    mentions = find_mention_records(cand, ctx["records"], ctx["wiki_md"])
    if not mentions:
        return None
    score = compute_score(cand, mentions, ctx["goals_text"], ctx["now"])
    return (cand, score, mentions)


def _load_user_goals() -> str:
    """USER_MODEL.md's Current section (lowercased) — the goal-overlap
    keyword pool for w₃. Empty string when the file is missing. The
    embedding upgrade (max-sim over Voyage embeddings) is v2 — this
    keyword variant is enough to prove the term earns its place."""
    if not USER_MODEL_MD.exists():
        return ""
    text = USER_MODEL_MD.read_text().lower()
    m = re.search(r"##\s*current(.*?)(?=^## |\Z)", text,
                  re.MULTILINE | re.DOTALL)
    return m.group(1) if m else text


def compute_score(candidate: dict, mentions: list[dict],
                  goals_text: str, now: datetime) -> dict:
    """S = base_activation + spread + goal_overlap. All weights = 1.

    base_activation = ln(Σᵢ (t_now − tᵢ)⁻⁰·⁵) with tᵢ in DAYS. ACT-R form.
    spread = distinct source streams (Notes / Claude / code / …). ACT-R
             lacks this; it's cross-context validity evidence.
    goal_overlap = count of non-trivial tokens the candidate name shares
                   with USER_MODEL.md's Current section.

    Returns full breakdown dict so the ledger prints term-by-term.
    """
    import math
    activations = []
    for m in mentions:
        try:
            ts = parse_ts(m["header_ts"])
            age_days = max(1.0, (now - ts).total_seconds() / 86400.0)
            activations.append(age_days ** -DECAY_RATE)
        except Exception:  # noqa: BLE001
            continue
    base = math.log(sum(activations)) if activations else 0.0
    streams = {m["source_stream"] for m in mentions if m["source_stream"]}
    spread = float(len(streams))
    goal_tokens = set(re.findall(r"[a-z]{4,}", goals_text))
    cand_tokens = set(re.findall(r"[a-z]{4,}", candidate["name"].lower()))
    goal_overlap = float(len(cand_tokens & goal_tokens))
    return {
        "S": base + spread + goal_overlap,
        "base_activation": base,
        "spread": spread,
        "goal_overlap": goal_overlap,
        "n_mentions": len(mentions),
        "streams": sorted(streams),
    }


def _concept_summary_llm(candidate: dict, sample_excerpts: list[str],
                         budget: Budget) -> str | None:
    """One 3-sentence factual summary via interactive tier. Returns None
    on LLM failure — page still writes with a placeholder note."""
    if not sample_excerpts:
        return None
    prompt = (
        f"Write a 3-sentence factual summary of the concept "
        f"'{candidate['name']}' based ONLY on these excerpts from Brian's "
        f"personal notes and Claude threads. Do not invent. If the "
        f"excerpts don't support a claim, say so plainly. No preamble.\n\n"
        f"---\n"
        + "\n\n---\n".join(sample_excerpts[:8])
    )
    return budget.chat(
        prompt, f"promote-summary:{_slugify(candidate['name'])}"
    )


def _write_concept_page(candidate: dict, score: dict, mentions: list[dict],
                        summary: str | None, out_dir: Path) -> Path:
    """Write ~/.mikai/wiki/concepts/<slug>.md — idempotent overwrite."""
    slug = _slugify(candidate["name"])
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slug}.md"
    aliases = candidate.get("aliases") or []
    lines = [
        "---",
        f"name: {candidate['name']}",
        f"slug: {slug}",
        f"kind: {candidate.get('kind', 'unknown')}",
        f"promoted_at: {datetime.now(timezone.utc).isoformat()}",
        f"salience_score: {score['S']:.3f}",
        f"n_mentions: {score['n_mentions']}",
        f"aliases: [{', '.join(aliases)}]" if aliases
        else "aliases: []",
        "---",
        "",
        f"# {candidate['name']}",
        "",
        summary or "_(no summary — LLM call skipped or failed)_",
        "",
        "## Salience breakdown",
        "",
        f"- **S = {score['S']:.3f}**",
        f"- base_activation (ACT-R ln Σ(Δt)⁻⁰·⁵): {score['base_activation']:.3f}",
        f"- spread (distinct source streams): {int(score['spread'])}"
        f" — {', '.join(score['streams']) if score['streams'] else '—'}",
        f"- goal_overlap (∩ USER_MODEL.md Current): {int(score['goal_overlap'])}",
        "",
        f"## Mentions ({score['n_mentions']} sections)",
        "",
    ]
    for m in mentions[:100]:  # cap link list at 100 for page readability
        ts = m["header_ts"]
        name = m["section_name"]
        lines.append(
            f"- [[{ts} — {name}]]  _(source: {m['source_stream']})_"
        )
    if len(mentions) > 100:
        lines.append(f"- _(…and {len(mentions) - 100} more)_")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_salience_ledger(
    ranked: list[tuple[dict, dict, list[dict]]],
    threshold: float,
    cap: int,
    promoted_slugs: set[str],
    path: Path,
) -> None:
    """Write wiki-salience.md — every scored candidate + term breakdown.
    Audit surface AND the labeling instrument the afternoon test needs."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Salience Ledger — {today}",
        "",
        f"- candidates scored: {len(ranked)}",
        f"- threshold: {threshold:.2f}",
        f"- promotion cap: {cap}/night",
        f"- promoted this pass: {len(promoted_slugs)}",
        "",
        "Formula: `S = ln(Σ(Δt)^-0.5) + spread + goal_overlap`,"
        " all weights = 1, d = 0.5",
        "",
        "## Ranked candidates",
        "",
        "| Rank | Concept | S | base | spread | goal | mentions | Promoted? |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines[-2] = ("| Rank | Concept | S | base | spread | goal | mentions"
                 " | aliases | Promoted? |")
    lines[-1] = "|---|---|---|---|---|---|---|---|---|"
    for i, (cand, score, _) in enumerate(ranked, 1):
        slug = _slugify(cand["name"])
        promoted = "✓" if slug in promoted_slugs else ""
        aliases = cand.get("aliases") or []
        alias_cell = ", ".join(aliases[:3]) + (
            f" (+{len(aliases) - 3})" if len(aliases) > 3 else ""
        ) if aliases else ""
        lines.append(
            f"| {i} | {cand['name']} | {score['S']:.2f} | "
            f"{score['base_activation']:.2f} | {int(score['spread'])} | "
            f"{int(score['goal_overlap'])} | {score['n_mentions']} | "
            f"{alias_cell} | {promoted} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_promote(idx: WikiIndex, budget: Budget, threshold: float, cap: int,
                dry_run: bool, verbose: bool) -> str:
    """Consolidation MVP: score all candidates, promote top-N above
    threshold to concept pages, write salience ledger."""
    print("[pass E] loading candidates")
    onto_cands = parse_ontology_candidates(ONTOLOGY_OUT)
    ngram_cands = extract_ngram_candidates(idx, WIKI_MD)
    ngram_lower_cands = extract_lowercase_ngram_candidates(idx, WIKI_MD)
    # union across three sources — ontology entries take precedence on
    # name conflict (they carry entity/place/org typing), then capitalized
    # n-grams, then lowercase (the Build 1 addition).
    seen_names = {c["name"].lower() for c in onto_cands}
    def _add_new(pool: list[dict]) -> list[dict]:
        out = []
        for c in pool:
            if c["name"].lower() not in seen_names:
                seen_names.add(c["name"].lower())
                out.append(c)
        return out
    merged = onto_cands + _add_new(ngram_cands) + _add_new(ngram_lower_cands)
    # Build 1: self-corpus stoplist — exclude infrastructure vocabulary
    # BEFORE scoring so it never appears in the ledger.
    stoplist = _build_self_corpus_stoplist()
    dropped = [c for c in merged
               if c["name"].lower() in stoplist
               or _slugify(c["name"]) in stoplist]
    merged = [c for c in merged
              if c["name"].lower() not in stoplist
              and _slugify(c["name"]) not in stoplist]
    print(
        f"[pass E] candidates: {len(onto_cands)} ontology + "
        f"{len(ngram_cands)} capitalized + {len(ngram_lower_cands)} lowercase "
        f"= {len(merged) + len(dropped)} raw, "
        f"{len(dropped)} dropped by self-corpus stoplist "
        f"({len(stoplist)} entries), {len(merged)} to score"
    )
    if verbose and dropped:
        sample = ", ".join(c["name"] for c in dropped[:10])
        print(f"[pass E] stoplist drops (sample): {sample}"
              + (f", …+{len(dropped) - 10} more" if len(dropped) > 10 else ""))

    # Build 2: fold aliases so 'Claude Code' / 'claude-code' collapse to
    # one row and 'Mint Monstera' folds into its head. Head candidate
    # keeps type; aliases list rides in dict['aliases'].
    pre_fold_count = len(merged)
    merged = _fold_aliases(merged)
    print(f"[pass E] alias folding: {pre_fold_count} → {len(merged)} "
          f"({pre_fold_count - len(merged)} aliases folded into heads)")

    goals_text = _load_user_goals()
    if goals_text:
        goal_tokens = len(set(re.findall(r"[a-z]{4,}", goals_text)))
        print(
            f"[pass E] loaded USER_MODEL.md Current section: "
            f"{goal_tokens} distinct tokens for goal_overlap"
        )
    else:
        print("[pass E] no USER_MODEL.md — goal_overlap term will be 0")

    now = datetime.now(timezone.utc)
    # Build 2.5: multiprocessing scoring. CPU-bound regex over ~8k
    # sections × ~5k candidates was ~40 min single-threaded; Pool over
    # ~8 cores brings it under 10 min. Records list is pickleable; the
    # index and wiki_md path go through the worker initializer once.
    import multiprocessing as mp
    import os as _os
    workers = min(_os.cpu_count() or 4, 8)
    print(f"[pass E] scoring {len(merged)} candidates across {workers} workers "
          f"(mp.Pool over multiprocessing — expect ~5–10 min)")
    with mp.Pool(
        processes=workers,
        initializer=_promote_worker_init,
        initargs=(idx.records, str(WIKI_MD), goals_text, now.isoformat()),
    ) as pool:
        # imap_unordered lets us print progress as results stream in
        scored: list[tuple[dict, dict, list[dict]]] = []
        done = 0
        for result in pool.imap_unordered(
            _promote_worker_score, merged, chunksize=8,
        ):
            done += 1
            if verbose and done % 200 == 0:
                print(f"  scored {done}/{len(merged)}")
            if result is not None:
                scored.append(result)
    scored.sort(key=lambda x: x[1]["S"], reverse=True)

    if verbose or dry_run:
        print(f"[pass E] top 20 by S:")
        for cand, score, _ in scored[:20]:
            print(f"  S={score['S']:.2f}  base={score['base_activation']:.2f}  "
                  f"spread={int(score['spread'])}  "
                  f"goal={int(score['goal_overlap'])}  {cand['name']}")

    to_promote = [x for x in scored if x[1]["S"] >= threshold][:cap]
    print(
        f"[pass E] {len(to_promote)} of {len(scored)} pass threshold "
        f"({threshold}, cap {cap})"
    )

    promoted_slugs: set[str] = set()
    if not dry_run:
        for cand, score, mentions in to_promote:
            # gather 8 sample excerpts for the LLM summary
            excerpts = []
            wanted = {m["byte_start"] for m in mentions[:8]}
            for r in idx.records:
                if r.get("byte_start") in wanted:
                    try:
                        text = idx.read_section(WIKI_MD, r)
                        excerpts.append(excerpt(text, 300))
                    except Exception:  # noqa: BLE001
                        pass
                    if len(excerpts) >= 8:
                        break
            summary = _concept_summary_llm(cand, excerpts, budget)
            page = _write_concept_page(cand, score, mentions, summary,
                                       CONCEPTS_DIR)
            promoted_slugs.add(_slugify(cand["name"]))
            print(f"[pass E] promoted -> {page}")
    else:
        for cand, _, _ in to_promote:
            promoted_slugs.add(_slugify(cand["name"]))
            print(f"[pass E] would promote: {cand['name']}")

    if not dry_run:
        _write_salience_ledger(scored, threshold, cap, promoted_slugs,
                               SALIENCE_LEDGER)
        print(f"[pass E] ledger -> {SALIENCE_LEDGER}")
    else:
        print(f"[pass E] would write ledger with {len(scored)} rows "
              f"-> {SALIENCE_LEDGER}")

    return (f"promote: scored {len(scored)}, promoted {len(promoted_slugs)} "
            f"(threshold {threshold}, cap {cap})")


# ── CLI ───────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="dream_bootstrap",
        description="One-shot wiki narrative + ontology bootstrap.",
    )
    ap.add_argument(
        "which", nargs="?", default="all",
        choices=["all", "narrative", "ontology", "compact", "user-model",
                 "promote"],
        help="which pass to run (default: all = narrative + ontology; "
             "compact, user-model, and promote run only when named "
             "explicitly. user-model rebuilds ~/.mikai/brain/USER_MODEL.md "
             "via 1 interactive LLM call — attached to dream-weekly, not "
             "nightly. promote is the Consolidation MVP — scores every "
             "candidate concept and promotes top-N above --promote-threshold "
             "to ~/.mikai/wiki/concepts/*.md, one 3-sentence LLM summary "
             "per promotion.)",
    )
    ap.add_argument("--promote-threshold", type=float,
                    default=PROMOTE_DEFAULT_THRESHOLD,
                    help="salience score threshold for promotion "
                         f"(default {PROMOTE_DEFAULT_THRESHOLD})")
    ap.add_argument("--promote-cap", type=int, default=PROMOTE_DEFAULT_CAP,
                    help="max promotions per pass "
                         f"(default {PROMOTE_DEFAULT_CAP}/night)")
    ap.add_argument("--narrative-days", type=int, default=30)
    ap.add_argument("--incremental", action="store_true",
                    help="narrative only: nightly delta since the last "
                         "incremental run (state: wiki/.narrative-state.json), "
                         "APPENDED as a dated '## Δ' entry; 1 LLM call")
    ap.add_argument("--ledger-mode", default=None, metavar="MODE",
                    help="on success, write a ledger.run(mode=MODE, ...) row "
                         "to progress.jsonl (used by scheduled runners so the "
                         "health check can see the job fired)")
    ap.add_argument("--batch-sections", type=int, default=300,
                    help="max sections per ontology batch (default 300)")
    ap.add_argument("--max-calls", type=int, default=50,
                    help="hard cap on total LLM calls (default 50)")
    ap.add_argument("--resume", action="store_true",
                    help="skip ontology batches already checkpointed")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.incremental and args.which != "narrative":
        sys.exit("--incremental only applies to the narrative pass")
    if not WIKI_MD.exists():
        sys.exit(f"{WIKI_MD} not found")
    idx = load_index()
    budget = Budget(args.max_calls)
    t0 = time.monotonic()
    summary = ""

    try:
        if args.which == "narrative" and args.incremental:
            summary = run_narrative_incremental(idx, budget,
                                                args.dry_run, args.verbose)
        elif args.which in ("all", "narrative"):
            run_narrative(idx, args.narrative_days, budget,
                          args.dry_run, args.verbose)
            summary = f"full narrative rebuild (last {args.narrative_days}d)"
        if args.which in ("all", "ontology"):
            run_ontology(idx, args.batch_sections, budget,
                         args.dry_run, args.verbose, args.resume)
            summary = (summary + "; " if summary else "") + "ontology rebuild"
        if args.which == "compact":
            summary = "wiki compaction"
            run_compact(idx, args.dry_run, args.verbose)
        if args.which == "user-model":
            summary = run_user_model(budget, args.dry_run, args.verbose)
        if args.which == "promote":
            summary = run_promote(
                idx, budget,
                threshold=args.promote_threshold,
                cap=args.promote_cap,
                dry_run=args.dry_run,
                verbose=args.verbose,
            )
        if args.ledger_mode and not args.dry_run:
            _ledger_trace(args.ledger_mode, summary or "completed", budget)
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

"""Latent-thread detector — surfaces thread-shaped topics from the wiki.

MIKAI's L4 today only tracks threads Brian hand-seeded. The corpus,
though, contains hundreds of hits for topics that ARE thread-shaped
(dry eyes, plant care, proposal-to-Germaine, AI-competency job hunt)
but were never entered as threads. This module closes the gap:

    ontology → filter → WikiFTS → one LLM call → proposed-thread-*.md

Analogous to `hydrator.py` (which proposes entities), but the accept
gate is heavier: we call the interactive-tier LLM once per candidate
to decide (a) is this even thread-shaped, and (b) what's its state,
department, and next step. Only proposals with confidence ≥ 0.6 land.

Proposals go to the inbox — never directly to threads/. Brian's
judgment stays in the loop, same as the entity flow.

Filters, in order:
- mentions below --min-mentions (default 30 — high bar; noisy singletons
  are ignored)
- last_seen older than --min-recency-days (default 60 — dormant topics
  belong in the wiki, not the active-thread surface)
- type outside {thing, person, org, place} (concepts are not thread-shaped)
- slug IS the primary entity of an existing thread (skip — already tracked)
- proposed-thread-<slug>.md already in inbox (skip — idempotent)
- LLM rejects (is_thread_shaped=false OR confidence < 0.6)

Backs up inbox/ before writing. Never touches threads/ or entities/.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
import types
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import infra.mikai_llm as mikai_llm

from . import BRAIN_ROOT, INBOX_DIR, INBOX_PROCESSED, THREADS_DIR
from . import ledger as brain_ledger
from . import threads as brain_threads

# Same bind-at-import pattern as hydrator.py — tests repoint HOME and
# reload the module to rebind these.
ONTOLOGY_PATH = Path(
    os.environ.get(
        "MIKAI_WIKI_ONTOLOGY",
        str(Path.home() / ".mikai" / "wiki" / "wiki-ontology.md"),
    )
)

ALLOWED_TYPES = {"person", "org", "thing", "place"}
DEFAULT_MIN_MENTIONS = 30
DEFAULT_MIN_RECENCY_DAYS = 60
DEFAULT_LIMIT = 15
CONFIDENCE_GATE = 0.6
VALID_STATES = ("exploring", "evaluating", "decided", "acting", "stalled")
VALID_DEPARTMENTS = ("ai_work", "body", "domestic", "love", "misc")
FTS_TOP_K = 8


@dataclass
class OntologyEntity:
    slug: str
    type: str
    mentions: int
    first_seen: str
    last_seen: str
    sources: str


@dataclass
class Verdict:
    is_thread_shaped: bool
    why: str
    state: str
    next_step: str
    department: str
    confidence: float
    title: str


# ── Ontology parsing (subset of hydrator._parse; same table shape) ───────


def parse_ontology(path: Path = ONTOLOGY_PATH) -> list[OntologyEntity]:
    """Parse the ontology markdown table. The ⚠ "Possibly inferred" flag
    is not filtered here — thread-shape gating is stricter than entity
    gating (an LLM call decides), so noisy names get rejected downstream."""
    if not path.exists():
        return []
    entities: list[OntologyEntity] = []
    for line in path.read_text().splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            continue
        name, etype, mentions_s, first_seen, last_seen, sources = cells
        if name in ("entity", "---") or set(name) <= {"-"}:
            continue
        slug = name.replace("⚠", "").strip()
        try:
            mentions = int(mentions_s)
        except ValueError:
            continue
        entities.append(OntologyEntity(
            slug=slug, type=etype, mentions=mentions,
            first_seen=first_seen, last_seen=last_seen, sources=sources,
        ))
    return entities


# ── Thread + inbox awareness ─────────────────────────────────────────────


def primary_entities_of_existing_threads() -> set[str]:
    """First entry in every thread's `entities:` frontmatter — the
    primary anchor. A candidate whose slug matches one of these is
    already tracked, don't re-propose."""
    out: set[str] = set()
    for t in brain_threads.load_all():
        if t.entities:
            out.add(t.entities[0].strip().lower())
    return out


def _already_proposed(slug: str) -> bool:
    name = f"proposed-thread-{slug}.md"
    if (INBOX_DIR / name).exists():
        return True
    if INBOX_PROCESSED.exists():
        for p in INBOX_PROCESSED.iterdir():
            if p.name == name or p.name.endswith(f"__{name}"):
                return True
    return False


def _parse_date(s: str):
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# ── WikiFTS standalone loader (same trick as mikai_ask.core) ─────────────
# wiki_fts.py imports `from sidecar.l3.wiki_index import …`, and
# sidecar.l3.__init__ pulls in graphiti_core (sidecar-venv only). Load
# both files directly and register wiki_index under the dotted name that
# wiki_fts imports, so wiki_fts's own import succeeds without ever
# executing sidecar.l3.__init__.

_wiki_index_mod = None
_wiki_fts_mod = None
_REPO = Path(__file__).resolve().parents[2]


def _load_wiki_modules():
    global _wiki_index_mod, _wiki_fts_mod
    if _wiki_fts_mod is not None:
        return _wiki_index_mod, _wiki_fts_mod
    l3 = _REPO / "infra" / "graphiti" / "sidecar" / "l3"

    def _load(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    if "sidecar.l3.wiki_index" in sys.modules:
        _wiki_index_mod = sys.modules["sidecar.l3.wiki_index"]
    else:
        _wiki_index_mod = _load("sidecar.l3.wiki_index", l3 / "wiki_index.py")
        sidecar_pkg = sys.modules.setdefault("sidecar", types.ModuleType("sidecar"))
        l3_pkg = sys.modules.setdefault("sidecar.l3", types.ModuleType("sidecar.l3"))
        sidecar_pkg.l3 = l3_pkg
        l3_pkg.wiki_index = _wiki_index_mod

    _wiki_fts_mod = _load("_latent_threads_wiki_fts", l3 / "wiki_fts.py")
    return _wiki_index_mod, _wiki_fts_mod


def _wiki_dir() -> Path:
    return Path.home() / ".mikai" / "wiki"


def _fts_search(query: str, k: int = FTS_TOP_K) -> list[dict]:
    """Top-k BM25 sections for `query`. Empty on missing wiki or
    FTS5-less interpreter — a candidate with no FTS context still runs,
    just with less evidence for the LLM."""
    wiki_md = _wiki_dir() / "wiki.md"
    if not wiki_md.exists():
        return []
    wiki_index_mod, wiki_fts_mod = _load_wiki_modules()
    idx_path = _wiki_dir() / "wiki.index"
    if idx_path.exists():
        idx = wiki_index_mod.WikiIndex.load(idx_path)
        idx.refresh(wiki_md)
    else:
        idx = wiki_index_mod.WikiIndex.build(wiki_md)
    fts = wiki_fts_mod.WikiFTS.rebuild_if_stale(idx, wiki_md)
    if fts is None:
        return []
    try:
        return fts.search(query, limit=k)
    finally:
        fts.close()


# ── LLM verdict ──────────────────────────────────────────────────────────


_VERDICT_PROMPT = """\
You are triaging one candidate entity from Brian's personal corpus for
"thread-shape" — i.e., is there ongoing decision-making or action
around this topic that Brian would want tracked as an active thread,
versus just a name that shows up a lot but doesn't imply any pending
work?

A thread-shaped topic has some or all of:
- open questions or choices Brian is still weighing
- a concrete next action he hasn't taken yet
- signs of a stall (recurring mentions without progress)
- a decision that was made but hasn't been acted on
Reject topics that are pure noun/reference material, historical, or
already-resolved.

Candidate entity: {slug}
Type: {type}
Mentions in wiki: {mentions}
First seen: {first_seen}   Last seen: {last_seen}
Sources: {sources}

Retrieved wiki snippets (BM25 top-{k} for "{slug}"):

{snippets}

Return ONLY valid JSON, no prose, no markdown fences, exactly these keys:

{{
  "is_thread_shaped": true|false,
  "why": "one line reason",
  "state": "exploring|evaluating|decided|acting|stalled",
  "next_step": "one concrete action Brian should take, or empty string",
  "department": "ai_work|body|domestic|love|misc",
  "confidence": 0.0-1.0,
  "title": "human-readable thread title, e.g. 'Dry eyes — daily care routine'"
}}

If is_thread_shaped is false, still fill state/next_step/department with
best-guess placeholders and set confidence appropriately low.
"""


def _format_snippet(h: dict) -> str:
    header_ts = h.get("header_ts", "?")
    name = h.get("name", "?")
    src = h.get("source", "?")
    snip = str(h.get("snippet", "")).strip()
    return f"[{header_ts}] {name} ({src}) — {snip}"


def _build_prompt(e: OntologyEntity, hits: list[dict]) -> str:
    snippets = (
        "\n".join(f"- {_format_snippet(h)}" for h in hits)
        if hits else "(no wiki snippets — candidate has no FTS hits)"
    )
    return _VERDICT_PROMPT.format(
        slug=e.slug, type=e.type, mentions=e.mentions,
        first_seen=e.first_seen, last_seen=e.last_seen, sources=e.sources,
        k=len(hits) or FTS_TOP_K, snippets=snippets,
    )


def _parse_verdict(raw: str) -> Verdict | None:
    """Parse the LLM response into a Verdict. Tolerant of stray prose
    around the JSON (a lone { … } block is extracted). Returns None on
    unrecoverable garbage — caller rejects the candidate."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        # strip a markdown fence if the model added one anyway
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    state = str(obj.get("state", "")).strip().lower()
    if state not in VALID_STATES:
        state = "exploring"
    dept = str(obj.get("department", "")).strip().lower()
    if dept not in VALID_DEPARTMENTS:
        dept = "misc"
    try:
        conf = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return Verdict(
        is_thread_shaped=bool(obj.get("is_thread_shaped", False)),
        why=str(obj.get("why", "")).strip()[:200],
        state=state,
        next_step=str(obj.get("next_step", "")).strip(),
        department=dept,
        confidence=max(0.0, min(1.0, conf)),
        title=str(obj.get("title", "")).strip() or "",
    )


def classify(e: OntologyEntity) -> tuple[Verdict | None, list[dict]]:
    """One LLM call. Returns (verdict, snippets used). Verdict is None
    when the response is unparseable — treated as a rejection upstream."""
    hits = _fts_search(e.slug)
    prompt = _build_prompt(e, hits)
    raw = mikai_llm.chat(prompt, tier="interactive", json_mode=True)
    return _parse_verdict(raw), hits


# ── Selection ────────────────────────────────────────────────────────────


def select_candidates(
    *,
    min_mentions: int = DEFAULT_MIN_MENTIONS,
    min_recency_days: int = DEFAULT_MIN_RECENCY_DAYS,
    limit: int = DEFAULT_LIMIT,
    ontology_path: Path = ONTOLOGY_PATH,
    today: date | None = None,
) -> list[OntologyEntity]:
    """Cheap pre-LLM filter — every reject here saves one interactive
    call. Sorted by mentions desc, most-cited first."""
    today = today or date.today()
    cutoff = today - timedelta(days=min_recency_days)
    tracked = primary_entities_of_existing_threads()
    out: list[OntologyEntity] = []
    for e in sorted(parse_ontology(ontology_path), key=lambda x: -x.mentions):
        if e.mentions < min_mentions:
            continue
        if e.type not in ALLOWED_TYPES:
            continue
        last = _parse_date(e.last_seen)
        if last is None or last < cutoff:
            continue
        if e.slug.lower() in tracked:
            continue
        if _already_proposed(e.slug):
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


# ── Proposal writing ─────────────────────────────────────────────────────


def _proposal_text(
    e: OntologyEntity, v: Verdict, hits: list[dict], today_iso: str
) -> str:
    title = v.title or e.slug.replace("-", " ").title()
    next_step_field = f'"{v.next_step}"' if v.next_step else '""'
    top_snippets = hits[:3]
    evidence = (
        "\n".join(
            f"- [{h.get('header_ts', '?')}] {str(h.get('snippet', '')).strip()}"
            for h in top_snippets
        )
        if top_snippets else "- (no wiki snippets retrieved)"
    )
    return (
        "---\n"
        "proposal_kind: thread\n"
        f"slug: {e.slug}\n"
        f"title: {title}\n"
        f"state: {v.state}\n"
        f"state_since: {today_iso}\n"
        f"last_activity: {today_iso}\n"
        f"next_step: {next_step_field}\n"
        "next_step_due:\n"
        f"entities: [{e.slug}]\n"
        f"department: {v.department}\n"
        f"confidence: {v.confidence:.2f}\n"
        f"why: \"{v.why}\"\n"
        f"mentions: {e.mentions}\n"
        f"last_seen_in_wiki: {e.last_seen}\n"
        f"sources: {e.sources}\n"
        "---\n"
        "\n"
        f"# Proposed thread: {title}\n"
        "\n"
        f"_Auto-detected from wiki-ontology.md on {today_iso}. Detected in "
        f"{e.mentions} sections spanning {e.first_seen} → {e.last_seen}, sourced "
        f"from {e.sources}. Confidence: {v.confidence:.2f}._\n"
        "\n"
        "_Triage this file to (a) promote to threads/" f"{e.slug}.md, "
        "(b) merge into an existing thread, or (c) delete as noise._\n"
        "\n"
        "## Evidence\n"
        f"{evidence}\n"
    )


def _backup_inbox() -> Path | None:
    if not INBOX_DIR.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = BRAIN_ROOT / "state" / "inbox-backups" / f"latent-{ts}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(INBOX_DIR, dest)
    return dest


# ── Runner ───────────────────────────────────────────────────────────────


def run(
    *,
    dry_run: bool = False,
    min_mentions: int = DEFAULT_MIN_MENTIONS,
    min_recency_days: int = DEFAULT_MIN_RECENCY_DAYS,
    limit: int = DEFAULT_LIMIT,
    verbose: bool = True,
) -> dict:
    """Full pipeline: select → classify → write. Returns a stats dict."""
    candidates = select_candidates(
        min_mentions=min_mentions,
        min_recency_days=min_recency_days,
        limit=limit,
    )
    stats: dict = {
        "candidates": len(candidates),
        "accepted": 0,
        "rejected": 0,
        "unparseable": 0,
        "proposed": [],
        "verdicts": [],
    }
    if verbose:
        print(
            f"latent-threads: {len(candidates)} candidate(s) after filters "
            f"(min_mentions={min_mentions}, min_recency_days={min_recency_days}, "
            f"limit={limit})"
        )
    if not candidates:
        if not dry_run:
            brain_ledger.run(
                mode="latent-threads",
                did="proposed 0 threads: (no candidates)",
                extra={"candidates": 0, "accepted": 0, "rejected": 0},
            )
        return stats

    today_iso = date.today().isoformat()
    backup: Path | None = None
    if not dry_run:
        backup = _backup_inbox()
        if verbose and backup is not None:
            print(f"latent-threads: inbox backed up to {backup}")
        INBOX_DIR.mkdir(parents=True, exist_ok=True)

    for e in candidates:
        verdict, hits = classify(e)
        record = {
            "slug": e.slug, "mentions": e.mentions,
            "is_thread_shaped": None, "confidence": None,
            "state": None, "verdict": "reject", "why": "",
        }
        if verdict is None:
            stats["unparseable"] += 1
            stats["rejected"] += 1
            record["verdict"] = "unparseable"
            if verbose:
                print(f"  {e.slug:<28} mentions={e.mentions:>4}  → REJECT (unparseable LLM response)")
        elif not verdict.is_thread_shaped:
            stats["rejected"] += 1
            record.update(is_thread_shaped=False, confidence=verdict.confidence,
                          state=verdict.state, why=verdict.why)
            if verbose:
                print(f"  {e.slug:<28} mentions={e.mentions:>4}  → REJECT (not thread-shaped: {verdict.why})")
        elif verdict.confidence < CONFIDENCE_GATE:
            stats["rejected"] += 1
            record.update(is_thread_shaped=True, confidence=verdict.confidence,
                          state=verdict.state, verdict="low-confidence",
                          why=verdict.why)
            if verbose:
                print(f"  {e.slug:<28} mentions={e.mentions:>4}  → REJECT (confidence {verdict.confidence:.2f} < {CONFIDENCE_GATE})")
        else:
            stats["accepted"] += 1
            stats["proposed"].append(e.slug)
            record.update(is_thread_shaped=True, confidence=verdict.confidence,
                          state=verdict.state, verdict="accept",
                          why=verdict.why)
            if verbose:
                print(
                    f"  {e.slug:<28} mentions={e.mentions:>4}  → ACCEPT "
                    f"[{verdict.state}, dept={verdict.department}, "
                    f"conf={verdict.confidence:.2f}] {verdict.title}"
                )
            if not dry_run:
                path = INBOX_DIR / f"proposed-thread-{e.slug}.md"
                path.write_text(_proposal_text(e, verdict, hits, today_iso))
        stats["verdicts"].append(record)

    if verbose:
        print(
            f"latent-threads: accepted={stats['accepted']} "
            f"rejected={stats['rejected']} (unparseable={stats['unparseable']})"
        )
    if not dry_run:
        slug_list = ", ".join(stats["proposed"]) or "(none)"
        brain_ledger.run(
            mode="latent-threads",
            did=f"proposed {stats['accepted']} threads: {slug_list}",
            extra={
                "candidates": stats["candidates"],
                "accepted": stats["accepted"],
                "rejected": stats["rejected"],
                "unparseable": stats["unparseable"],
                "proposed": stats["proposed"],
            },
        )
    return stats


def _cli() -> int:
    ap = argparse.ArgumentParser(
        prog="mikai_brain.latent_threads",
        description="Detect thread-shaped topics in the wiki and propose "
                    "them into ~/.mikai/brain/inbox/ for triage.",
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="Print candidates + verdicts without writing proposals")
    ap.add_argument("--min-mentions", type=int, default=DEFAULT_MIN_MENTIONS,
                    help=f"Min wiki mentions (default {DEFAULT_MIN_MENTIONS})")
    ap.add_argument("--min-recency-days", type=int,
                    default=DEFAULT_MIN_RECENCY_DAYS,
                    help=f"Skip entities whose last_seen is older than N days "
                         f"(default {DEFAULT_MIN_RECENCY_DAYS})")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help=f"Max candidates per run (default {DEFAULT_LIMIT}) — "
                         "one LLM call each")
    ap.add_argument("--verbose", action="store_true", default=False,
                    help="Print each candidate's verdict as it lands")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress even the summary line")
    args = ap.parse_args()
    run(
        dry_run=args.dry_run,
        min_mentions=args.min_mentions,
        min_recency_days=args.min_recency_days,
        limit=args.limit,
        verbose=(args.verbose or not args.quiet),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

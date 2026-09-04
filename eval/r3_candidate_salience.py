"""r3_candidate_salience.py — rank wiki-raw sources for next ingest round.

Reads the wiki-raw universe, filters out sources already ingested into
`~/.mikai/wiki-mikai-parallel-test/raw/sources/`, computes a per-source
salience score using GOALS.md overlap, existing-concept overlap, recency,
substance, vocab-diversity, and a noise penalty. Emits a ranked markdown
report + JSON.

Stdlib-only. Mirrors bridge slug/hash conventions so dedup is exact.

Usage:
    python eval/r3_candidate_salience.py
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WIKI_MD = Path.home() / ".mikai" / "wiki-raw" / "wiki.md"
WIKI_INDEX = Path.home() / ".mikai" / "wiki-raw" / "wiki.index"
INGESTED_DIR = Path.home() / ".mikai" / "wiki-mikai-parallel-test" / "raw" / "sources"
CONCEPTS_DIR = Path.home() / ".mikai" / "wiki-mikai-parallel-test" / "wiki" / "concepts"
VAULT_ROOT = Path.home() / ".mikai" / "wiki-mikai-parallel-test"
SALIENCE_LEDGER = Path.home() / ".mikai" / "wiki" / "wiki-salience.md"
GOALS_MD = Path.home() / ".mikai" / "brain" / "GOALS.md"
USER_MODEL_MD = Path.home() / ".mikai" / "brain" / "USER_MODEL.md"
PROFILE_MD = Path.home() / ".mikai" / "brain" / "PROFILE.md"
BRAIN_MD = Path.home() / ".mikai" / "brain" / "BRAIN.md"

# Level 3 (Session-11 Phase 3): broader personal-profile weights.
# Each source contributes tokens with a trust weight — highest for the
# compiled observed model, lowest for broader corpus vocabulary.
PROFILE_WEIGHTS = {
    "user_model": 1.5,       # USER_MODEL.md — compiled observed themes
    "profile": 1.0,          # PROFILE.md — curated identity
    "brain_priorities": 0.7, # BRAIN.md ## Current priorities
    "entities": 0.5,         # entity page slugs (people/places/things)
    "wisdom_titles": 0.5,    # wisdom theme titles
    "goals_habits": 0.5,     # goal/habit/reflection slugs (personal life axes)
    "queries": 0.4,          # query page slugs (open questions)
    "journal_tags": 0.3,     # journal frontmatter tag tokens (broader life)
}
MIN_PROFILE_TOKEN_LEN = 4

REPORTS_DIR = REPO / "eval" / "reports"

# Level 2 weights. Concept score is now an UNBOUNDED weighted sum
# (Σ log(1+in-degree) over concept hits), so it doesn't need a multiplier
# to dominate — a MIKAI-central source easily reaches 8-15 concept units.
W_GOAL = 3.0
W_RECENCY = 1.0
W_SUBSTANCE = 1.0
# Level 3.1 (Session-11 tuning): noise blacklist removed. Discrimination
# now handled by signal-density — sources with zero weighted_concept +
# weighted_personal + goal_overlap naturally rank at bottom. Blacklisting
# broad-life keywords like "yoga" or "plant" produced false negatives on
# personal-domain clusters Brian actively cares about.
W_AGGREGATION = 1.5   # bonus cap for multi-topic dense threads

# Level 4 axes (per docs/INGESTION_LOG.md "8-axis candidate scorecard"):
# A retrieval hit potential (IR), B vocabulary novelty (KR),
# C alias risk (Entity Resolution — NEGATIVE), G episodic vs semantic
# (Cognitive Science — emitted, no score contribution).
W_AXIS_A_RETRIEVAL = 1.0
W_AXIS_B_NOVELTY = 1.0
W_AXIS_C_ALIAS = -0.5
# Level 2: min slug length filter — excludes noise slugs like `agent`,
# `time`, `data`, `brand`, `system` that hit every text.
MIN_SLUG_LEN = 5

# Cheap English stopwords (mirrors eval/salience_recall.py::_STOP).
_STOP = frozenset("""
the this that these those my our your his her their its
a an and or but for nor so yet as if in on at by to of from with
he she they we you it me us them him
is are was were be being been have has had do does did
will would could should may might must shall can also just more most
what who which how why when where about above below into like near
they them their there here now today more some such very much many
""".split())

_EXTRA_STOP_GOALS = {"matters", "finding", "taking", "starting", "care",
                     "and", "or", "of", "to", "for"}

# Level 3.1: noise blacklist removed. Personal-domain keywords like yoga,
# plant, coffee, dining are legitimate Brian-interest clusters. Filtering
# on them produced false negatives on aggregated life/health threads.
# Discrimination is now purely evidence-based: low signal-density
# (weighted_concept + weighted_personal + goal_overlap all near zero) is
# the definition of "off-topic," and gets no penalty — those candidates
# just naturally rank at bottom.


# ── Load WikiIndex standalone (mirrors wiki_md_to_raw_sources.py) ─────

def _load_wiki_index():
    p = REPO / "infra" / "graphiti" / "sidecar" / "l3" / "wiki_index.py"
    spec = importlib.util.spec_from_file_location("_wi_r3", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.WikiIndex


# ── Slugify + filename (identical to bridge) ──────────────────────────

def slugify(text: str, max_len: int = 60) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:max_len].rstrip("-") or "untitled"


def filename_for_record(record: dict) -> str:
    date = str(record.get("header_ts", "unknown"))[:10]
    name_slug = slugify(str(record.get("name", "unnamed")))
    hash_key = f"{record.get('source', '?')}|{record.get('name', '?')}"
    h6 = hashlib.sha1(hash_key.encode("utf-8")).hexdigest()[:6]
    return f"{date}-{name_slug}-{h6}.md"


def filename_for_thread(title: str, earliest_date: str) -> str:
    slug = slugify(title)
    h6 = hashlib.sha1(f"claude-thread|{title}".encode("utf-8")).hexdigest()[:6]
    return f"{earliest_date}-{slug}-{h6}.md"


# ── Tokenize ──────────────────────────────────────────────────────────

def tokenize(text: str, minlen: int = 4) -> set[str]:
    tokens = re.findall(r"[a-z][a-z0-9]{" + str(minlen - 1) + r",}", text.lower())
    return {t for t in tokens if t not in _STOP}


def tokenize_list(text: str, minlen: int = 4) -> list[str]:
    tokens = re.findall(r"[a-z][a-z0-9]{" + str(minlen - 1) + r",}", text.lower())
    return [t for t in tokens if t not in _STOP]


# ── Goal tokens ────────────────────────────────────────────────────────

def load_goal_tokens(path: Path) -> tuple[set[str], list[str]]:
    """Return (all_goal_tokens, per-goal-title list). Titles used only for
    the report."""
    if not path.exists():
        return set(), []
    raw = path.read_text(encoding="utf-8", errors="replace")
    tokens: set[str] = set()
    titles: list[str] = []
    for m in re.finditer(
        r"^##\s+(.+?)\s*$(.*?)(?=^##\s|\Z)", raw, re.MULTILINE | re.DOTALL
    ):
        title = m.group(1).strip()
        body = m.group(2).strip()
        titles.append(title)
        title_tok = {t for t in tokenize(title, minlen=3) if t not in _EXTRA_STOP_GOALS}
        body_tok = tokenize(body, minlen=4)
        tokens |= title_tok | body_tok
    return tokens, titles


# ── Existing concept slugs ────────────────────────────────────────────

def load_concept_weights(concepts_dir: Path,
                          salience_ledger: Path,
                          vault_root: Path) -> dict[str, float]:
    """Return dict[slug -> weight] for concept slugs of length >= MIN_SLUG_LEN.

    Level 2 rewrite of load_concept_slugs. Two changes:

    1. Weight per slug reflects its centrality in the wiki. Preferred
       source: `~/.mikai/wiki/wiki-salience.md` S-column (post-ingest
       concept salience, versioned v001-v004). Fallback: wikilink
       in-degree over the vault (how many pages link to `[[concepts/X]]`
       or `[[X]]`), log-normalized.

    2. Min slug length. Short slugs like `agent`, `time`, `data`, `brand`,
       `system` are excluded because they hit every text — that was the
       saturation bug in the pre-Level-2 scorer.

    Only kebab-case slugs with a hyphen are included (single-word
    concepts under MIN_SLUG_LEN are dropped as noise; multi-word concepts
    like `personal-intent-graph` are the informative ones)."""
    weights: dict[str, float] = {}

    # Try ledger first (post-ingest authoritative scorer)
    if salience_ledger.exists():
        try:
            raw = salience_ledger.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"##\s+Ranked candidates\s*\n(.*)", raw,
                          re.DOTALL | re.IGNORECASE)
            if m:
                lines = [ln for ln in m.group(1).splitlines()
                         if ln.strip().startswith("|")]
                if len(lines) >= 3:
                    headers = [h.strip().lower() for h in lines[0].strip("|").split("|")]
                    for line in lines[2:]:
                        cells = [c.strip() for c in line.strip("|").split("|")]
                        if not cells:
                            continue
                        row = dict(zip(headers, cells))
                        name = row.get("concept") or row.get("candidate") or row.get("name") or cells[0]
                        s_str = row.get("s") or row.get("score") or ""
                        try:
                            s_val = float(s_str)
                        except (ValueError, TypeError):
                            continue
                        slug = slugify(name)
                        if len(slug) >= MIN_SLUG_LEN and "-" in slug:
                            # Ledger S values run 3-10ish; log-compress to comparable scale
                            weights[slug] = math.log1p(max(0.0, s_val))
            if weights:
                print(f"[r3] concept weights: loaded {len(weights)} slugs "
                      f"from ledger {salience_ledger}", file=sys.stderr)
                return weights
        except Exception as exc:
            print(f"[r3] ledger parse failed ({exc}); falling back to in-degree",
                  file=sys.stderr)

    # Fallback: wikilink in-degree over the vault
    slug_set: set[str] = set()
    if concepts_dir.is_dir():
        for p in concepts_dir.iterdir():
            if p.suffix != ".md" or p.name in {"index.md", "log.md"}:
                continue
            stem = p.stem.lower()
            if len(stem) >= MIN_SLUG_LEN and "-" in stem:
                slug_set.add(stem)

    if not slug_set:
        print("[r3] WARNING: no concept slugs found; concept score will be zero",
              file=sys.stderr)
        return {}

    # Count in-degree by walking all .md files under vault and tallying [[wikilinks]]
    wl_pat = re.compile(r"\[\[(?:concepts/)?([a-z0-9][a-z0-9-]*)(?:[|#][^\]]*)?\]\]",
                         re.IGNORECASE)
    in_degree: dict[str, int] = {s: 0 for s in slug_set}
    for md in vault_root.rglob("*.md"):
        if md.name in {"index.md", "log.md"}:
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for target in wl_pat.findall(text):
            t = target.lower()
            if t in in_degree:
                in_degree[t] += 1

    for slug, deg in in_degree.items():
        weights[slug] = math.log1p(deg)  # in {0, log2=0.69, log3=1.10, ..., log(1+27)=3.33}

    print(f"[r3] concept weights: computed {len(weights)} slugs from in-degree "
          f"under {vault_root} (max weight {max(weights.values(), default=0):.2f})",
          file=sys.stderr)
    return weights


# ── Personal-profile vocabulary (Level 3) ─────────────────────────────

def _tokens_from_text(text: str, minlen: int = MIN_PROFILE_TOKEN_LEN,
                       slugs_only: bool = False) -> set[str]:
    """Extract meaningful tokens from a text blob. Kebab-case slugs are
    kept whole. When slugs_only=False, longish bare words are also
    included (used for brain files where free prose signals interest).

    Level-3 tightening: raised minlen default to 6 so generic words
    (`agent`, `system`, `product`, `output`) don't flood the vocabulary."""
    out: set[str] = set()
    # Whole slugs (kebab-case)
    for slug in re.findall(r"[a-z][a-z0-9]{2,}(?:-[a-z0-9]+)+", text.lower()):
        if len(slug) >= minlen:
            out.add(slug)
    if slugs_only:
        return out
    # Bare word tokens — longer threshold to skip filler
    for tok in re.findall(r"[a-z][a-z0-9]{" + str(max(minlen, 6) - 1) + r",}", text.lower()):
        if tok not in _STOP:
            out.add(tok)
    return out


def _parse_frontmatter_tags(text: str) -> list[str]:
    """Extract `tags: [...]` values from YAML-ish frontmatter. Returns
    lowercased tokens with hyphens preserved."""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return []
    fm = m.group(1)
    for line in fm.splitlines():
        line = line.strip()
        if not line.lower().startswith("tags:"):
            continue
        value = line.partition(":")[2].strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            return [t.strip().strip('"').strip("'").lower()
                    for t in inner.split(",") if t.strip()]
    return []


def load_personal_vocabulary(vault_root: Path) -> dict[str, float]:
    """Level 3: build a broader personal profile beyond MIKAI-central
    concepts. Weight each token by which signal it came from.

    Returns dict[token -> max_weight_seen]. A token appearing in multiple
    signals keeps its strongest weight (max-pool, not sum).

    Signals (highest to lowest trust):
      - USER_MODEL.md — LLM-compiled observed themes
      - PROFILE.md — hand-curated identity statement
      - BRAIN.md "Current priorities" section
      - Entity page slugs (people, places, things already in the graph)
      - Wisdom / goal / habit / query page slugs (personal life axes)
      - Journal frontmatter tag tokens
    """
    vocab: dict[str, float] = {}

    def _add(tokens: set[str], weight: float):
        for t in tokens:
            if len(t) < MIN_PROFILE_TOKEN_LEN:
                continue
            if t in vocab:
                vocab[t] = max(vocab[t], weight)
            else:
                vocab[t] = weight

    # 1. USER_MODEL.md
    if USER_MODEL_MD.exists():
        _add(_tokens_from_text(USER_MODEL_MD.read_text(encoding="utf-8", errors="replace")),
             PROFILE_WEIGHTS["user_model"])

    # 2. PROFILE.md
    if PROFILE_MD.exists():
        _add(_tokens_from_text(PROFILE_MD.read_text(encoding="utf-8", errors="replace")),
             PROFILE_WEIGHTS["profile"])

    # 3. BRAIN.md — Current priorities section only
    if BRAIN_MD.exists():
        raw = BRAIN_MD.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^##\s+Current priorities\s*$(.*?)(?=^## |\Z)",
                       raw, re.MULTILINE | re.DOTALL)
        if m:
            _add(_tokens_from_text(m.group(1)), PROFILE_WEIGHTS["brain_priorities"])

    # 4-8. Vault non-concept pages — slugs from filenames + frontmatter tags
    signal_by_dir = {
        "entities": PROFILE_WEIGHTS["entities"],
        "wisdom": PROFILE_WEIGHTS["wisdom_titles"],
        "goals": PROFILE_WEIGHTS["goals_habits"],
        "habits": PROFILE_WEIGHTS["goals_habits"],
        "reflections": PROFILE_WEIGHTS["goals_habits"],
        "queries": PROFILE_WEIGHTS["queries"],
        "journal": PROFILE_WEIGHTS["journal_tags"],
    }
    for dirname, weight in signal_by_dir.items():
        d = vault_root / "wiki" / dirname
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.suffix != ".md" or p.name in {"index.md", "log.md"}:
                continue
            # Slug from filename (keep multi-word slugs whole; split constituents)
            stem = p.stem.lower()
            _add({stem}, weight)  # whole slug
            for part in stem.split("-"):
                if len(part) >= MIN_PROFILE_TOKEN_LEN and part not in _STOP:
                    _add({part}, weight)
            # Frontmatter tags from journal + others (add all)
            try:
                text_head = p.read_text(encoding="utf-8", errors="replace")[:2000]
                for tag in _parse_frontmatter_tags(text_head):
                    _add({tag}, weight)
                    for part in tag.split("-"):
                        if len(part) >= MIN_PROFILE_TOKEN_LEN and part not in _STOP:
                            _add({part}, weight * 0.7)  # constituent tokens weaker
            except Exception:
                pass

    return vocab


# ── Ingested-set builder ──────────────────────────────────────────────

def load_ingested_filenames(ingested_dir: Path) -> set[str]:
    if not ingested_dir.is_dir():
        return set()
    return {p.name for p in ingested_dir.iterdir() if p.suffix == ".md"}


# ── Candidate grouping ────────────────────────────────────────────────

def is_claude_thread_turn(record: dict) -> bool:
    src = str(record.get("source", ""))
    name = str(record.get("name", ""))
    return src.startswith("claude-thread") and name.count("::") >= 3


def parse_thread_turn(record: dict) -> tuple[str, int, str]:
    parts = str(record.get("name", "")).split("::")
    title = parts[1] if len(parts) > 1 else "unknown"
    try:
        idx = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        idx = 0
    role = parts[3] if len(parts) > 3 else "unknown"
    return title, idx, role


# ── Level 4 axes (docs/INGESTION_LOG.md 8-axis scorecard) ────────────

def _query_tokens(vault_root: Path) -> tuple[set[str], int]:
    """Axis A support: return (token set from wiki/queries/*, page count).
    Empty set if no queries dir. Tokens ≥5 chars, stopwords dropped."""
    qdir = vault_root / "wiki" / "queries"
    tokens: set[str] = set()
    count = 0
    if not qdir.is_dir():
        return tokens, 0
    for p in qdir.iterdir():
        if p.suffix != ".md" or p.name in {"index.md", "log.md"}:
            continue
        count += 1
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # Strip frontmatter
        text_body = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)
        for t in tokenize(text_body, minlen=5):
            tokens.add(t)
        # Also include title tokens from filename slug
        for t in p.stem.split("-"):
            if len(t) >= 5:
                tokens.add(t.lower())
    return tokens, count


_KEBAB_2_3_RE = re.compile(r"\b([a-z][a-z0-9]{2,}(?:-[a-z][a-z0-9]{2,}){1,2})\b")


def _extract_kebab_phrases(text: str) -> set[str]:
    """Axis B support: 2-3-word kebab-shaped noun phrases from body.
    Nashsu tends to emit these when it names a concept; a body dense
    with them is dense with candidate concepts."""
    return set(_KEBAB_2_3_RE.findall(text.lower()))


def _load_all_slug_variants(concept_weights: dict[str, float]) -> set[str]:
    """Axis C support: existing concept slugs + hyphen->space variants.
    Kept as a set so alias detection can O(1) membership-test."""
    variants: set[str] = set()
    for slug in concept_weights.keys():
        variants.add(slug)
        variants.add(slug.replace("-", " "))
    return variants


def _jaro_winkler(s1: str, s2: str, p: float = 0.1) -> float:
    """Stdlib-only Jaro-Winkler. Cheap for slug-length strings."""
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0
    match_dist = max(len1, len2) // 2 - 1
    if match_dist < 0:
        match_dist = 0
    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    for i in range(len1):
        start = max(0, i - match_dist)
        end = min(i + match_dist + 1, len2)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    k = 0
    transpositions = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    transpositions //= 2
    jaro = (matches / len1 + matches / len2 +
            (matches - transpositions) / matches) / 3
    prefix = 0
    for i in range(min(4, len1, len2)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break
    return jaro + prefix * p * (1 - jaro)


_EPISODIC_TITLE_RE = re.compile(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|"
    r"january|february|march|april|june|july|august|september|"
    r"october|november|december)\s|"
    r"^\d{4}-\d{2}-\d{2}|journal|diary|reflection|daily|log\s",
    re.IGNORECASE,
)
_EPISODIC_BODY_TOKENS = frozenset([
    "yesterday", "today", "tonight", "i felt", "i was", "i thought",
    "i went", "i saw", "i noticed", "i did", "this morning",
    "this afternoon", "this evening",
])
_SEMANTIC_TITLE_HINTS = frozenset([
    "framework", "architecture", "principle", "pattern", "theory",
    "model", "definition", "taxonomy", "concept",
])


def _compute_axis_g_episodic_score(title: str, body: str) -> float:
    """Axis G: 0.0 = pure episodic, 1.0 = pure semantic, 0.5 = ambiguous.
    Heuristic — routing signal for downstream page-type placement."""
    title_lower = title.lower()
    body_lower = body[:3000].lower()  # first 3KB for cheap scan

    ep_hits = 0
    if _EPISODIC_TITLE_RE.search(title_lower):
        ep_hits += 2
    ep_hits += sum(1 for tok in _EPISODIC_BODY_TOKENS if tok in body_lower)

    sem_hits = 0
    for hint in _SEMANTIC_TITLE_HINTS:
        if hint in title_lower:
            sem_hits += 2
    # Abstract definitional language markers
    for phrase in ("is defined as", "refers to", "the concept of",
                    "as a principle", "in general", "systematically"):
        if phrase in body_lower:
            sem_hits += 1

    if ep_hits == 0 and sem_hits == 0:
        return 0.5
    return sem_hits / (ep_hits + sem_hits)


# ── Salience scoring ──────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(s: str) -> datetime | None:
    try:
        # WikiIndex stores ISO 8601
        s = s.rstrip("Z")
        if "+" not in s and s.count(":") >= 2:
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(s)
    except Exception:
        return None


def compute_component_scores(
    body: str,
    latest_ts: datetime | None,
    turn_count: int,
    total_bytes: int,
    is_thread: bool,
    title: str,
    goal_tokens: set[str],
    concept_weights: dict[str, float],
    personal_vocab: dict[str, float],
    now: datetime,
    query_tokens: set[str] | None = None,
    query_page_count: int = 0,
    slug_variants: set[str] | None = None,
) -> dict:
    """Level 4 scoring. Level 3.1 base plus 4 new axes from the 8-discipline
    scorecard in docs/INGESTION_LOG.md:
      - Axis A retrieval hit potential (IR): overlap with wiki/queries tokens
      - Axis B vocabulary novelty (KR): kebab-phrase count NOT in existing vocab
      - Axis C alias risk (Entity Resolution): near-match count vs slugs, PENALTY
      - Axis G episodic vs semantic (Cognitive Science): 0=episodic 1=semantic,
        emitted but no direct score contribution (routing signal for downstream)
    Legacy Level 3.1 fields (weighted_concept, weighted_personal, etc.) remain
    unchanged so old JSONs stay comparable."""
    body_lower = body.lower()
    body_tokens_list = tokenize_list(body, minlen=4)
    body_tokens_set = set(body_tokens_list)
    body_lower_spaced = body_lower.replace("-", " ")

    # 1) goal_overlap
    if goal_tokens:
        hit = body_tokens_set & goal_tokens
        goal_overlap = min(1.0, len(hit) / max(1, len(goal_tokens)))
    else:
        goal_overlap = 0.0

    # 2) LEVEL 2: weighted concept intersection (MIKAI-central signal)
    weighted_concept = 0.0
    concept_hits: list[tuple[str, float]] = []
    for slug, weight in concept_weights.items():
        slug_spaced = slug.replace("-", " ")
        if _slug_present(body_lower, slug) or _slug_present(body_lower_spaced, slug_spaced):
            weighted_concept += weight
            concept_hits.append((slug, weight))
    concept_hits.sort(key=lambda x: -x[1])

    # 2b) LEVEL 3: weighted personal-vocabulary intersection, length-normalized.
    #     Kebab slugs matched whole-word (like concept slugs); bare-word
    #     tokens matched against the body token set for speed. Skip tokens
    #     already counted in weighted_concept to avoid double-count.
    #     Length normalization: raw sum is divided by log(1 + body_bytes/1000)
    #     so long bodies don't linearly accumulate hits into a runaway score.
    #     This is the standard IR document-length compensation.
    concept_slug_set = set(concept_weights.keys())
    weighted_personal_raw = 0.0
    personal_hits: list[tuple[str, float]] = []
    for tok, weight in personal_vocab.items():
        if tok in concept_slug_set:
            continue  # already scored under weighted_concept
        if "-" in tok:
            tok_spaced = tok.replace("-", " ")
            if _slug_present(body_lower, tok) or _slug_present(body_lower_spaced, tok_spaced):
                weighted_personal_raw += weight
                personal_hits.append((tok, weight))
        else:
            if tok in body_tokens_set:
                weighted_personal_raw += weight
                personal_hits.append((tok, weight))
    personal_hits.sort(key=lambda x: -x[1])
    # Length-normalize: divisor grows logarithmically with body size.
    # 1KB body → divisor ~1.0; 10KB → ~2.4; 100KB → ~4.7; 1MB → ~7.0.
    length_norm = math.log(2 + total_bytes / 1000.0)
    weighted_personal = weighted_personal_raw / length_norm

    # 3) recency
    if latest_ts is not None:
        days_old = (now - latest_ts).total_seconds() / 86400.0
        recency = max(0.0, 1.0 - days_old / 365.0)
    else:
        recency = 0.0

    # 4) substance
    if is_thread:
        substance = min(1.0, math.log(1 + turn_count) / math.log(30))
    else:
        substance = min(1.0, math.log(1 + total_bytes / 1000.0) / math.log(50))

    # 5) Level 3.1: aggregation bonus — reward long, multi-topic threads
    # that consolidate many personal-vocab-hitting arcs into one source.
    # A 329-turn thread touching 100+ unique personal tokens (like a
    # rolling health/posture/exercise discussion) is worth more than
    # five smaller threads on aspects of the same domain, because
    # ingestion happens once and yields more concept coverage per LLM
    # call. Formula: log-scaled by n_personal_hits, capped at W_AGGREGATION.
    n_personal_hits = len(personal_hits)
    aggregation_bonus = min(
        W_AGGREGATION,
        math.log(1 + n_personal_hits) / math.log(1 + 100) * W_AGGREGATION,
    ) if n_personal_hits > 0 else 0.0

    # ── LEVEL 4 axes (docs/INGESTION_LOG.md 8-discipline scorecard) ──

    # Axis A: retrieval hit potential — overlap with existing query pages,
    # normalized by query page count so a wiki with more queries doesn't
    # inflate the signal. Discipline: Information Retrieval.
    axis_a_retrieval = 0.0
    axis_a_hits = 0
    if query_tokens and query_page_count > 0:
        hit = body_tokens_set & query_tokens
        axis_a_hits = len(hit)
        # Log-normalize by query page count so 100-page-vault ≈ 10-page-vault
        axis_a_retrieval = min(1.0, len(hit) / max(1.0, math.log(1 + query_page_count) * 20.0))

    # Axis B: vocabulary novelty — kebab 2-3-word phrases the body coins
    # that don't already exist as concept slugs. Discipline: KR.
    kebab_phrases = _extract_kebab_phrases(body)
    if concept_weights:
        concept_slug_set_local = set(concept_weights.keys())
        novel_kebab = {p for p in kebab_phrases if p not in concept_slug_set_local}
    else:
        novel_kebab = kebab_phrases
    axis_b_novelty = min(1.0, math.log(1 + len(novel_kebab)) / math.log(20))

    # Axis C: alias risk — count body kebab-phrases that are near-matches
    # to EXISTING slugs (substring, shared 5-char prefix, or Jaro-Winkler
    # > 0.85). High alias risk = likely to produce dupes = PENALTY.
    # Discipline: Entity Resolution.
    axis_c_alias_hits = 0
    if slug_variants:
        for phrase in kebab_phrases:
            if phrase in slug_variants:
                continue  # exact match doesn't count as alias risk
            near_match = False
            # Substring match to any existing slug (short-circuit)
            for slug in slug_variants:
                if len(slug) >= 5 and (slug in phrase or phrase in slug):
                    near_match = True
                    break
            # Prefix + Jaro-Winkler fallback if no substring hit
            if not near_match:
                for slug in slug_variants:
                    if len(slug) < 5 or len(phrase) < 5:
                        continue
                    if slug[:5] == phrase[:5]:
                        if _jaro_winkler(slug, phrase) > 0.85:
                            near_match = True
                            break
            if near_match:
                axis_c_alias_hits += 1
    axis_c_alias_penalty = W_AXIS_C_ALIAS * min(
        1.0, math.log(1 + axis_c_alias_hits) / math.log(20)
    )

    # Axis G: episodic-vs-semantic classification (0..1, 0.5 ambiguous).
    # Discipline: Cognitive Science of Memory (Tulving). NOT scored — routing
    # signal only.
    axis_g_episodic_score = _compute_axis_g_episodic_score(title, body)

    # Level 4 formula: Level 3.1 base + Axis A + Axis B + Axis C penalty.
    # Axis G omitted from score sum by design (routing signal).
    score_l3_1 = (
        weighted_concept
        + weighted_personal
        + W_GOAL * goal_overlap
        + W_RECENCY * recency
        + W_SUBSTANCE * substance
        + aggregation_bonus
    )
    score = (
        score_l3_1
        + W_AXIS_A_RETRIEVAL * axis_a_retrieval
        + W_AXIS_B_NOVELTY * axis_b_novelty
        + axis_c_alias_penalty  # already negative-signed
    )
    return {
        "score": score,
        "score_l3_1": score_l3_1,
        "goal_overlap": goal_overlap,
        "weighted_concept": weighted_concept,
        "concept_hits_top": [{"slug": s, "weight": round(w, 3)} for s, w in concept_hits[:8]],
        "n_concept_hits": len(concept_hits),
        "weighted_personal": weighted_personal,
        "personal_hits_top": [{"tok": t, "weight": round(w, 3)} for t, w in personal_hits[:8]],
        "n_personal_hits": n_personal_hits,
        "recency": recency,
        "substance": substance,
        "aggregation_bonus": aggregation_bonus,
        "axis_a_retrieval": axis_a_retrieval,
        "axis_a_hits": axis_a_hits,
        "axis_b_novelty": axis_b_novelty,
        "axis_b_novel_kebab_count": len(novel_kebab),
        "axis_c_alias_risk": axis_c_alias_penalty,
        "axis_c_alias_hits": axis_c_alias_hits,
        "axis_g_episodic_score": axis_g_episodic_score,
        "body_bytes": total_bytes,
        "n_body_tokens": len(body_tokens_list),
    }


def _slug_present(text: str, slug: str) -> bool:
    """Whole-word check: slug must be surrounded by non-word chars or
    start/end. Slug is already lowercased with hyphens (or spaces)."""
    idx = text.find(slug)
    while idx != -1:
        before_ok = idx == 0 or not text[idx - 1].isalnum()
        end = idx + len(slug)
        after_ok = end == len(text) or not text[end].isalnum()
        if before_ok and after_ok:
            return True
        idx = text.find(slug, idx + 1)
    return False


# ── Main pipeline ─────────────────────────────────────────────────────

def build_candidates(WikiIndex, ingested: set[str],
                     goal_tokens: set[str], concept_weights: dict[str, float],
                     personal_vocab: dict[str, float],
                     wiki_md: Path, wiki_index: Path,
                     query_tokens: set[str] | None = None,
                     query_page_count: int = 0,
                     slug_variants: set[str] | None = None,
                     debug_limit: int | None = None) -> tuple[list[dict], dict]:
    """Return (candidates_ranked, stats). Level 2: excludes claude-code
    dev-session turns and malformed claude-thread orphans from the
    candidate universe entirely (per Session-10 spec). Level 4 adds
    query_tokens / query_page_count / slug_variants for axes A, B, C."""
    idx = WikiIndex.load(wiki_index)
    print(f"[r3] loaded {len(idx.records)} sections from wiki.index",
          file=sys.stderr)
    now = _now_utc()

    # Partition into threads (grouped) vs other sources.
    # Level 2 filters: drop claude-code entirely, drop malformed
    # claude-thread orphans (name lacks the '::title::idx::role' shape).
    thread_groups: dict[str, list[dict]] = defaultdict(list)
    other_records: list[dict] = []
    skipped_claude_code = 0
    skipped_malformed_thread = 0
    for r in idx.records:
        src = str(r.get("source", ""))
        if src.startswith("claude-code"):
            skipped_claude_code += 1
            continue
        if src.startswith("claude-thread"):
            if is_claude_thread_turn(r):
                title, _, _ = parse_thread_turn(r)
                thread_groups[title].append(r)
            else:
                skipped_malformed_thread += 1
            continue
        other_records.append(r)

    print(f"[r3] {len(thread_groups)} unique claude threads, "
          f"{len(other_records)} other sections | "
          f"filtered: {skipped_claude_code} claude-code, "
          f"{skipped_malformed_thread} malformed thread orphans",
          file=sys.stderr)

    candidates: list[dict] = []
    skipped_ingested = 0
    skipped_empty = 0

    # Thread candidates
    for title, turns in thread_groups.items():
        turns_sorted = sorted(turns, key=lambda r: parse_thread_turn(r)[1])
        earliest_date = str(turns_sorted[0].get("header_ts", "unknown"))[:10]
        latest_ts_str = str(turns_sorted[-1].get("header_ts", ""))
        latest_ts = _parse_ts(latest_ts_str)
        fname = filename_for_thread(title, earliest_date)
        if fname in ingested:
            skipped_ingested += 1
            continue
        # Read section bodies
        body_parts: list[str] = []
        total_bytes = 0
        for rec in turns_sorted:
            try:
                b = WikiIndex.read_section(wiki_md, rec)
                if b.startswith("### "):
                    b = b.split("\n", 1)[1] if "\n" in b else ""
                body_parts.append(b)
                total_bytes += len(b.encode("utf-8"))
            except Exception:
                continue
        body = "\n\n".join(body_parts)
        if not body.strip():
            skipped_empty += 1
            continue
        scores = compute_component_scores(
            body, latest_ts, len(turns_sorted), total_bytes,
            is_thread=True, title=title,
            goal_tokens=goal_tokens, concept_weights=concept_weights,
            personal_vocab=personal_vocab,
            query_tokens=query_tokens,
            query_page_count=query_page_count,
            slug_variants=slug_variants,
            now=now,
        )
        candidates.append({
            "kind": "thread",
            "title": title,
            "filename": fname,
            "earliest_date": earliest_date,
            "latest_ts": latest_ts_str,
            "turns": len(turns_sorted),
            **scores,
        })
        if debug_limit and len(candidates) >= debug_limit:
            break

    # Other sources
    for rec in other_records:
        fname = filename_for_record(rec)
        if fname in ingested:
            skipped_ingested += 1
            continue
        try:
            body = WikiIndex.read_section(wiki_md, rec)
        except Exception:
            skipped_empty += 1
            continue
        if body.startswith("### "):
            body = body.split("\n", 1)[1] if "\n" in body else ""
        if not body.strip():
            skipped_empty += 1
            continue
        total_bytes = len(body.encode("utf-8"))
        latest_ts_str = str(rec.get("header_ts", ""))
        latest_ts = _parse_ts(latest_ts_str)
        title = str(rec.get("name", ""))
        source_type = str(rec.get("source", "")).split(":")[0]
        scores = compute_component_scores(
            body, latest_ts, 0, total_bytes,
            is_thread=False, title=title,
            goal_tokens=goal_tokens, concept_weights=concept_weights,
            personal_vocab=personal_vocab,
            query_tokens=query_tokens,
            query_page_count=query_page_count,
            slug_variants=slug_variants,
            now=now,
        )
        candidates.append({
            "kind": source_type or "unknown",
            "title": title,
            "filename": fname,
            "earliest_date": latest_ts_str[:10],
            "latest_ts": latest_ts_str,
            "turns": 0,
            **scores,
        })
        if debug_limit and len(candidates) >= debug_limit:
            break

    # Sort descending by score
    candidates.sort(key=lambda c: -c["score"])

    stats = {
        "total_sections": len(idx.records),
        "skipped_claude_code": skipped_claude_code,
        "skipped_malformed_thread": skipped_malformed_thread,
        "unique_threads": len(thread_groups),
        "other_records": len(other_records),
        "ingested_files": len(ingested),
        "skipped_already_ingested": skipped_ingested,
        "skipped_empty": skipped_empty,
        "candidates_evaluated": len(candidates),
    }
    return candidates, stats


# ── Report rendering ──────────────────────────────────────────────────

def _fmt_score_cell(v: float) -> str:
    return f"{v:.2f}"


def render_report(candidates: list[dict], stats: dict, goals: list[str],
                  concept_slugs_count: int, max_concept_weight: float,
                  personal_vocab_count: int, max_personal_weight: float,
                  top_n_table: int = 30,
                  batch_n: int = 15) -> str:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = []
    lines.append(f"# R Candidate Salience — Level 4 (adds IR / KR / Entity-Resolution / Cog-Sci axes) — {date}")
    lines.append("")
    lines.append("Ranked candidates for the next ingestion round, scored via **weighted "
                 "concept intersection** (Session-10 spec in `fuzzy-shimmying-wreath.md`).")
    lines.append("")
    lines.append("**Disposable one-shot scorer.** Purpose: schedule which un-ingested "
                 "wiki-raw sources get the next paid `claude -p` call. Not a peer of the "
                 "post-ingest salience system (`wiki-salience.md` / `dream_bootstrap.py`); "
                 "no eval, no versioning. Judged only by downstream post-ingest recall@10 "
                 "lift. Retire when the wiki-raw backlog drains.")
    lines.append("")
    lines.append("## Universe & filtering")
    lines.append("")
    lines.append(f"- Total wiki-raw sections: **{stats['total_sections']}**")
    lines.append(f"- Filtered out — `claude-code` per-turn fragments: "
                 f"**{stats['skipped_claude_code']}**")
    lines.append(f"- Filtered out — malformed `claude-thread` orphans "
                 f"(name missing `::title::idx::role`): "
                 f"**{stats['skipped_malformed_thread']}**")
    lines.append(f"- Unique claude threads (well-formed): **{stats['unique_threads']}**")
    lines.append(f"- Other sections (apple-notes, perplexity, ...): "
                 f"**{stats['other_records']}**")
    lines.append(f"- Already ingested into parallel vault: "
                 f"**{stats['ingested_files']}** files")
    lines.append(f"- Skipped as already-ingested during scoring: "
                 f"**{stats['skipped_already_ingested']}**")
    lines.append(f"- Skipped as empty body: **{stats['skipped_empty']}**")
    lines.append(f"- **Candidates evaluated: {stats['candidates_evaluated']}**")
    lines.append("")
    lines.append("## Scoring — Level 3 formula")
    lines.append("")
    lines.append("```")
    lines.append("score = Σ log(1 + in_degree(c))       ← weighted_concept  (MIKAI-central, UNBOUNDED)")
    lines.append("      + Σ profile_weight(t)           ← weighted_personal (broader Brian-profile, UNBOUNDED)")
    lines.append("      + 3 · goal_overlap              ← 0-1")
    lines.append("      + recency                       ← 0-1 (linear decay over 365d)")
    lines.append("      + substance                     ← 0-1 (log(turns) or log(bytes))")
    lines.append("      + aggregation_bonus             ← 0-1.5 (log-scaled by n_personal_hits, rewards multi-topic dense threads)")
    lines.append("```")
    lines.append("")
    lines.append("**Level 3.1 tuning changes:** removed hard-coded noise blacklist "
                 "(yoga/plants/dining/etc. — false negatives on personal-domain clusters "
                 "Brian actively cares about); added aggregation bonus so long threads "
                 "consolidating many personal-vocab topics score above thin single-topic "
                 "sources. Signal density (weighted_concept + weighted_personal + goal_overlap) "
                 "is now the sole off-topic discriminator — zero-signal sources naturally "
                 "rank at bottom.")
    lines.append("")
    lines.append(f"**weighted_concept** — MIKAI-central signal. Sums `log(1+in-degree)` over "
                 f"concept slugs (min length {MIN_SLUG_LEN}, kebab-case) hit in source body. "
                 f"Max concept weight this run: **{max_concept_weight:.2f}**. Vocab: "
                 f"{concept_slugs_count} slugs.")
    lines.append("")
    lines.append(f"**weighted_personal** — broader Brian-profile signal (Level 3 addition). "
                 f"Sums per-token weight from a compiled personal vocabulary. Sources: "
                 f"USER_MODEL.md (1.5), PROFILE.md (1.0), BRAIN.md priorities (0.7), "
                 f"entity slugs (0.5), wisdom/goals/habits/reflections (0.5), queries (0.4), "
                 f"journal tags (0.3). Max personal weight this run: **{max_personal_weight:.2f}**. "
                 f"Vocab: {personal_vocab_count} tokens. Tokens already in concept vocab are "
                 f"excluded from this component to avoid double-counting.")
    lines.append("")
    lines.append(f"Goal source: `~/.mikai/brain/GOALS.md` ({len(goals)} goals).")
    lines.append("")
    lines.append("### Level 4 additions (4 new axes from `docs/INGESTION_LOG.md` 8-discipline scorecard)")
    lines.append("")
    lines.append("- **axis_a_retrieval** (IR, weight +1.0): overlap with tokens in `wiki/queries/*.md` "
                 "— predicts which candidates will get queried later.")
    lines.append("- **axis_b_novelty** (KR, weight +1.0): 2-3-word kebab-phrases in body NOT already "
                 "in concept vocab — sources that expand vocabulary score higher.")
    lines.append("- **axis_c_alias_risk** (Entity Resolution, weight -0.5): near-matches to existing "
                 "slugs (substring + prefix + Jaro-Winkler > 0.85) — high risk = likely to produce dupes.")
    lines.append("- **axis_g_episodic_score** (Cognitive Science, no direct weight): 0.0=episodic, "
                 "1.0=semantic, 0.5=ambiguous. Routing signal only — emitted for downstream page-type placement.")
    lines.append("")
    lines.append(f"## Top {top_n_table} candidates")
    lines.append("")
    lines.append("| # | score | l3.1 | w_conc | w_pers | axA | axB | axC | axG | kind | KB | turns | title |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, c in enumerate(candidates[:top_n_table], 1):
        kb = c["body_bytes"] // 1024
        turns = c["turns"] if c["turns"] else "—"
        title = c["title"][:55].replace("|", "\\|")
        lines.append(
            f"| {i} | {c['score']:.2f} | {c.get('score_l3_1', 0.0):.2f} | "
            f"{c['weighted_concept']:.2f} | {c.get('weighted_personal', 0.0):.2f} | "
            f"{c.get('axis_a_retrieval', 0.0):.2f} | "
            f"{c.get('axis_b_novelty', 0.0):.2f} | "
            f"{c.get('axis_c_alias_risk', 0.0):.2f} | "
            f"{c.get('axis_g_episodic_score', 0.5):.2f} | "
            f"{c['kind']} | {kb} | {turns} | {title} |"
        )
    lines.append("")

    # Show top hits per candidate — makes rankings auditable
    lines.append(f"### Top concept + personal hits per candidate (top {min(15, top_n_table)})")
    lines.append("")
    for i, c in enumerate(candidates[:min(15, top_n_table)], 1):
        c_hits = c.get("concept_hits_top", [])
        p_hits = c.get("personal_hits_top", [])
        c_str = ", ".join(f"`{h['slug']}` ({h['weight']:.2f})" for h in c_hits[:3]) if c_hits else "—"
        p_str = ", ".join(f"`{h['tok']}` ({h['weight']:.2f})" for h in p_hits[:3]) if p_hits else "—"
        lines.append(f"- **{i}.** {c['title'][:60]}")
        lines.append(f"  - concepts: {c_str}")
        lines.append(f"  - personal: {p_str}")
    lines.append("")

    # Next-batch recommendation
    batch = candidates[:batch_n]
    total_kb = sum(c["body_bytes"] for c in batch) / 1024
    est_min_p8 = (len(batch) * 200) / 60.0 / 8
    est_min_p1 = (len(batch) * 200) / 60.0
    lines.append(f"## Recommended next batch (top {batch_n})")
    lines.append("")
    lines.append(f"- Total volume: **{total_kb:.0f}KB** across {len(batch)} sources")
    lines.append(f"- Est. wall-clock: **~{est_min_p8:.0f}min** at workers=8, "
                 f"**~{est_min_p1:.0f}min** at workers=1 "
                 f"(assumes ~200s/source average)")
    lines.append(f"- Would land as R3-{date}-mikai-followup")
    lines.append("")
    lines.append("| # | score | w_conc | w_pers | title | KB | filename |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, c in enumerate(batch, 1):
        kb = c["body_bytes"] // 1024
        lines.append(
            f"| {i} | {c['score']:.2f} | {c['weighted_concept']:.2f} | "
            f"{c.get('weighted_personal', 0.0):.2f} | "
            f"{c['title'][:60]} | {kb} | `{c['filename']}` |"
        )
    lines.append("")

    # Appendix: tail candidates for auditability (cap at 200 rows for readability)
    tail = candidates[top_n_table:]
    if tail:
        cap = min(len(tail), 200)
        lines.append(f"## Appendix — next {cap} candidates (rank {top_n_table+1}+, brief)")
        lines.append("")
        for i, c in enumerate(tail[:cap], top_n_table + 1):
            lines.append(
                f"- {i}. **{c['score']:.2f}** [w_conc={c['weighted_concept']:.2f}, "
                f"{c['kind']}, {c['body_bytes']//1024}KB] {c['title'][:80]}"
            )
        if len(tail) > cap:
            lines.append(f"")
            lines.append(f"_({len(tail) - cap} additional low-score candidates omitted; "
                         f"see JSON for full list.)_")
    return "\n".join(lines) + "\n"


# ── Entry ─────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=30,
                    help="rows in the top-N table (default 30)")
    ap.add_argument("--batch-n", type=int, default=15,
                    help="rows in the recommended-batch section (default 15)")
    ap.add_argument("--report", type=Path, default=None,
                    help="report path (default eval/reports/r3_candidates_salience_<today>.md)")
    ap.add_argument("--json", type=Path, default=None,
                    help="JSON output path (default alongside report)")
    args = ap.parse_args()

    t0 = time.time()

    WikiIndex = _load_wiki_index()
    vault_root = VAULT_ROOT

    print("[r3] loading goals + concepts + personal-vocab + ingested-set...",
          file=sys.stderr)
    goal_tokens, goal_titles = load_goal_tokens(GOALS_MD)
    print(f"[r3]   goal_tokens: {len(goal_tokens)}, "
          f"goal_titles: {len(goal_titles)}", file=sys.stderr)
    concept_weights = load_concept_weights(CONCEPTS_DIR, SALIENCE_LEDGER, vault_root)
    max_w = max(concept_weights.values()) if concept_weights else 0.0
    print(f"[r3]   concept_weights: {len(concept_weights)} slugs "
          f"(max weight {max_w:.2f})", file=sys.stderr)
    personal_vocab = load_personal_vocabulary(vault_root)
    max_pw = max(personal_vocab.values()) if personal_vocab else 0.0
    print(f"[r3]   personal_vocab: {len(personal_vocab)} tokens "
          f"(max weight {max_pw:.2f})", file=sys.stderr)
    ingested = load_ingested_filenames(INGESTED_DIR)
    print(f"[r3]   ingested files: {len(ingested)}", file=sys.stderr)

    # Level 4 pre-loads: query tokens (Axis A) + slug variants (Axis C).
    query_tokens, query_page_count = _query_tokens(vault_root)
    print(f"[r3]   query_tokens: {len(query_tokens)} across "
          f"{query_page_count} query pages (Axis A)", file=sys.stderr)
    slug_variants = _load_all_slug_variants(concept_weights)
    print(f"[r3]   slug_variants: {len(slug_variants)} (Axis C)", file=sys.stderr)

    candidates, stats = build_candidates(
        WikiIndex, ingested, goal_tokens, concept_weights, personal_vocab,
        WIKI_MD, WIKI_INDEX,
        query_tokens=query_tokens,
        query_page_count=query_page_count,
        slug_variants=slug_variants,
    )

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    default_report = REPORTS_DIR / f"r4_candidates_level4_{date}.md"
    default_json = REPORTS_DIR / f"r4_candidates_level4_{date}.json"
    report_path = args.report or default_report
    json_path = args.json or default_json

    report = render_report(candidates, stats, goal_titles,
                           concept_slugs_count=len(concept_weights),
                           max_concept_weight=max_w,
                           personal_vocab_count=len(personal_vocab),
                           max_personal_weight=max_pw,
                           top_n_table=args.top_n, batch_n=args.batch_n)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    json_path.write_text(json.dumps({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "level": 4,
        "min_slug_len": MIN_SLUG_LEN,
        "min_profile_token_len": MIN_PROFILE_TOKEN_LEN,
        "stats": stats,
        "weights": {
            "weighted_concept_multiplier": 1.0,
            "weighted_personal_multiplier": 1.0,
            "goal_overlap": W_GOAL,
            "recency": W_RECENCY,
            "substance": W_SUBSTANCE,
            "aggregation_bonus_cap": W_AGGREGATION,
            "axis_a_retrieval": W_AXIS_A_RETRIEVAL,
            "axis_b_novelty": W_AXIS_B_NOVELTY,
            "axis_c_alias_penalty": W_AXIS_C_ALIAS,
            "axis_g_episodic_score": "emitted-only-no-weight",
            "profile_source_weights": PROFILE_WEIGHTS,
        },
        "goal_titles": goal_titles,
        "n_concept_slugs": len(concept_weights),
        "max_concept_weight": max_w,
        "n_personal_tokens": len(personal_vocab),
        "max_personal_weight": max_pw,
        "n_query_tokens": len(query_tokens),
        "query_page_count": query_page_count,
        "candidates": candidates,
    }, indent=2), encoding="utf-8")

    dt = time.time() - t0
    print(f"[r3] wrote {report_path} ({report_path.stat().st_size} bytes)",
          file=sys.stderr)
    print(f"[r3] wrote {json_path}", file=sys.stderr)
    print(f"[r3] elapsed: {dt:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()

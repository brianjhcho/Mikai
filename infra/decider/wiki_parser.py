"""
wiki_parser.py — parse ~/.mikai/wiki/wiki.md into structured threads.

The wiki is the formal user-identity synthesis produced nightly by
infra/graphiti/dream.py. It contains four sections:
  ## Who      — stable self-model
  ## Now      — active threads (bulleted: **Name** — STATE. detail...)
  ## Tensions — held contradictions (numbered)
  ## Wants    — inferred goals (bulleted with certainty in words)

This parser extracts threads from ## Now, tensions from ## Tensions, and
wants from ## Wants. Each gets a structured shape FIGS can rank.

The 4-factor surface-priority metric (see ARCHITECTURE.md §7):
    surface_priority = thread_recency × thread_state × tension_pressure × delivery_cost⁻¹

This module computes the WIKI-derived components (state, tension, recency
of last log mention). delivery_cost is FIGS's job (dismiss rate + ToD).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

WIKI_PATH = Path.home() / ".mikai" / "wiki" / "wiki.md"
LOG_PATH = Path.home() / ".mikai" / "wiki" / "log.md"


# State weights — derived from the wiki's `## Now` state vocabulary
# (Acting / Decided / Exploring) and noonchi's stalled detection.
STATE_WEIGHTS = {
    "acting": 1.0,      # in flight, most likely to need a nudge
    "stalled": 0.95,    # acting with no movement; explicitly priority signal
    "decided": 0.7,     # committed but not done; could need scheduling
    "exploring": 0.4,   # still scoping; lower urgency
    "unknown": 0.3,     # no state tag visible
}


@dataclass
class WikiThread:
    """A single thread parsed from the wiki's ## Now section."""
    slug: str              # short id, e.g. "mikai_task_state"
    title: str             # the bold-prefix name, e.g. "MIKAI (Task State Awareness 2.0)"
    state: str             # acting/decided/exploring/stalled/unknown
    detail: str            # the full bullet body
    tension_membership: list[int] = field(default_factory=list)  # which tensions reference this
    last_logged_at: str | None = None  # most recent log.md entry date


@dataclass
class WikiTension:
    """A single tension from ## Tensions (numbered list)."""
    index: int            # 1-based
    title: str            # first sentence / bold prefix
    detail: str           # full body
    related_thread_slugs: list[str] = field(default_factory=list)


@dataclass
class WikiWant:
    certainty: str        # "Clearly" / "Probably" / "Possibly" — first word of bullet
    text: str


@dataclass
class ParsedWiki:
    who: str              # the ## Who paragraph
    threads: list[WikiThread]
    tensions: list[WikiTension]
    wants: list[WikiWant]
    last_dream_at: str | None = None
    available: bool = True       # False if file missing
    error: str | None = None


def _slugify(title: str) -> str:
    """Make a stable id from a thread title."""
    s = title.lower()
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s[:60]


def _split_sections(text: str) -> dict[str, str]:
    """Split wiki body into ## sections."""
    sections: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = m.group(1).strip().lower()
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


_BULLET_RE = re.compile(r"^-\s+(.+)$", re.MULTILINE)
_THREAD_HEADER_RE = re.compile(
    r"^\*\*(?P<title>[^*]+)\*\*\s*[—\-–]\s*(?P<state>Acting|Decided|Exploring|Stalled|Done)?\.?\s*(?P<rest>.*)",
    re.IGNORECASE | re.DOTALL,
)


def _parse_now(now_text: str) -> list[WikiThread]:
    """Parse ## Now section into WikiThread objects.

    Expected format per bullet:
      - **MIKAI (Task State Awareness 2.0)** — Acting. Core architecture is ...
    """
    threads: list[WikiThread] = []
    if not now_text:
        return threads

    # Split on top-level bullet markers, keeping the dash so multi-line bullets
    # aren't broken by inline dashes/em-dashes in the body.
    blocks = re.split(r"\n(?=-\s+\*\*)", now_text)
    for block in blocks:
        block = block.strip()
        if not block.startswith("-"):
            continue
        body = block[1:].strip()  # strip leading "- "
        m = _THREAD_HEADER_RE.match(body)
        if not m:
            # Bullet doesn't start with **Title** — skip.
            continue
        title = m.group("title").strip()
        state_raw = (m.group("state") or "").strip().lower()
        state = state_raw if state_raw in STATE_WEIGHTS else "unknown"
        rest = m.group("rest").strip()
        full_detail = body  # keep the whole bullet text including header
        threads.append(WikiThread(
            slug=_slugify(title),
            title=title,
            state=state,
            detail=full_detail,
        ))
    return threads


_TENSION_RE = re.compile(r"^\d+\.\s+(.+?)(?=^\d+\.\s|\Z)", re.MULTILINE | re.DOTALL)


def _parse_tensions(text: str) -> list[WikiTension]:
    """Parse ## Tensions section. Numbered list."""
    tensions: list[WikiTension] = []
    if not text:
        return tensions
    for i, m in enumerate(_TENSION_RE.finditer(text), start=1):
        body = m.group(1).strip()
        title_line = body.split("\n", 1)[0].strip()
        # Often: **Title** Detail...
        title_match = re.match(r"\*\*([^*]+)\*\*[\.:\s—\-–]*(.*)", title_line)
        title = title_match.group(1).strip() if title_match else title_line[:80]
        tensions.append(WikiTension(index=i, title=title, detail=body))
    return tensions


_WANT_BULLET_RE = re.compile(
    r"^-\s+\*\*(?P<certainty>Clearly|Probably|Possibly)\*\*[:\.]?\s*(?P<text>.+)",
    re.MULTILINE,
)


def _parse_wants(text: str) -> list[WikiWant]:
    wants: list[WikiWant] = []
    if not text:
        return wants
    for m in _WANT_BULLET_RE.finditer(text):
        wants.append(WikiWant(
            certainty=m.group("certainty"),
            text=m.group("text").strip(),
        ))
    return wants


def _last_dream_timestamp(log_text: str) -> str | None:
    """Get the most recent dream timestamp from log.md."""
    if not log_text:
        return None
    # log.md format: "## Dream YYYY-MM-DDTHH:MM  ·  N episodes..."
    matches = re.findall(r"^##\s*Dream\s+(\S+)", log_text, re.MULTILINE)
    return matches[-1] if matches else None  # last = most recent (append-only)


def _link_tensions_to_threads(
    tensions: list[WikiTension],
    threads: list[WikiThread],
) -> None:
    """Mark which threads are referenced by each tension (in-place)."""
    for tension in tensions:
        tdetail_lower = tension.detail.lower()
        for thread in threads:
            # Match by title fragment (first word of title or full title)
            title_words = thread.title.lower().split()
            if not title_words:
                continue
            first_word = title_words[0]
            if (thread.title.lower() in tdetail_lower or
                (len(first_word) > 4 and first_word in tdetail_lower)):
                tension.related_thread_slugs.append(thread.slug)
                thread.tension_membership.append(tension.index)


def parse_wiki(wiki_path: Path = WIKI_PATH, log_path: Path = LOG_PATH) -> ParsedWiki:
    """Read and parse the wiki + log. Returns a ParsedWiki always (with
    `available=False` if the file is missing — adapters never raise)."""
    if not wiki_path.exists():
        return ParsedWiki(
            who="", threads=[], tensions=[], wants=[],
            available=False,
            error=f"wiki.md not found at {wiki_path}. Has dream.py run yet?",
        )

    try:
        text = wiki_path.read_text(encoding="utf-8")
    except OSError as e:
        return ParsedWiki(
            who="", threads=[], tensions=[], wants=[],
            available=False, error=f"read failed: {e}",
        )

    sections = _split_sections(text)
    who = sections.get("who", "").strip()
    threads = _parse_now(sections.get("now", ""))
    tensions = _parse_tensions(sections.get("tensions", ""))
    wants = _parse_wants(sections.get("wants", ""))

    _link_tensions_to_threads(tensions, threads)

    last_dream_at = None
    if log_path.exists():
        try:
            last_dream_at = _last_dream_timestamp(log_path.read_text(encoding="utf-8"))
        except OSError:
            pass

    return ParsedWiki(
        who=who,
        threads=threads,
        tensions=tensions,
        wants=wants,
        last_dream_at=last_dream_at,
        available=True,
    )


# ── Scoring ────────────────────────────────────────────────────────────


def score_thread(thread: WikiThread, parsed: ParsedWiki) -> float:
    """Compute wiki-derived components of surface_priority.

    Returns a 0..1 score that's the product of:
      thread_state (from STATE_WEIGHTS)
      tension_pressure (1.5x boost if mentioned in ## Tensions, capped to 1.0)
      detail_quality (length of bullet, capped)
    Recency and delivery cost are computed by FIGS, not here.
    """
    state_w = STATE_WEIGHTS.get(thread.state, STATE_WEIGHTS["unknown"])
    tension_boost = 1.0 if not thread.tension_membership else min(
        1.0, 0.6 + 0.2 * len(thread.tension_membership)
    )
    # Detail length proxy for specificity. ≥400 chars maxes the factor.
    detail_factor = min(1.0, len(thread.detail) / 400.0)
    raw = state_w * tension_boost * detail_factor
    return min(1.0, raw)


if __name__ == "__main__":
    import json
    parsed = parse_wiki()
    print(f"available: {parsed.available}")
    if parsed.error:
        print(f"error: {parsed.error}")
    print(f"last_dream_at: {parsed.last_dream_at}")
    print(f"threads: {len(parsed.threads)}")
    print(f"tensions: {len(parsed.tensions)}")
    print(f"wants: {len(parsed.wants)}")
    print()
    print("=== Threads (ranked by wiki-score) ===")
    ranked = sorted(
        parsed.threads,
        key=lambda t: score_thread(t, parsed),
        reverse=True,
    )
    for t in ranked:
        s = score_thread(t, parsed)
        print(f"  {s:.2f} [{t.state:<10}] {t.title}")
        if t.tension_membership:
            print(f"        ↳ tensions: {t.tension_membership}")
        print(f"        detail: {t.detail[:120]}...")
        print()
    print("=== Tensions ===")
    for t in parsed.tensions:
        print(f"  #{t.index}: {t.title}")
        if t.related_thread_slugs:
            print(f"     related: {t.related_thread_slugs}")

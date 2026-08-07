"""Latent-thread detector — surfaces thread-shape topics from the
substrate that Brian hasn't yet crystallized into a `threads/` file.

The old detector (mentions >= 30) treated importance as frequency. That
buried dormant-but-load-bearing topics (dry-eyes, China proposal,
plants) and surfaced tooling noise (claude-md, python). See
docs/USER_MODEL_RESEARCH.md — the fix is to rank against the compiled
UserModel: an entity aligned with a theme surfaces even under the
mention floor; a high-count entity that isn't life-topic-shaped
gets skipped.

Read-only on the substrate. Writes proposals into brain/inbox/ as
`proposed-thread-<slug>.md` — Brian triages, MIKAI never auto-creates.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from . import BRAIN_ROOT, INBOX_DIR, INBOX_PROCESSED, THREADS_DIR
from .hydrator import parse_ontology, OntologyEntity, ONTOLOGY_PATH
from . import user_model as user_model_mod

# Frequency is now a FLOOR, not the ranker. Anything below is
# statistical noise; anything above is a candidate that the model must
# still bless.
MENTIONS_FLOOR = 3
DEFAULT_LIMIT = 10

# Substrate-noise blocklist — the concept-density lens's blocklist,
# same intent: strip meta-concepts + tooling + generic tokens that
# extraction leaks. Kept small; expand as it drifts.
NOISE_SLUGS = {
    "mikai", "figs", "graphiti", "claude", "claude-code", "claude-md",
    "claude.ai", "the-user", "user", "brian", "brian-cho", "briancho",
    "system", "thing", "things", "concept", "concepts",
    "python", "javascript", "typescript", "sql", "git",
}


@dataclass
class LatentThread:
    slug: str
    type: str
    mentions: int
    first_seen: str
    last_seen: str
    sources: str
    score: float          # user-model alignment bonus + frequency floor
    reason: str           # one-liner: why this made it (or would have)
    theme_match: str = "" # which UserModel.theme it aligned with (if any)


# ── Existing-thread detection ────────────────────────────────────────


def _existing_thread_slugs() -> set[str]:
    if not THREADS_DIR.exists():
        return set()
    out: set[str] = set()
    for p in THREADS_DIR.iterdir():
        if p.is_file() and p.name.endswith(".md"):
            out.add(p.stem)
    return out


def _already_proposed(slug: str) -> bool:
    name = f"proposed-thread-{slug}.md"
    if (INBOX_DIR / name).exists():
        return True
    if INBOX_PROCESSED.exists():
        return any(p.name.endswith(f"__{name}") or p.name == name
                   for p in INBOX_PROCESSED.iterdir())
    return False


# ── Alignment scoring ────────────────────────────────────────────────


def _tokenize(text: str) -> set[str]:
    """Cheap tokenizer for theme-vs-slug overlap. Splits on non-alnum,
    lowercases, keeps tokens of length >= 3."""
    out: set[str] = set()
    cur = []
    for ch in text.lower():
        if ch.isalnum():
            cur.append(ch)
        else:
            if len(cur) >= 3:
                out.add("".join(cur))
            cur = []
    if len(cur) >= 3:
        out.add("".join(cur))
    return out


def _theme_alignment(slug: str, themes: list[str]) -> tuple[float, str]:
    """Return (bonus, matched-theme). Bonus is proportional to token
    overlap so a slug shared with two themes scores higher than one.
    An exact substring match dominates — that's the strong signal."""
    if not themes:
        return 0.0, ""
    slug_tokens = _tokenize(slug.replace("-", " "))
    best_bonus = 0.0
    best_theme = ""
    for theme in themes:
        theme_l = theme.lower()
        if slug.lower() in theme_l or slug.replace("-", " ").lower() in theme_l:
            bonus = 5.0
            if bonus > best_bonus:
                best_bonus = bonus
                best_theme = theme
            continue
        theme_tokens = _tokenize(theme_l)
        overlap = slug_tokens & theme_tokens
        if overlap:
            bonus = 1.0 + len(overlap) * 0.5
            if bonus > best_bonus:
                best_bonus = bonus
                best_theme = theme
    return best_bonus, best_theme


def _score(ent: OntologyEntity, um: user_model_mod.UserModel | None
           ) -> tuple[float, str, str]:
    """Compose the ranker score. Returns (score, reason, matched_theme)."""
    freq_component = min(ent.mentions / 20.0, 3.0)  # log-shaped soft cap

    if um is None:
        # No user model yet — fall back to frequency alone. Same shape as
        # before but scored, not hard-thresholded, so downstream can see
        # how weak the signal is.
        return freq_component, f"frequency-only ({ent.mentions} mentions)", ""

    # Fable §3: themes + unresolved are one rotating slot now (`current`).
    # Alignment scoring stays: any current-list item that matches the
    # slug earns the ranker bonus. The old "themes stronger than
    # unresolved" tie-break is gone with the merge.
    bonus, matched = _theme_alignment(ent.slug, um.current)
    if bonus > 0:
        return freq_component + bonus, (
            f"aligns with current '{matched}' (bonus {bonus:.1f}) "
            f"+ {ent.mentions} mentions"
        ), matched

    return freq_component, f"frequency-only ({ent.mentions} mentions)", ""


# ── Selection ────────────────────────────────────────────────────────


def select_candidates(
    *,
    limit: int = DEFAULT_LIMIT,
    mentions_floor: int = MENTIONS_FLOOR,
    ontology_path: Path = ONTOLOGY_PATH,
    um: user_model_mod.UserModel | None = None,
) -> list[LatentThread]:
    """Score all ontology entities against the user model; return the
    top-N latent-thread candidates that (a) aren't already threads,
    (b) aren't already proposed, (c) aren't substrate noise."""
    if um is None:
        um = user_model_mod.load()

    existing = _existing_thread_slugs()
    all_ents = parse_ontology(ontology_path)

    scored: list[LatentThread] = []
    for e in all_ents:
        if e.slug in NOISE_SLUGS:
            continue
        if e.flagged:
            continue
        if e.mentions < mentions_floor:
            continue
        if e.slug in existing:
            continue
        if _already_proposed(e.slug):
            continue

        score, reason, theme = _score(e, um)

        # With a user model present, require some alignment for anything
        # under a stricter mention gate. Prevents pure-frequency winners
        # from dominating when they contribute no theme signal.
        if um is not None and theme == "" and e.mentions < 15:
            continue

        scored.append(LatentThread(
            slug=e.slug, type=e.type, mentions=e.mentions,
            first_seen=e.first_seen, last_seen=e.last_seen,
            sources=e.sources, score=score, reason=reason,
            theme_match=theme,
        ))

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:limit]


# ── Proposal writing ─────────────────────────────────────────────────


def _proposal_text(t: LatentThread) -> str:
    today = date.today().isoformat()
    return (
        "---\n"
        "proposal_kind: thread\n"
        f"slug: {t.slug}\n"
        f"suggested_state: exploring\n"
        f"score: {t.score:.2f}\n"
        f"reason: {t.reason}\n"
        f"theme_match: {t.theme_match or '-'}\n"
        f"mentions: {t.mentions}\n"
        f"first_seen: {t.first_seen}\n"
        f"last_seen: {t.last_seen}\n"
        f"sources: {t.sources}\n"
        "---\n"
        "\n"
        f"# Proposed thread: {t.slug}\n"
        "\n"
        f"_Auto-detected latent thread on {today}. Reason: {t.reason}._\n"
        "\n"
        f"Detected in {t.mentions} sections spanning {t.first_seen} → "
        f"{t.last_seen}, sourced from {t.sources}.\n"
        "\n"
        f"Triage: (a) create ~/.mikai/brain/threads/{t.slug}.md, "
        "(b) merge into an existing thread, or (c) reject as noise.\n"
    )


def run(
    *,
    dry_run: bool = False,
    limit: int = DEFAULT_LIMIT,
    mentions_floor: int = MENTIONS_FLOOR,
    verbose: bool = True,
) -> list[LatentThread]:
    um = user_model_mod.load()
    if verbose and um is None:
        print("latent-threads: no USER_MODEL.md yet — running frequency-only")
    elif verbose:
        print(
            f"latent-threads: using UserModel "
            f"({len(um.current)} current items, {len(um.durable)} durable)"
        )

    candidates = select_candidates(
        limit=limit, mentions_floor=mentions_floor, um=um,
    )
    if verbose:
        mode = "would propose" if dry_run else "proposing"
        print(f"latent-threads: {len(candidates)} thread(s) {mode}")
        for c in candidates:
            print(f"  {c.slug:<28} score={c.score:5.2f}  {c.reason}")
    if dry_run or not candidates:
        return candidates

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    for c in candidates:
        (INBOX_DIR / f"proposed-thread-{c.slug}.md").write_text(
            _proposal_text(c)
        )
    if verbose:
        print(f"latent-threads: wrote {len(candidates)} proposal(s) to {INBOX_DIR}")
    return candidates


def _cli() -> int:
    ap = argparse.ArgumentParser(
        prog="mikai_brain.latent_threads",
        description=("Surface latent threads from the wiki ontology using "
                     "the compiled UserModel as the ranker (not raw counts)."),
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--mentions-floor", type=int, default=MENTIONS_FLOOR)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    run(dry_run=args.dry_run, limit=args.limit,
        mentions_floor=args.mentions_floor, verbose=not args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

"""Inbox processor.

Reads every file in ~/.mikai/brain/inbox/, classifies it into one of three
epistemic types, does the right write-back, then moves the file to
inbox/processed/ with a date prefix.

Epistemic types (SPEC §7):
- fragment:              a one-line note / half-thought / stray idea
- structured_ideation:   a deliberate exploration or plan draft
- processed_reflection:  a decision or resolution — the highest-signal shape

Classification is deterministic first (length, structure, decision-language,
date presence). Only ambiguous items go to the LLM (interactive tier via
mikai_llm — one call, budget tight).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from . import INBOX_DIR, INBOX_PROCESSED, THREADS_DIR, DECISIONS_LOG, ENTITIES_DIR, ledger
from . import threads as thread_mod

Epistemic = Literal["fragment", "structured_ideation", "processed_reflection"]

DECISION_LANG = re.compile(
    r"\b(?:decided|chose|choosing|will|shipping|going with|committed|resolved|"
    r"agreed|settled on|final)\b",
    re.IGNORECASE,
)
STRUCTURE_MARKERS = ("\n#", "\n- ", "\n* ", "\n1.", "\n2.")


# ── Classification ──────────────────────────────────────────────────────


@dataclass
class Classification:
    kind: Epistemic
    confidence: float               # 0..1
    matched_thread: str = ""        # slug, if any
    rationale: str = ""


def _shape(text: str) -> tuple[int, int, bool, bool]:
    """Coarse shape: (chars, newlines, has_structure, has_decision_language)."""
    return (
        len(text),
        text.count("\n"),
        any(m in text for m in STRUCTURE_MARKERS),
        bool(DECISION_LANG.search(text)),
    )


def _match_thread(text: str) -> str:
    """Simple: pick the thread with the most shared 5+ char tokens.
    Returns slug or ''.  Not a semantic match — just a hint."""
    tokens = {w.lower() for w in re.findall(r"[A-Za-z]{5,}", text)}
    if not tokens:
        return ""
    best_slug = ""
    best_score = 0
    for t in thread_mod.load_all():
        body_tokens = {w.lower() for w in re.findall(r"[A-Za-z]{5,}", t.path.read_text())}
        if not body_tokens:
            continue
        score = len(tokens & body_tokens)
        if score > best_score:
            best_score = score
            best_slug = t.slug
    if best_score < 3:
        return ""
    return best_slug


def classify_heuristic(text: str) -> Classification | None:
    """Deterministic pass. Returns None if the shape is ambiguous."""
    n_chars, n_newlines, has_structure, has_decision = _shape(text)

    # Very short → fragment
    if n_chars < 200 and n_newlines < 3:
        return Classification(
            kind="fragment",
            confidence=0.9,
            matched_thread=_match_thread(text),
            rationale="short single-thought shape",
        )

    # Contains decision language → processed_reflection
    if has_decision and n_chars > 100:
        return Classification(
            kind="processed_reflection",
            confidence=0.85,
            matched_thread=_match_thread(text),
            rationale="decision language present",
        )

    # Structured (headings / lists) and moderately long → ideation
    if has_structure and n_chars > 400:
        return Classification(
            kind="structured_ideation",
            confidence=0.75,
            matched_thread=_match_thread(text),
            rationale="structured markup + length",
        )

    return None  # ambiguous — LLM tie-break


_LLM_PROMPT = """You are MIKAI's inbox triage. Classify this piece of text into
exactly one epistemic type:

- fragment:              a stray thought, one-liner, or half-formed note
- structured_ideation:   a deliberate exploration or plan draft (multiple ideas, structure)
- processed_reflection:  a resolution or decision — synthesis has already happened

Text:
---
{text}
---

Return strict JSON:
{{"kind": "<one of the three>", "confidence": <0..1>, "rationale": "<one short line>"}}"""


def classify_llm(text: str) -> Classification:
    from infra import mikai_llm
    raw = mikai_llm.chat(_LLM_PROMPT.format(text=text[:4000]), tier="interactive", json_mode=True)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: treat as fragment with low confidence rather than crashing
        return Classification(
            kind="fragment", confidence=0.3, rationale="LLM parse failed — defaulted to fragment"
        )
    kind = obj.get("kind", "fragment")
    if kind not in ("fragment", "structured_ideation", "processed_reflection"):
        # An off-schema kind would fall through apply() with no write-back
        # while the item still gets archived — silent drop. Default down.
        kind = "fragment"
    try:
        confidence = float(obj.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    return Classification(
        kind=kind,
        confidence=confidence,
        matched_thread=_match_thread(text),
        rationale=obj.get("rationale", ""),
    )


# ── Write-back per type ────────────────────────────────────────────────


def _slugify(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9-]+", "-", s.strip().lower())
    return re.sub(r"-+", "-", s).strip("-")[:60] or "note"


def apply(text: str, source_name: str, cls: Classification) -> str:
    """Do the write-back for this classified inbox item. Returns a short
    human-readable summary of what happened."""
    today = date.today().isoformat()

    if cls.kind == "fragment":
        if cls.matched_thread:
            t = next((x for x in thread_mod.load_all() if x.slug == cls.matched_thread), None)
            if t is not None:
                thread_mod.append_log_line(t, f"[inbox:{source_name}] {text.strip()[:240]}")
                return f"→ appended fragment to thread {t.slug}"
        # Otherwise: park in BRAIN.md scratch section (create if missing)
        from . import BRAIN_MD
        BRAIN_MD.parent.mkdir(parents=True, exist_ok=True)
        header = "\n\n## Scratch (auto-parked fragments)\n"
        existing = BRAIN_MD.read_text() if BRAIN_MD.exists() else ""
        if "## Scratch" not in existing:
            existing = existing.rstrip() + header
        existing = existing.rstrip() + f"\n- {today} [{source_name}] {text.strip()[:240]}\n"
        BRAIN_MD.write_text(existing)
        return "→ parked fragment in BRAIN.md scratch"

    if cls.kind == "structured_ideation":
        # New thread in `exploring`
        slug = cls.matched_thread or f"{today}-{_slugify(text.splitlines()[0][:80])}"
        path = THREADS_DIR / f"{slug}.md"
        if path.exists():
            # Extend the existing thread's log
            t = thread_mod.parse_thread(path)
            thread_mod.append_log_line(t, f"[inbox:{source_name}] ideation appended below")
            path.write_text(path.read_text().rstrip() + f"\n\n### From inbox: {source_name}\n\n{text.strip()}\n")
            return f"→ extended thread {slug} with ideation"
        # Fresh thread
        title = text.splitlines()[0].strip("# ").strip()[:80] or slug
        frontmatter = (
            f"---\nslug: {slug}\ntitle: {title}\nstate: exploring\n"
            f"state_since: {today}\nlast_activity: {today}\n"
            f"next_step: \"(from inbox — needs a next step)\"\n"
            f"entities: []\ndepartment: \n---\n\n"
            f"## Log\n- {today} [exploring] Created from inbox item `{source_name}`.\n\n"
            f"## Content\n\n{text.strip()}\n"
        )
        path.write_text(frontmatter)
        return f"→ created new exploring thread {slug}"

    if cls.kind == "processed_reflection":
        # Two writes: decision log entry + thread update if matched
        d_num = _next_decision_num()
        _append_decision(
            num=d_num,
            date_iso=today,
            summary=text.strip().splitlines()[0][:120],
            body=text.strip(),
            source=source_name,
        )
        if cls.matched_thread:
            t = next((x for x in thread_mod.load_all() if x.slug == cls.matched_thread), None)
            if t is not None:
                thread_mod.set_state(t, "decided", f"decision recorded as D-op-{d_num:03d}")
                return f"→ D-op-{d_num:03d} logged; thread {t.slug} → decided"
        return f"→ D-op-{d_num:03d} logged (unmatched to a thread)"

    return "→ (no write-back — unknown kind)"


def _next_decision_num() -> int:
    if not DECISIONS_LOG.exists():
        return 1
    nums = [int(m.group(1)) for m in re.finditer(r"D-op-(\d+)", DECISIONS_LOG.read_text())]
    return (max(nums) if nums else 0) + 1


def _append_decision(num: int, date_iso: str, summary: str, body: str, source: str) -> None:
    DECISIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = (
        f"\n## D-op-{num:03d} · {date_iso} · {summary}\n\n"
        f"**Source:** inbox item `{source}`\n\n"
        f"{body}\n"
    )
    with DECISIONS_LOG.open("a") as f:
        f.write(entry)


# ── Entity proposals (from hydrator) ────────────────────────────────────


def _entity_proposal_meta(text: str) -> dict[str, str] | None:
    """Return frontmatter dict if this is a `proposal_kind: entity` item."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta if meta.get("proposal_kind") == "entity" else None


def _handle_entity_proposal(item: Path, meta: dict[str, str],
                            auto_accept: set[str], verbose: bool) -> str:
    """Entity proposals are NOT fragments/ideation/reflections. Default:
    surface for Brian's manual review and leave in inbox — never auto-create
    entity files. Only an explicit --auto-accept-entity <slug> creates the
    stub and archives the proposal."""
    slug = meta.get("slug", "")
    if slug not in auto_accept:
        if verbose:
            print(f"  {item.name}  →  entity proposal '{slug}' "
                  f"({meta.get('type', '?')}, {meta.get('mentions', '?')} mentions) "
                  "— review manually or rerun with --auto-accept-entity")
        return "held"
    entity_path = ENTITIES_DIR / f"{slug}.md"
    if not entity_path.exists():
        ENTITIES_DIR.mkdir(parents=True, exist_ok=True)
        entity_path.write_text(
            f"---\nname: {slug}\ntype: {meta.get('type', 'thing')}\n"
            f"status: active\nowner_thread: \n---\n\n"
            f"_(Accepted from hydrator proposal on {date.today().isoformat()}. "
            "Backfill body facts from Brian's actual data only.)_\n"
        )
    shutil.move(str(item), str(INBOX_PROCESSED / f"{date.today().isoformat()}__{item.name}"))
    if verbose:
        print(f"  {item.name}  →  entity '{slug}' accepted → {entity_path}")
    return "accepted"


# ── Main entry ───────────────────────────────────────────────────────────


def run(*, use_llm: bool = True, verbose: bool = True,
        auto_accept_entities: set[str] | None = None) -> int:
    if not INBOX_DIR.exists():
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_PROCESSED.mkdir(parents=True, exist_ok=True)
    items = [p for p in sorted(INBOX_DIR.iterdir())
             if p.is_file() and not p.name.startswith(".") and p.parent == INBOX_DIR]
    if not items:
        if verbose:
            print("inbox empty — nothing to triage")
        return 0
    n_done = 0
    for item in items:
        try:
            text = item.read_text(errors="replace")
        except Exception as exc:
            print(f"  ! skip {item.name}: {exc}")
            continue
        meta = _entity_proposal_meta(text)
        if meta is not None:
            if _handle_entity_proposal(item, meta, auto_accept_entities or set(), verbose) == "accepted":
                n_done += 1
            continue
        cls = classify_heuristic(text)
        if cls is None:
            if use_llm:
                cls = classify_llm(text)
            else:
                cls = Classification(kind="fragment", confidence=0.4, rationale="ambiguous — llm disabled")
        summary = apply(text, source_name=item.name, cls=cls)
        # Move to processed with date prefix
        dest = INBOX_PROCESSED / f"{date.today().isoformat()}__{item.name}"
        shutil.move(str(item), str(dest))
        n_done += 1
        if verbose:
            print(f"  {item.name}  →  {cls.kind} ({cls.confidence:.2f})  {summary}")

    ledger.run(
        mode="triage",
        did=f"Triaged {n_done} inbox item(s).",
        extra={"items": [p.name for p in items]},
    )
    return n_done


def _cli() -> int:
    ap = argparse.ArgumentParser(prog="mikai_brain.triage", description="Process ~/.mikai/brain/inbox/")
    ap.add_argument("--no-llm", action="store_true", help="Skip LLM tie-break; treat ambiguous items as fragments")
    ap.add_argument("--auto-accept-entity", action="append", default=[], metavar="SLUG",
                    help="Accept an entity proposal by slug: create the entity stub and archive the proposal (repeatable)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    run(use_llm=not args.no_llm, verbose=not args.quiet,
        auto_accept_entities=set(args.auto_accept_entity))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

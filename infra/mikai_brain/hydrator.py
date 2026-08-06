"""L3 → L4 hydrator.

Reads the wiki ontology (`~/.mikai/wiki/wiki-ontology.md`, rebuilt by
`dream_weekly`), cross-references `~/.mikai/brain/entities/`, and drops
`proposed-entity-<slug>.md` items into `~/.mikai/brain/inbox/` for triage.

This closes the bridge between corpus-extracted entities (L3) and the
curated brain entity files (L4). Entities are never created directly —
proposals go through the inbox so Brian's judgment stays in the loop
(the workflow that would have caught the Bethany hallucination).

Filters, in order:
- already present in brain/entities/ (skip)
- listed in the ontology's "Possibly inferred" section (skip — flagged
  names need Brian's eye anyway, don't auto-propose)
- mentions below threshold (skip — single-source noise; --min-mentions)
- type outside person/org/thing/place (skip — ENTITY_MODEL doctrine:
  abstract concepts are not entities)
- proposal already sitting in inbox/ or inbox/processed/ (skip — idempotent)

Read-only on the wiki. Never writes to entities/. Backs up inbox/ before
writing proposals.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from . import BRAIN_ROOT, ENTITIES_DIR, INBOX_DIR, INBOX_PROCESSED

# Bound at import (same pattern as the package constants): tests repoint
# HOME / set MIKAI_WIKI_ONTOLOGY and reload.
ONTOLOGY_PATH = Path(
    os.environ.get(
        "MIKAI_WIKI_ONTOLOGY",
        str(Path.home() / ".mikai" / "wiki" / "wiki-ontology.md"),
    )
)

ALLOWED_TYPES = {"person", "org", "thing", "place"}
DEFAULT_MIN_MENTIONS = 5
DEFAULT_LIMIT = 30

_FLAG_SECTION = re.compile(r"^##\s*.*Possibly inferred", re.IGNORECASE)
_FLAGGED_NAME = re.compile(r"`([^`]+)`")


@dataclass
class OntologyEntity:
    slug: str
    type: str
    mentions: int
    first_seen: str
    last_seen: str
    sources: str
    flagged: bool = False


# ── Parsing ──────────────────────────────────────────────────────────────


def parse_ontology(path: Path = ONTOLOGY_PATH) -> list[OntologyEntity]:
    """Parse the ontology markdown table + the "Possibly inferred" section."""
    text = path.read_text()

    # Collect flagged names from the "Possibly inferred" section.
    flagged: set[str] = set()
    in_flag_section = False
    for line in text.splitlines():
        if _FLAG_SECTION.match(line):
            in_flag_section = True
            continue
        if in_flag_section:
            if line.startswith("## "):
                in_flag_section = False
                continue
            flagged.update(_FLAGGED_NAME.findall(line))

    entities: list[OntologyEntity] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            continue
        name, etype, mentions_s, first_seen, last_seen, sources = cells
        if name in ("entity", "---") or set(name) <= {"-"}:
            continue  # header / separator rows
        # Rows for flagged entities carry a trailing ⚠ marker — strip it.
        row_flagged = "⚠" in name
        slug = name.replace("⚠", "").strip()
        try:
            mentions = int(mentions_s)
        except ValueError:
            continue
        entities.append(
            OntologyEntity(
                slug=slug,
                type=etype,
                mentions=mentions,
                first_seen=first_seen,
                last_seen=last_seen,
                sources=sources,
                flagged=row_flagged or slug in flagged,
            )
        )
    return entities


def existing_entity_slugs() -> set[str]:
    """Slugs already curated in brain/entities/. Ignores `.hallucinated-*`
    and `.bak-*` variants — those are not live entities."""
    if not ENTITIES_DIR.exists():
        return set()
    slugs = set()
    for p in ENTITIES_DIR.iterdir():
        if not p.is_file() or not p.name.endswith(".md"):
            continue  # skips foo.md.hallucinated-*, foo.md.bak-*
        slugs.add(p.name[: -len(".md")])
    return slugs


def _already_proposed(slug: str) -> bool:
    """A proposal for this slug already sits in inbox/ or was processed."""
    name = f"proposed-entity-{slug}.md"
    if (INBOX_DIR / name).exists():
        return True
    if INBOX_PROCESSED.exists():
        # triage archives with a date prefix: YYYY-MM-DD__<name>
        return any(p.name.endswith(f"__{name}") or p.name == name
                   for p in INBOX_PROCESSED.iterdir())
    return False


# ── Proposal writing ─────────────────────────────────────────────────────


def _proposal_text(e: OntologyEntity) -> str:
    today = date.today().isoformat()
    return (
        "---\n"
        "proposal_kind: entity\n"
        f"slug: {e.slug}\n"
        f"type: {e.type}\n"
        f"mentions: {e.mentions}\n"
        f"first_seen: {e.first_seen}\n"
        f"last_seen: {e.last_seen}\n"
        f"sources: {e.sources}\n"
        "---\n"
        "\n"
        f"# Proposed entity: {e.slug}\n"
        "\n"
        f"_Auto-hydrated from wiki-ontology.md on {today}. Triage this file\n"
        f"to either (a) create ~/.mikai/brain/entities/{e.slug}.md with backfilled\n"
        "body facts, (b) merge into an existing entity (add alias), or (c)\n"
        "reject as noise (delete this file)._\n"
        "\n"
        f"Detected in {e.mentions} sections spanning {e.first_seen} → {e.last_seen}, sourced\n"
        f"from {e.sources}.\n"
    )


def _backup_inbox() -> Path | None:
    """Copy inbox/ aside before writing, in case something goes wrong."""
    if not INBOX_DIR.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BRAIN_ROOT / "state" / "inbox-backups" / ts
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(INBOX_DIR, dest)
    return dest


def select_candidates(
    *,
    min_mentions: int = DEFAULT_MIN_MENTIONS,
    limit: int = DEFAULT_LIMIT,
    ontology_path: Path = ONTOLOGY_PATH,
) -> list[OntologyEntity]:
    """Apply all filters; return proposal candidates, highest-mention first."""
    existing = existing_entity_slugs()
    out: list[OntologyEntity] = []
    for e in sorted(parse_ontology(ontology_path), key=lambda x: -x.mentions):
        if e.slug in existing:
            continue
        if e.flagged:
            continue
        if e.mentions < min_mentions:
            continue
        if e.type not in ALLOWED_TYPES:
            continue
        if _already_proposed(e.slug):
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


def run(
    *,
    dry_run: bool = False,
    min_mentions: int = DEFAULT_MIN_MENTIONS,
    limit: int = DEFAULT_LIMIT,
    verbose: bool = True,
) -> list[OntologyEntity]:
    candidates = select_candidates(min_mentions=min_mentions, limit=limit)
    if verbose:
        mode = "would propose" if dry_run else "proposing"
        print(f"hydrator: {len(candidates)} entities {mode} "
              f"(min_mentions={min_mentions}, limit={limit})")
        for e in candidates:
            print(f"  {e.slug:<28} {e.type:<7} {e.mentions:>4} mentions  "
                  f"{e.first_seen} → {e.last_seen}")
    if dry_run or not candidates:
        return candidates

    backup = _backup_inbox()
    if verbose and backup is not None:
        print(f"hydrator: inbox backed up to {backup}")
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    for e in candidates:
        (INBOX_DIR / f"proposed-entity-{e.slug}.md").write_text(_proposal_text(e))
    if verbose:
        print(f"hydrator: wrote {len(candidates)} proposal(s) to {INBOX_DIR}")
    return candidates


def _cli() -> int:
    ap = argparse.ArgumentParser(
        prog="mikai_brain.hydrator",
        description="Propose brain entities from the wiki ontology (via inbox).",
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be proposed without writing")
    ap.add_argument("--min-mentions", type=int, default=DEFAULT_MIN_MENTIONS,
                    help=f"Minimum mention count (default {DEFAULT_MIN_MENTIONS})")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help=f"Max proposals per run (default {DEFAULT_LIMIT})")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    run(dry_run=args.dry_run, min_mentions=args.min_mentions,
        limit=args.limit, verbose=not args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

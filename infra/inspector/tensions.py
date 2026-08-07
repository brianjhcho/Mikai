"""Wiki tensions parser.

Scans ``~/.mikai/wiki/wiki.md`` for every ``## Tensions`` (or
``## Tensions & Open Questions``) section, extracts the bullets under
each, and writes a normalised list to
``~/.mikai/brain/state/tensions.json`` — the Inspector's read-model.

Bullet shapes supported (the wiki uses all three across time):

  * ``- **Title:** body``            (canonical narrative form)
  * ``- **Title** — body``           (some claude-thread exports)
  * ``- Plain sentence bullet.``     (early thread exports without titles)

Template placeholder text ("List unresolved questions, tradeoffs …")
is skipped — the LLM thread-formatting prompt template lives inline
inside imported claude threads and is not itself a tension.

Provenance is the nearest ``### `` episode header above the bullet, or
the nearest ``## `` section header when no episode header exists. When
the provenance line carries an ISO timestamp we hoist it into
``first_seen_date`` (yyyy-mm-dd). Otherwise the field is None.

State is preserved by merging with the console prototype's
``~/.mikai/console/tensions.json`` on every regen — that file carries
``status`` / ``notes`` / ``releasedAt`` per tension slug, and hand
input there must survive a rebuild.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import CONSOLE_TENSIONS_JSON, TENSIONS_JSON, WIKI_MD

TENSIONS_HEADER_RE = re.compile(r"^## Tensions( & Open Questions)?\s*$")
NEXT_SECTION_RE = re.compile(r"^## ")
BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
BOLD_TITLE_COLON_RE = re.compile(r"^\*\*([^*]+?):\*\*\s*(.*)$")
BOLD_TITLE_DASH_RE = re.compile(r"^\*\*([^*]+?)\*\*\s*[—\-–]\s*(.*)$")
BOLD_TITLE_BARE_RE = re.compile(r"^\*\*([^*]+?)\*\*\s*(.*)$")
EPISODE_HEADER_RE = re.compile(r"^### ")
SECTION_HEADER_RE = re.compile(r"^## (.+?)\s*$")
ISO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

TEMPLATE_PLACEHOLDER_PREFIX = "list unresolved questions"

MAX_TITLE_CHARS = 90


def _slugify(title: str) -> str:
    """Match the console prototype's slug convention: lowercase, hyphen,
    strip punctuation, collapse runs."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:80] or "untitled-tension"


def _extract_title_body(inner: str) -> tuple[str, str]:
    """Given the bullet body (post ``- ``), return (title, body).

    Handles the three bullet shapes; falls back to first-sentence-as-
    title when there is no bold prefix.
    """
    m = BOLD_TITLE_COLON_RE.match(inner)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = BOLD_TITLE_DASH_RE.match(inner)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = BOLD_TITLE_BARE_RE.match(inner)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # Plain bullet — split into "title" (first fragment) + "body".
    sentence = re.split(r"(?<=[.?!])\s+", inner, maxsplit=1)
    title = sentence[0].strip().rstrip(".?!")
    if len(title) > MAX_TITLE_CHARS:
        title = title[:MAX_TITLE_CHARS].rstrip() + "…"
    body = sentence[1].strip() if len(sentence) > 1 else ""
    return title, body


def _split_bullets(block_lines: list[str]) -> list[str]:
    """Collapse continuation lines into a single bullet body."""
    bullets: list[str] = []
    current: list[str] = []
    for raw in block_lines:
        m = BULLET_RE.match(raw)
        if m:
            if current:
                bullets.append(" ".join(current).strip())
                current = []
            current.append(m.group(1).strip())
        elif current:
            stripped = raw.strip()
            if stripped:
                # continuation of previous bullet
                current.append(stripped)
            else:
                # blank line ends the bullet block
                bullets.append(" ".join(current).strip())
                current = []
    if current:
        bullets.append(" ".join(current).strip())
    return bullets


def parse_wiki_tensions(wiki_path: Path | None = None) -> list[dict]:
    """Parse tensions from wiki.md. Returns list of dicts:

        {title, body, slug, provenance, first_seen_date, section}

    ``section`` is the header text ("Tensions" or "Tensions & Open
    Questions"); ``provenance`` is the nearest ``### `` header above
    the section, or a coarse fallback.
    """
    wiki_path = wiki_path or WIKI_MD
    if not wiki_path.exists():
        return []

    tensions: list[dict] = []
    seen_slugs: set[str] = set()

    last_episode_header = None
    last_section_header = "wiki narrative top"

    with wiki_path.open("r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip("\n")
        if EPISODE_HEADER_RE.match(line):
            last_episode_header = line[4:].strip()
        elif TENSIONS_HEADER_RE.match(line):
            section_name = line[3:].strip()  # after "## "
            # collect lines until next "## " or EOF
            block: list[str] = []
            j = i + 1
            while j < n:
                nxt = lines[j].rstrip("\n")
                if NEXT_SECTION_RE.match(nxt):
                    break
                block.append(nxt)
                j += 1
            provenance = last_episode_header or last_section_header
            first_seen = _extract_iso_date(provenance) if provenance else None
            for bullet_body in _split_bullets(block):
                if not bullet_body:
                    continue
                if bullet_body.lower().startswith(TEMPLATE_PLACEHOLDER_PREFIX):
                    continue
                title, body = _extract_title_body(bullet_body)
                if not title:
                    continue
                slug = _slugify(title)
                if slug in seen_slugs:
                    # De-dupe by title across sections; keep first.
                    continue
                seen_slugs.add(slug)
                tensions.append({
                    "slug": slug,
                    "title": title,
                    "body": body,
                    "provenance": provenance,
                    "first_seen_date": first_seen,
                    "section": section_name,
                })
            i = j
            continue
        elif SECTION_HEADER_RE.match(line):
            last_section_header = line[3:].strip()
        i += 1

    return tensions


def _extract_iso_date(text: str) -> str | None:
    m = ISO_DATE_RE.search(text)
    return m.group(1) if m else None


def load_console_state(path: Path | None = None) -> dict:
    """Read the console prototype's per-tension state
    ({status, notes, releasedAt}) keyed by slug. Empty dict when
    missing / unparseable."""
    path = path or CONSOLE_TENSIONS_JSON
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def merge_state(tensions: list[dict], console_state: dict) -> list[dict]:
    """Overlay ``status`` / ``notes`` / ``releasedAt`` from the console
    prototype onto freshly parsed tensions, matching by slug."""
    merged: list[dict] = []
    for t in tensions:
        state = console_state.get(t["slug"], {})
        merged.append({
            **t,
            "status": state.get("status", "holding"),
            "notes": state.get("notes", []),
            "released_at": state.get("releasedAt"),
            "release_note": state.get("releaseNote"),
        })
    return merged


def build(wiki_path: Path | None = None,
          console_state_path: Path | None = None) -> list[dict]:
    parsed = parse_wiki_tensions(wiki_path)
    state = load_console_state(console_state_path)
    return merge_state(parsed, state)


def write_json(tensions: list[dict],
               out_path: Path | None = None,
               *, backup: bool = True) -> Path:
    out_path = out_path or TENSIONS_JSON
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if backup and out_path.exists():
        bak = out_path.with_suffix(
            out_path.suffix + ".bak-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
        shutil.copy2(out_path, bak)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(tensions),
        "tensions": tensions,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2)
                        + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="inspector.tensions",
                                 description="Parse wiki.md tensions")
    ap.add_argument("--dry-run", action="store_true",
                    help="print summary, write nothing")
    ap.add_argument("--wiki", type=Path, default=None,
                    help="override wiki.md path")
    ap.add_argument("--out", type=Path, default=None,
                    help="override output tensions.json path")
    args = ap.parse_args(argv)

    tensions = build(wiki_path=args.wiki)
    print(f"tensions: parsed {len(tensions)}")
    for t in tensions[:10]:
        print(f"  · [{t['status']:<8}] {t['title'][:70]}")
    if len(tensions) > 10:
        print(f"  … +{len(tensions) - 10} more")
    if args.dry_run:
        print("dry-run: nothing written")
        return 0
    path = write_json(tensions, out_path=args.out)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

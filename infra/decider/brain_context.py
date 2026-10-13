"""File-based context for the Surface Engine.

Replaces the Graphiti/Neo4j context source. Everything here is read-only:

- Thread files: ``$MIKAI_BRAIN_ROOT/threads/*.md`` (default ``~/.mikai/brain``),
  YAML-ish frontmatter with slug, title, state, state_since, last_activity,
  next_step, entities, department.
- Priority docs: BRAIN.md / GOALS.md / USER_MODEL.md from the brain root.
- Wiki pages: ``$MIKAI_WIKI_ROOT/wiki/{concepts,entities,wisdom}/<slug>.md``
  (default ``~/.mikai/wiki-mikai-parallel-test``), looked up only for the
  entities a thread names, so the prompt stays small.

Python 3.9 compatible, stdlib only (launchd runs /usr/bin/python3).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

WIKI_KINDS = ("concepts", "entities", "wisdom")
BRAIN_DOCS = ("BRAIN.md", "GOALS.md", "USER_MODEL.md")
CLOSED_STATES = {"completed", "done", "abandoned", "resolved"}

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]*$")


def brain_root() -> Path:
    return Path(os.environ.get("MIKAI_BRAIN_ROOT", str(Path.home() / ".mikai" / "brain"))).expanduser()


def wiki_root() -> Path:
    return Path(os.environ.get(
        "MIKAI_WIKI_ROOT", str(Path.home() / ".mikai" / "wiki-mikai-parallel-test"),
    )).expanduser()


@dataclass
class Thread:
    slug: str
    title: str
    state: str
    state_since: str = ""
    last_activity: str = ""
    next_step: str = ""
    entities: list = field(default_factory=list)
    department: str = ""
    body: str = ""
    path: str = ""

    def days_quiet(self, today: date | None = None) -> int | None:
        d = _parse_date(self.last_activity)
        if d is None:
            return None
        return ((today or datetime.now(timezone.utc).date()) - d).days


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def _unquote(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse the leading ``---`` block. Supports ``key: value``, inline
    ``[a, b]`` lists and block ``- item`` lists. Returns (fields, body)."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    fields: dict = {}
    current_list_key: str | None = None
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
        stripped = line.strip()
        if current_list_key and stripped.startswith("- "):
            fields[current_list_key].append(_unquote(stripped[2:]))
            continue
        current_list_key = None
        if ":" not in line or line.startswith((" ", "\t")):
            continue
        key, _, raw = line.partition(":")
        key = key.strip()
        raw = raw.strip()
        if raw == "":
            fields[key] = []
            current_list_key = key
        elif raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            fields[key] = [_unquote(x) for x in inner.split(",") if x.strip()] if inner else []
        else:
            fields[key] = _unquote(raw)
    if end is None:
        return {}, text
    return fields, "\n".join(lines[end + 1:]).strip()


def load_threads(root: Path | None = None) -> list[Thread]:
    tdir = (root or brain_root()) / "threads"
    if not tdir.is_dir():
        return []
    threads = []
    for path in sorted(tdir.glob("*.md")):
        try:
            fields, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if not fields:
            continue
        entities = fields.get("entities") or []
        if isinstance(entities, str):
            entities = [entities] if entities else []
        threads.append(Thread(
            slug=str(fields.get("slug") or path.stem),
            title=str(fields.get("title") or path.stem),
            state=str(fields.get("state") or "unknown").lower(),
            state_since=str(fields.get("state_since") or ""),
            last_activity=str(fields.get("last_activity") or ""),
            next_step=str(fields.get("next_step") or ""),
            entities=[str(e) for e in entities],
            department=str(fields.get("department") or ""),
            body=body,
            path=str(path),
        ))
    return threads


def rank_threads(threads: list[Thread], today: date | None = None) -> list[Thread]:
    """Open threads first, quietest first. Closed threads sort last."""
    def key(t: Thread):
        quiet = t.days_quiet(today)
        return (t.state in CLOSED_STATES, -(quiet if quiet is not None else -1))
    return sorted(threads, key=key)


def load_brain_docs(root: Path | None = None, max_chars: int = 3000) -> dict:
    base = root or brain_root()
    docs = {}
    for name in BRAIN_DOCS:
        p = base / name
        if p.is_file():
            try:
                docs[name] = p.read_text(encoding="utf-8")[:max_chars]
            except OSError:
                pass
    return docs


def find_wiki_page(slug: str, root: Path | None = None) -> Path | None:
    """Resolve ``slug`` or ``kind/slug`` to a wiki page on disk, else None."""
    s = (slug or "").strip().strip("[]").strip()
    if not s:
        return None
    base = (root or wiki_root()) / "wiki"
    if "/" in s:
        kind, _, name = s.partition("/")
        if kind in WIKI_KINDS and _SLUG_RE.match(name):
            p = base / kind / f"{name}.md"
            return p if p.is_file() else None
        return None
    if not _SLUG_RE.match(s):
        return None
    for kind in WIKI_KINDS:
        p = base / kind / f"{s}.md"
        if p.is_file():
            return p
    return None


def load_wiki_snippets(threads: list[Thread], root: Path | None = None,
                       per_thread: int = 2, chars: int = 300) -> list[dict]:
    """For each thread, include up to ``per_thread`` wiki pages named by its
    entities (falling back to the thread slug). Retire stubs are skipped."""
    out: list[dict] = []
    seen: set = set()
    for t in threads:
        found = 0
        for candidate in list(t.entities) + [t.slug]:
            if found >= per_thread:
                break
            page = find_wiki_page(candidate, root)
            if page is None or str(page) in seen:
                continue
            try:
                fields, body = parse_frontmatter(page.read_text(encoding="utf-8"))
            except OSError:
                continue
            if fields.get("retired_to"):
                continue
            seen.add(str(page))
            found += 1
            out.append({
                "slug": f"{page.parent.name}/{page.stem}",
                "thread": t.slug,
                "title": str(fields.get("title") or page.stem),
                "snippet": " ".join(body.split())[:chars],
            })
    return out


def citation_exists(cite: str, brain: Path | None = None, wiki: Path | None = None) -> bool:
    """True when ``cite`` names a thread file or a wiki page that exists on disk."""
    c = (cite or "").strip().strip("[]").strip()
    if not c:
        return False
    if c.startswith("threads/"):
        c = c[len("threads/"):]
    if _SLUG_RE.match(c) and ((brain or brain_root()) / "threads" / f"{c}.md").is_file():
        return True
    return find_wiki_page(c, wiki) is not None

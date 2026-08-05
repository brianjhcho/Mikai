"""BrainStore port + FileStore adapter.

Analog of the L3Backend port (ARCH-024) at brain scope. All retrieval
by any brain-scope caller goes through the port. Adapters live behind
the env switch MIKAI_BRAIN_BACKEND=files|mikai.

Today: FileStore is the only implementation. MikaiStore is a stub that
will forward to the MIKAI L3 MCP tools when the file store hits its
ceiling — probably 500+ threads/entities out. Phase 3 in SPEC.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from . import THREADS_DIR, ENTITIES_DIR, BRAIN_MD


# ── Port ─────────────────────────────────────────────────────────────────


@dataclass
class Passage:
    """One retrieved chunk — file identity + span + preview text."""

    source: str                     # relative path under brain/
    kind: str                       # "thread" | "entity" | "brain"
    snippet: str                    # ~500 char preview
    score: float = 0.0              # bigger = more relevant


@dataclass
class Facts:
    """Entity-shaped view."""

    name: str
    kind: str = ""
    status: str = ""
    body: str = ""
    owner_thread: str = ""


class BrainStore(Protocol):
    def recall(self, query: str, limit: int = 8) -> list[Passage]: ...
    def entity(self, name: str) -> Facts | None: ...
    def record(self, target_path: str, note: str) -> None: ...


# ── FileStore ────────────────────────────────────────────────────────────


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")


def _tokens(s: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(s)}


def _score(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    text_tokens = _tokens(text)
    if not text_tokens:
        return 0.0
    hits = len(query_tokens & text_tokens)
    if hits == 0:
        return 0.0
    # Small bonus for exact substring hits — cheap way to reward phrases.
    q_lower = " ".join(query_tokens)
    if q_lower in text.lower():
        hits += 2
    return hits / (len(query_tokens) ** 0.5)


def _preview(text: str, n: int = 500) -> str:
    text = text.strip().replace("\n\n", " ¶ ")
    return text[:n] + ("…" if len(text) > n else "")


class FileStore:
    """Regex + token-overlap retrieval over brain/ markdown files."""

    def recall(self, query: str, limit: int = 8) -> list[Passage]:
        q_tokens = _tokens(query)
        hits: list[Passage] = []

        # BRAIN.md always gets first pass at low weight — it's the
        # first-node summary and shouldn't dominate specific hits.
        if BRAIN_MD.exists():
            body = BRAIN_MD.read_text()
            s = _score(q_tokens, body)
            if s > 0:
                hits.append(Passage(
                    source=str(BRAIN_MD.relative_to(BRAIN_MD.parent.parent)),
                    kind="brain",
                    snippet=_preview(body),
                    score=s * 0.7,
                ))

        for path in sorted(THREADS_DIR.glob("*.md")):
            body = path.read_text()
            s = _score(q_tokens, body)
            if s > 0:
                hits.append(Passage(
                    source=str(path.relative_to(path.parent.parent)),
                    kind="thread",
                    snippet=_preview(body),
                    score=s,
                ))

        for path in sorted(ENTITIES_DIR.glob("*.md")):
            body = path.read_text()
            s = _score(q_tokens, body)
            if s > 0:
                hits.append(Passage(
                    source=str(path.relative_to(path.parent.parent)),
                    kind="entity",
                    snippet=_preview(body),
                    score=s * 0.9,
                ))

        hits.sort(key=lambda p: p.score, reverse=True)
        return hits[:limit]

    def entity(self, name: str) -> Facts | None:
        slug = name.strip().lower().replace(" ", "-")
        path = ENTITIES_DIR / f"{slug}.md"
        if not path.exists():
            return None
        return _parse_entity(path)

    def record(self, target_path: str, note: str) -> None:
        """Append `note` to the given brain/ path. Creates the file's parent
        dir if needed. Never overwrites existing content."""
        target = (BRAIN_MD.parent / target_path).resolve()
        # Safety: never write outside brain/
        brain_root = BRAIN_MD.parent.resolve()
        try:
            target.relative_to(brain_root)
        except ValueError as exc:
            raise ValueError(f"record() target outside brain/: {target}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a") as f:
            if target.exists() and target.stat().st_size > 0:
                f.write("\n")
            f.write(note.rstrip() + "\n")


# ── Entity parsing ──────────────────────────────────────────────────────


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _parse_entity(path: Path) -> Facts:
    raw = path.read_text()
    frontmatter: dict[str, str] = {}
    body = raw
    m = _FRONTMATTER_RE.match(raw)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                frontmatter[k.strip()] = v.strip()
        body = m.group(2)
    return Facts(
        name=frontmatter.get("name", path.stem),
        kind=frontmatter.get("type", ""),
        status=frontmatter.get("status", ""),
        body=body.strip(),
        owner_thread=frontmatter.get("owner_thread", ""),
    )


# ── MikaiStore stub (Phase 3) ────────────────────────────────────────────


class MikaiStore:
    """Placeholder — will forward to MIKAI L3 MCP tools.

    Not implemented yet. See docs/DECISIONS.md ARCH-024 for the L3Backend
    port shape this will proxy. Enabled by MIKAI_BRAIN_BACKEND=mikai.
    """

    def recall(self, query: str, limit: int = 8) -> list[Passage]:
        raise NotImplementedError("MikaiStore is a Phase-3 stub — set MIKAI_BRAIN_BACKEND=files")

    def entity(self, name: str) -> Facts | None:
        raise NotImplementedError("MikaiStore is a Phase-3 stub")

    def record(self, target_path: str, note: str) -> None:
        raise NotImplementedError("MikaiStore is a Phase-3 stub")


# ── Factory ──────────────────────────────────────────────────────────────


def make_store() -> BrainStore:
    backend = os.environ.get("MIKAI_BRAIN_BACKEND", "files").lower()
    if backend == "files":
        return FileStore()
    if backend == "mikai":
        return MikaiStore()
    raise ValueError(f"Unknown MIKAI_BRAIN_BACKEND: {backend!r}")

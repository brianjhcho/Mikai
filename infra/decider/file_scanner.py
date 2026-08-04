"""File-scanner ingestion — walks the user's document folders and writes
file metadata + text-shape content into MIKAI's L3 substrate via the port.

Design commitments:
- **Never moves a file.** Read-only walk. File organization is L5
  actuation and belongs to the tap-approve loop (OpenClaw bridge).
- **Metadata for everything, text for what's cheap to read.** PDF/DOCX
  extraction is best-effort via pdftotext / textutil (macOS system
  tools); when unavailable, metadata is still ingested.
- **Dedup by (path, size, mtime).** State kept in ~/.mikai/file-scanner-state.json.
  A file whose mtime hasn't changed is skipped on the next run.
- **Fail closed on protected paths.** ~/Library, ~/.git*, node_modules,
  .venv are hard-skipped even if inside a scan root.
- **Stdlib only.** No new dependencies in the decider path.

Selected via `python3 file_scanner.py [--roots ...] [--limit N] [--dry-run]`.
Runs against whichever L3 backend is selected — WikiAdapter appends
to wiki-episodes.log; Graphiti routes into the real graph.

Load-bearing insight: MIKAI's L3 doesn't need to *understand* every file.
It needs to know they exist, when they last changed, and what shape they
are. That's the substrate. L4 (Sumimasen) reasons over it later; L5
(OpenClaw file-ops) mutates it when the user approves.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


# ── Config ───────────────────────────────────────────────────────────────────

DEFAULT_ROOTS = [
    str(Path.home() / "Desktop"),
    str(Path.home() / "Downloads"),
    str(Path.home() / "Documents"),
]

# Anywhere these appear in a path segment, the walker skips the whole tree.
HARD_SKIP_SEGMENTS = {
    "Library",           # user Library — TCC + huge + noise
    ".git",              # git internals
    ".svn",
    ".hg",
    "node_modules",      # npm bloat
    ".venv",
    "venv",
    ".env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".DS_Store",
    ".Trash",
    ".cache",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".next",
    "target",            # Rust build
    ".terraform",
}

# Extensions we know are worth reading as text (best-effort).
TEXT_EXTENSIONS = {
    ".md", ".txt", ".rst", ".org",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".csv", ".tsv",
    ".log",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rb", ".go", ".rs",
    ".sh", ".bash", ".zsh",
    ".html", ".xml",
    ".sql",
    ".env.example",  # never real .env
}

# Extensions we try to text-extract via a system tool.
PDF_EXTENSIONS = {".pdf"}
DOC_EXTENSIONS = {".doc", ".docx", ".rtf"}

# File-size cap for text extraction (bytes). Metadata is still ingested
# above this; content extraction is skipped.
MAX_TEXT_BYTES = 500_000  # 500 KB — larger docs get metadata-only

STATE_PATH = Path.home() / ".mikai" / "file-scanner-state.json"


# ── Helpers ──────────────────────────────────────────────────────────────────


@dataclass
class FileFact:
    """The shape of a single file's episode payload."""

    abs_path: str
    name: str
    parent_dir: str
    size_bytes: int
    mtime_utc: datetime
    mimetype: str | None
    ext: str
    text_extracted: bool
    text_preview: str | None  # first N chars if extracted, else None
    text_bytes: int  # 0 when not extracted


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))
    except OSError as exc:
        print(f"WARN: file-scanner state save failed: {exc}", file=sys.stderr)


def _path_should_skip(p: Path) -> bool:
    if p.name.startswith("."):
        return True  # hidden files (macOS metadata, dotfiles)
    for seg in p.parts:
        if seg in HARD_SKIP_SEGMENTS:
            return True
    return False


def _extract_text(path: Path) -> tuple[bool, str | None, int]:
    """Best-effort text extraction. Returns (extracted, preview, bytes).
    Falls back to (False, None, 0) if no tool is available.
    """
    ext = path.suffix.lower()
    try:
        size = path.stat().st_size
    except OSError:
        return (False, None, 0)
    if size > MAX_TEXT_BYTES:
        return (False, None, 0)  # metadata-only for huge files

    # Direct-read text formats
    if ext in TEXT_EXTENSIONS:
        try:
            content = path.read_text(errors="replace")
            return (True, content[:2000], len(content))
        except OSError:
            return (False, None, 0)

    # PDF via `pdftotext` (poppler; not always installed)
    if ext in PDF_EXTENSIONS:
        try:
            proc = subprocess.run(
                ["pdftotext", "-layout", "-nopgbrk", "-q", str(path), "-"],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode == 0 and proc.stdout:
                return (True, proc.stdout[:2000], len(proc.stdout))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return (False, None, 0)

    # DOC / DOCX / RTF via `textutil` (macOS built-in)
    if ext in DOC_EXTENSIONS:
        try:
            proc = subprocess.run(
                ["textutil", "-convert", "txt", "-stdout", str(path)],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode == 0 and proc.stdout:
                return (True, proc.stdout[:2000], len(proc.stdout))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return (False, None, 0)

    return (False, None, 0)


def _fact_for(path: Path) -> FileFact | None:
    try:
        st = path.stat()
    except OSError:
        return None
    mtype, _ = mimetypes.guess_type(str(path))
    extracted, preview, tbytes = _extract_text(path)
    return FileFact(
        abs_path=str(path),
        name=path.name,
        parent_dir=str(path.parent),
        size_bytes=st.st_size,
        mtime_utc=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
        mimetype=mtype,
        ext=path.suffix.lower(),
        text_extracted=extracted,
        text_preview=preview,
        text_bytes=tbytes,
    )


def _episode_content(fact: FileFact) -> str:
    """Render a FileFact as an episode-shaped string. This is what lands
    in the graph / episode log — searchable prose describing the file.
    """
    lines = [
        f"File: {fact.name}",
        f"Path: {fact.abs_path}",
        f"Size: {fact.size_bytes:,} bytes",
        f"Modified: {fact.mtime_utc.isoformat(timespec='seconds')}",
        f"MIME: {fact.mimetype or '(unknown)'}",
    ]
    if fact.text_extracted and fact.text_preview:
        lines.append("")
        lines.append(f"--- Text preview ({fact.text_bytes} bytes total) ---")
        lines.append(fact.text_preview)
    return "\n".join(lines)


def _dedup_key(fact: FileFact) -> str:
    """State key: path + size + mtime. Mtime alone can reset on file-copy;
    size guards against pathological zero-time collisions."""
    return f"{fact.abs_path}|{fact.size_bytes}|{fact.mtime_utc.isoformat()}"


# ── Walk ─────────────────────────────────────────────────────────────────────


def walk_facts(roots: list[str], limit: int | None) -> list[FileFact]:
    """Yield FileFact for every non-skipped file under the given roots."""
    facts: list[FileFact] = []
    for root in roots:
        root_path = Path(root).expanduser().resolve()
        if not root_path.exists():
            print(f"SKIP: root does not exist: {root_path}", file=sys.stderr)
            continue
        for path in root_path.rglob("*"):
            if not path.is_file():
                continue
            if _path_should_skip(path):
                continue
            fact = _fact_for(path)
            if fact is None:
                continue
            facts.append(fact)
            if limit is not None and len(facts) >= limit:
                return facts
    return facts


# ── Main ─────────────────────────────────────────────────────────────────────


async def _write_episodes(facts: list[FileFact], dry_run: bool) -> int:
    """Write episodes via the L3 port. Returns count actually written."""
    if dry_run:
        for f in facts[:5]:
            print(f"[DRY] {f.abs_path} · {f.size_bytes:,}b · "
                  f"{'text' if f.text_extracted else 'metadata-only'}")
        if len(facts) > 5:
            print(f"[DRY] ... and {len(facts) - 5} more")
        return 0

    # Lazy-import so a dry-run has no sidecar dependencies at all.
    # NB: this import path assumes the Desktop MIKAI clone is on PYTHONPATH
    # or the script is run from there. When WikiAdapter is selected via
    # MIKAI_L3_BACKEND=wiki, the ingest is an append to
    # ~/.mikai/wiki/wiki-episodes.log — no sidecar needed.
    graphiti_root = Path.home() / "Desktop" / "MIKAI" / "infra" / "graphiti"
    if str(graphiti_root) not in sys.path:
        sys.path.insert(0, str(graphiti_root))
    from sidecar.l3 import Episode, make_backend  # noqa: E402

    backend = await make_backend()
    written = 0
    try:
        for f in facts:
            episode = Episode(
                content=_episode_content(f),
                source_description=f"filesystem-scan:{f.ext or 'no-ext'}",
                reference_time=f.mtime_utc,
                name=f.name,
            )
            try:
                await backend.ingest_episode(episode)
                written += 1
            except Exception as exc:
                print(f"WARN: ingest failed for {f.abs_path}: {exc}",
                      file=sys.stderr)
    finally:
        await backend.close()
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description="MIKAI file-scanner ingestion")
    ap.add_argument("--roots", nargs="+", default=DEFAULT_ROOTS,
                    help="Directories to walk (default: Desktop, Downloads, Documents)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap the walk at N files (safety for first runs)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be ingested without writing")
    ap.add_argument("--force", action="store_true",
                    help="Ignore dedup state; re-ingest every file")
    args = ap.parse_args()

    t0 = time.time()
    print(f"Walking {len(args.roots)} roots: {args.roots}")
    if args.limit:
        print(f"  cap: {args.limit} files")

    facts = walk_facts(args.roots, args.limit)
    print(f"Found {len(facts):,} files (elapsed {time.time() - t0:.1f}s)")

    state = {} if args.force else _load_state()
    fresh: list[FileFact] = []
    for f in facts:
        k = _dedup_key(f)
        if k in state:
            continue
        fresh.append(f)
        state[k] = {
            "seen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "size_bytes": f.size_bytes,
        }

    text_hits = sum(1 for f in fresh if f.text_extracted)
    print(f"Fresh (never-seen or changed): {len(fresh):,} — "
          f"{text_hits:,} with extracted text")

    written = asyncio.run(_write_episodes(fresh, args.dry_run))
    if not args.dry_run:
        _save_state(state)
        print(f"Ingested {written:,} episodes")
        print(f"State: {STATE_PATH}")
    else:
        print(f"DRY-RUN: would ingest {len(fresh):,} episodes")

    print(f"Done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

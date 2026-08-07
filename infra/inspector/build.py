"""Inspector build — collect Inspector state and write outputs.

Outputs:
  ~/.mikai/brain/state/tensions.json        parsed + merged tension read-model
  ~/.mikai/brain/inspector.html             standalone inspector page

The Inspector's data model is deliberately smaller than the cockpit's:
this is a diagnostic surface, not an operational one. It carries the
things a *builder* wants to audit — what MIKAI has noticed, not what
MIKAI proposes to do about it.
"""

from __future__ import annotations

import html as _html
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from infra.mikai_brain import (BRAIN_MD, BRAIN_ROOT, PROGRESS_LOG, STATE_DIR,
                               THREADS_DIR)

from . import (INSPECTOR_HTML, TENSIONS_JSON, WIKI_DIR, WIKI_MD)
from .render import render_html
from .tensions import build as build_tensions
from .tensions import write_json as write_tensions_json

USER_MODEL_MD = BRAIN_ROOT / "USER_MODEL.md"
WIKI_NARRATIVE = WIKI_DIR / "wiki-narrative.md"
WIKI_ONTOLOGY = WIKI_DIR / "wiki-ontology.md"
SURFACING_HTML = BRAIN_ROOT / "surfacing.html"
DELIVERY_LOG = STATE_DIR / "delivery_events.jsonl"

# Per-file cap for embedded wiki content. wiki.md is ~33 MB, which is
# too large to inline whole into the static page — we take the tail
# (most recent sections, append-only file) plus a small head slice.
# Everything under this cap gets embedded whole.
_WIKI_INLINE_CAP = 800_000  # 800 KB per file
_WIKI_LARGE_TAIL_BYTES = 600_000  # tail slice for wiki.md
_WIKI_LARGE_HEAD_BYTES = 40_000   # small head slice for context


# NOTE: The four canned-query panels (obsessions / aphorisms / ideas /
# expertise) were removed on 2026-08-06 — same over-taxonomy Fable
# rejected, dressed as UI tabs instead of files. The bottom ASK bar
# covers those asks on demand; Brian types the question himself.
# Only three panels remain: TENSIONS (parsed from wiki.md), USER MODEL
# (rendered from USER_MODEL.md), SUBSTRATE (real metrics).


def _file_bytes(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _file_mtime(path: Path) -> str | None:
    try:
        ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return ts.isoformat(timespec="seconds")
    except FileNotFoundError:
        return None


def _read_text(path: Path, *, limit: int = 200_000) -> str:
    if not path.exists():
        return ""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return raw[:limit]


def _thread_count() -> int:
    if not THREADS_DIR.exists():
        return 0
    return sum(1 for p in THREADS_DIR.iterdir() if p.is_dir())


def _episode_count() -> int:
    """Rough count — cheap grep against wiki.md for episode headers.

    Uses the shared wiki-episodes.log line count as a fast proxy so we
    do not re-scan 33 MB on every rebuild.
    """
    log = WIKI_DIR / "wiki-episodes.log"
    if log.exists():
        try:
            with log.open("rb") as f:
                return sum(1 for _ in f)
        except OSError:
            return 0
    return 0


def _entity_count() -> int:
    ents = BRAIN_ROOT / "entities"
    if not ents.exists():
        return 0
    return sum(1 for p in ents.rglob("*.md"))


def _last_ask_ts() -> str | None:
    """Peek at progress.jsonl for the most recent 'ask' or attention
    fire — pure read, no state mutation."""
    if not PROGRESS_LOG.exists():
        return None
    try:
        with PROGRESS_LOG.open("r", encoding="utf-8") as f:
            last = None
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("mode") in ("ask", "standup", "figs-decide"):
                    last = row
            return last["ts"] if last else None
    except OSError:
        return None


def _last_attention_fire() -> dict | None:
    """Most recent Attention Engine tick — cockpit's standup writes
    these; if figs-decide ever becomes a mode we'll pick it up too."""
    if not PROGRESS_LOG.exists():
        return None
    latest: dict | None = None
    try:
        with PROGRESS_LOG.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                mode = row.get("mode", "")
                if mode in ("standup", "figs-decide"):
                    latest = row
    except OSError:
        return None
    if not latest:
        return None
    return {
        "ts": latest.get("ts"),
        "mode": latest.get("mode"),
        "did": latest.get("did"),
        "surfaced": latest.get("surfaced", 0),
    }


def _dismiss_rate_7d() -> tuple[float, int] | None:
    """Simple 7-day dismiss rate from delivery_events.jsonl, if present."""
    log = STATE_DIR / "delivery_events.jsonl"
    if not log.exists():
        return None
    cutoff = datetime.now(timezone.utc).timestamp() - 7 * 86400
    responded = 0
    dismissed = 0
    try:
        with log.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = row.get("ts")
                try:
                    ts_epoch = datetime.fromisoformat(ts).timestamp()
                except (TypeError, ValueError):
                    continue
                if ts_epoch < cutoff:
                    continue
                verdict = row.get("verdict") or row.get("outcome")
                if verdict is None:
                    continue
                responded += 1
                if verdict in ("dismiss", "dismissed", "no"):
                    dismissed += 1
    except OSError:
        return None
    if responded == 0:
        return (0.0, 0)
    return (dismissed / responded, responded)


# ─── L4 SIGNALS collector ────────────────────────────────────────────
#
# Absorbs the standalone ~/.mikai/brain/surfacing.html into the
# Inspector. Two collection strategies (best-first):
#   1. If surfacing.html exists, parse its <body> and hand back the
#      raw HTML for each <section>. This preserves the exact rendering
#      that already worked without us having to re-derive it.
#   2. Fallback: derive a minimal signals snapshot straight from
#      progress.jsonl + delivery_events.jsonl.
# After the panel proves out, the standalone HTML gets deleted; the
# fallback path remains as the only source of L4 signals.

_SECTION_RE = re.compile(
    r'<section\s+id="([^"]+)"[^>]*>(.*?)</section>', re.DOTALL)


def _parse_surfacing_html() -> dict | None:
    if not SURFACING_HTML.exists():
        return None
    try:
        raw = SURFACING_HTML.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    sections: dict[str, str] = {}
    for m in _SECTION_RE.finditer(raw):
        sections[m.group(1)] = m.group(2).strip()
    # Also capture the header stamp line ("as of ...") for provenance.
    stamp_m = re.search(
        r'<div class="stamp">\s*([^<]+?)(?:<button|</div)', raw, re.DOTALL)
    stamp = stamp_m.group(1).strip() if stamp_m else None
    return {
        "source": "surfacing.html",
        "mtime": _file_mtime(SURFACING_HTML),
        "stamp": stamp,
        "sections": sections,  # id → inner HTML
    }


def _derive_signals_from_logs() -> dict:
    """Fallback if surfacing.html is gone: minimal live snapshot from
    the progress + delivery logs. Deliberately terse — enough to show
    the panel isn't dead, not a full re-implementation of surfacing.py."""
    deliveries: list[dict] = []
    if DELIVERY_LOG.exists():
        try:
            with DELIVERY_LOG.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    deliveries.append(row)
        except OSError:
            pass
    deliveries = deliveries[-20:]
    ticks: list[dict] = []
    if PROGRESS_LOG.exists():
        try:
            with PROGRESS_LOG.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if row.get("mode") in ("standup", "figs-decide"):
                        ticks.append(row)
        except OSError:
            pass
    return {
        "source": "logs",
        "mtime": None,
        "stamp": None,
        "sections": {},
        "deliveries": deliveries[-20:],
        "ticks": ticks[-10:],
    }


def _build_l4_signals() -> dict:
    parsed = _parse_surfacing_html()
    if parsed and parsed["sections"]:
        return parsed
    return _derive_signals_from_logs()


# ─── WIKI collector ──────────────────────────────────────────────────
#
# File browser + client-side search over ~/.mikai/wiki/*. The tab
# lists every non-backup file in the directory (auto-discovered) and
# inlines each file's content up to _WIKI_INLINE_CAP. wiki.md is too
# large to inline whole; we take a small head slice + a large tail
# slice (the file is append-only, so the tail is the recent content).

_WIKI_INCLUDE_EXTS = (".md", ".log")


def _read_wiki_file(path: Path) -> tuple[str, dict]:
    """Read a wiki file, returning (embed_text, meta) where meta
    carries size / truncation info for the UI."""
    size = _file_bytes(path)
    if size <= _WIKI_INLINE_CAP:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "", {"error": "read failed"}
        return text, {"truncated": False, "bytes": size, "shown_bytes": size}
    # Large file — head + tail slices, joined by a marker so client-side
    # search still hits both ends.
    head = ""
    tail = ""
    try:
        with path.open("rb") as f:
            head = f.read(_WIKI_LARGE_HEAD_BYTES).decode("utf-8", "replace")
            f.seek(max(0, size - _WIKI_LARGE_TAIL_BYTES))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        pass
    marker = (
        f"\n\n<!-- inspector: {size - _WIKI_LARGE_HEAD_BYTES - _WIKI_LARGE_TAIL_BYTES} "
        f"bytes elided between head and tail — open the file directly "
        f"for the middle -->\n\n"
    )
    return head + marker + tail, {
        "truncated": True,
        "bytes": size,
        "shown_bytes": len(head) + len(tail),
    }


def _build_wiki() -> dict:
    if not WIKI_DIR.exists():
        return {"dir": str(WIKI_DIR), "files": []}
    files: list[dict] = []
    for path in sorted(WIKI_DIR.iterdir()):
        if not path.is_file():
            continue
        if path.suffix not in _WIKI_INCLUDE_EXTS:
            continue
        # Exclude .bak-* backup snapshots; they're noise for the
        # builder view.
        if ".bak-" in path.name or path.name.endswith(".bak"):
            continue
        text, meta = _read_wiki_file(path)
        files.append({
            "name": path.name,
            "path": str(path),
            "bytes": meta.get("bytes", 0),
            "mtime": _file_mtime(path),
            "truncated": meta.get("truncated", False),
            "shown_bytes": meta.get("shown_bytes", 0),
            "text": text,
            "kind": "log" if path.suffix == ".log" else "md",
        })
    return {"dir": str(WIKI_DIR), "files": files}


def _launchctl_mikai_jobs() -> list[str]:
    """Return the mikai-labelled entries from ``launchctl list``. Used
    on the Substrate panel so Brian can see at a glance whether the
    ingestion daemon is loaded. Safe (read-only) command."""
    try:
        out = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True, timeout=3,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    lines = []
    for row in out.stdout.splitlines():
        if "mikai" in row.lower():
            lines.append(row.strip())
    return lines


def build_state() -> dict:
    """Assemble the Inspector's read-model. Pure — no writes."""
    now = datetime.now(timezone.utc)
    tensions = build_tensions()
    user_model_text = _read_text(USER_MODEL_MD, limit=32_000)
    dismiss = _dismiss_rate_7d()
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "generated_at_human": now.strftime("%Y-%m-%d %H:%M UTC"),
        "tensions": tensions,
        "tensions_count": len(tensions),
        "user_model": {
            "text": user_model_text,
            "mtime": _file_mtime(USER_MODEL_MD),
            "bytes": _file_bytes(USER_MODEL_MD),
        },
        "substrate": {
            "wiki_bytes": _file_bytes(WIKI_MD),
            "wiki_mtime": _file_mtime(WIKI_MD),
            "wiki_narrative_mtime": _file_mtime(WIKI_NARRATIVE),
            "wiki_ontology_mtime": _file_mtime(WIKI_ONTOLOGY),
            "episode_count": _episode_count(),
            "entity_count": _entity_count(),
            "thread_count": _thread_count(),
            "tensions_count": len(tensions),
            "brain_md_mtime": _file_mtime(BRAIN_MD),
            "last_ask": _last_ask_ts(),
            "attention_last": _last_attention_fire(),
            "dismiss_rate_7d": dismiss[0] if dismiss else None,
            "dismiss_responded_7d": dismiss[1] if dismiss else 0,
            "launchd_jobs": _launchctl_mikai_jobs(),
        },
        "l4_signals": _build_l4_signals(),
        "wiki": _build_wiki(),
        "endpoints": {
            "ask_stream": "http://localhost:8210/ask/stream",
        },
    }


def write_outputs(state: dict,
                  html_path: Path | None = None,
                  *, refresh_only: bool = False) -> list[Path]:
    """Write tensions.json (always) and inspector.html (unless refresh_only)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    written.append(write_tensions_json(state["tensions"],
                                       out_path=TENSIONS_JSON,
                                       backup=False))
    if refresh_only:
        return written
    target = html_path or INSPECTOR_HTML
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        # Backup any file we mutate — per project standing convention.
        bak = target.with_suffix(
            target.suffix + ".bak-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
        try:
            target.replace(bak)
        except OSError:
            pass
    target.write_text(render_html(state), encoding="utf-8")
    written.append(target)
    return written


def summarize(state: dict) -> str:
    sub = state["substrate"]
    lines = [
        f"inspector: {state['tensions_count']} tension(s) parsed",
        f"  wiki       : {sub['wiki_bytes']/1e6:.1f} MB · "
        f"{sub['episode_count']:>4} episodes · {sub['entity_count']} entities",
        f"  threads    : {sub['thread_count']}",
        f"  user_model : {state['user_model']['bytes']} B · "
        f"mtime {state['user_model']['mtime']}",
        f"  launchd    : {len(sub['launchd_jobs'])} mikai job(s) loaded",
    ]
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    st = build_state()
    print(summarize(st))
    for p in write_outputs(st):
        print(f"wrote {p}")

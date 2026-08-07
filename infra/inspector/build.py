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

import json
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


# Canned queries — each opens the panel with a prompt pre-filled that
# reflects the retrieval shape MIKAI's substrate is best at. Every
# panel is answered by the same /ask/stream endpoint the cockpit uses;
# no new inference path.
CANNED_QUERIES: dict[str, dict] = {
    "obsessions": {
        "title": "Obsessions",
        "subtitle": "recurring returns across contexts and years",
        "glyph": "spiral",
        "query": (
            "Which recurring themes have I returned to across the most "
            "contexts and years? Rank by depth of return, not raw "
            "frequency. Cite provenance from the wiki. Format as a "
            "table with columns: theme · first surfaced · last touched · "
            "why it keeps coming back."
        ),
    },
    "aphorisms": {
        "title": "Aphorisms",
        "subtitle": "compressed lines that keep re-earning shelf space",
        "glyph": "quote",
        "query": (
            "From my wiki and thread exports, extract the most "
            "compressed lines I have written or endorsed — the ones "
            "that function as aphorisms in my own idiom. Prefer lines I "
            "have referenced more than once. Group by domain (design, "
            "training, epistemics, relationships)."
        ),
    },
    "ideas": {
        "title": "Ideas",
        "subtitle": "propositions I have not yet built or refuted",
        "glyph": "lightbulb",
        "query": (
            "List propositions I have floated but not yet built or "
            "refuted — genuine ideas, not tasks. For each, cite where I "
            "first raised it and where I most recently returned to it. "
            "Flag any that have gone cold for more than 90 days."
        ),
    },
    "expertise": {
        "title": "Expertise",
        "subtitle": "domains where the substrate carries real depth",
        "glyph": "book",
        "query": (
            "Which domains has my substrate accumulated genuine depth in "
            "— versus surface familiarity? Ground each claim in the "
            "number and specificity of episodes, not word count. "
            "Distinguish 'thinks about' from 'has practiced'."
        ),
    },
}


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
        "queries": CANNED_QUERIES,
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

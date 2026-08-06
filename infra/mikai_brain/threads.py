"""Thread file parsing + writing.

Thread files are markdown with YAML-ish frontmatter and a `## Log`
section of dated bullet points. This module owns the on-disk shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from . import THREADS_DIR

STATES = ("exploring", "evaluating", "decided", "acting", "stalled", "completed")


@dataclass
class Thread:
    slug: str                       # filename stem
    path: Path
    title: str = ""
    state: str = "exploring"
    state_since: str = ""           # ISO date
    last_activity: str = ""         # ISO date
    next_step: str = ""
    next_step_due: str = ""         # ISO date, optional
    entities: list[str] = field(default_factory=list)
    department: str = ""
    frontmatter_extra: dict[str, str] = field(default_factory=dict)
    log_lines: list[str] = field(default_factory=list)   # raw log body lines


_FM_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _today() -> str:
    return date.today().isoformat()


def _parse_frontmatter(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in block.splitlines():
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def _parse_list(s: str) -> list[str]:
    s = s.strip()
    if not s:
        return []
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1]
        return [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
    return [x.strip() for x in s.split(",") if x.strip()]


def _extract_log_lines(body: str) -> list[str]:
    """Return lines under a `## Log` heading, bullet lines only."""
    lines = body.splitlines()
    in_log = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("## log"):
            in_log = True
            continue
        if in_log:
            if stripped.startswith("## "):
                break
            if stripped.startswith("- "):
                out.append(stripped)
    return out


def parse_thread(path: Path) -> Thread:
    raw = path.read_text()
    m = _FM_RE.match(raw)
    if not m:
        return Thread(slug=path.stem, path=path, title=path.stem, log_lines=[])
    fm = _parse_frontmatter(m.group(1))
    body = m.group(2)
    known = {"slug", "title", "state", "state_since", "last_activity",
             "next_step", "next_step_due", "entities", "department"}
    extra = {k: v for k, v in fm.items() if k not in known}
    return Thread(
        slug=fm.get("slug", path.stem),
        path=path,
        title=fm.get("title", path.stem),
        state=fm.get("state", "exploring").strip(),
        state_since=fm.get("state_since", ""),
        last_activity=fm.get("last_activity", ""),
        next_step=fm.get("next_step", "").strip('"').strip("'"),
        next_step_due=fm.get("next_step_due", ""),
        entities=_parse_list(fm.get("entities", "")),
        department=fm.get("department", ""),
        frontmatter_extra=extra,
        log_lines=_extract_log_lines(body),
    )


def load_all() -> list[Thread]:
    if not THREADS_DIR.exists():
        return []
    return [parse_thread(p) for p in sorted(THREADS_DIR.glob("*.md"))]


def match_threads_in_text(text: str, threads: list[Thread] | None = None) -> list[Thread]:
    """Conservative thread matching for action-scenario write-back.

    A thread matches only when the text clearly names it:
      1. its exact slug appears ("proposal-timing"), or
      2. its slug with hyphens as spaces appears ("proposal timing"), or
      3. its full title appears (titles < 6 chars are too generic — ignored), or
      4. a distinctive slug component (>= 6 chars) appears as a whole word
         AND exactly one thread owns that component ("proposal" matches
         proposal-timing — but not if proposal-venue also exists).

    False appends pollute thread logs, so ties and short/generic tokens
    never match. Returns [] rather than guessing.
    """
    if threads is None:
        threads = load_all()
    t = (text or "").lower()
    if not t.strip():
        return []
    matched: dict[str, Thread] = {}
    for th in threads:
        slug = th.slug.lower()
        title = (th.title or "").strip().lower()
        if slug in t or slug.replace("-", " ") in t:
            matched[th.slug] = th
        elif len(title) >= 6 and title in t:
            matched[th.slug] = th
    component_owners: dict[str, list[Thread]] = {}
    for th in threads:
        for comp in set(th.slug.lower().split("-")):
            if len(comp) >= 6:
                component_owners.setdefault(comp, []).append(th)
    words = set(re.findall(r"[a-z0-9]+", t))
    for comp, owners in component_owners.items():
        if len(owners) == 1 and comp in words:
            matched[owners[0].slug] = owners[0]
    return [matched[k] for k in sorted(matched)]


def _append_to_log_section(body: str, bullet: str) -> str:
    """Insert `bullet` at the end of the ## Log section. Appending to end
    of file is wrong whenever another section (e.g. ## Content) follows
    ## Log — the bullet would land there and _extract_log_lines would
    never see it."""
    lines = body.splitlines()
    log_idx: int | None = None
    insert_at: int | None = None
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("## log"):
            log_idx = i
            continue
        if log_idx is not None and line.strip().startswith("## "):
            insert_at = i
            break
    if log_idx is None:
        return body.rstrip() + f"\n\n## Log\n{bullet}\n"
    if insert_at is None:
        return body.rstrip() + f"\n{bullet}\n"
    while insert_at > log_idx + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    return "\n".join(lines[:insert_at] + [bullet, ""] + lines[insert_at:]).rstrip() + "\n"


def append_log_line(t: Thread, line: str) -> None:
    """Append `- {today} {line}` under the ## Log section of t.path.
    Also bumps last_activity to today in the frontmatter."""
    raw = t.path.read_text()
    m = _FM_RE.match(raw)
    if not m:
        return
    fm_text = m.group(1)
    body = m.group(2)
    # Bump last_activity in frontmatter
    today = _today()
    new_fm_lines: list[str] = []
    seen_last_activity = False
    for fm_line in fm_text.splitlines():
        if fm_line.startswith("last_activity:"):
            new_fm_lines.append(f"last_activity: {today}")
            seen_last_activity = True
        else:
            new_fm_lines.append(fm_line)
    if not seen_last_activity:
        new_fm_lines.append(f"last_activity: {today}")
    new_fm = "\n".join(new_fm_lines)
    new_body = _append_to_log_section(body, f"- {today} {line}")
    t.path.write_text(f"---\n{new_fm}\n---\n{new_body}")


def set_state(t: Thread, new_state: str, reason: str) -> None:
    """Update state + state_since in frontmatter, append a transition line
    to the log. Idempotent — if state is already new_state, does nothing."""
    if new_state not in STATES:
        raise ValueError(f"Unknown state: {new_state!r}")
    if t.state == new_state:
        return
    raw = t.path.read_text()
    m = _FM_RE.match(raw)
    if not m:
        return
    fm_text = m.group(1)
    body = m.group(2)
    today = _today()
    new_fm_lines: list[str] = []
    seen = {"state": False, "state_since": False, "last_activity": False}
    for fm_line in fm_text.splitlines():
        if fm_line.startswith("state:"):
            new_fm_lines.append(f"state: {new_state}")
            seen["state"] = True
        elif fm_line.startswith("state_since:"):
            new_fm_lines.append(f"state_since: {today}")
            seen["state_since"] = True
        elif fm_line.startswith("last_activity:"):
            new_fm_lines.append(f"last_activity: {today}")
            seen["last_activity"] = True
        else:
            new_fm_lines.append(fm_line)
    for k, v in (("state", new_state), ("state_since", today), ("last_activity", today)):
        if not seen[k]:
            new_fm_lines.append(f"{k}: {v}")
    new_fm = "\n".join(new_fm_lines)
    transition = f"- {today} [{t.state}→{new_state}] {reason}"
    new_body = _append_to_log_section(body, transition)
    t.path.write_text(f"---\n{new_fm}\n---\n{new_body}")
    t.state = new_state
    t.state_since = today
    t.last_activity = today

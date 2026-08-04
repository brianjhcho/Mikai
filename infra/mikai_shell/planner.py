"""LLM-based file-organization planner.

Takes: (1) a file inventory from file_scanner, (2) the user's declared
life-tier config, (3) the user's natural-language prompt.

Returns: a proposed folder taxonomy for the target root + a batch of
concrete (src, dst, rationale) moves that would achieve it.

Single innovation surface (per Brian's directive): the LLM reasoning
against the substrate. Everything else is stock.

LLM choice: DeepSeek V3 via the OpenAI-compatible endpoint already used
by the calendar planner + full_corpus_dream. Cheapest known option with
reliable JSON output.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib import request as urlreq

# Reuse the file-scanner's fact-gathering code.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "decider"))
from file_scanner import FileFact, walk_facts  # noqa: E402

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
LIFE_TIER_PATH = Path.home() / ".mikai" / "life-tier.json"

MAX_FILES_PER_PROMPT = 300  # cap prompt size; more than this needs chunking


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class ProposedMove:
    src: str
    dst: str            # absolute path — planner returns concrete destinations
    rationale: str      # one-line "why" the LLM produced


@dataclass
class OrganizationPlan:
    scope: str                              # e.g. "~/Desktop"
    taxonomy: list[str] = field(default_factory=list)
        # target folders the LLM invented (absolute paths)
    moves: list[ProposedMove] = field(default_factory=list)
    rationale: str = ""                     # LLM's overall explanation
    unclassified: list[str] = field(default_factory=list)
        # files the LLM chose not to move (kept in place)
    llm_raw: str = ""                       # for debugging


# ── LLM prompt ───────────────────────────────────────────────────────────────


def _load_life_tier_json() -> dict:
    if not LIFE_TIER_PATH.exists():
        return {}
    try:
        return json.loads(LIFE_TIER_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def _life_tier_prompt_block(life_tier: dict) -> str:
    if not life_tier or "top_tier" not in life_tier:
        return "(no life-tier config — organize by generic file-type)"
    lines = ["Brian's declared top-tier life themes (organize aligned to these when possible):"]
    for tier in life_tier.get("top_tier", []):
        name = tier.get("name", "?")
        lines.append(f"  - {name}")
        filts = tier.get("filter_goals", [])
        if filts:
            lines.append(f"    matches: {', '.join(filts[:6])}")
    return "\n".join(lines)


def _file_inventory_block(facts: list[FileFact]) -> str:
    """Compact per-file text block. Cap MAX_FILES_PER_PROMPT."""
    lines = []
    for f in facts[:MAX_FILES_PER_PROMPT]:
        # Include text preview when available — that's what turns "IMG_1234.jpg"
        # into signal the LLM can classify against.
        preview = ""
        if f.text_preview:
            snip = f.text_preview[:180].replace("\n", " ")
            preview = f' preview="{snip}…"'
        lines.append(
            f"  - {f.name} ({f.mimetype or f.ext or 'unknown'}, {f.size_bytes:,}b){preview}"
        )
    if len(facts) > MAX_FILES_PER_PROMPT:
        lines.append(f"  ... [{len(facts) - MAX_FILES_PER_PROMPT} more files elided]")
    return "\n".join(lines)


def _build_prompt(
    root: str,
    facts: list[FileFact],
    user_prompt: str,
    life_tier: dict,
) -> str:
    return f"""You are MIKAI's file-organization planner. The user's request is:

"{user_prompt}"

Target root: {root} ({len(facts)} files)

{_life_tier_prompt_block(life_tier)}

FILE INVENTORY:
{_file_inventory_block(facts)}

## Your job

1. Look across the inventory. Notice clusters (topic, project, temporality, type).
2. Propose a TARGET FOLDER STRUCTURE under the target root. Prefer 4-8 folders,
   aligned to Brian's life-tier themes where files match. Generic buckets
   (Screenshots, Archive, Media) are fine for files that don't fit a theme.
3. For each file, decide whether to move it (and where) or leave in place.
4. Concrete destination paths: full absolute paths under the target root.
5. NEVER propose destinations outside the target root.
6. NEVER propose deletions.
7. Files with mtime in the last 72 hours are probably in active use —
   prefer leaving them in place unless the user's prompt clearly implies otherwise.

## Output — STRICT JSON, no prose, no markdown fences

Files NOT listed in `moves` are implicitly left in place — do NOT emit an
`unclassified` list. Prefer conservative movement: if a file's shape is
unclear or ambiguous, leave it in place rather than move it.

{{
  "taxonomy": ["<absolute path to folder 1>", "<absolute path to folder 2>", ...],
  "moves": [
    {{"src": "<abs src path>", "dst": "<abs dst path>", "rationale": "<one-line why>"}},
    ...
  ],
  "rationale": "<one paragraph explaining the overall shape of the proposed organization>"
}}
"""


# ── LLM call ─────────────────────────────────────────────────────────────────


def _call_deepseek(prompt: str, timeout: float = 90.0) -> str:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError(
            "DEEPSEEK_API_KEY not set — source ~/.mikai/launchd.env first"
        )
    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        # Manifest can be large (100+ moves × ~120 chars each) — bump ceiling
        # so DeepSeek doesn't truncate mid-JSON on medium/large scans.
        "max_tokens": 32000,
    }).encode()
    req = urlreq.Request(
        DEEPSEEK_URL, data=payload, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        },
    )
    with urlreq.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode()


# ── Public entry point ───────────────────────────────────────────────────────


def plan(root: str, user_prompt: str) -> OrganizationPlan:
    """Scan `root`, ask the LLM to propose an organization, return the plan.
    No files are touched. Caller is responsible for approval + execution.
    """
    root_abs = str(Path(root).expanduser().resolve())
    facts = walk_facts([root_abs], limit=None)
    life_tier = _load_life_tier_json()
    prompt = _build_prompt(root_abs, facts, user_prompt, life_tier)

    raw = _call_deepseek(prompt)
    try:
        outer = json.loads(raw)
        content = outer["choices"][0]["message"]["content"]
        obj = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LLM response unparseable: {exc}\n\n{raw[:500]}") from exc

    return OrganizationPlan(
        scope=root_abs,
        taxonomy=[str(p) for p in obj.get("taxonomy", [])],
        moves=[
            ProposedMove(
                src=m["src"],
                dst=m["dst"],
                rationale=m.get("rationale", ""),
            )
            for m in obj.get("moves", [])
            if "src" in m and "dst" in m
        ],
        rationale=obj.get("rationale", ""),
        unclassified=[str(p) for p in obj.get("unclassified", [])],
        llm_raw=raw,
    )


# ── Safety validation ───────────────────────────────────────────────────────


def validate(plan: OrganizationPlan) -> list[str]:
    """Return a list of issues with the plan. Empty list = safe to proceed.
    The shell should refuse to execute a plan with any critical issue."""
    issues: list[str] = []
    scope = Path(plan.scope).resolve()
    for m in plan.moves:
        src = Path(m.src).resolve()
        dst = Path(m.dst).resolve()
        try:
            src.relative_to(scope)
        except ValueError:
            issues.append(f"CRITICAL: src outside scope — {m.src}")
        try:
            dst.relative_to(scope)
        except ValueError:
            issues.append(f"CRITICAL: dst outside scope — {m.dst}")
        if not src.exists():
            issues.append(f"WARN: src does not exist — {m.src}")
        if src == dst:
            issues.append(f"WARN: move is a no-op — {m.src}")
        if str(dst).endswith("/"):
            issues.append(f"WARN: dst looks like a folder, not a file — {m.dst}")
    return issues

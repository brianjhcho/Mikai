"""UserModel — compiled model of Brian, built from the whole substrate.

Motivation: MIKAI's mention-count filters (`hydrator.py`,
`latent_threads.py`) treat importance as repetition. That surfaces
tooling noise and buries dormant-but-load-bearing threads (dry-eye
research, plant care, China proposal). Frequency is a floor, not a
signal. See docs/USER_MODEL_RESEARCH.md for the survey and design
lessons.

This module compiles a bounded, human-legible `USER_MODEL.md` from the
substrate — the Karpathy LLM-wiki idea applied to user modeling. One
interactive LLM call (or a small map-reduce for large substrates)
synthesizes:

    values         — one-liner strings, near-permanent
    themes         — thread-shape topics MIKAI has evidence for
    preferences    — data-format / interaction preferences
    unresolved     — open loops detected but not decided
    source_signals — provenance for each entry (audit trail)

Downstream (latent-threads ranker, hydrator, mikai_ask composer) reads
the compiled model instead of raw counts. Rebuilt weekly by
`dream_bootstrap.py user-model` — never on the request path (that's
the ChatGPT-memory prompt-injection attack surface).

On-disk shape:

    ~/.mikai/brain/USER_MODEL.md          human-legible, byte-capped
    ~/.mikai/brain/state/user_model.json  structured, for programmatic use

Hard byte cap on the markdown (Hermes-USER.md lesson: ~2 KB). Overflow
raises RuntimeError — silent truncation would be worse than a failed
rebuild, since downstream would score against a mutilated model.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import BRAIN_ROOT, BRAIN_MD, ENTITIES_DIR, STATE_DIR, THREADS_DIR

USER_MODEL_MD = BRAIN_ROOT / "USER_MODEL.md"
USER_MODEL_JSON = STATE_DIR / "user_model.json"

# Hermes USER.md lesson: bounded so it can ride in every downstream
# prompt without eating context. Overflow errors; never silently
# truncates. Downstream would score against a mutilated model.
MARKDOWN_BYTE_CAP = 2000

# Input budget for the synthesizer call. Wiki narrative + ontology can
# be large; we sample rather than truncate blindly. Kept well under the
# 150K interactive-tier margin used elsewhere.
INPUT_CHAR_BUDGET = 100_000


@dataclass
class UserModel:
    values: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    source_signals: list[str] = field(default_factory=list)
    updated_at: str = ""

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "UserModel":
        return cls(
            values=list(d.get("values", [])),
            themes=list(d.get("themes", [])),
            preferences=list(d.get("preferences", [])),
            unresolved=list(d.get("unresolved", [])),
            source_signals=list(d.get("source_signals", [])),
            updated_at=str(d.get("updated_at", "")),
        )

    def to_markdown(self) -> str:
        """Human-legible USER_MODEL.md. Section order deliberately
        matches how downstream will scan it: values (frame), themes
        (ranker input), preferences (composer input), unresolved
        (surface targets), signals (provenance)."""
        ts = self.updated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        parts = [
            "# USER_MODEL.md — what MIKAI has observed about Brian",
            "",
            f"_Compiled by dream-weekly at {ts}. Do not hand-edit;"
            " changes are overwritten. See docs/USER_MODEL_RESEARCH.md._",
            "",
            _section("Values (near-permanent)", self.values),
            _section("Themes (current thread-shape topics)", self.themes),
            _section("Preferences (interaction / format)", self.preferences),
            _section("Unresolved loops (detected, not decided)", self.unresolved),
            _section("Source signals (provenance)", self.source_signals),
        ]
        return "\n".join(parts).rstrip() + "\n"

    def within_cap(self) -> bool:
        return len(self.to_markdown().encode("utf-8")) <= MARKDOWN_BYTE_CAP


def _section(heading: str, items: list[str]) -> str:
    if not items:
        return f"## {heading}\n\n_(none)_\n"
    body = "\n".join(f"- {item.strip()}" for item in items if item.strip())
    return f"## {heading}\n\n{body}\n"


# ── Input collection ──────────────────────────────────────────────────


def _read_or_empty(path: Path) -> str:
    try:
        return path.read_text()
    except (FileNotFoundError, PermissionError):
        return ""


def _collect_wiki_signals(char_budget: int) -> str:
    """Wiki narrative + ontology are the compiled artifacts already —
    they distill the substrate. Sample head + tail so both stable
    themes (start) and recent shifts (end) survive the budget."""
    wiki_dir = Path.home() / ".mikai" / "wiki"
    narrative = _read_or_empty(wiki_dir / "wiki-narrative.md")
    ontology = _read_or_empty(wiki_dir / "wiki-ontology.md")

    per = max(char_budget // 2, 1000)
    return "\n\n".join([
        "### wiki-narrative.md (excerpt)",
        _head_tail(narrative, per),
        "### wiki-ontology.md (excerpt)",
        _head_tail(ontology, per),
    ])


def _head_tail(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    half = budget // 2
    return text[:half] + f"\n\n… [{len(text) - budget} chars elided] …\n\n" + text[-half:]


def _collect_entities(entities_dir: Path, max_entities: int = 40) -> str:
    """Frontmatter + first ~10 lines of each entity file. Entities
    Brian curated are the strongest declared signal of what matters."""
    if not entities_dir.exists():
        return "(no entities/ directory)"
    files = sorted(p for p in entities_dir.iterdir()
                   if p.is_file() and p.name.endswith(".md"))
    files = files[:max_entities]
    blocks: list[str] = []
    for p in files:
        try:
            lines = p.read_text().splitlines()[:12]
        except (OSError, UnicodeDecodeError):
            continue
        blocks.append(f"### entity: {p.stem}\n" + "\n".join(lines))
    return "\n\n".join(blocks) if blocks else "(no entity files)"


def _collect_threads(threads_dir: Path) -> str:
    """One line per thread: slug, state, next_step. The `unresolved`
    signal is basically the union of exploring / evaluating / stalled
    threads that lack a next_step_due."""
    if not threads_dir.exists():
        return "(no threads/ directory)"
    from . import threads as brain_threads  # avoid module-level cycle
    lines: list[str] = []
    try:
        for t in brain_threads.load_all():
            snippet = (t.next_step or "").strip().splitlines()[0] if t.next_step else ""
            lines.append(
                f"- [{t.state}] {t.slug} — {t.title or '(no title)'}"
                + (f"  next: {snippet}" if snippet else "")
            )
    except Exception as exc:  # noqa: BLE001 — best-effort input
        return f"(threads unreadable: {exc})"
    return "\n".join(lines) if lines else "(no threads)"


def _collect_ledger(char_budget: int = 4000) -> str:
    """Last N progress.jsonl rows — what MIKAI actually did recently.
    Behavior beats stated preference (collaborative-filtering lesson)."""
    from . import PROGRESS_LOG
    if not PROGRESS_LOG.exists():
        return "(no ledger)"
    try:
        text = PROGRESS_LOG.read_text()
    except OSError:
        return "(ledger unreadable)"
    if len(text) <= char_budget:
        return text
    return "… (older elided) …\n" + text[-char_budget:]


def collect_inputs(char_budget: int = INPUT_CHAR_BUDGET) -> str:
    """Assemble the input bundle for the synthesizer call."""
    wiki_share = char_budget // 2
    parts = [
        "## PROFILE.md (hand-curated identity)",
        _read_or_empty(BRAIN_ROOT / "PROFILE.md") or "(no PROFILE.md)",
        "## BRAIN.md (current priorities, weekly-consolidated)",
        _read_or_empty(BRAIN_MD) or "(no BRAIN.md)",
        "## wiki signals",
        _collect_wiki_signals(wiki_share),
        "## brain/entities/ (curated + hydrated)",
        _collect_entities(ENTITIES_DIR),
        "## brain/threads/ (active + stalled)",
        _collect_threads(THREADS_DIR),
        "## recent ledger (what MIKAI actually did)",
        _collect_ledger(),
    ]
    bundle = "\n\n".join(parts)
    if len(bundle) > char_budget:
        bundle = bundle[:char_budget] + "\n\n… [bundle truncated to char budget] …"
    return bundle


# ── Prompt + synthesizer ──────────────────────────────────────────────


_PROMPT_HEADER = """\
You are the reflective layer of MIKAI, Brian's task-state awareness
engine. Read the substrate below and synthesize a short, honest model
of Brian AS A PERSON — not a mention-count summary.

Return ONLY a JSON object with these fields (no prose, no fences):

{
  "values":         [ "one-liner about how he works or what he weights" , ... ],
  "themes":         [ "concrete topic he keeps returning to" , ... ],
  "preferences":    [ "interaction/format/tool preference" , ... ],
  "unresolved":     [ "open loop MIKAI has detected but Brian hasn't decided" , ... ],
  "source_signals": [ "'<entry> ← <evidence>' — one per non-obvious entry" , ... ]
}

Rules:
- 3 to 8 items per list. No filler. If you can't back an item, drop it.
- Prefer specific over generic: "prefers Fable 5 for reasoning, Opus for
  building" beats "cares about model choice".
- Themes are life-topics, NOT tools. Skip 'git', 'python', 'claude-code'.
- Unresolved = things Brian has been circling but hasn't picked. Not
  every open todo — the ones that keep showing up undecided.
- Source signals are audit rows so a human can check your work. Cite
  the file kind (PROFILE / ontology / thread / ledger) briefly.
- Total output MUST fit in about 1500 characters when rendered as
  markdown bullets. Be tight.

SUBSTRATE FOLLOWS:
"""


def _extract_json(text: str) -> dict:
    """Peel a JSON object out of the LLM response. Tolerates a leading
    code fence or a preamble line — same defensive shape used by the
    graphiti sidecar's DeepSeek adapter."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise RuntimeError(f"synthesizer returned no JSON object: {text[:200]!r}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"synthesizer JSON invalid: {exc}: {m.group(0)[:200]!r}")


def build(*, chat_fn=None, char_budget: int = INPUT_CHAR_BUDGET) -> UserModel:
    """Compile a UserModel from the whole substrate.

    Single interactive-tier call. `chat_fn` is injected for tests
    (default: infra.mikai_llm.chat with tier='interactive').
    """
    if chat_fn is None:
        import infra.mikai_llm as mikai_llm  # avoid import-at-module load
        def chat_fn(prompt: str) -> str:
            return mikai_llm.chat(prompt, tier="interactive")

    bundle = collect_inputs(char_budget=char_budget)
    prompt = _PROMPT_HEADER + bundle
    raw = chat_fn(prompt)
    payload = _extract_json(raw)
    model = UserModel.from_dict(payload)
    model.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if not model.within_cap():
        raise RuntimeError(
            f"USER_MODEL.md would exceed {MARKDOWN_BYTE_CAP}-byte cap "
            f"({len(model.to_markdown().encode('utf-8'))} bytes). "
            "Tighten the synthesizer prompt or shrink field counts. "
            "Silent truncation is refused (see docs/USER_MODEL_RESEARCH.md)."
        )
    return model


# ── Persistence ──────────────────────────────────────────────────────


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = path.with_name(f"{path.name}.bak-{ts}")
    dest.write_bytes(path.read_bytes())
    return dest


def save(model: UserModel) -> tuple[Path, Path]:
    """Write both artifacts atomically-ish (tmp + rename). Backs up
    any prior USER_MODEL.md so a bad rebuild is recoverable."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    BRAIN_ROOT.mkdir(parents=True, exist_ok=True)

    _backup(USER_MODEL_MD)

    md_tmp = USER_MODEL_MD.with_suffix(".md.tmp")
    md_tmp.write_text(model.to_markdown(), encoding="utf-8")
    md_tmp.replace(USER_MODEL_MD)

    json_tmp = USER_MODEL_JSON.with_suffix(".json.tmp")
    json_tmp.write_text(
        json.dumps(model.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    json_tmp.replace(USER_MODEL_JSON)

    return USER_MODEL_MD, USER_MODEL_JSON


def load() -> UserModel | None:
    """Load the last-compiled UserModel from state/user_model.json,
    or None if it hasn't been built yet. Downstream (latent-threads,
    hydrator, mikai_ask) call this and gracefully skip when None."""
    if not USER_MODEL_JSON.exists():
        return None
    try:
        return UserModel.from_dict(json.loads(USER_MODEL_JSON.read_text()))
    except (json.JSONDecodeError, OSError):
        return None


# ── CLI ──────────────────────────────────────────────────────────────


def _print_model(model: UserModel, stream=None) -> None:
    stream = stream or sys.stdout
    print(model.to_markdown(), file=stream)
    print(
        f"[user_model] {len(model.to_markdown().encode('utf-8'))} bytes "
        f"(cap {MARKDOWN_BYTE_CAP}) — values={len(model.values)} "
        f"themes={len(model.themes)} prefs={len(model.preferences)} "
        f"unresolved={len(model.unresolved)} signals={len(model.source_signals)}",
        file=sys.stderr,
    )


def _cli() -> int:
    ap = argparse.ArgumentParser(
        prog="mikai_brain.user_model",
        description="Compile USER_MODEL.md from the substrate.",
    )
    ap.add_argument("action", nargs="?", default="build", choices=["build", "show"])
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be written; skip persistence")
    args = ap.parse_args()

    if args.action == "show":
        model = load()
        if model is None:
            print("no USER_MODEL yet — run `build`", file=sys.stderr)
            return 1
        _print_model(model)
        return 0

    model = build()
    if args.dry_run:
        print("[user_model] DRY RUN — no files written", file=sys.stderr)
        _print_model(model)
        return 0

    md_path, json_path = save(model)
    _print_model(model)
    print(f"[user_model] wrote {md_path}", file=sys.stderr)
    print(f"[user_model] wrote {json_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

#!/usr/bin/env python3
"""
accrete.py — CANON-5 density enrichment (criterion 2 of consolidation completeness).

When a source's body discusses an existing canonical from a NEW angle,
canonicalization won't touch the canonical (no new slug is proposed) —
the canonical body stays static. Accretion fills this gap: for each
existing canonical the source references via wikilink, decide whether
the source has new material about the concept, and if so append a
synthesized paragraph to the canonical (fence-marked, reversible).

Two-tier gate to bound LLM cost:
  1. Cosine gate: embed source body vs canonical body; only proceed if
     cosine ≥ SOURCE_CANONICAL_FLOOR (default 0.55). Cheap.
  2. LLM adjudication: "Does the source contain material about <concept>
     that isn't already on the canonical? If yes, produce a 1-3 paragraph
     synthesized addition. If no, skip." Returns JSON verdict.

Verdicts:
  append → append body to canonical between fence markers
  skip   → no-op

Every append is logged to `.accretion-log.jsonl` for reversibility;
`.accretion-archive/` snapshots canonical body pre-append.
Kill-switch: MIKAI_ACCRETE=0.

Usage (per source after ingest):
    python accrete.py --project ~/.mikai/wiki-mikai-parallel-test \
      --source-summary wiki/sources/<slug>.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dedup_embed import load_or_embed, normalize, cosine_pre_normalized  # noqa: E402

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

DEFAULT_SOURCE_CANONICAL_FLOOR = 0.55
DEFAULT_MAX_ACCRETION_TARGETS = 5  # per source; hard cap for cost control
LLM_TIMEOUT_S = 180
CACHE_DIR_NAME = ".embed-cache"
LOG_FILE = ".accretion-log.jsonl"
ARCHIVE_DIR = ".accretion-archive"

FENCE_OPEN_TMPL = "<!-- MIKAI-ACCRETION-FROM: {source} -->"
FENCE_CLOSE_TMPL = "<!-- MIKAI-ACCRETION-END: {source} -->"


def parse_frontmatter(text: str) -> tuple[dict, int]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, 0
    fields: dict = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.startswith("#") or ":" not in line or line.startswith(" "):
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if val.startswith("[") and val.endswith("]"):
            fields[key] = [x.strip().strip("\"'") for x in val[1:-1].split(",") if x.strip()]
        else:
            fields[key] = val
    return fields, m.end()


def extract_wikilink_targets(body: str) -> list[str]:
    targets: list[str] = []
    for raw in WIKILINK_RE.findall(body):
        t = raw.split("|", 1)[0].strip()
        if t:
            targets.append(t)
    return targets


def resolve_target_to_path(project: Path, target: str) -> Path | None:
    """Convert `[[concepts/foo]]` or `[[foo]]` to a canonical page path.
    Also honors aliases-index."""
    idx_path = project / "wiki" / ".aliases-index.json"
    aliases_idx: dict = {}
    try:
        aliases_idx = json.loads(idx_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    # Split kind/slug
    if "/" in target:
        kind, slug = target.split("/", 1)
        p = project / "wiki" / kind / f"{slug}.md"
        if p.exists():
            return p
        # try alias resolution
        canonical = aliases_idx.get(slug)
        if canonical:
            p = project / "wiki" / kind / f"{canonical}.md"
            if p.exists():
                return p
        return None
    # unqualified — try all kinds
    for kind in ("concepts", "entities", "wisdom"):
        p = project / "wiki" / kind / f"{target}.md"
        if p.exists():
            return p
        canonical = aliases_idx.get(target)
        if canonical:
            p = project / "wiki" / kind / f"{canonical}.md"
            if p.exists():
                return p
    return None


def is_canonical_page(text: str) -> bool:
    """True if page has frontmatter AND no retired_to redirect."""
    fields, _ = parse_frontmatter(text)
    if not fields:
        return False
    if fields.get("retired_to"):
        return False
    return True


def build_adjudication_prompt(
    canonical_slug: str,
    canonical_title: str,
    canonical_body: str,
    source_slug: str,
    source_body: str,
) -> str:
    return f"""You are deciding whether a source contains material about a concept that isn't already on the canonical page. Your job is to enrich the canonical when justified, and to skip when the source has nothing new to add.

## Canonical page: `{canonical_slug}`
Title: {canonical_title}

Current body (first 3000 chars):
{canonical_body[:3000]}

## Source: `{source_slug}` (first 4000 chars)
{source_body[:4000]}

## Task
Does the source contain substantive material about `{canonical_title}` that is NOT already on the canonical page? Specifically:
- A new angle or framing that expands the concept's coverage
- A concrete example or case study the canonical lacks
- A distinction, mechanism, or trade-off not currently noted
- Attribution / provenance the canonical is missing

If YES, produce a 1-3 paragraph addition in Markdown that fits the canonical's voice. Use existing wikilinks where appropriate. Cite the source at the end via `— from [[sources/{source_slug}]]`.

If NO (source is redundant, only mentions the concept in passing, or contradicts the canonical without adding), skip.

Return ONE JSON object, no fences:
{{
  "action": "append" | "skip",
  "content": "<markdown to append, or empty if skip>",
  "reasoning": "one sentence"
}}"""


def call_claude(prompt: str, model: str) -> dict:
    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", model, "--output-format", "json"],
            input=prompt, capture_output=True, text=True, timeout=LLM_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"error": f"claude timeout/missing: {e}"}
    if proc.returncode != 0:
        return {"error": f"claude exit {proc.returncode}: {proc.stderr[:300]}"}
    try:
        outer = json.loads(proc.stdout)
        text = outer.get("result", "").strip()
    except json.JSONDecodeError as e:
        return {"error": f"outer JSON parse: {e}"}
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        return {"error": f"inner JSON parse: {e}", "raw": text[:300]}


def apply_append(
    canonical_path: Path,
    source_slug: str,
    content: str,
    archive_dir: Path,
) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    archive = archive_dir / f"{canonical_path.stem}.pre-accretion-from-{source_slug}.{stamp}.md"
    archive.write_text(canonical_path.read_text(encoding="utf-8"), encoding="utf-8")

    text = canonical_path.read_text(encoding="utf-8")
    open_f = FENCE_OPEN_TMPL.format(source=source_slug)
    close_f = FENCE_CLOSE_TMPL.format(source=source_slug)
    section = f"\n\n{open_f}\n{content.strip()}\n{close_f}\n"
    canonical_path.write_text(text.rstrip() + section, encoding="utf-8")
    return archive


def append_log(project: Path, entry: dict) -> None:
    (project / LOG_FILE).open("a", encoding="utf-8").write(
        json.dumps(entry, sort_keys=True) + "\n"
    )


def main() -> int:
    if os.environ.get("MIKAI_ACCRETE", "1") == "0":
        print(json.dumps({"skipped": "MIKAI_ACCRETE=0"}))
        return 0

    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--source-summary", required=True,
                    help="path (relative or absolute) to wiki/sources/<slug>.md")
    ap.add_argument("--top-n", type=int, default=DEFAULT_MAX_ACCRETION_TARGETS,
                    help="max canonicals to accrete per source (ranked by cosine)")
    ap.add_argument("--cosine-floor", type=float, default=DEFAULT_SOURCE_CANONICAL_FLOOR)
    ap.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ap.add_argument("--ollama-model", default="nomic-embed-text")
    ap.add_argument("--model", default="claude-sonnet-4-5")
    ap.add_argument("--dry-run", action="store_true",
                    help="return verdict JSON without applying")
    args = ap.parse_args()

    project = Path(args.project).expanduser().resolve()
    src_path = Path(args.source_summary)
    if not src_path.is_absolute():
        src_path = (project / src_path).resolve()
    if not src_path.exists():
        print(json.dumps({"error": f"source not found: {src_path}"}))
        return 1

    src_text = src_path.read_text(encoding="utf-8")
    src_fields, src_end = parse_frontmatter(src_text)
    src_body = src_text[src_end:]
    src_slug = src_path.stem

    # Extract wikilink targets, resolve to canonical paths
    raw_targets = extract_wikilink_targets(src_body)
    seen: set[str] = set()
    canonical_pages: list[tuple[str, Path]] = []
    for t in raw_targets:
        p = resolve_target_to_path(project, t)
        if p is None or str(p) in seen:
            continue
        seen.add(str(p))
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if not is_canonical_page(text):
            continue
        # Skip source-summary self references and administrative pages
        if p.parent.name not in ("concepts", "entities", "wisdom"):
            continue
        canonical_pages.append((t, p))

    if not canonical_pages:
        print(json.dumps({"source": src_slug, "targets": 0, "accreted": 0}))
        return 0

    # Cosine gate: rank by cosine(source_body, canonical_body)
    cache_dir = project / CACHE_DIR_NAME
    try:
        src_vec_n = normalize(load_or_embed(args.ollama_host, args.ollama_model, src_body, cache_dir))
    except Exception as e:
        print(json.dumps({"error": f"source embed failed: {e}"}))
        return 1

    scored: list[tuple[float, str, Path]] = []
    for target, cpath in canonical_pages:
        ctext = cpath.read_text(encoding="utf-8")
        _, cend = parse_frontmatter(ctext)
        cbody = ctext[cend:]
        if len(cbody.strip()) < 100:
            continue
        try:
            cvec_n = normalize(load_or_embed(args.ollama_host, args.ollama_model, cbody, cache_dir))
        except Exception:
            continue
        score = cosine_pre_normalized(src_vec_n, cvec_n)
        scored.append((score, target, cpath))

    scored.sort(key=lambda t: t[0], reverse=True)
    above_floor = [x for x in scored if x[0] >= args.cosine_floor][: args.top_n]

    outcomes: list[dict] = []
    for score, target, cpath in above_floor:
        ctext = cpath.read_text(encoding="utf-8")
        cfields, cend = parse_frontmatter(ctext)
        cbody = ctext[cend:]
        canonical_slug = f"{cpath.parent.name}/{cpath.stem}"
        title = cfields.get("title") or cpath.stem
        title = title if isinstance(title, str) else cpath.stem

        prompt = build_adjudication_prompt(
            canonical_slug=canonical_slug,
            canonical_title=title,
            canonical_body=cbody,
            source_slug=src_slug,
            source_body=src_body,
        )
        verdict = call_claude(prompt, args.model)
        outcome = {
            "canonical": canonical_slug,
            "cosine": round(score, 4),
            "verdict": verdict,
        }
        if verdict.get("error"):
            outcomes.append(outcome)
            continue

        action = verdict.get("action", "skip")
        if action == "append" and not args.dry_run:
            content = verdict.get("content", "").strip()
            if content:
                archive = apply_append(cpath, src_slug, content, project / ARCHIVE_DIR)
                outcome["applied"] = "append"
                outcome["archive"] = str(archive.relative_to(project))
                append_log(project, {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": src_slug,
                    "canonical": canonical_slug,
                    "cosine": round(score, 4),
                    "chars_appended": len(content),
                    "archive": str(archive.relative_to(project)),
                    "reasoning": verdict.get("reasoning", ""),
                })
        elif action == "append" and args.dry_run:
            outcome["applied"] = f"DRY-RUN:append (chars={len(verdict.get('content', ''))})"
        else:
            outcome["applied"] = "skip"
        outcomes.append(outcome)

    print(json.dumps({
        "source": src_slug,
        "targets": len(canonical_pages),
        "considered": len(above_floor),
        "outcomes": outcomes,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

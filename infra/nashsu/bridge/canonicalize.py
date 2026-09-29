#!/usr/bin/env python3
"""
canonicalize.py — Phase 2 of Wikipedia-redirect canonicalization.

For a single just-minted wiki page, run the CONSOLIDATION_ARCHITECTURE.md §5a
three-tier resolution pipeline and apply the verdict:

    1. Exact / normalized alias-table match (from wiki/.aliases-index.json)
    2. Embedding kNN over existing pages (nomic-embed-text via Ollama, reuses
       ~/.mikai/wiki-mikai-parallel-test/.embed-cache/ built by pre_extract_topk.py)
    3. LLM merge adjudication (`claude -p`, JSON verdict) — invoked only if
       tier 1 misses AND tier 2 returns candidates above the cosine floor.

Verdicts and their effects:
    mint   → no-op; the just-written page stays as-is
    merge  → append body to canonical (with fence markers for reversibility),
             add proposed slug to canonical's aliases: frontmatter, delete
             the just-written file, write a retire stub in its place
    rename → move file to canonical slug, then treat as merge

Every non-mint verdict is logged to `.canonicalization-log.jsonl` in the
vault. The body prior to merge is archived to `.canonicalization-archive/`
so the Phase 4 undo tool can reverse it.

Kill-switch: env MIKAI_CANONICALIZE=0 → exits with mint verdict and no work.

Usage (called per-page after autoIngest returns):
    python canonicalize.py --project ~/.mikai/wiki-mikai-parallel-test \
      --page wiki/concepts/proposed-slug.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# Reuse the existing embedding + cache infrastructure so cache lookups
# hit — same _sha keying and raw-list cache format used by dedup_embed
# and pre_extract_topk. Prevents the "0 candidates" false-negative that
# would occur if we hashed a different proxy text or a different value shape.
sys.path.insert(0, str(Path(__file__).parent))
from dedup_embed import load_or_embed, normalize, cosine_pre_normalized  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────

DEFAULT_TOP_K = 10
DEFAULT_COSINE_FLOOR = 0.75
LLM_TIMEOUT_S = 180
CACHE_DIR_NAME = ".embed-cache"
ALIASES_INDEX = "wiki/.aliases-index.json"
LOG_FILE = ".canonicalization-log.jsonl"
ARCHIVE_DIR = ".canonicalization-archive"

MERGE_FENCE_OPEN = "<!-- MIKAI-CANONICALIZE-MERGE-FROM: {slug} -->"
MERGE_FENCE_CLOSE = "<!-- MIKAI-CANONICALIZE-MERGE-END: {slug} -->"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
LIST_INLINE_RE = re.compile(r"^\[(.*)\]$")


# ── Frontmatter helpers (mirror build_aliases.py) ─────────────────────────

def parse_frontmatter(text: str) -> tuple[dict[str, str | list[str]], int]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, 0
    body = m.group(1)
    fields: dict[str, str | list[str]] = {}
    for line in body.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if ":" not in line or line.startswith(" "):
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        lm = LIST_INLINE_RE.match(val)
        if lm:
            items = [x.strip().strip("\"'") for x in lm.group(1).split(",") if x.strip()]
            fields[key] = items
        else:
            fields[key] = val
    return fields, m.end()


def render_list(items: list[str]) -> str:
    return "[" + ", ".join(sorted(set(items))) + "]"


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


# ── Embedding + cosine (reuses pre_extract_topk cache layout) ─────────────

def cache_key_for_text(text: str, model: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\n")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


def load_cached_embedding(cache_dir: Path, key: str) -> list[float] | None:
    p = cache_dir / f"{key}.json"
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return obj.get("embedding")
    except (OSError, json.JSONDecodeError):
        return None


def save_cached_embedding(cache_dir: Path, key: str, embedding: list[float]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{key}.json").write_text(
        json.dumps({"embedding": embedding}), encoding="utf-8"
    )


def embed_via_ollama(text: str, host: str, model: str) -> list[float]:
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/embeddings",
        data=json.dumps({"model": model, "prompt": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        obj = json.loads(resp.read().decode("utf-8"))
    return obj["embedding"]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def proxy_text_for_page(fields: dict, body: str) -> str:
    """title + first paragraph — same proxy pre_extract_topk uses."""
    title = fields.get("title") or ""
    if isinstance(title, list):
        title = " ".join(title)
    body = body.strip()
    first_para = body.split("\n\n", 1)[0][:800]
    return f"{title}\n\n{first_para}".strip()


# ── Tier 1: alias-table lookup ────────────────────────────────────────────

def normalize_for_lookup(s: str) -> str:
    return slugify(s)


def tier1_alias_lookup(
    proposed_slug: str,
    proposed_title: str | None,
    aliases_index: dict[str, str],
) -> str | None:
    """Return canonical slug if proposed matches an alias, else None."""
    candidates = {proposed_slug}
    if proposed_title:
        candidates.add(slugify(proposed_title))
    for cand in candidates:
        norm = normalize_for_lookup(cand)
        if norm in aliases_index:
            target = aliases_index[norm]
            # exclude self-map (proposed slug already IS the canonical)
            if target != proposed_slug:
                return target
    return None


# ── Tier 2: embedding kNN over existing canonical pages ───────────────────

def tier2_embedding_knn(
    proposed_page_path: Path,
    proposed_body: str,
    project: Path,
    aliases_index: dict[str, str],
    top_k: int,
    cosine_floor: float,
    ollama_host: str,
    ollama_model: str,
) -> list[tuple[str, float]]:
    """kNN over existing (non-retired) concept/entity/wisdom pages.

    Uses `dedup_embed.load_or_embed` for identical cache-key + raw-list
    format with pre_extract_topk / dedup_embed. Embeds the full page body
    (not a proxy) to hit the same cache entries those tools populated.

    Returns (slug, cosine) pairs sorted descending by cosine, filtered to
    cosine >= cosine_floor and excluding the proposed page itself.
    """
    cache_dir = project / CACHE_DIR_NAME
    proposed_slug = proposed_page_path.stem

    proposed_emb = load_or_embed(ollama_host, ollama_model, proposed_body, cache_dir)
    proposed_n = normalize(proposed_emb)

    scores: list[tuple[str, float]] = []
    for kind in ("concepts", "entities", "wisdom"):
        d = project / "wiki" / kind
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            slug = p.stem
            if slug == proposed_slug:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            fields, end = parse_frontmatter(text)
            if not fields or fields.get("retired_to"):
                continue
            cand_body = text[end:]
            if len(cand_body.strip()) < 100:  # skip stubs — same filter as dedup_embed
                continue
            try:
                emb = load_or_embed(ollama_host, ollama_model, cand_body, cache_dir)
            except Exception:
                continue
            score = cosine_pre_normalized(proposed_n, normalize(emb))
            if score >= cosine_floor:
                scores.append((f"{kind}/{slug}", score))

    scores.sort(key=lambda t: t[1], reverse=True)
    return scores[:top_k]


# ── Tier 3: LLM merge adjudication ────────────────────────────────────────

def build_adjudication_prompt(
    proposed_slug: str,
    proposed_title: str,
    proposed_body_preview: str,
    candidates: list[tuple[str, float]],
    candidate_pages: dict[str, tuple[str, str, list[str]]],
) -> str:
    """Render the JSON-verdict prompt. candidate_pages: slug → (title, preview, aliases)."""
    parts: list[str] = []
    parts.append(
        "You are adjudicating a canonicalization decision for a personal wiki. "
        "A source ingest just proposed a new page. Existing pages with high "
        "embedding similarity are shown below. Your job: decide whether the "
        "proposed page names the SAME concept as one of the candidates (merge "
        "or rename), or is a genuinely new concept (mint)."
    )
    parts.append("")
    parts.append("## Proposed new page")
    parts.append(f"- **Slug**: `{proposed_slug}`")
    parts.append(f"- **Title**: {proposed_title}")
    parts.append(f"- **Body preview** (first 600 chars):\n\n{proposed_body_preview[:600]}")
    parts.append("")
    parts.append("## Candidate existing pages (top-K by embedding cosine)")
    for slug, score in candidates:
        cand_title, cand_prev, cand_aliases = candidate_pages.get(slug, ("", "", []))
        alias_note = f" — also known as: {', '.join(cand_aliases)}" if cand_aliases else ""
        parts.append(f"### `{slug}` (cosine={score:.3f}){alias_note}")
        parts.append(f"**Title**: {cand_title}")
        parts.append(f"**Body preview**: {cand_prev[:400]}")
        parts.append("")
    parts.append("## Verdict")
    parts.append(
        "Return ONE JSON object with these fields:\n"
        "  action: 'mint' | 'merge' | 'rename'\n"
        "  canonical: slug of the canonical page (for merge/rename; null for mint)\n"
        "  reasoning: one sentence explaining the decision\n"
    )
    parts.append("")
    parts.append(
        "Decision rules:\n"
        "- Use `merge` when the proposed page is a SYNONYM or NEAR-DUPLICATE of a "
        "candidate — same concept, same content span, only the name differs. The "
        "proposed body will be appended to the canonical.\n"
        "- Use `rename` when the proposed page IS the canonical topic and the "
        "candidate is actually a sub-concept or narrower framing — the proposed "
        "page becomes the canonical, the candidate would eventually get retired "
        "(NOT YET; we only handle the current write).\n"
        "- Use `mint` when the proposed page is a distinct concept, even if "
        "thematically adjacent. High cosine can mean 'related topic,' not 'same "
        "topic.' When in doubt, mint.\n"
    )
    parts.append("")
    parts.append("Reply with ONE JSON object, no fences, no prose.")
    return "\n".join(parts)


def call_claude_adjudicate(prompt: str, model: str) -> dict:
    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", model, "--output-format", "json"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=LLM_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"error": f"claude timeout/missing: {e}"}
    if proc.returncode != 0:
        return {"error": f"claude exit {proc.returncode}: {proc.stderr[:300]}"}
    try:
        outer = json.loads(proc.stdout)
        text = outer.get("result", "").strip()
    except json.JSONDecodeError as e:
        return {"error": f"outer JSON parse: {e}", "raw": proc.stdout[:300]}
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


# ── Verdict application (merge / rename / mint) ───────────────────────────

def read_page(path: Path) -> tuple[dict, int, str, str]:
    text = path.read_text(encoding="utf-8")
    fields, end = parse_frontmatter(text)
    return fields, end, text[:end], text[end:]


def append_body_to_canonical(
    canonical_path: Path,
    loser_slug: str,
    loser_body: str,
) -> None:
    """Append loser body to canonical between fence markers for reversibility."""
    text = canonical_path.read_text(encoding="utf-8")
    open_f = MERGE_FENCE_OPEN.format(slug=loser_slug)
    close_f = MERGE_FENCE_CLOSE.format(slug=loser_slug)
    section = f"\n\n{open_f}\n{loser_body.strip()}\n{close_f}\n"
    canonical_path.write_text(text.rstrip() + section, encoding="utf-8")


def add_alias_to_canonical(canonical_path: Path, new_alias: str) -> None:
    text = canonical_path.read_text(encoding="utf-8")
    fields, end = parse_frontmatter(text)
    if not fields:
        return
    existing = fields.get("aliases", [])
    if not isinstance(existing, list):
        existing = []
    if new_alias in existing:
        return
    merged = sorted(set(existing) | {new_alias})
    fm_block = text[:end]
    body = text[end:]
    line = f"aliases: {render_list(merged)}"
    if re.search(r"^aliases:\s*", fm_block, re.MULTILINE):
        fm_block = re.sub(r"^aliases:\s*.*$", line, fm_block, count=1, flags=re.MULTILINE)
    else:
        fm_block = re.sub(r"(\n)---\n$", rf"\1{line}\n---\n", fm_block, count=1)
    canonical_path.write_text(fm_block + body, encoding="utf-8")


def archive_loser(loser_path: Path, archive_dir: Path) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    dest = archive_dir / f"{loser_path.stem}.{stamp}.md"
    dest.write_text(loser_path.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def write_retire_stub(loser_path: Path, canonical_slug: str, original_title: str, kind: str) -> None:
    canonical_kind_slug = canonical_slug if "/" in canonical_slug else f"{kind}/{canonical_slug}"
    stub = (
        f"---\n"
        f"type: {kind[:-1] if kind.endswith('s') else kind}\n"
        f'title: "{original_title}"\n'
        f"retired_to: {canonical_slug.split('/', 1)[-1]}\n"
        f"---\n\n"
        f"This page has been merged into [[{canonical_kind_slug}]].\n"
    )
    loser_path.write_text(stub, encoding="utf-8")


def append_log(project: Path, entry: dict) -> None:
    log_path = project / LOG_FILE
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def refresh_aliases_index(project: Path, alias: str, canonical: str) -> None:
    idx_path = project / ALIASES_INDEX
    try:
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        idx = {}
    idx[alias] = canonical
    idx_path.write_text(json.dumps(idx, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ── Main resolver ─────────────────────────────────────────────────────────

def resolve_and_apply(args: argparse.Namespace) -> dict:
    project = Path(args.project).expanduser().resolve()
    page = Path(args.page)
    if not page.is_absolute():
        page = (project / page).resolve()
    if not page.exists():
        return {"action": "mint", "reason": "page-not-found", "path": str(page)}

    kind = page.parent.name  # "concepts" | "entities" | "wisdom"
    if kind not in ("concepts", "entities", "wisdom"):
        return {"action": "mint", "reason": "unsupported-kind", "kind": kind}

    fields, end, _fm_block, body = read_page(page)
    if not fields:
        return {"action": "mint", "reason": "no-frontmatter"}
    if fields.get("retired_to"):
        return {"action": "mint", "reason": "already-retired-stub"}

    proposed_slug = page.stem
    proposed_title = fields.get("title") if isinstance(fields.get("title"), str) else proposed_slug

    # Load alias index
    idx_path = project / ALIASES_INDEX
    try:
        aliases_index = json.loads(idx_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        aliases_index = {}

    # Tier 1: exact / normalized alias match
    canonical = tier1_alias_lookup(proposed_slug, proposed_title, aliases_index)
    tier: int
    candidates: list[tuple[str, float]] = []
    verdict: dict

    if canonical:
        tier = 1
        verdict = {"action": "merge", "canonical": canonical, "reasoning": "tier1-alias-hit"}
    else:
        # Tier 2: embedding kNN — full body, matching pre_extract_topk cache convention
        candidates = tier2_embedding_knn(
            page,
            body,
            project,
            aliases_index,
            top_k=args.top_k,
            cosine_floor=args.cosine_floor,
            ollama_host=args.ollama_host,
            ollama_model=args.ollama_model,
        )
        if not candidates:
            tier = 2
            verdict = {"action": "mint", "reasoning": "tier2-no-candidates-above-floor"}
        else:
            # Tier 3: LLM adjudication
            tier = 3
            cand_pages: dict[str, tuple[str, str, list[str]]] = {}
            for slug_kinded, _score in candidates:
                cslug = slug_kinded.split("/", 1)[-1]
                ckind = slug_kinded.split("/", 1)[0]
                cpath = project / "wiki" / ckind / f"{cslug}.md"
                try:
                    ctext = cpath.read_text(encoding="utf-8")
                except OSError:
                    continue
                cfields, cend = parse_frontmatter(ctext)
                ctitle = cfields.get("title") if isinstance(cfields.get("title"), str) else cslug
                cprev = ctext[cend:].strip().split("\n\n", 1)[0]
                caliases = cfields.get("aliases", [])
                if not isinstance(caliases, list):
                    caliases = []
                cand_pages[slug_kinded] = (ctitle, cprev, caliases)

            prompt = build_adjudication_prompt(
                proposed_slug=proposed_slug,
                proposed_title=proposed_title,
                proposed_body_preview=body.strip(),
                candidates=candidates,
                candidate_pages=cand_pages,
            )
            verdict = call_claude_adjudicate(prompt, args.model)
            if "error" in verdict:
                # fail-safe: any adjudication error → mint (don't corrupt vault)
                verdict = {"action": "mint", "reasoning": f"llm-error: {verdict['error'][:200]}"}

    # Apply verdict
    action = verdict.get("action", "mint")
    outcome: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "proposed_slug": proposed_slug,
        "proposed_title": proposed_title,
        "kind": kind,
        "tier": tier,
        "candidates": [{"slug": s, "cosine": round(c, 4)} for s, c in candidates],
        "verdict": verdict,
    }

    # Dry-run short-circuit: return the verdict without any writes (no
    # append_log, no archive, no fence-insert, no alias mutation). Used by
    # the batch harness that reports on the existing vault before deciding
    # whether to apply.
    if getattr(args, "dry_run", False):
        outcome["applied"] = f"DRY-RUN:{action}"
        return outcome

    if action == "mint":
        outcome["applied"] = "mint"
        # only log non-trivial mints (tier 2+ with candidates that got adjudicated)
        if tier >= 3:
            append_log(project, outcome)
        return outcome

    canonical_slug = verdict.get("canonical") or ""
    if not canonical_slug:
        outcome["applied"] = "mint-fallback-no-canonical"
        outcome["error"] = "action=merge/rename but no canonical slug returned"
        append_log(project, outcome)
        return outcome

    canonical_kind = canonical_slug.split("/", 1)[0] if "/" in canonical_slug else kind
    canonical_bare = canonical_slug.split("/", 1)[-1]
    canonical_path = project / "wiki" / canonical_kind / f"{canonical_bare}.md"
    if not canonical_path.exists():
        outcome["applied"] = "mint-fallback-canonical-missing"
        outcome["error"] = f"canonical {canonical_slug} not found on disk"
        append_log(project, outcome)
        return outcome

    if action == "rename":
        # rename semantics: the just-written slug SHOULD BE the canonical.
        # For phase-2 v1 we conservatively downgrade rename to merge — the
        # LLM adjudication rules explicitly avoid retiring existing pages
        # from this hook. Log the intent; apply as merge.
        outcome["rename_downgraded_to_merge"] = True

    # Archive loser (for reversibility)
    archive_path = archive_loser(page, project / ARCHIVE_DIR)
    outcome["archive"] = str(archive_path.relative_to(project))

    # Append body to canonical (fenced for undo)
    append_body_to_canonical(canonical_path, proposed_slug, body)

    # Add alias to canonical. Track EXACTLY which aliases we added so
    # canonicalize_undo.py can remove precisely those and no others —
    # otherwise a slugified-title alias that differs from proposed_slug
    # (e.g. "Canary 2" → "canary-2" vs proposed_slug "canary2") stays
    # behind on undo and breaks byte-identical round-trip.
    aliases_added: list[str] = []
    add_alias_to_canonical(canonical_path, proposed_slug)
    aliases_added.append(proposed_slug)
    proposed_title_slug = slugify(proposed_title) if isinstance(proposed_title, str) else ""
    if proposed_title_slug and proposed_title_slug != proposed_slug:
        add_alias_to_canonical(canonical_path, proposed_title_slug)
        aliases_added.append(proposed_title_slug)

    # Write retire stub in place of loser
    title_str = proposed_title if isinstance(proposed_title, str) else proposed_slug
    write_retire_stub(page, canonical_slug, title_str, kind)

    # Refresh aliases index — mirror the exact set we added
    for alias in aliases_added:
        refresh_aliases_index(project, alias, canonical_bare)

    outcome["applied"] = "merge"
    outcome["canonical_path"] = str(canonical_path.relative_to(project))
    outcome["aliases_added"] = aliases_added
    append_log(project, outcome)
    return outcome


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> int:
    if os.environ.get("MIKAI_CANONICALIZE", "1") == "0":
        print(json.dumps({"action": "mint", "reasoning": "MIKAI_CANONICALIZE=0"}))
        return 0

    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--page", required=True, help="relative or absolute path to newly-written page")
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ap.add_argument("--cosine-floor", type=float, default=DEFAULT_COSINE_FLOOR)
    ap.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ap.add_argument("--ollama-model", default="nomic-embed-text")
    ap.add_argument("--model", default="claude-sonnet-4-5", help="claude -p model for adjudication")
    ap.add_argument("--dry-run", action="store_true",
                    help="return verdict JSON without applying (no writes to canonical, loser, or index)")
    args = ap.parse_args()

    result = resolve_and_apply(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""ARCH-034 write-time semantic gate.

For each GENUINELY NEW entity/concept/wisdom mention nashsu's stage-1
analysis proposes, decide whether it should really become a new page or be
redirected to an existing one, BEFORE stage-2 generation writes it:

  Tier 1 (cosine >= --tier1-threshold, default 0.95)
      Hard redirect. No LLM call — the mention embedding is close enough
      to an existing page's title+first-paragraph embedding that it is
      almost certainly the same thing.

  Tier 2 (--tier2-threshold <= cosine < --tier1-threshold, default 0.85-0.95)
      Ambiguous band. Ask `claude -p` to adjudicate MERGE vs KEEP, given
      the mention description and the matched page's full body. MERGE
      redirects; KEEP allows the new page. Skippable via --tier2-llm 0
      (env MIKAI_GATE_TIER2_LLM=0) to test Tier 1 in isolation.

  Tier 3 (cosine < --tier2-threshold)
      Passthrough. No change.

Existing-page embeddings reuse the same cache and (slug + title + first
paragraph) proxy convention as test_write_time_gate.py's research probe.
Mention embeddings use (proposed_slug + one_line_description) per ARCH-034.

Report-only against the vault: this script never writes wiki files. It
reads mentions + existing pages and writes a decisions JSON that the
ingest.ts caller uses to rewrite the stage-1 analysis text before stage-2.

Degrades to Tier 3 (pass-through) with a warning if Ollama is unreachable
or a specific mention fails to embed. Never raises to block ingest.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dedup_embed import (  # noqa: E402
    ollama_embed,  # noqa: F401  (re-exported for callers that patch this module)
    load_or_embed,
    cosine_pre_normalized,
    normalize,
)

_FRONTMATTER_RX = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_TITLE_RX = re.compile(r"^title:\s*(.+)$", re.MULTILINE)
_RETIRED_RX = re.compile(r"^retired_to\s*:", re.MULTILINE)

PAGE_KINDS = ("concepts", "entities", "wisdom")

JUDGE_PROMPT = """You are auditing a knowledge-base at write time, deciding whether a
NEWLY PROPOSED page duplicates an EXISTING page.

NEW MENTION (not yet written, proposed slug: {proposed_slug})
{mention_text}

EXISTING PAGE: {matched_slug}
{existing_body}

Output JSON with exactly these fields:
{{
  "verdict": "MERGE" | "KEEP",
  "reasoning": "<one sentence>",
  "confidence": <0.0-1.0>
}}

MERGE = the new mention is the same concept/entity/wisdom as the existing page
under a different name — redirect it to the existing page instead of creating
a new one. KEEP = related but genuinely distinct; the new page should be created.
"""


def _sha_free_key(text: str, model: str) -> str:
    # load_or_embed hashes internally; this helper just documents the
    # cache key inputs so callers don't need to reimplement hashing.
    return f"{model}\n{text}"


def page_proxy(path: Path) -> str | None:
    """title + first paragraph after frontmatter — proxy for what a
    write-time gate would score an existing page against. None for
    retired stubs or unparseable files."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _FRONTMATTER_RX.match(text)
    if not m:
        return None
    frontmatter = m.group(1)
    if _RETIRED_RX.search(frontmatter):
        return None
    body = text[m.end():]
    title_m = _TITLE_RX.search(frontmatter)
    title = title_m.group(1).strip().strip('"').strip("'") if title_m else path.stem
    paras = [p.strip() for p in body.split("\n\n") if p.strip()]
    first_para = ""
    for p in paras:
        if p.startswith("#"):
            continue
        first_para = p
        break
    proxy = f"{title}\n\n{first_para}".strip()
    return proxy if len(proxy) > 10 else None


def page_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _FRONTMATTER_RX.match(text)
    return text[m.end():].strip() if m else text.strip()


def load_existing_pages(wiki_dir: Path) -> dict:
    """slug -> {"path": Path, "proxy": str, "kind": str} for every live
    (non-retired) concept/entity/wisdom page. slug is bare (no kind
    prefix) since ARCH-034 scores mentions against ALL kinds together."""
    pages: dict[str, dict] = {}
    for kind in PAGE_KINDS:
        d = wiki_dir / kind
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            proxy = page_proxy(p)
            if proxy is None:
                continue
            slug = p.stem
            if slug in pages:
                # Same bare slug in two kind dirs — keep first, note nothing;
                # collision is rare and not this gate's concern to resolve.
                continue
            pages[slug] = {"path": p, "proxy": proxy, "kind": kind}
    return pages


def ensure_user_path() -> None:
    extra = (
        Path.home() / ".local" / "bin",
        Path.home() / ".superset" / "bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    )
    parts = os.environ.get("PATH", "").split(os.pathsep)
    for p in extra:
        if p.is_dir() and str(p) not in parts:
            parts.append(str(p))
    os.environ["PATH"] = os.pathsep.join(parts)


def claude_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}


def call_claude(prompt: str, model: str, timeout: float = 120.0) -> str:
    ensure_user_path()
    argv = ["claude", "-p", "--model", model, "--output-format", "json", "--tools", ""]
    proc = subprocess.run(
        argv, input=prompt, capture_output=True, text=True, timeout=timeout, env=claude_env(),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed (rc={proc.returncode}): {proc.stderr[:500]}")
    envelope = json.loads(proc.stdout)
    result = envelope.get("result")
    if not isinstance(result, str):
        raise RuntimeError(f"claude -p json envelope missing 'result': {proc.stdout[:500]}")
    return result


def extract_json_object(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object found in: {text[:300]}")
    return json.loads(text[start:end + 1])


def adjudicate(
    proposed_slug: str,
    mention_text: str,
    matched_slug: str,
    matched_path: Path,
    model: str,
) -> dict:
    existing_body = page_body(matched_path)
    prompt = JUDGE_PROMPT.format(
        proposed_slug=proposed_slug,
        mention_text=mention_text,
        matched_slug=matched_slug,
        existing_body=existing_body[:6000],
    )
    raw = call_claude(prompt, model=model)
    parsed = extract_json_object(raw)
    return {
        "verdict": parsed.get("verdict"),
        "reasoning": parsed.get("reasoning"),
        "confidence": parsed.get("confidence"),
    }


def run_gate(
    mentions_payload: dict,
    tier1_threshold: float,
    tier2_threshold: float,
    tier2_llm_enabled: bool,
    model: str,
    embed_model: str,
    host: str,
    cache_dir: Path,
) -> dict:
    source = mentions_payload.get("source", "")
    existing_pages_dir = Path(mentions_payload["existing_pages_dir"]).expanduser()
    mentions = mentions_payload.get("mentions", [])

    t0 = time.time()
    warnings: list[str] = []

    existing_pages = load_existing_pages(existing_pages_dir)
    slugs = list(existing_pages.keys())

    embeds_ok = True
    if slugs:
        for i, slug in enumerate(slugs, 1):
            info = existing_pages[slug]
            try:
                info["vec"] = normalize(load_or_embed(host, embed_model, info["proxy"], cache_dir))
            except (urllib.error.URLError, RuntimeError, ConnectionError, OSError) as exc:
                embeds_ok = False
                warnings.append(f"ollama embed failed for existing page {slug}: {exc}")
                info["vec"] = None

    gate_hits: dict[str, list] = {
        "tier1_hard": [], "tier2_llm_merge": [], "tier2_llm_keep": [], "tier3_passthrough": [],
    }
    overrides: dict[str, dict] = {}

    for mention in mentions:
        kind = mention.get("kind", "concept")
        proposed_slug = mention["proposed_slug"]
        description = mention.get("one_line_description", "")
        mention_text = f"{proposed_slug}\n\n{description}".strip()

        if not embeds_ok or not slugs:
            gate_hits["tier3_passthrough"].append(
                {"proposed_slug": proposed_slug, "kind": kind, "reason": "ollama_unavailable_or_no_pages"}
            )
            continue

        try:
            mention_vec = normalize(load_or_embed(host, embed_model, mention_text, cache_dir))
        except (urllib.error.URLError, RuntimeError, ConnectionError, OSError) as exc:
            warnings.append(f"ollama embed failed for mention {proposed_slug}: {exc}")
            gate_hits["tier3_passthrough"].append(
                {"proposed_slug": proposed_slug, "kind": kind, "reason": "embed_failed"}
            )
            continue

        best_cos = -1.0
        best_slug = None
        for slug, info in existing_pages.items():
            if info.get("vec") is None or slug == proposed_slug:
                continue
            c = cosine_pre_normalized(mention_vec, info["vec"])
            if c > best_cos:
                best_cos = c
                best_slug = slug

        if best_slug is None:
            gate_hits["tier3_passthrough"].append(
                {"proposed_slug": proposed_slug, "kind": kind, "reason": "no_existing_pages"}
            )
            continue

        if best_cos >= tier1_threshold:
            gate_hits["tier1_hard"].append(
                {"proposed_slug": proposed_slug, "kind": kind, "matched_slug": best_slug, "cosine": round(best_cos, 4)}
            )
            overrides[proposed_slug] = {
                "action": "redirect_to", "target": best_slug, "tier": 1, "cosine": round(best_cos, 4),
            }
            continue

        if best_cos >= tier2_threshold:
            if not tier2_llm_enabled:
                gate_hits["tier3_passthrough"].append(
                    {"proposed_slug": proposed_slug, "kind": kind, "matched_slug": best_slug,
                     "cosine": round(best_cos, 4), "reason": "tier2_llm_disabled"}
                )
                continue
            try:
                verdict = adjudicate(
                    proposed_slug, mention_text, best_slug, existing_pages[best_slug]["path"], model,
                )
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"tier2 adjudication failed for {proposed_slug} vs {best_slug}: {exc}")
                gate_hits["tier3_passthrough"].append(
                    {"proposed_slug": proposed_slug, "kind": kind, "matched_slug": best_slug,
                     "cosine": round(best_cos, 4), "reason": "adjudication_error"}
                )
                continue

            record = {
                "proposed_slug": proposed_slug, "kind": kind, "matched_slug": best_slug,
                "cosine": round(best_cos, 4), "verdict": verdict.get("verdict"),
                "reasoning": verdict.get("reasoning"), "confidence": verdict.get("confidence"),
            }
            if verdict.get("verdict") == "MERGE":
                gate_hits["tier2_llm_merge"].append(record)
                overrides[proposed_slug] = {
                    "action": "redirect_to", "target": best_slug, "tier": 2, "cosine": round(best_cos, 4),
                }
            else:
                gate_hits["tier2_llm_keep"].append(record)
            continue

        gate_hits["tier3_passthrough"].append(
            {"proposed_slug": proposed_slug, "kind": kind, "matched_slug": best_slug, "cosine": round(best_cos, 4)}
        )

    metrics = {
        "mentions_checked": len(mentions),
        "existing_pages_loaded": len(existing_pages),
        "tier1_hard": len(gate_hits["tier1_hard"]),
        "tier2_llm_merge": len(gate_hits["tier2_llm_merge"]),
        "tier2_llm_keep": len(gate_hits["tier2_llm_keep"]),
        "tier3_passthrough": len(gate_hits["tier3_passthrough"]),
        "elapsed_s": round(time.time() - t0, 2),
        "warnings": warnings,
    }

    return {"source": source, "gate_hits": gate_hits, "overrides": overrides, "metrics": metrics}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mentions", required=True, help="input JSON: {source, existing_pages_dir, mentions[]}")
    ap.add_argument("--out", required=True, help="output JSON path")
    ap.add_argument("--tier1-threshold", type=float,
                     default=float(os.environ.get("MIKAI_GATE_TIER1_THRESHOLD", "0.95")))
    ap.add_argument("--tier2-threshold", type=float,
                     default=float(os.environ.get("MIKAI_GATE_TIER2_THRESHOLD", "0.85")))
    ap.add_argument("--tier2-llm", type=int, default=int(os.environ.get("MIKAI_GATE_TIER2_LLM", "1")),
                     help="1 (default) runs Tier 2 LLM adjudication; 0 makes Tier 2 band passthrough")
    ap.add_argument("--model", default="claude-sonnet-4-5", help="model for Tier 2 adjudication")
    ap.add_argument("--embed-model", default="nomic-embed-text")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ap.add_argument("--cache-dir", default=None,
                     help="embed cache dir; defaults to <existing_pages_dir>/../.embed-cache")
    args = ap.parse_args()

    mentions_payload = json.loads(Path(args.mentions).read_text())
    existing_pages_dir = Path(mentions_payload["existing_pages_dir"]).expanduser()
    cache_dir = Path(args.cache_dir).expanduser() if args.cache_dir else existing_pages_dir.parent / ".embed-cache"

    result = run_gate(
        mentions_payload,
        tier1_threshold=args.tier1_threshold,
        tier2_threshold=args.tier2_threshold,
        tier2_llm_enabled=bool(args.tier2_llm),
        model=args.model,
        embed_model=args.embed_model,
        host=args.host,
        cache_dir=cache_dir,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))

    m = result["metrics"]
    print(
        f"[write-time-gate] source={result['source']!r} mentions={m['mentions_checked']} "
        f"tier1={m['tier1_hard']} tier2_merge={m['tier2_llm_merge']} "
        f"tier2_keep={m['tier2_llm_keep']} passthrough={m['tier3_passthrough']} "
        f"({m['elapsed_s']}s)"
    )
    for w in m["warnings"]:
        print(f"[write-time-gate] WARN: {w}", file=sys.stderr)
    print(f"[write-time-gate] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
referential_integrity.py — CANON-7 measurement pass.

Measures whether SLUG DISCIPLINE (the prompt-level replacement for the
removed enrichWithWikilinks) actually produces correctly-wikilinked
bodies. Sweeps source-summary + concept + entity + wisdom pages for
token strings that match known canonical titles/aliases, and reports
the fraction wrapped in [[wikilinks]] vs left bare.

Target: ≥95% resolution rate. Below that suggests SLUG DISCIPLINE + top-K
isn't sufficient and a bounded batched enrichment pass should be revived.

Zero LLM calls; deterministic; safe to run alongside ingestion.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# Ignore mentions inside wikilinks, inside code blocks, and inside inline code.
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]+`")

# Kinds of pages whose bodies we sweep for mentions.
SWEEP_KINDS = ("sources", "concepts", "entities", "wisdom")
# Kinds of pages that provide canonical slugs/aliases to match against.
CANONICAL_KINDS = ("concepts", "entities", "wisdom")


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
            items = [x.strip().strip("\"'") for x in val[1:-1].split(",") if x.strip()]
            fields[key] = items
        else:
            fields[key] = val
    return fields, m.end()


def build_canonical_lookup(vault: Path) -> dict[str, str]:
    """title/alias (lowercased, whitespace-normalized) → canonical slug (kinded).

    E.g. 'personal intent graph' → 'concepts/personal-intent-graph'
         'intent-graph' (alias) → 'concepts/personal-intent-graph'
    Skips retired pages (they aren't valid destinations).
    """
    lookup: dict[str, str] = {}
    for kind in CANONICAL_KINDS:
        d = vault / "wiki" / kind
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fields, _ = parse_frontmatter(text)
            if not fields or fields.get("retired_to"):
                continue
            slug = p.stem
            kinded = f"{kind}/{slug}"
            keys: set[str] = {slug.lower(), slug.replace("-", " ").lower()}
            title = fields.get("title")
            if isinstance(title, str) and title.strip():
                keys.add(title.strip().lower())
            aliases = fields.get("aliases") or []
            if isinstance(aliases, list):
                for a in aliases:
                    if isinstance(a, str):
                        keys.add(a.strip().lower())
                        keys.add(a.replace("-", " ").strip().lower())
            for k in keys:
                if len(k) < 4:
                    continue  # skip trivial short strings
                # Prefer first-writer-wins on collisions (deterministic)
                lookup.setdefault(k, kinded)
    return lookup


def strip_wikilinks_code(body: str) -> tuple[str, list[str]]:
    """Return (body-without-wikilinks-and-code, list of wikilink targets found)."""
    targets = WIKILINK_RE.findall(body)
    body_no_wiki = WIKILINK_RE.sub(" ", body)
    body_no_code = CODE_FENCE_RE.sub(" ", body_no_wiki)
    body_no_inline = INLINE_CODE_RE.sub(" ", body_no_code)
    return body_no_inline, targets


def token_positions(body: str, needle: str) -> int:
    """Case-insensitive whole-word occurrence count."""
    if not needle:
        return 0
    pattern = r"\b" + re.escape(needle) + r"\b"
    return len(re.findall(pattern, body, flags=re.IGNORECASE))


def sweep_page(
    path: Path,
    lookup: dict[str, str],
) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    fields, end = parse_frontmatter(text)
    if fields.get("retired_to"):
        return {}
    body = text[end:]
    body_stripped, existing_targets = strip_wikilinks_code(body)

    # Count wikilink references to canonical slugs
    existing_target_slugs = set()
    for t in existing_targets:
        t_clean = t.split("|", 1)[0].strip()
        if "/" not in t_clean:
            for kind in CANONICAL_KINDS:
                existing_target_slugs.add(f"{kind}/{t_clean}")
        else:
            existing_target_slugs.add(t_clean)

    # For each canonical, count bare mentions in the stripped body
    self_slug = f"{path.parent.name}/{path.stem}"
    bare_mentions: dict[str, int] = {}
    for key, canonical in lookup.items():
        if canonical == self_slug:
            continue
        n = token_positions(body_stripped, key)
        if n > 0:
            bare_mentions[canonical] = bare_mentions.get(canonical, 0) + n

    return {
        "path": str(path),
        "wikilink_count": len(existing_targets),
        "linked_canonicals": len(existing_target_slugs),
        "bare_canonicals_referenced": len(bare_mentions),
        "bare_mentions_total": sum(bare_mentions.values()),
        "top_bare": Counter(bare_mentions).most_common(5),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--sample-size", type=int, default=0,
                    help="if >0, sweep only this many pages (random per seed)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="/tmp/referential-integrity.json")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    print(f"[refint] building canonical lookup...", flush=True)
    lookup = build_canonical_lookup(vault)
    print(f"[refint] canonical lookup keys: {len(lookup)} (canonicals: "
          f"{len(set(lookup.values()))})", flush=True)

    pages: list[Path] = []
    for kind in SWEEP_KINDS:
        d = vault / "wiki" / kind
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            pages.append(p)

    if args.sample_size > 0:
        import random
        random.seed(args.seed)
        pages = random.sample(pages, min(args.sample_size, len(pages)))

    print(f"[refint] sweeping {len(pages)} pages...", flush=True)
    results = []
    total_wl = 0
    total_bare = 0
    for p in pages:
        r = sweep_page(p, lookup)
        if r:
            results.append(r)
            total_wl += r["wikilink_count"]
            total_bare += r["bare_mentions_total"]

    resolved_rate = (total_wl / (total_wl + total_bare)) if (total_wl + total_bare) else 0.0

    summary = {
        "vault": str(vault),
        "pages_swept": len(results),
        "canonical_keys": len(lookup),
        "unique_canonicals": len(set(lookup.values())),
        "total_wikilinks": total_wl,
        "total_bare_mentions": total_bare,
        "resolved_rate": round(resolved_rate, 4),
    }
    print(f"[refint] summary: {json.dumps(summary, sort_keys=True)}", flush=True)

    # Top offenders — pages with the most bare mentions
    offenders = sorted(
        [r for r in results if r["bare_mentions_total"] > 0],
        key=lambda r: r["bare_mentions_total"],
        reverse=True,
    )[:20]

    Path(args.out).write_text(
        json.dumps({
            "summary": summary,
            "top_offenders": offenders,
            "per_page": results,
        }, indent=2),
        encoding="utf-8",
    )
    print(f"[refint] full report: {args.out}", flush=True)
    if offenders:
        print(f"[refint] top 5 offenders (most bare mentions):", flush=True)
        for r in offenders[:5]:
            name = Path(r["path"]).name
            top = ", ".join(f"{s}={n}" for s, n in r["top_bare"][:3])
            print(f"  {name} — {r['bare_mentions_total']} bare mentions; top: {top}",
                  flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

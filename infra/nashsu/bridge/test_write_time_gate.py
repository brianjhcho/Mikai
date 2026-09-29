"""Standalone research probe: would a write-time embedding gate have caught
the synonym collisions that post-hoc dedup (dedup_embed.py) finds?

For a set of already-ingested source files, this reads the concept/entity
pages each source wrote (via .llm-wiki/ingest-cache.json), embeds a "mention
proxy" (title + first paragraph) for each written page, and cosines it
against every OTHER existing concept/entity page in the vault. A hit above
threshold means: at write time, this page's mention should have been
redirected to an existing page instead of creating a new one.

Report-only. No writes to the vault. No changes to nashsu vendor code.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dedup_embed import (  # noqa: E402
    ollama_embed,
    load_or_embed,
    cosine_pre_normalized,
    normalize,
)

_FRONTMATTER_RX = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_TITLE_RX = re.compile(r"^title:\s*(.+)$", re.MULTILINE)
_RETIRED_RX = re.compile(r"^retired_to:", re.MULTILINE)


def mention_proxy(path: Path) -> str | None:
    """Title + first paragraph after frontmatter, as a proxy for the
    stage-1 mention description a write-time gate would score."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _FRONTMATTER_RX.match(text)
    if not m:
        return None
    frontmatter = m.group(1)
    if _RETIRED_RX.search(frontmatter):
        return None
    body = text[m.end():]
    title_m = _TITLE_RX.search(frontmatter)
    title = title_m.group(1).strip() if title_m else path.stem
    # First non-heading, non-empty paragraph.
    paras = [p.strip() for p in body.split("\n\n") if p.strip()]
    first_para = ""
    for p in paras:
        if p.startswith("#"):
            continue
        first_para = p
        break
    proxy = f"{title}\n\n{first_para}".strip()
    return proxy if len(proxy) > 10 else None


def load_all_pages(project: Path) -> dict:
    """slug -> {"path", "proxy"} for all live (non-retired) concept/entity pages."""
    pages = {}
    for sub in ("concepts", "entities"):
        d = project / "wiki" / sub
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            proxy = mention_proxy(p)
            if proxy is None:
                continue
            pages[f"{sub}/{p.stem}"] = {"path": str(p), "proxy": proxy}
    return pages


def written_slugs_for_source(cache: dict, source_name: str) -> list:
    entry = cache.get("entries", {}).get(source_name)
    if not entry:
        return []
    out = []
    for f in entry.get("filesWritten", []):
        m = re.match(r"^wiki/(concepts|entities)/([^/]+)\.md$", f)
        if m:
            out.append(f"{m.group(1)}/{m.group(2)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--sources-list", required=True)
    ap.add_argument("--thresholds", default="0.70,0.75,0.80,0.85,0.90")
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--model", default="nomic-embed-text")
    ap.add_argument("--gate-threshold", type=float, default=0.85)
    args = ap.parse_args()

    project = Path(args.project).expanduser()
    cache_dir = project / ".embed-cache"
    thresholds = [float(t) for t in args.thresholds.split(",")]

    cache = json.loads((project / ".llm-wiki" / "ingest-cache.json").read_text())
    source_names = [
        s.strip() for s in Path(args.sources_list).read_text().splitlines() if s.strip()
    ]

    print(f"[gate-test] loading all live concept/entity pages under {project}/wiki")
    all_pages = load_all_pages(project)
    print(f"[gate-test] {len(all_pages)} live pages loaded")

    # Embed every page's proxy once (cached).
    print("[gate-test] embedding page proxies (cached where possible)")
    for i, (slug, info) in enumerate(all_pages.items(), 1):
        info["vec"] = normalize(load_or_embed(args.host, args.model, info["proxy"], cache_dir))
        if i % 100 == 0 or i == len(all_pages):
            print(f"[gate-test]   {i}/{len(all_pages)}")

    # Collect the mention slugs to test: pages written by the given sources.
    mention_slugs = []
    for source_name in source_names:
        for slug in written_slugs_for_source(cache, source_name):
            if slug in all_pages:
                mention_slugs.append((source_name, slug))
    mention_slugs = sorted(set(mention_slugs))
    print(f"[gate-test] {len(mention_slugs)} mentions to test across {len(source_names)} sources")

    all_slugs = list(all_pages.keys())
    results = []
    for source_name, slug in mention_slugs:
        vec = all_pages[slug]["vec"]
        best_cos = -1.0
        best_slug = None
        for other in all_slugs:
            if other == slug:
                continue
            c = cosine_pre_normalized(vec, all_pages[other]["vec"])
            if c > best_cos:
                best_cos = c
                best_slug = other
        results.append(
            {
                "source": source_name,
                "mention_slug": slug,
                "top_cosine": round(best_cos, 4),
                "matched_slug": best_slug,
                "gate_hit_at_0.85": best_cos >= args.gate_threshold,
            }
        )

    results.sort(key=lambda r: r["top_cosine"], reverse=True)

    # Threshold sweep.
    sweep = []
    for t in thresholds:
        hits = [r for r in results if r["top_cosine"] >= t]
        mean_cos = sum(r["top_cosine"] for r in hits) / len(hits) if hits else 0.0
        sweep.append(
            {
                "threshold": t,
                "total_hits": len(hits),
                "hit_rate": round(len(hits) / len(results), 4) if results else 0.0,
                "mean_top_cosine": round(mean_cos, 4),
            }
        )

    top20 = results[:20]

    payload = {
        "project": str(project),
        "sources_tested": source_names,
        "mentions_checked": len(results),
        "gate_threshold": args.gate_threshold,
        "gate_hits": [r for r in results if r["gate_hit_at_0.85"]],
        "threshold_sweep": sweep,
        "per_mention_results": results,
        "top20": top20,
    }
    Path(args.out_json).write_text(json.dumps(payload, indent=2))

    lines = []
    lines.append("# Write-time gate test report\n")
    lines.append(f"- **Project**: `{project}`")
    lines.append(f"- **Sources tested**: {len(source_names)}")
    lines.append(f"- **Mentions checked**: {len(results)}")
    lines.append(f"- **Gate threshold**: {args.gate_threshold}")
    lines.append(f"- **Gate hits**: {len(payload['gate_hits'])} "
                 f"({round(100 * len(payload['gate_hits']) / len(results), 1) if results else 0}%)")
    lines.append("")

    lines.append("## Threshold sweep\n")
    lines.append("| threshold | total hits | hit-rate | mean top-cosine |")
    lines.append("|---:|---:|---:|---:|")
    for s in sweep:
        lines.append(
            f"| {s['threshold']:.2f} | {s['total_hits']} | {s['hit_rate']:.2%} | {s['mean_top_cosine']:.4f} |"
        )
    lines.append("")

    lines.append("## Per-source mention table\n")
    lines.append("| source | mention slug | top-cosine | matched slug | verdict-would-be |")
    lines.append("|---|---|---:|---|---|")
    for r in results:
        verdict = "REDIRECT to existing" if r["gate_hit_at_0.85"] else "keep new page"
        lines.append(
            f"| `{r['source']}` | `{r['mention_slug']}` | {r['top_cosine']:.4f} | `{r['matched_slug']}` | {verdict} |"
        )
    lines.append("")

    lines.append("## Top 20 gate hits (full detail for hand-review)\n")
    lines.append("| mention slug | matched slug | cosine |")
    lines.append("|---|---|---:|")
    for r in top20:
        lines.append(f"| `{r['mention_slug']}` | `{r['matched_slug']}` | {r['top_cosine']:.4f} |")
    lines.append("")

    Path(args.out_md).write_text("\n".join(lines))
    print(f"[gate-test] wrote {args.out_md}")
    print(f"[gate-test] wrote {args.out_json}")
    print(
        f"[gate-test] mentions={len(results)} gate_hits(@{args.gate_threshold})="
        f"{len(payload['gate_hits'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

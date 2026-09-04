"""Post-hoc measurement of Mechanism B (pre-extraction semantic top-K) effect.

No nashsu patching required. Reads existing state:
  - .llm-wiki/ingest-cache.json  → per-source `filesWritten` + timestamps
  - wiki/.mikai-neighbors/<source>.md  → top-K neighbors that reached the prompt

For each source whose ingest had a neighbors file present, computes:

  REUSED     — filesWritten entries that were CREATED by an earlier ingest
               (i.e. the LLM chose to UPDATE an existing page rather than coin a new slug)
  COINED     — filesWritten entries that this source CREATED for the first time
  TOP-K HIT  — of the REUSED slugs, how many appeared in the top-K neighbors
               (Mechanism B did its job: LLM saw the neighbor and reused it)
  TOP-K MISS-BUT-COINED
             — COINED slugs whose *canonical name* appears in top-K neighbors
               (Mechanism B surfaced the slug but LLM ignored it → SLUG DISCIPLINE failure)

Reports per-source + aggregate. Answers "did Mechanism B actually change LLM behavior?"

Usage:
  python3 measure_topk_effect.py --project ~/.mikai/wiki-mikai-parallel-test
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


# `[[concepts/slug]]` or `[[entities/slug]]` or `[[wisdom/slug]]` inside a neighbors file
NEIGHBOR_LINE_RE = re.compile(r"\[\[((?:concepts|entities|wisdom)/[^\]]+)\]\]")

# knowledge-page filesWritten paths we care about (skip index.md / log.md / source-summaries)
KNOWLEDGE_DIRS = ("concepts", "entities", "wisdom")


def parse_neighbors(path: Path) -> set[str]:
    """Extract slugs (as `concepts/foo`, `entities/bar`, `wisdom/baz`) from a neighbors file."""
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8", errors="replace")
    return set(NEIGHBOR_LINE_RE.findall(text))


def load_cache(project: Path) -> dict:
    cache_path = project / ".llm-wiki" / "ingest-cache.json"
    with cache_path.open() as f:
        return json.load(f)


def slug_creation_map(entries: dict) -> dict[str, int]:
    """Map each knowledge-page slug (e.g. `concepts/foo`) to the EARLIEST timestamp
    that any source wrote it. Sources sorted by timestamp so first-writer wins."""
    ordered = sorted(entries.items(), key=lambda kv: kv[1].get("timestamp", 0))
    first_seen: dict[str, int] = {}
    for src_name, entry in ordered:
        ts = entry.get("timestamp", 0)
        for rel in entry.get("filesWritten", []):
            # rel is like "wiki/concepts/foo.md"
            parts = rel.split("/")
            if len(parts) >= 3 and parts[0] == "wiki" and parts[1] in KNOWLEDGE_DIRS:
                slug = f"{parts[1]}/{Path(parts[2]).stem}"
                first_seen.setdefault(slug, ts)
    return first_seen


def analyze_source(
    src_name: str,
    entry: dict,
    neighbors_dir: Path,
    first_seen: dict[str, int],
) -> dict:
    ts = entry.get("timestamp", 0)
    neighbors_path = neighbors_dir / src_name
    neighbors = parse_neighbors(neighbors_path)

    reused: list[str] = []
    coined: list[str] = []
    top_k_hits: list[str] = []
    coined_but_in_neighbors: list[str] = []

    for rel in entry.get("filesWritten", []):
        parts = rel.split("/")
        if len(parts) < 3 or parts[0] != "wiki" or parts[1] not in KNOWLEDGE_DIRS:
            continue
        slug = f"{parts[1]}/{Path(parts[2]).stem}"
        was_first = first_seen.get(slug, ts) >= ts
        if was_first:
            coined.append(slug)
            if slug in neighbors:
                coined_but_in_neighbors.append(slug)
        else:
            reused.append(slug)
            if slug in neighbors:
                top_k_hits.append(slug)

    return {
        "source": src_name,
        "neighbor_count": len(neighbors),
        "written_knowledge_pages": len(reused) + len(coined),
        "reused": reused,
        "coined": coined,
        "top_k_hits": top_k_hits,
        "coined_but_in_neighbors": coined_but_in_neighbors,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, type=Path)
    args = ap.parse_args()

    project: Path = args.project
    neighbors_dir = project / "wiki" / ".mikai-neighbors"
    if not neighbors_dir.is_dir():
        print(f"[measure] no neighbors dir at {neighbors_dir}")
        return 1

    cache = load_cache(project)
    entries = cache.get("entries", {})
    first_seen = slug_creation_map(entries)

    neighbor_names = {p.name for p in neighbors_dir.glob("*.md")}
    # Only entries whose ingest actually ran while Mechanism B was live —
    # i.e., ingest timestamp is after the neighbors-dir was created. Cache-hit
    # re-ingests keep their old timestamps and would falsely count as R7 work.
    nb_dir_ms = int(neighbors_dir.stat().st_mtime * 1000)
    r7_entries = [
        (k, v) for k, v in entries.items()
        if k in neighbor_names and v.get("timestamp", 0) >= nb_dir_ms - 60_000
    ]
    r7_entries.sort(key=lambda kv: kv[1].get("timestamp", 0))
    skipped_cache_hits = sum(
        1 for k in neighbor_names
        if k in entries and entries[k].get("timestamp", 0) < nb_dir_ms - 60_000
    )
    if skipped_cache_hits:
        print(f"(skipped {skipped_cache_hits} cache-hit re-ingests — neighbor file present but no LLM ran)")
        print()

    print(f"# Mechanism B effect report — {project.name}")
    print()
    print(f"Sources with neighbor files: {len(r7_entries)}")
    print(f"Total knowledge pages tracked (all-time): {len(first_seen)}")
    print()

    agg_reused = 0
    agg_coined = 0
    agg_hits = 0
    agg_coined_in_neighbors = 0

    for src_name, entry in r7_entries:
        r = analyze_source(src_name, entry, neighbors_dir, first_seen)
        agg_reused += len(r["reused"])
        agg_coined += len(r["coined"])
        agg_hits += len(r["top_k_hits"])
        agg_coined_in_neighbors += len(r["coined_but_in_neighbors"])

        print(f"## {src_name}")
        print(f"- neighbors surfaced: {r['neighbor_count']}")
        print(f"- knowledge pages written: {r['written_knowledge_pages']}")
        print(f"- REUSED (updated existing slug): {len(r['reused'])}")
        print(f"- COINED (new slug): {len(r['coined'])}")
        print(f"- TOP-K HITS (reused slug appeared in top-K): {len(r['top_k_hits'])}")
        if r["top_k_hits"]:
            for h in r["top_k_hits"]:
                print(f"    hit: {h}")
        print(f"- COINED-BUT-IN-NEIGHBORS (LLM ignored the neighbor): {len(r['coined_but_in_neighbors'])}")
        if r["coined_but_in_neighbors"]:
            for m in r["coined_but_in_neighbors"]:
                print(f"    ignored: {m}")
        print()

    total = agg_reused + agg_coined
    reuse_rate = agg_reused / total if total else 0.0
    top_k_hit_rate = agg_hits / agg_reused if agg_reused else 0.0
    slug_discipline_fail_rate = agg_coined_in_neighbors / agg_coined if agg_coined else 0.0

    print("## Aggregate")
    print(f"- Total knowledge pages written: {total}")
    print(f"- REUSED: {agg_reused}  ({reuse_rate:.1%})")
    print(f"- COINED: {agg_coined}")
    print(f"- TOP-K HIT rate on REUSED: {agg_hits}/{agg_reused} ({top_k_hit_rate:.1%})")
    print(f"- SLUG DISCIPLINE failure rate (coined despite neighbor available): "
          f"{agg_coined_in_neighbors}/{agg_coined} ({slug_discipline_fail_rate:.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

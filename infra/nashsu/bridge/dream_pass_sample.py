"""ARCH-035 probe — dream pass sample.

Standalone, report-only proof-of-concept for the periodic dream pass:
builds the wikilink graph over concepts/entities/wisdom, runs Louvain
community detection, ranks clusters by consolidation potential, and
runs LLM adjudication (`claude -p`) on the top candidates.

No writes to the vault. Emits a markdown report only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import networkx as nx
from networkx.algorithms.community import louvain_communities

WIKI_SUBDIRS = ["concepts", "entities", "wisdom"]
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?(?:#[^\]]+)?\]\]")
_FRONTMATTER_RX = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_TITLE_RX = re.compile(r'^title:\s*"?(.*?)"?\s*$', re.MULTILINE)
_RETIRED_RX = re.compile(r"^retired_to:", re.MULTILINE)


def parse_page(path: Path, node_id: str) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _FRONTMATTER_RX.match(text)
    frontmatter = m.group(1) if m else ""
    body = text[m.end():] if m else text
    retired = bool(_RETIRED_RX.search(frontmatter))
    tm = _TITLE_RX.search(frontmatter)
    title = tm.group(1) if tm else path.stem.replace("-", " ").title()
    links = {lk.strip().lower() for lk in WIKILINK_RE.findall(body)}
    return {
        "id": node_id,
        "slug": path.stem,
        "title": title,
        "path": str(path),
        "body": body.strip(),
        "word_count": len(body.split()),
        "retired": retired,
        "links": links,
    }


def load_pages(wiki_dir: Path) -> dict:
    pages = {}
    for sub in WIKI_SUBDIRS:
        d = wiki_dir / sub
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            node_id = f"{sub}/{p.stem}"
            page = parse_page(p, node_id)
            if page["retired"]:
                continue
            pages[node_id] = page
    return pages


def build_graph(pages: dict) -> nx.Graph:
    g = nx.Graph()
    for node_id, page in pages.items():
        g.add_node(node_id, title=page["title"], word_count=page["word_count"])
    for node_id, page in pages.items():
        for target in page["links"]:
            # normalize target: may or may not carry a subdir prefix
            candidates = [target] if "/" in target else [f"{sub}/{target}" for sub in WIKI_SUBDIRS]
            for cand in candidates:
                if cand in pages and cand != node_id:
                    g.add_edge(node_id, cand)
    return g


def score_cluster(g: nx.Graph, members: set, pages: dict) -> dict:
    inbound = {m: g.degree(m) for m in members}
    sorted_members = sorted(members, key=lambda m: inbound[m], reverse=True)
    hub = sorted_members[0]
    hub_degree = inbound[hub]
    second_degree = inbound[sorted_members[1]] if len(sorted_members) > 1 else 0
    total_words = sum(pages[m]["word_count"] for m in members)
    internal_edges = g.subgraph(members).number_of_edges()
    max_edges = len(members) * (len(members) - 1) / 2
    density = internal_edges / max_edges if max_edges else 0.0
    hub_gravity = (hub_degree - second_degree) / (hub_degree + 1)
    score = density * 0.4 + hub_gravity * 0.4 + min(total_words / 3000, 1.0) * 0.2
    return {
        "members": sorted_members,
        "size": len(members),
        "hub": hub,
        "hub_degree": hub_degree,
        "density": round(density, 3),
        "hub_gravity": round(hub_gravity, 3),
        "total_words": total_words,
        "score": round(score, 4),
    }


def rank_clusters(g: nx.Graph, communities: list, pages: dict) -> list:
    scored = []
    for community in communities:
        if not (3 <= len(community) <= 15):
            continue
        scored.append(score_cluster(g, community, pages))
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored


def build_adjudication_prompt(cluster: dict, pages: dict) -> str:
    lines = [
        "The following concept pages appear to be in a semantic cluster (they cross-reference each other in the wiki graph).",
        "Should they be consolidated?",
        "",
        "CLUSTER MEMBERS:",
    ]
    for i, member_id in enumerate(cluster["members"], 1):
        page = pages[member_id]
        excerpt = page["body"][:300].replace("\n", " ").strip()
        lines.append(f"{i}. {member_id} — {page['title']}")
        lines.append(f"   {excerpt}")
    lines.append("")
    lines.append("Output JSON:")
    lines.append(json.dumps({
        "verdict": "PROMOTE-HUB | MERGE-CREATE-HUB | KEEP-INDEPENDENT",
        "canonical_slug": "<the slug the cluster consolidates around, or null if KEEP>",
        "reasoning": "<one paragraph>",
        "confidence": "<0.0-1.0>",
        "members_to_absorb": ["<slug>", "..."],
    }, indent=2))
    return "\n".join(lines)


def adjudicate(cluster: dict, pages: dict, model: str) -> dict:
    prompt = build_adjudication_prompt(cluster, pages)
    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", model, "--output-format", "json"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"error": str(e)}
    if proc.returncode != 0:
        return {"error": f"claude -p exit {proc.returncode}: {proc.stderr[:500]}"}
    try:
        outer = json.loads(proc.stdout)
        result_text = outer.get("result", "")
    except json.JSONDecodeError as e:
        return {"error": f"outer JSON parse failed: {e}", "raw": proc.stdout[:500]}
    result_text = result_text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", result_text, re.DOTALL)
    if fence:
        result_text = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", result_text, re.DOTALL)
        if brace:
            result_text = brace.group(0)
    try:
        return json.loads(result_text)
    except json.JSONDecodeError as e:
        return {"error": f"inner JSON parse failed: {e}", "raw": result_text[:500]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--wiki-dir",
        default=str(Path.home() / ".mikai" / "wiki-mikai-parallel-test" / "wiki"),
    )
    ap.add_argument("--report", default="/tmp/dream-pass-sample-report.md")
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--adjudicate-n", type=int, default=2)
    ap.add_argument("--model", default="claude-sonnet-4-5")
    args = ap.parse_args()

    wiki_dir = Path(args.wiki_dir)
    print(f"[dream-pass-sample] loading pages from {wiki_dir}")
    pages = load_pages(wiki_dir)
    print(f"[dream-pass-sample] {len(pages)} non-retired pages loaded")

    g = build_graph(pages)
    print(f"[dream-pass-sample] graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")

    communities = louvain_communities(g, seed=42)
    sizes = sorted((len(c) for c in communities), reverse=True)
    print(f"[dream-pass-sample] {len(communities)} communities detected")

    ranked = rank_clusters(g, communities, pages)
    print(f"[dream-pass-sample] {len(ranked)} clusters in 3-15 size range")

    top = ranked[: args.top_n]

    verdicts = []
    for i, cluster in enumerate(top[: args.adjudicate_n]):
        print(f"[dream-pass-sample] adjudicating cluster {i + 1} (hub={cluster['hub']})...")
        verdict = adjudicate(cluster, pages, args.model)
        verdicts.append(verdict)
        print(f"[dream-pass-sample]   verdict: {verdict.get('verdict', verdict.get('error', 'UNKNOWN'))}")

    # Size distribution buckets
    buckets = {"1": 0, "2": 0, "3-5": 0, "6-15": 0, "16-50": 0, "50+": 0}
    for s in sizes:
        if s == 1:
            buckets["1"] += 1
        elif s == 2:
            buckets["2"] += 1
        elif s <= 5:
            buckets["3-5"] += 1
        elif s <= 15:
            buckets["6-15"] += 1
        elif s <= 50:
            buckets["16-50"] += 1
        else:
            buckets["50+"] += 1

    lines = []
    lines.append("# Dream Pass Sample Report (ARCH-035 probe)\n")
    lines.append(f"- **Vault**: `{wiki_dir}`")
    lines.append(f"- **Non-retired pages loaded**: {len(pages)}")
    lines.append(f"- **Graph**: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")
    lines.append(f"- **Communities detected**: {len(communities)}")
    lines.append("")
    lines.append("## Community size distribution")
    lines.append("")
    lines.append("| bucket | count |")
    lines.append("|---|---:|")
    for k, v in buckets.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append(f"## Top-{args.top_n} candidate clusters (3-15 members, ranked by consolidation-potential score)")
    lines.append("")
    for i, cluster in enumerate(top, 1):
        lines.append(f"### {i}. Hub: `{cluster['hub']}` (score {cluster['score']}, size {cluster['size']}, hub-degree {cluster['hub_degree']}, density {cluster['density']})")
        lines.append("")
        lines.append("Members:")
        for m in cluster["members"]:
            lines.append(f"- `{m}` — {pages[m]['title']} ({pages[m]['word_count']} words, degree {g.degree(m)})")
        lines.append("")

    lines.append(f"## LLM adjudication ({args.adjudicate_n} of top-{args.top_n} clusters)")
    lines.append("")
    for i, (cluster, verdict) in enumerate(zip(top[: args.adjudicate_n], verdicts), 1):
        lines.append(f"### Cluster {i}: hub `{cluster['hub']}`")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(verdict, indent=2))
        lines.append("```")
        lines.append("")

    # Projected impact if all top-N clusters were applied at their (assumed) verdict.
    # For the adjudicated ones, use the actual verdict; for the rest, assume PROMOTE-HUB/MERGE
    # (i.e. all non-hub members retire) as an upper-bound estimate.
    total_retired = 0
    total_words_before = sum(pages[m]["word_count"] for c in top for m in c["members"])
    for i, cluster in enumerate(top):
        if i < len(verdicts) and verdicts[i].get("verdict") == "KEEP-INDEPENDENT":
            continue
        if i < len(verdicts) and "members_to_absorb" in verdicts[i]:
            total_retired += len(verdicts[i]["members_to_absorb"])
        else:
            total_retired += cluster["size"] - 1

    projected_concept_count = len(pages) - total_retired
    projected_mean_words = total_words_before / max(len(top), 1) if top else 0

    lines.append("## Estimated impact if top-5 clusters applied at their (assumed) verdict")
    lines.append("")
    lines.append(f"- **Pages retired (estimate)**: {total_retired}")
    lines.append(f"- **Concept count**: {len(pages)} → {projected_concept_count}")
    lines.append(f"- **Total words across top-5 clusters**: {total_words_before}")
    lines.append("")

    Path(args.report).write_text("\n".join(lines))
    print(f"[dream-pass-sample] wrote {args.report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

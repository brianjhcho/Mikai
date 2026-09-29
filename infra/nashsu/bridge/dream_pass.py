"""ARCH-035 dream pass — production periodic cluster consolidation.

Extends `dream_pass_sample.py`'s Louvain + LLM adjudication proof-of-concept
with recursive sub-clustering so the pass can attack large ("blob") Louvain
communities (50+ pages), not just the naturally-sized 3-15 clusters.

Recursive strategy, per community found at level 1:
  - size < min-cluster:      skip (too small to consolidate)
  - min-cluster..max-cluster: LLM-adjudicate directly
  - max-cluster+1..49:        try one round of recursive Louvain on the
                               community-induced subgraph. If it decomposes
                               into usable pieces, recurse into each; if it
                               doesn't decompose, adjudicate the whole
                               community as one oversized cluster (marked).
  - 50+ ("blob"):             mandatory recursive Louvain, up to
                               --max-recursion levels. A sub-community that
                               still won't decompose (or exceeds the
                               recursion budget) falls back to embedding
                               k-means partitioning (~10 members/group).

Report-only: no writes to the vault. Emits a markdown report + a verdicts
JSON that also carries an inert `apply_plan` (structured retire/absorb
instructions) for a future apply-phase to consume — this script never
executes it.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import networkx as nx
from networkx.algorithms.community import louvain_communities

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dedup_embed import load_or_embed, normalize, cosine_pre_normalized  # noqa: E402

WIKI_SUBDIRS = ["concepts", "entities", "wisdom"]
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?(?:#[^\]]+)?\]\]")
_FRONTMATTER_RX = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_TITLE_RX = re.compile(r'^title:\s*"?(.*?)"?\s*$', re.MULTILINE)
_RETIRED_RX = re.compile(r"^retired_to:", re.MULTILINE)

DROP_FRACTION_THRESHOLD = 0.4  # if louvain drops this much mass into <min-cluster pieces, treat as "didn't decompose"


# --- page loading / graph building (same as dream_pass_sample.py) ---

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
            candidates = [target] if "/" in target else [f"{sub}/{target}" for sub in WIKI_SUBDIRS]
            for cand in candidates:
                if cand in pages and cand != node_id:
                    g.add_edge(node_id, cand)
    return g


def embed_proxy_text(page: dict) -> str:
    """title + first non-heading paragraph — same proxy shape as
    test_write_time_gate.py's mention_proxy()."""
    paras = [p.strip() for p in page["body"].split("\n\n") if p.strip()]
    first_para = ""
    for p in paras:
        if p.startswith("#"):
            continue
        first_para = p
        break
    return f"{page['title']}\n\n{first_para}".strip()


def build_embedding_graph(pages: dict, embed_cfg: dict, threshold: float, calibration_thresholds: list | None = None) -> tuple:
    """Nodes = all non-retired pages; edges = pairs with cosine >= threshold
    on nomic-embed-text embeddings of (title + first paragraph). Also scores
    a calibration sweep of thresholds in the same pairwise pass so a second
    --signal wikilink-style full pairwise scan isn't needed."""
    g = nx.Graph()
    vecs = {}
    total = len(pages)
    print(f"[dream-pass] embedding {total} pages for --signal embedding (proxy = title + first paragraph)")
    for i, (node_id, page) in enumerate(pages.items(), 1):
        g.add_node(node_id, title=page["title"], word_count=page["word_count"])
        text = embed_proxy_text(page) or page["title"]
        try:
            vecs[node_id] = normalize(load_or_embed(embed_cfg["host"], embed_cfg["model"], text, embed_cfg["cache_dir"]))
        except Exception as e:
            print(f"[dream-pass]   embed FAIL {node_id}: {e}")
            vecs[node_id] = None
        if i % 100 == 0 or i == total:
            print(f"[dream-pass]   embedded {i}/{total}")

    valid_ids = [nid for nid in g.nodes if vecs.get(nid)]
    cal_thresholds = sorted(set(calibration_thresholds or []) | {threshold})
    cal_counts = {t: 0 for t in cal_thresholds}
    pair_count = len(valid_ids) * (len(valid_ids) - 1) // 2
    print(f"[dream-pass] scoring {pair_count} pairs across thresholds {cal_thresholds}")
    for a, b in combinations(valid_ids, 2):
        c = cosine_pre_normalized(vecs[a], vecs[b])
        for t in cal_thresholds:
            if c >= t:
                cal_counts[t] += 1
        if c >= threshold:
            g.add_edge(a, b, weight=round(c, 4))
    return g, cal_counts


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


# --- embedding k-means fallback for blobs that won't decompose via Louvain ---

def _chunk_evenly(members: list, group_size: int) -> list:
    members = sorted(members)
    return [members[i:i + group_size] for i in range(0, len(members), group_size)]


def kmeans_partition(members: set, pages: dict, group_size: int, embed_cfg: dict, seed: int = 42, max_iter: int = 20) -> list:
    members = sorted(members)
    k = max(1, round(len(members) / group_size))
    vecs = {}
    for m in members:
        text = (pages[m]["body"][:3000] or pages[m]["title"]).strip() or pages[m]["title"]
        try:
            vecs[m] = normalize(load_or_embed(embed_cfg["host"], embed_cfg["model"], text, embed_cfg["cache_dir"]))
        except Exception:
            vecs[m] = None

    valid = [m for m in members if vecs.get(m)]
    invalid = [m for m in members if not vecs.get(m)]
    if k <= 1 or len(valid) <= k:
        return _chunk_evenly(members, group_size)

    rng = random.Random(seed)
    centroids = [vecs[m] for m in rng.sample(valid, k)]
    assignment = {}
    for _ in range(max_iter):
        new_assignment = {}
        for m in valid:
            sims = [cosine_pre_normalized(vecs[m], c) for c in centroids]
            new_assignment[m] = max(range(k), key=lambda i: sims[i])
        stable = new_assignment == assignment
        assignment = new_assignment
        if stable:
            break
        for ci in range(k):
            cluster_vecs = [vecs[m] for m in valid if assignment[m] == ci]
            if not cluster_vecs:
                continue
            dim = len(cluster_vecs[0])
            mean = [sum(v[d] for v in cluster_vecs) / len(cluster_vecs) for d in range(dim)]
            centroids[ci] = normalize(mean)

    groups_by_idx = defaultdict(list)
    for m, ci in assignment.items():
        groups_by_idx[ci].append(m)
    groups = [members for members in groups_by_idx.values() if members]
    for i, m in enumerate(invalid):
        groups[i % len(groups)].append(m)
    return groups


# --- recursive decomposition ---

def process_community(
    g: nx.Graph,
    members: set,
    pages: dict,
    depth: int,
    is_blob: bool,
    max_recursion: int,
    min_cluster: int,
    max_cluster: int,
    kmeans_group_size: int,
    embed_cfg: dict,
    recursion_log: list,
) -> list:
    size = len(members)
    if size < min_cluster:
        if size > 0:
            recursion_log.append({"depth": depth, "size": size, "action": "dropped-too-small"})
        return []
    if size <= max_cluster:
        return [{"members": sorted(members), "size": size, "depth": depth, "method": "direct" if depth == 0 else "recursive-louvain"}]

    if depth >= max_recursion:
        groups = kmeans_partition(members, pages, kmeans_group_size, embed_cfg)
        recursion_log.append({"depth": depth, "size": size, "action": "kmeans-fallback-recursion-budget-exhausted", "groups": len(groups)})
        leaves = []
        for grp in groups:
            if len(grp) < min_cluster:
                continue
            leaves.append({"members": sorted(grp), "size": len(grp), "depth": depth, "method": "kmeans-fallback"})
        return leaves

    subg = g.subgraph(members)
    sub_communities = louvain_communities(subg, seed=42)
    dropped_mass = sum(len(c) for c in sub_communities if len(c) < min_cluster)
    effectively_decomposed = len(sub_communities) > 1 and (dropped_mass / size) < DROP_FRACTION_THRESHOLD

    if not effectively_decomposed:
        if is_blob:
            groups = kmeans_partition(members, pages, kmeans_group_size, embed_cfg)
            recursion_log.append({"depth": depth, "size": size, "action": "kmeans-fallback-no-decomposition", "groups": len(groups)})
            leaves = []
            for grp in groups:
                if len(grp) < min_cluster:
                    continue
                leaves.append({"members": sorted(grp), "size": len(grp), "depth": depth, "method": "kmeans-fallback"})
            return leaves
        recursion_log.append({"depth": depth, "size": size, "action": "adjudicate-whole-undecomposed"})
        return [{"members": sorted(members), "size": size, "depth": depth, "method": "large-undecomposed"}]

    recursion_log.append({"depth": depth, "size": size, "action": "recursive-louvain-split", "sub_communities": len(sub_communities)})
    leaves = []
    for sub in sub_communities:
        leaves.extend(process_community(g, sub, pages, depth + 1, is_blob, max_recursion, min_cluster, max_cluster, kmeans_group_size, embed_cfg, recursion_log))
    return leaves


def decompose_all(g: nx.Graph, communities: list, pages: dict, min_cluster: int, max_cluster: int, max_recursion: int, kmeans_group_size: int, embed_cfg: dict) -> tuple:
    leaves = []
    recursion_log = []
    for community in communities:
        size = len(community)
        if size < min_cluster:
            continue
        if size <= max_cluster:
            leaves.append({"members": sorted(community), "size": size, "depth": 0, "method": "direct"})
            continue
        is_blob = size >= 50
        leaves.extend(process_community(g, community, pages, 1, is_blob, max_recursion, min_cluster, max_cluster, kmeans_group_size, embed_cfg, recursion_log))
    return leaves, recursion_log


# --- LLM adjudication (same protocol as dream_pass_sample.py) ---

def build_adjudication_prompt(cluster: dict, pages: dict) -> str:
    members = cluster["members"]
    marked = cluster["method"] == "large-undecomposed"
    lines = [
        "The following concept pages appear to be in a semantic cluster (they cross-reference each other in the wiki graph).",
        "Should they be consolidated?",
    ]
    if marked:
        lines.append(f"NOTE: this cluster is an oversized ({len(members)}-member) community that graph-decomposition could not split further. Treat it as one candidate for a single canonical hub, or say KEEP-INDEPENDENT if it is really several unrelated topics glued together.")
    lines.append("")
    lines.append("CLUSTER MEMBERS:")
    shown = members[:25]
    for i, member_id in enumerate(shown, 1):
        page = pages[member_id]
        excerpt_len = 300 if len(shown) <= 15 else 150
        excerpt = page["body"][:excerpt_len].replace("\n", " ").strip()
        lines.append(f"{i}. {member_id} — {page['title']}")
        lines.append(f"   {excerpt}")
    if len(members) > len(shown):
        lines.append(f"... and {len(members) - len(shown)} more members (titles only): " + ", ".join(pages[m]["title"] for m in members[len(shown):]))
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


def retired_count(verdict: dict, size: int) -> int:
    if verdict.get("verdict") == "KEEP-INDEPENDENT":
        return 0
    if "members_to_absorb" in verdict and isinstance(verdict["members_to_absorb"], list):
        return len(verdict["members_to_absorb"])
    if "error" in verdict:
        return 0
    return max(size - 1, 0)


def build_apply_plan_entry(cluster: dict, verdict: dict) -> dict | None:
    v = verdict.get("verdict")
    if v not in ("PROMOTE-HUB", "MERGE-CREATE-HUB"):
        return None
    canonical = verdict.get("canonical_slug")
    absorb = verdict.get("members_to_absorb") or [m for m in cluster["members"] if m != canonical]
    return {
        "verdict": v,
        "canonical_slug": canonical,
        "retire": absorb,
        "cluster_id": cluster.get("cluster_id"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(Path.home() / ".mikai" / "wiki-mikai-parallel-test" / "wiki"))
    ap.add_argument("--report", default="/tmp/dream-pass-report.md")
    ap.add_argument("--verdicts", default="/tmp/dream-pass-verdicts.json")
    ap.add_argument("--min-cluster", type=int, default=3)
    ap.add_argument("--max-cluster", type=int, default=15)
    ap.add_argument("--max-recursion", type=int, default=3)
    ap.add_argument("--signal", choices=["wikilink", "embedding"], default="wikilink", help="clustering graph signal: wikilink co-occurrence (default) or embedding cosine similarity")
    ap.add_argument("--edge-threshold", type=float, default=0.75, help="cosine threshold for an edge in the --signal embedding graph")
    ap.add_argument("--calibration-thresholds", default="0.75,0.80,0.85", help="comma-separated cosine thresholds to report edge counts for (--signal embedding only)")
    ap.add_argument("--kmeans-group-size", type=int, default=10)
    ap.add_argument("--limit-clusters", type=int, default=None, help="cap number of leaf clusters sent to LLM adjudication, ranked by consolidation-potential score")
    ap.add_argument("--dry-run", action="store_true", help="judge only; omit the apply_plan section from the verdicts JSON")
    ap.add_argument("--model", default="claude-sonnet-4-5")
    ap.add_argument("--embed-host", default="http://localhost:11434")
    ap.add_argument("--embed-model", default="nomic-embed-text")
    ap.add_argument("--embed-cache-dir", default=str(Path.home() / ".mikai" / "wiki-mikai-parallel-test" / ".embed-cache"))
    args = ap.parse_args()

    wiki_dir = Path(args.vault)
    embed_cfg = {"host": args.embed_host, "model": args.embed_model, "cache_dir": Path(args.embed_cache_dir)}

    print(f"[dream-pass] loading pages from {wiki_dir}")
    pages = load_pages(wiki_dir)
    print(f"[dream-pass] {len(pages)} non-retired pages loaded")

    edge_calibration = None
    if args.signal == "embedding":
        calibration_thresholds = [float(t) for t in args.calibration_thresholds.split(",")]
        g, edge_calibration = build_embedding_graph(pages, embed_cfg, args.edge_threshold, calibration_thresholds)
    else:
        g = build_graph(pages)
    print(f"[dream-pass] signal={args.signal} graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")

    communities = louvain_communities(g, seed=42)
    sizes = sorted((len(c) for c in communities), reverse=True)
    print(f"[dream-pass] {len(communities)} level-1 communities detected")

    buckets = {"1": 0, "2": 0, "3-5": 0, "6-15": 0, "16-49": 0, "50+": 0}
    for s in sizes:
        if s == 1:
            buckets["1"] += 1
        elif s == 2:
            buckets["2"] += 1
        elif s <= 5:
            buckets["3-5"] += 1
        elif s <= 15:
            buckets["6-15"] += 1
        elif s <= 49:
            buckets["16-49"] += 1
        else:
            buckets["50+"] += 1

    print("[dream-pass] decomposing communities recursively...")
    leaves, recursion_log = decompose_all(g, communities, pages, args.min_cluster, args.max_cluster, args.max_recursion, args.kmeans_group_size, embed_cfg)
    for i, leaf in enumerate(leaves):
        leaf["cluster_id"] = i
    print(f"[dream-pass] {len(leaves)} leaf clusters after recursion (target range {args.min_cluster}-{args.max_cluster}, plus any marked large-undecomposed)")

    scored = [dict(score_cluster(g, set(leaf["members"]), pages), **{k: leaf[k] for k in ("depth", "method", "cluster_id")}) for leaf in leaves]
    scored.sort(key=lambda c: c["score"], reverse=True)

    to_adjudicate = scored if args.limit_clusters is None else scored[: args.limit_clusters]
    print(f"[dream-pass] adjudicating {len(to_adjudicate)} of {len(scored)} leaf clusters")

    verdicts = []
    for i, cluster in enumerate(to_adjudicate):
        print(f"[dream-pass]   ({i + 1}/{len(to_adjudicate)}) cluster {cluster['cluster_id']} hub={cluster['hub']} size={cluster['size']} method={cluster['method']}...")
        verdict = adjudicate(cluster, pages, args.model)
        verdicts.append({"cluster": cluster, "verdict": verdict})
        print(f"[dream-pass]     -> {verdict.get('verdict', verdict.get('error', 'UNKNOWN'))}")

    verdict_counts = defaultdict(int)
    for v in verdicts:
        key = v["verdict"].get("verdict", "ERROR" if "error" in v["verdict"] else "UNKNOWN")
        verdict_counts[key] += 1

    adjudicated_ids = {v["cluster"]["cluster_id"] for v in verdicts}
    remaining = [c for c in scored if c["cluster_id"] not in adjudicated_ids]

    total_adjudicated_size = sum(v["cluster"]["size"] for v in verdicts) or 1
    total_adjudicated_retired = sum(retired_count(v["verdict"], v["cluster"]["size"]) for v in verdicts)
    retirement_rate = total_adjudicated_retired / total_adjudicated_size

    projected_retired_adjudicated = total_adjudicated_retired
    projected_retired_extrapolated = round(sum(c["size"] for c in remaining) * retirement_rate)
    projected_retired_total = projected_retired_adjudicated + projected_retired_extrapolated

    new_hub_pages_adjudicated = sum(1 for v in verdicts if v["verdict"].get("verdict") == "MERGE-CREATE-HUB")
    merge_rate = new_hub_pages_adjudicated / len(verdicts) if verdicts else 0.0
    projected_new_hubs = new_hub_pages_adjudicated + round(len(remaining) * merge_rate * (1 / max(args.max_cluster, 1)))

    projected_concept_count = len(pages) - projected_retired_total

    concept_pages = {k: v for k, v in pages.items() if k.startswith("concepts/")}
    concept_leaf_ids = set()
    for leaf in leaves:
        if any(m.startswith("concepts/") for m in leaf["members"]):
            concept_leaf_ids.add(leaf["cluster_id"])
    concept_retired_adjudicated = sum(
        retired_count(v["verdict"], v["cluster"]["size"])
        * (sum(1 for m in v["cluster"]["members"] if m.startswith("concepts/")) / v["cluster"]["size"])
        for v in verdicts
    )
    concept_share_of_extrapolated = projected_retired_extrapolated * (
        sum(1 for c in remaining for m in leaves[c["cluster_id"]]["members"] if m.startswith("concepts/"))
        / max(sum(c["size"] for c in remaining), 1)
    ) if remaining else 0
    projected_concept_retired = round(concept_retired_adjudicated + concept_share_of_extrapolated)
    projected_concept_count_only = len(concept_pages) - projected_concept_retired

    apply_plan = []
    if not args.dry_run:
        for v in verdicts:
            entry = build_apply_plan_entry(v["cluster"], v["verdict"])
            if entry:
                apply_plan.append(entry)

    # --- report ---
    lines = []
    lines.append("# Dream Pass Report (ARCH-035)\n")
    lines.append(f"- **Vault**: `{wiki_dir}`")
    lines.append(f"- **Non-retired pages loaded**: {len(pages)} (concepts: {len(concept_pages)})")
    lines.append(f"- **Signal**: {args.signal}" + (f" (edge-threshold={args.edge_threshold})" if args.signal == "embedding" else ""))
    lines.append(f"- **Graph**: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")
    lines.append(f"- **Level-1 communities detected**: {len(communities)}")
    lines.append(f"- **Leaf clusters after recursion**: {len(leaves)}")
    lines.append(f"- **Recursion budget**: max-recursion={args.max_recursion}, min/max-cluster={args.min_cluster}/{args.max_cluster}, kmeans-group-size={args.kmeans_group_size}")
    lines.append("")
    if edge_calibration is not None:
        lines.append("## Embedding edge calibration")
        lines.append("")
        lines.append(f"- **Embedding model**: `{args.embed_model}` via `{args.embed_host}`")
        lines.append("- **Proxy text**: title + first paragraph")
        lines.append(f"- **Chosen edge threshold**: {args.edge_threshold} ({g.number_of_edges()} edges)")
        lines.append("")
        lines.append("| cosine threshold | edges |")
        lines.append("|---:|---:|")
        for t in sorted(edge_calibration):
            lines.append(f"| {t} | {edge_calibration[t]} |")
        lines.append("")
    lines.append("## Level-1 community size distribution")
    lines.append("")
    lines.append("| bucket | count |")
    lines.append("|---|---:|")
    for k, v in buckets.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append(f"## Recursion log ({len(recursion_log)} events)")
    lines.append("")
    action_counts = defaultdict(int)
    for ev in recursion_log:
        action_counts[ev["action"]] += 1
    for action, count in sorted(action_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"- **{action}**: {count}")
    lines.append("")
    depth_counts = defaultdict(int)
    for leaf in leaves:
        depth_counts[leaf["depth"]] += 1
    lines.append("Leaf clusters by recursion depth reached:")
    for d in sorted(depth_counts):
        lines.append(f"- depth {d}: {depth_counts[d]} leaves")
    lines.append("")
    method_counts = defaultdict(int)
    for leaf in leaves:
        method_counts[leaf["method"]] += 1
    lines.append("Leaf clusters by method:")
    for m, c in sorted(method_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {m}: {c}")
    lines.append("")

    lines.append(f"## Adjudication ({len(verdicts)} of {len(scored)} leaf clusters, ranked by consolidation-potential score)")
    lines.append("")
    lines.append("Verdict distribution (adjudicated only):")
    for k, v in verdict_counts.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")
    for i, v in enumerate(verdicts, 1):
        cluster, verdict = v["cluster"], v["verdict"]
        lines.append(f"### {i}. Cluster {cluster['cluster_id']} — hub `{cluster['hub']}` (score {cluster['score']}, size {cluster['size']}, depth {cluster['depth']}, method {cluster['method']})")
        lines.append("")
        lines.append("Members: " + ", ".join(f"`{m}`" for m in cluster["members"][:15]) + (f" ... +{cluster['size'] - 15} more" if cluster["size"] > 15 else ""))
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(verdict, indent=2))
        lines.append("```")
        lines.append("")

    lines.append("## Projected impact")
    lines.append("")
    lines.append(f"- **Pages retired — adjudicated leaf clusters**: {projected_retired_adjudicated}")
    lines.append(f"- **Pages retired — extrapolated over remaining {len(remaining)} un-adjudicated leaf clusters** (using observed retirement rate {retirement_rate:.1%} from adjudicated sample): {projected_retired_extrapolated}")
    lines.append(f"- **Pages retired — projected total**: {projected_retired_total}")
    lines.append(f"- **New hub pages (MERGE-CREATE-HUB) — projected**: {projected_new_hubs}")
    lines.append(f"- **Concept count**: {len(pages)} → {projected_concept_count} (all subdirs)")
    lines.append(f"- **Concept-only count** (`concepts/` subdir): {len(concept_pages)} → {projected_concept_count_only}")
    compression_pct = (projected_retired_total / len(pages)) * 100 if pages else 0
    lines.append(f"- **Compression**: {compression_pct:.1f}% of all pages projected retired")
    lines.append(f"- **ARCH-035 gate (≥25% compression, ≤900 from ~1200 concepts)**: {'PASS' if compression_pct >= 25 else 'FAIL — see limitations'}")
    lines.append("")

    lines.append("## Limitations")
    lines.append("")
    lines.append(f"- Only {len(to_adjudicate)} of {len(scored)} leaf clusters were LLM-adjudicated (`--limit-clusters` cost control); the rest are extrapolated from the observed retirement rate, which is a coarse estimate, not a per-cluster judgment.")
    lines.append("- A community whose induced subgraph fragments into mostly singletons/pairs (>40% of mass in sub-groups below --min-cluster) is treated as \"didn't effectively decompose\" and routed to the same fallback as a genuinely undecomposable blob (kmeans for blobs, whole-cluster adjudication for 16-49s) — this avoids silently losing mass to dropped fragments, but means some blobs skip straight to embedding k-means without exhausting the recursion budget.")
    lines.append("- k-means fallback uses local Ollama embeddings (nomic-embed-text) with a pure-Python Lloyd's-algorithm implementation (no numpy/sklearn available in this environment) — adequate at these cluster sizes but not vectorized.")
    lines.append("- This is report-only: no vault writes. The `apply_plan` in the verdicts JSON is inert structured data for a future apply-phase (nashsu's `mergeDuplicateGroup` + `rewriteCrossReferences`), not executed here.")
    lines.append("")

    Path(args.report).write_text("\n".join(lines))
    print(f"[dream-pass] wrote {args.report}")

    payload = {
        "vault": str(wiki_dir),
        "config": vars(args),
        "summary": {
            "pages_loaded": len(pages),
            "concept_pages_loaded": len(concept_pages),
            "signal": args.signal,
            "graph_nodes": g.number_of_nodes(),
            "graph_edges": g.number_of_edges(),
            "embedding_edge_calibration": {str(t): c for t, c in edge_calibration.items()} if edge_calibration is not None else None,
            "level1_communities": len(communities),
            "level1_size_buckets": buckets,
            "leaf_clusters": len(leaves),
            "leaf_clusters_by_method": dict(method_counts),
            "leaf_clusters_by_depth": dict(depth_counts),
            "adjudicated_count": len(verdicts),
            "verdict_counts": dict(verdict_counts),
            "projected_retired_total": projected_retired_total,
            "projected_concept_count": projected_concept_count,
            "projected_concept_count_only": projected_concept_count_only,
            "compression_pct": round(compression_pct, 2),
        },
        "recursion_log": recursion_log,
        "leaf_clusters": scored,
        "verdicts": [{"cluster_id": v["cluster"]["cluster_id"], "cluster": v["cluster"], "verdict": v["verdict"]} for v in verdicts],
        "apply_plan": apply_plan,
    }
    Path(args.verdicts).write_text(json.dumps(payload, indent=2))
    print(f"[dream-pass] wrote {args.verdicts}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

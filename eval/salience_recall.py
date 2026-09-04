"""Salience recall eval — Consolidation quality metric.

Reads Brian's gold goals (~/.mikai/brain/GOALS.md) and the current
salience ledger (~/.mikai/wiki/wiki-salience.md). For each goal, finds
the best-matching candidate in the ledger by token overlap. Computes:

- recall@10, recall@20 — how many of the N goals appear in top-K
- MRR — mean reciprocal rank of first-hit-per-goal (1.0 = all rank 1)
- NDCG@10 — position-weighted relevance

Ground truth: `~/.mikai/brain/GOALS.md`, one H2 per goal.
System output: `~/.mikai/wiki/wiki-salience.md`, ranked markdown table.

Writes two artifacts per run:
- eval/reports/salience-<version>-<date>.md  (human-readable report)
- eval/history.jsonl                          (append-only machine log)

Called manually (`python -m eval.salience_recall --version v001`) or
via the make target (`make eval-salience VERSION=v001`).

No external dependencies. Pure stdlib. Runs in <2 seconds.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GOALS_MD = Path.home() / ".mikai" / "brain" / "GOALS.md"
SALIENCE_MD = Path.home() / ".mikai" / "wiki" / "wiki-salience.md"
REPORTS_DIR = REPO / "eval" / "reports"
HISTORY_JSONL = REPO / "eval" / "history.jsonl"
DASHBOARD_HTML = REPO / "eval" / "plot_salience.html"

# Cheap English stopwords for token filtering (shared shape with
# infra/graphiti/dream_bootstrap._NGRAM_STOP).
_STOP = frozenset("""
the this that these those my our your his her their its
a an and or but for nor so yet as if in on at by to of from with
he she they we you it me us them him
is are was were be being been have has had do does did
will would could should may might must shall can also just more most
what who which how why when where about above below into like near
they them their there here now today more some such very much many
""".split())


def tokenize(text: str, minlen: int = 4) -> set[str]:
    """Lowercase, drop stopwords, keep ≥minlen alphabetic tokens."""
    tokens = re.findall(r"[a-z][a-z0-9]{" + str(minlen - 1) + r",}", text.lower())
    return {t for t in tokens if t not in _STOP}


def load_goals(path: Path) -> list[dict]:
    """Parse GOALS.md. Each H2 is one goal: title + body.
    Returns [{'name': str, 'text': str, 'title_tokens': set[str],
    'body_tokens': set[str]}].

    Matching uses TITLE tokens only (v0). Body tokens are informational
    but not used for matching — otherwise every candidate shares a
    generic body word with something ("System Settings" matched
    "consumer groups" on the body's 'political' → 'system' link in v001
    dry-run, a false positive)."""
    if not path.exists():
        sys.exit(f"GOALS.md not found at {path}")
    raw = path.read_text()
    goals = []
    for m in re.finditer(
        r"^##\s+(.+?)\s*$(.*?)(?=^##\s|\Z)", raw, re.MULTILINE | re.DOTALL
    ):
        title = m.group(1).strip()
        body = m.group(2).strip()
        # Strip common connective words from title tokens: 'and', 'or',
        # 'matters', 'finding', 'taking' aren't concept anchors.
        _EXTRA_STOP = {"matters", "finding", "taking", "starting", "care",
                       "and", "or", "of", "to", "for"}
        title_tokens = {t for t in tokenize(title, minlen=3)
                        if t not in _EXTRA_STOP}
        body_tokens = tokenize(body, minlen=4)
        if title_tokens or body_tokens:
            goals.append({
                "name": title,
                "text": body,
                "title_tokens": title_tokens,
                "body_tokens": body_tokens,
                "tokens": title_tokens,  # matching key
            })
    return goals


def load_ledger(path: Path) -> list[dict]:
    """Parse wiki-salience.md's ranked table. Returns list of dicts
    with rank, name, S, base, spread, goal_overlap, mentions, and
    optionally aliases/G columns when present.

    Robust to column-set changes across versions (v001 had no aliases
    column; v002 added it; v003 will add G)."""
    if not path.exists():
        sys.exit(f"Ledger not found at {path} — run `dream_bootstrap promote` first")
    raw = path.read_text()

    # Find the "## Ranked candidates" section
    m = re.search(
        r"##\s+Ranked candidates\s*\n(.*)", raw, re.DOTALL | re.IGNORECASE
    )
    if not m:
        sys.exit("no '## Ranked candidates' section in ledger")
    tbl = m.group(1)

    # First non-blank line = header, second = separator, rest = data.
    lines = [ln for ln in tbl.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 3:
        sys.exit("ledger table has fewer than 3 rows")
    headers = [h.strip().lower() for h in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[2:]:  # skip header + separator
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < len(headers):
            continue
        row = dict(zip(headers, cells))
        rows.append(row)
    return rows


def _cand_tokens(row: dict) -> set[str]:
    """Tokens from a candidate's name + any aliases."""
    name = row.get("concept", "") or row.get("candidate", "") or row.get("name", "")
    aliases = row.get("aliases", "")
    return tokenize(name + " " + aliases, minlen=3)  # allow 3-char for names like 'mba', 'ceo'


def find_best_match(goal: dict, ledger: list[dict],
                    limit: int | None = None) -> tuple[int, str, int] | None:
    """Return (rank, matched_concept_name, overlap_count) for the first
    candidate whose name+aliases share ≥1 non-stopword token with the
    goal's tokens. rank is 1-indexed. None if no match within `limit`.

    Ties: earliest rank wins (highest-scoring hit). We do NOT require
    the candidate's tokens to be a subset of goal tokens — one shared
    load-bearing word (posture ↔ workout) is enough."""
    for rank, row in enumerate(ledger[:limit] if limit else ledger, 1):
        ctokens = _cand_tokens(row)
        overlap = goal["tokens"] & ctokens
        if overlap:
            name = row.get("concept") or row.get("name") or ""
            return (rank, name, len(overlap))
    return None


def compute_metrics(goals: list[dict], ledger: list[dict],
                    k_values: tuple[int, ...] = (10, 20, 50)) -> dict:
    """Recall@K, MRR, NDCG@K for a set of goals against a ledger.

    NDCG: gain of a hit at rank r is 1/log2(r+1). Ideal DCG = one gain
    at rank 1 per goal (perfect ranking). So NDCG = DCG_actual /
    DCG_ideal, ∈ [0,1]."""
    per_goal = []
    reciprocal_ranks = []
    for goal in goals:
        match = find_best_match(goal, ledger)
        entry = {"name": goal["name"], "hit": bool(match)}
        if match:
            rank, matched_name, overlap = match
            entry["rank"] = rank
            entry["matched_concept"] = matched_name
            entry["overlap_tokens"] = overlap
            reciprocal_ranks.append(1.0 / rank)
        else:
            entry["rank"] = None
            entry["matched_concept"] = None
            reciprocal_ranks.append(0.0)
        per_goal.append(entry)

    recalls = {}
    for k in k_values:
        hits_at_k = sum(1 for g in per_goal if g["rank"] and g["rank"] <= k)
        recalls[f"recall@{k}"] = hits_at_k / len(goals) if goals else 0.0

    mrr = sum(reciprocal_ranks) / len(goals) if goals else 0.0

    # NDCG@10
    dcg = sum(
        1.0 / math.log2(g["rank"] + 1)
        for g in per_goal
        if g["rank"] and g["rank"] <= 10
    )
    ideal_dcg = sum(1.0 / math.log2(i + 1) for i in range(1, len(goals) + 1))
    ndcg10 = dcg / ideal_dcg if ideal_dcg > 0 else 0.0

    return {
        "n_goals": len(goals),
        "n_candidates": len(ledger),
        **recalls,
        "mrr": mrr,
        "ndcg@10": ndcg10,
        "per_goal": per_goal,
    }


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
            text=True, timeout=2,
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _write_report(version: str, metrics: dict, out_dir: Path,
                  goals_path: Path, ledger_path: Path) -> Path:
    """Human-readable markdown report."""
    out_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = out_dir / f"salience-{version}-{date}.md"
    lines = [
        f"# Salience Recall — {version} — {date}",
        "",
        f"- goals: {metrics['n_goals']}  (from `{goals_path}`)",
        f"- ranked candidates: {metrics['n_candidates']}  "
        f"(from `{ledger_path}`)",
        f"- git: {_git_sha()}",
        "",
        "## Headline metrics",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| **recall@10**  | {metrics['recall@10']:.2f} "
        f"({int(metrics['recall@10'] * metrics['n_goals'])}"
        f"/{metrics['n_goals']}) |",
        f"| recall@20  | {metrics['recall@20']:.2f} |",
        f"| recall@50  | {metrics['recall@50']:.2f} |",
        f"| MRR        | {metrics['mrr']:.3f} |",
        f"| NDCG@10    | {metrics['ndcg@10']:.3f} |",
        "",
        "## Per-goal breakdown",
        "",
        "| # | Goal | Hit? | Rank | Matched candidate | Overlap tokens |",
        "|---|---|---|---|---|---|",
    ]
    for i, g in enumerate(metrics["per_goal"], 1):
        hit = "✓" if g["hit"] else "✗"
        rank = str(g["rank"]) if g["rank"] else "—"
        matched = g["matched_concept"] or "—"
        overlap = str(g.get("overlap_tokens", "")) if g["hit"] else "—"
        lines.append(
            f"| {i} | {g['name']} | {hit} | {rank} | {matched} | {overlap} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _append_history(version: str, metrics: dict) -> None:
    """Append one JSON line to history.jsonl."""
    HISTORY_JSONL.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "version": version,
        "ts": datetime.now(timezone.utc).isoformat(),
        "git": _git_sha(),
        "n_goals": metrics["n_goals"],
        "n_candidates": metrics["n_candidates"],
        "recall@10": metrics["recall@10"],
        "recall@20": metrics["recall@20"],
        "recall@50": metrics["recall@50"],
        "mrr": metrics["mrr"],
        "ndcg@10": metrics["ndcg@10"],
    }
    with HISTORY_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _write_dashboard() -> None:
    """Regenerate the visual dashboard from history.jsonl.
    Reads every historical run and produces an inline-SVG chart +
    per-version table. No external deps — opens directly via file://."""
    if not HISTORY_JSONL.exists():
        return
    rows = []
    with HISTORY_JSONL.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if not rows:
        return

    # Best-so-far line (recall@10, monotonically non-decreasing)
    best = 0.0
    bests = []
    for r in rows:
        best = max(best, r.get("recall@10", 0.0))
        bests.append(best)

    # SVG layout: 900w × 400h, margins 60/40/40/60 (t/r/b/l)
    W, H = 900, 400
    ML, MR, MT, MB = 70, 40, 50, 60
    plot_w = W - ML - MR
    plot_h = H - MT - MB
    n = len(rows)
    bar_group_w = plot_w / max(n, 1)
    bar_w = min(bar_group_w * 0.35, 40)

    def y(v: float) -> float:
        return MT + plot_h - v * plot_h

    def x(i: int) -> float:
        return ML + bar_group_w * (i + 0.5)

    svg_parts = [
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="max-width:100%;height:auto;">',
        # Background + axes
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#0d1017"/>',
        f'<line x1="{ML}" y1="{MT}" x2="{ML}" y2="{MT+plot_h}" '
        f'stroke="#4a5262" stroke-width="1"/>',
        f'<line x1="{ML}" y1="{MT+plot_h}" x2="{W-MR}" y2="{MT+plot_h}" '
        f'stroke="#4a5262" stroke-width="1"/>',
    ]
    # Y-axis gridlines + labels (0.0 → 1.0 by 0.2)
    for v in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
        yv = y(v)
        svg_parts.append(
            f'<line x1="{ML}" y1="{yv}" x2="{W-MR}" y2="{yv}" '
            f'stroke="#1c2530" stroke-width="1"/>'
        )
        svg_parts.append(
            f'<text x="{ML-8}" y="{yv+4}" text-anchor="end" fill="#8b93a5" '
            f'font-size="11" font-family="system-ui">{v:.1f}</text>'
        )
    # Bars per run
    for i, r in enumerate(rows):
        cx = x(i)
        r10 = r.get("recall@10", 0.0)
        ndcg = r.get("ndcg@10", 0.0)
        # recall@10 bar (green)
        bh = plot_h * r10
        svg_parts.append(
            f'<rect x="{cx - bar_w}" y="{y(r10)}" width="{bar_w - 2}" '
            f'height="{bh}" fill="#6bb26b"/>'
        )
        # NDCG@10 bar (blue), offset right
        bhn = plot_h * ndcg
        svg_parts.append(
            f'<rect x="{cx + 2}" y="{y(ndcg)}" width="{bar_w - 2}" '
            f'height="{bhn}" fill="#6c9ce6"/>'
        )
        # X-axis label
        svg_parts.append(
            f'<text x="{cx}" y="{H-MB+18}" text-anchor="middle" fill="#e6e6e6" '
            f'font-size="12" font-family="system-ui" font-weight="600">'
            f'{r["version"]}</text>'
        )
    # Best-so-far line (recall@10 monotonic)
    if n > 1:
        pts = " ".join(f"{x(i)},{y(v)}" for i, v in enumerate(bests))
        svg_parts.append(
            f'<polyline points="{pts}" fill="none" stroke="#d4a04a" '
            f'stroke-width="2" stroke-dasharray="4 3"/>'
        )
    # Latest headline
    latest = rows[-1]
    svg_parts.append(
        f'<text x="{W/2}" y="30" text-anchor="middle" fill="#e6e6e6" '
        f'font-size="18" font-weight="700" font-family="system-ui">'
        f'{latest["version"]}: recall@10 = {latest["recall@10"]:.2f} '
        f'({int(latest["recall@10"]*latest["n_goals"])}/{latest["n_goals"]})'
        f'</text>'
    )
    # Legend
    svg_parts.append(
        f'<rect x="{W-MR-160}" y="{MT-30}" width="12" height="12" fill="#6bb26b"/>'
        f'<text x="{W-MR-145}" y="{MT-19}" fill="#e6e6e6" font-size="11" '
        f'font-family="system-ui">recall@10</text>'
        f'<rect x="{W-MR-80}" y="{MT-30}" width="12" height="12" fill="#6c9ce6"/>'
        f'<text x="{W-MR-65}" y="{MT-19}" fill="#e6e6e6" font-size="11" '
        f'font-family="system-ui">NDCG@10</text>'
    )
    svg_parts.append('</svg>')

    # Per-version detail table
    rows_html = []
    for r in reversed(rows):
        rows_html.append(
            f'<tr><td><strong>{r["version"]}</strong></td>'
            f'<td>{r.get("ts","")[:10]}</td>'
            f'<td>{r.get("git","-")}</td>'
            f'<td>{r["n_goals"]}</td>'
            f'<td>{r["n_candidates"]}</td>'
            f'<td class="metric-strong">{r["recall@10"]:.2f}</td>'
            f'<td>{r["recall@20"]:.2f}</td>'
            f'<td>{r["mrr"]:.3f}</td>'
            f'<td>{r["ndcg@10"]:.3f}</td></tr>'
        )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MIKAI Salience — recall@10 history</title>
<style>
  body {{ margin:0; padding:32px; background:#0b0d12; color:#e6e6e6;
    font-family:-apple-system,system-ui,sans-serif; line-height:1.5; }}
  h1 {{ font-size:24px; margin:0 0 8px; letter-spacing:-0.3px; }}
  .sub {{ color:#8b93a5; margin:0 0 24px; font-size:14px; }}
  .chart-wrap {{ max-width:1000px; margin:0 auto 24px;
    background:#14181f; border:1px solid #2a2f3a; border-radius:12px;
    padding:16px; }}
  table {{ max-width:1000px; margin:0 auto; width:100%; border-collapse:collapse; }}
  th,td {{ padding:8px 12px; text-align:left; border-bottom:1px solid #2a2f3a;
    font-size:13px; }}
  th {{ color:#8b93a5; font-weight:600; text-transform:uppercase;
    letter-spacing:0.6px; font-size:11px; }}
  .metric-strong {{ color:#6bb26b; font-weight:600; }}
  .note {{ color:#8b93a5; font-size:12px; max-width:1000px; margin:16px auto;
    font-style:italic; }}
</style>
</head>
<body>
<h1>MIKAI Salience — Consolidation Quality Trajectory</h1>
<p class="sub">recall@10 = (hits in top-10) / |goals|.
Ground truth: <code>~/.mikai/brain/GOALS.md</code>. System output:
<code>~/.mikai/wiki/wiki-salience.md</code>. Dashed line: best recall@10
so far (only goes up). Regenerated by every
<code>python -m eval.salience_recall --version vXXX</code> call.</p>
<div class="chart-wrap">
{''.join(svg_parts)}
</div>
<table>
<thead><tr><th>Version</th><th>Date</th><th>Git</th><th>Goals</th>
<th>Candidates</th><th>recall@10</th><th>recall@20</th><th>MRR</th>
<th>NDCG@10</th></tr></thead>
<tbody>
{''.join(rows_html)}
</tbody>
</table>
<p class="note">Rule: every major change to the Consolidation Layer
runs against this metric. Regressions get a ⚠ flag in
<code>docs/SALIENCE_VERSION_HISTORY.md</code>. Retrieval quality and
summary faithfulness are the other two axes (deferred to v0.2).</p>
</body>
</html>
"""
    DASHBOARD_HTML.write_text(html, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True,
                    help="e.g. v001, v002 — tags the report + history row")
    ap.add_argument("--goals", type=Path, default=GOALS_MD)
    ap.add_argument("--ledger", type=Path, default=SALIENCE_MD)
    ap.add_argument("--no-history", action="store_true",
                    help="don't append to history.jsonl (dry mode)")
    args = ap.parse_args()

    goals = load_goals(args.goals)
    ledger = load_ledger(args.ledger)
    print(f"[eval] {len(goals)} goals, {len(ledger)} ranked candidates")
    metrics = compute_metrics(goals, ledger)
    print(f"[eval] recall@10={metrics['recall@10']:.2f}  "
          f"MRR={metrics['mrr']:.3f}  NDCG@10={metrics['ndcg@10']:.3f}")
    for g in metrics["per_goal"]:
        if g["hit"]:
            print(f"  ✓ {g['name']:.<50} rank {g['rank']:>4} → {g['matched_concept']}")
        else:
            print(f"  ✗ {g['name']:.<50}  MISS")
    report = _write_report(args.version, metrics, REPORTS_DIR,
                           args.goals, args.ledger)
    print(f"[eval] report -> {report}")
    if not args.no_history:
        _append_history(args.version, metrics)
        print(f"[eval] history -> {HISTORY_JSONL}")
        _write_dashboard()
        print(f"[eval] dashboard -> {DASHBOARD_HTML}")


if __name__ == "__main__":
    main()

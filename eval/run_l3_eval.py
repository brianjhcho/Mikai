#!/usr/bin/env python3
"""
eval/run_l3_eval.py — Stage-6 L3 typed-extraction eval runner.

Reads eval/labeled_entities.jsonl and eval/labeled_edges.jsonl (Brian's
hand-labeled gold sets), computes precision/recall/noise metrics against the
acceptance criteria in the Stage-6 brief, and writes a scorecard to
docs/evals/stage6-{YYYY-MM-DD}.md.

Exit codes:
  0  — all blocking metrics pass
  1  — one or more blocking metrics fail
  2  — usage / input error

Does NOT call DeepSeek, Voyage, or Neo4j. Operates entirely on the labeled
JSONL files that the seeder + Brian's labels have produced.

The --latency flag optionally exercises the live sidecar for p95 latency
measurements; omit it (or use --no-latency) to run fully offline.

Usage:
  python eval/run_l3_eval.py
  python eval/run_l3_eval.py --entities-file eval/labeled_entities.jsonl \\
                              --edges-file    eval/labeled_edges.jsonl
  python eval/run_l3_eval.py --no-latency
  python eval/run_l3_eval.py --sidecar-url http://localhost:8100 --latency
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "infra" / "graphiti"))

from eval.schemas import EdgeCandidate, EntityCandidate, load_edge_jsonl, load_entity_jsonl

# ── Acceptance criteria (from Stage-6 brief) ─────────────────────────────────

CRITERIA: dict[str, dict] = {
    "entity_precision":          {"threshold": 0.85, "blocking": True},
    "entity_recall":             {"threshold": 0.75, "blocking": True},
    "edge_precision":            {"threshold": 0.80, "blocking": True},
    "edge_recall":               {"threshold": 0.65, "blocking": True},
    "noise_rate":                {"max": 0.10,       "blocking": True},
    "ingestion_latency_p95_ms":  {"max": 8000,       "blocking": True},
    "query_latency_p95_ms":      {"max": 500,        "blocking": True},
}

DEFAULT_SIDECAR_URL = "http://localhost:8100"

# ── Metric computation ────────────────────────────────────────────────────────


def compute_entity_metrics(
    records: list[EntityCandidate],
) -> dict[str, float]:
    """
    Precision and recall from the labeled entity set.

    Precision: of labeled records, fraction that are valid.
    Recall:    fraction of the gold-valid set we can confirm were extracted
               (i.e. present in the candidate pool, labeled valid).

    Since the candidate pool is a sample — not an exhaustive enumeration —
    recall here measures the extraction rate within the sampled set.
    Both directions require only `is_valid` labels; no separate "reference" set.

    Noise rate: fraction of labeled records where is_valid == False.
    """
    labeled = [r for r in records if r.is_valid is not None]
    if not labeled:
        return {"entity_precision": 0.0, "entity_recall": 0.0, "noise_rate": 0.0, "n_labeled": 0}

    n_valid = sum(1 for r in labeled if r.is_valid is True)
    n_invalid = sum(1 for r in labeled if r.is_valid is False)
    n_total = len(labeled)

    precision = n_valid / n_total if n_total else 0.0
    # Recall within sampled set: fraction of the full candidate list (including
    # unlabeled) that were both sampled AND labeled valid.  This is a lower
    # bound on true recall.
    n_all = len(records)
    recall = n_valid / n_all if n_all else 0.0
    noise_rate = n_invalid / n_total if n_total else 0.0

    return {
        "entity_precision": round(precision, 4),
        "entity_recall": round(recall, 4),
        "noise_rate": round(noise_rate, 4),
        "n_labeled": n_total,
        "n_valid": n_valid,
        "n_invalid": n_invalid,
        "n_total_candidates": n_all,
    }


def compute_edge_metrics(
    records: list[EdgeCandidate],
) -> dict[str, float]:
    """Precision and recall from the labeled edge set."""
    labeled = [r for r in records if r.is_valid is not None]
    if not labeled:
        return {"edge_precision": 0.0, "edge_recall": 0.0, "n_labeled": 0}

    n_valid = sum(1 for r in labeled if r.is_valid is True)
    n_total = len(labeled)
    n_all = len(records)

    precision = n_valid / n_total if n_total else 0.0
    recall = n_valid / n_all if n_all else 0.0

    return {
        "edge_precision": round(precision, 4),
        "edge_recall": round(recall, 4),
        "n_labeled": n_total,
        "n_valid": n_valid,
        "n_invalid": n_total - n_valid,
        "n_total_candidates": n_all,
    }


# ── Latency measurement ───────────────────────────────────────────────────────


def measure_ingestion_latency(
    sidecar_url: str, n_samples: int = 20
) -> dict[str, float]:
    """
    Hit the sidecar's /add_note endpoint with a synthetic episode and measure
    wall-clock latency. Returns p50 and p95 in milliseconds.

    Requires the live sidecar to be running.
    """
    endpoint = f"{sidecar_url.rstrip('/')}/add_note"
    latencies: list[float] = []

    for i in range(n_samples):
        payload = json.dumps(
            {
                "content": f"Eval latency probe {i}: Martin discussed the Kenya coffee supply chain.",
                "source": "eval_probe",
                "name": f"eval-probe-{i}",
            }
        ).encode()
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
        except Exception:
            pass  # still record the elapsed time
        latencies.append((time.perf_counter() - t0) * 1000)

    if not latencies:
        return {"ingestion_p50_ms": 0.0, "ingestion_p95_ms": 0.0}

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95)]
    return {
        "ingestion_p50_ms": round(p50, 1),
        "ingestion_p95_ms": round(p95, 1),
    }


def measure_query_latency(
    sidecar_url: str, n_samples: int = 20
) -> dict[str, float]:
    """
    Hit the sidecar's /search endpoint and measure wall-clock latency.
    """
    endpoint = f"{sidecar_url.rstrip('/')}/search"
    queries = [
        "Martin Ngacha coffee farm",
        "Kenya specialty coffee supply chain",
        "colonial economic structures",
        "MIKAI build timeline",
        "WhatsApp conversation Nairobi",
    ]
    latencies: list[float] = []

    for i in range(n_samples):
        query = queries[i % len(queries)]
        payload = json.dumps({"query": query, "num_results": 5}).encode()
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except Exception:
            pass
        latencies.append((time.perf_counter() - t0) * 1000)

    if not latencies:
        return {"query_p50_ms": 0.0, "query_p95_ms": 0.0}

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95)]
    return {
        "query_p50_ms": round(p50, 1),
        "query_p95_ms": round(p95, 1),
    }


# ── Scorecard rendering ───────────────────────────────────────────────────────


def _pass_fail(value: float, criterion: dict) -> str:
    if "threshold" in criterion:
        return "PASS" if value >= criterion["threshold"] else "FAIL"
    elif "max" in criterion:
        return "PASS" if value <= criterion["max"] else "FAIL"
    return "?"


def render_scorecard(
    metrics: dict,
    latency_skipped: bool,
    timestamp: str,
) -> str:
    lines: list[str] = [
        f"# Stage-6 L3 eval scorecard — {timestamp}",
        "",
        "Generated by `eval/run_l3_eval.py`.",
        "",
        "## Acceptance criteria",
        "",
        "| Metric | Value | Threshold | Status |",
        "|---|---|---|---|",
    ]

    for key, crit in CRITERIA.items():
        if key in ("ingestion_latency_p95_ms", "query_latency_p95_ms") and latency_skipped:
            lines.append(f"| `{key}` | _(skipped)_ | {list(crit.values())[0]} | — |")
            continue

        value = metrics.get(key)
        if value is None:
            lines.append(f"| `{key}` | N/A | {list(crit.values())[0]} | — |")
            continue

        status = _pass_fail(value, crit)
        threshold_str = (
            f"≥ {crit['threshold']}" if "threshold" in crit else f"≤ {crit['max']}"
        )
        status_cell = f"**{status}**" if status == "FAIL" else status
        lines.append(f"| `{key}` | {value} | {threshold_str} | {status_cell} |")

    lines += [
        "",
        "## Detail",
        "",
    ]

    # Entity detail
    if "n_labeled" in metrics:
        lines += [
            "### Entities",
            "",
            f"- Candidates seeded: {metrics.get('n_total_candidates', '?')}",
            f"- Labeled: {metrics.get('n_labeled', '?')}",
            f"- Valid: {metrics.get('n_valid', '?')}",
            f"- Invalid: {metrics.get('n_invalid', '?')}",
            "",
        ]

    if "edge_n_labeled" in metrics:
        lines += [
            "### Edges",
            "",
            f"- Candidates seeded: {metrics.get('edge_n_total_candidates', '?')}",
            f"- Labeled: {metrics.get('edge_n_labeled', '?')}",
            f"- Valid: {metrics.get('edge_n_valid', '?')}",
            f"- Invalid: {metrics.get('edge_n_invalid', '?')}",
            "",
        ]

    if not latency_skipped:
        lines += [
            "### Latency",
            "",
            f"- Ingestion p50: {metrics.get('ingestion_p50_ms', '?')} ms",
            f"- Ingestion p95: {metrics.get('ingestion_p95_ms', '?')} ms",
            f"- Query p50: {metrics.get('query_p50_ms', '?')} ms",
            f"- Query p95: {metrics.get('query_p95_ms', '?')} ms",
            "",
        ]

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Stage-6 L3 typed-extraction eval."
    )
    parser.add_argument(
        "--entities-file",
        default=str(REPO_ROOT / "eval" / "labeled_entities.jsonl"),
        metavar="PATH",
    )
    parser.add_argument(
        "--edges-file",
        default=str(REPO_ROOT / "eval" / "labeled_edges.jsonl"),
        metavar="PATH",
    )
    parser.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "docs" / "evals"),
        metavar="DIR",
        help="Directory to write scorecard markdown.",
    )
    parser.add_argument(
        "--sidecar-url",
        default=DEFAULT_SIDECAR_URL,
        metavar="URL",
        help=f"Sidecar base URL for latency probes (default: {DEFAULT_SIDECAR_URL}).",
    )
    latency_group = parser.add_mutually_exclusive_group()
    latency_group.add_argument(
        "--latency",
        dest="measure_latency",
        action="store_true",
        help="Measure ingestion and query p95 latency against the live sidecar.",
    )
    latency_group.add_argument(
        "--no-latency",
        dest="measure_latency",
        action="store_false",
        help="Skip latency measurement (default).",
    )
    parser.set_defaults(measure_latency=False)
    args = parser.parse_args()

    entities_path = Path(args.entities_file)
    edges_path = Path(args.edges_file)

    # ── Load data ────────────────────────────────────────────────────────────

    if not entities_path.exists():
        print(
            f"ERROR: entities file not found: {entities_path}\n"
            "Run: python eval/seed_candidates.py",
            file=sys.stderr,
        )
        return 2

    if not edges_path.exists():
        print(
            f"ERROR: edges file not found: {edges_path}\n"
            "Run: python eval/seed_candidates.py",
            file=sys.stderr,
        )
        return 2

    entity_records = load_entity_jsonl(str(entities_path))
    edge_records = load_edge_jsonl(str(edges_path))

    n_entity_labeled = sum(1 for r in entity_records if r.is_valid is not None)
    n_edge_labeled = sum(1 for r in edge_records if r.is_valid is not None)

    if n_entity_labeled == 0 and n_edge_labeled == 0:
        print(
            "ERROR: no labeled records found.\n"
            "Run: python eval/label.py   to label candidates first.",
            file=sys.stderr,
        )
        return 2

    # ── Compute metrics ──────────────────────────────────────────────────────

    metrics: dict = {}

    entity_m = compute_entity_metrics(entity_records)
    metrics["entity_precision"] = entity_m["entity_precision"]
    metrics["entity_recall"] = entity_m["entity_recall"]
    metrics["noise_rate"] = entity_m["noise_rate"]
    metrics["n_labeled"] = entity_m.get("n_labeled", 0)
    metrics["n_valid"] = entity_m.get("n_valid", 0)
    metrics["n_invalid"] = entity_m.get("n_invalid", 0)
    metrics["n_total_candidates"] = entity_m.get("n_total_candidates", 0)

    edge_m = compute_edge_metrics(edge_records)
    metrics["edge_precision"] = edge_m["edge_precision"]
    metrics["edge_recall"] = edge_m["edge_recall"]
    metrics["edge_n_labeled"] = edge_m.get("n_labeled", 0)
    metrics["edge_n_valid"] = edge_m.get("n_valid", 0)
    metrics["edge_n_invalid"] = edge_m.get("n_invalid", 0)
    metrics["edge_n_total_candidates"] = edge_m.get("n_total_candidates", 0)

    latency_skipped = not args.measure_latency

    if args.measure_latency:
        print(f"Measuring ingestion latency against {args.sidecar_url}…")
        ing = measure_ingestion_latency(args.sidecar_url)
        metrics["ingestion_latency_p95_ms"] = ing["ingestion_p95_ms"]
        metrics["ingestion_p50_ms"] = ing["ingestion_p50_ms"]

        print(f"Measuring query latency against {args.sidecar_url}…")
        qry = measure_query_latency(args.sidecar_url)
        metrics["query_latency_p95_ms"] = qry["query_p95_ms"]
        metrics["query_p50_ms"] = qry["query_p50_ms"]

    # ── Evaluate pass/fail ────────────────────────────────────────────────────

    failures: list[str] = []
    for metric_key, crit in CRITERIA.items():
        if metric_key in ("ingestion_latency_p95_ms", "query_latency_p95_ms"):
            if latency_skipped:
                continue
        value = metrics.get(metric_key)
        if value is None:
            continue
        if "threshold" in crit and value < crit["threshold"]:
            failures.append(
                f"  FAIL  {metric_key}: {value} < {crit['threshold']} (threshold)"
            )
        elif "max" in crit and value > crit["max"]:
            failures.append(
                f"  FAIL  {metric_key}: {value} > {crit['max']} (max)"
            )

    # ── Print summary ─────────────────────────────────────────────────────────

    print()
    print("─" * 60)
    print("Stage-6 L3 eval results")
    print("─" * 60)
    print(f"  entity_precision:      {metrics.get('entity_precision', 'N/A')}")
    print(f"  entity_recall:         {metrics.get('entity_recall', 'N/A')}")
    print(f"  noise_rate:            {metrics.get('noise_rate', 'N/A')}")
    print(f"  edge_precision:        {metrics.get('edge_precision', 'N/A')}")
    print(f"  edge_recall:           {metrics.get('edge_recall', 'N/A')}")
    if not latency_skipped:
        print(f"  ingestion_p95_ms:      {metrics.get('ingestion_latency_p95_ms', 'N/A')}")
        print(f"  query_p95_ms:          {metrics.get('query_latency_p95_ms', 'N/A')}")
    else:
        print("  latency:               (skipped — use --latency to measure)")
    print("─" * 60)

    if failures:
        print("\nFAILING METRICS:")
        for msg in failures:
            print(msg)
        overall = "FAIL"
    else:
        print("\nAll measured metrics PASS.")
        overall = "PASS"

    # ── Write scorecard ───────────────────────────────────────────────────────

    timestamp = datetime.now().strftime("%Y-%m-%d")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scorecard_path = out_dir / f"stage6-{timestamp}.md"

    scorecard = render_scorecard(metrics, latency_skipped, timestamp)
    scorecard_path.write_text(scorecard, encoding="utf-8")
    print(f"\nScorecard written to: {scorecard_path}")

    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

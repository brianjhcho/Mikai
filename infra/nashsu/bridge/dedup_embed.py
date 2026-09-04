"""R5 dedup — embedding-cosine banding via local Ollama.

Companion to `dedup_report.py`. Where that script uses lexical body-Jaccard
(catches only literal-token dupes), this one embeds every concept page body
via Ollama's HTTP `/api/embed` and cosine-scores all pairs, catching
synonym pairs (`information-asymmetry` vs `asymmetric-information`) that
Jaccard misses.

Report-only. No writes to the vault. Preserves Fable's 3 modifications:
  1. Retire-not-delete — emits merge PROPOSALS with `retire_to:` targets.
  2. Confidence-banded — HIGH / MEDIUM / LOW by cosine (thresholds
     tuned for nomic-embed-text default; override via CLI).
  3. Feed bodies, not descriptions — parses `## Overview` + `## Notes`
     from each concept page and embeds that.

Requires:
  - `ollama serve` running at $OLLAMA_HOST (default http://localhost:11434)
  - Embedding model pulled: `ollama pull nomic-embed-text`
  - `numpy` (already in .venv)

Vector cache: writes `~/.mikai/wiki-mikai-parallel-test/.embed-cache/<sha>.json`
per body so repeated runs skip Ollama round-trips.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error
from itertools import combinations
from pathlib import Path

# Reuse the parsing bits from the deterministic dedup script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dedup_report import parse_page  # noqa: E402


def _post_json(url: str, payload: dict, timeout: float = 60.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ollama_embed(host: str, model: str, text: str) -> list:
    """Call Ollama /api/embed for a single input. Returns the vector."""
    resp = _post_json(f"{host}/api/embed", {"model": model, "input": text})
    embs = resp.get("embeddings") or []
    if not embs:
        raise RuntimeError(f"empty embeddings from Ollama for model={model!r}")
    return embs[0]


def cosine(a, b) -> float:
    # Pure-Python cosine; 541 pages × 768 dims fits ~30s for full pairwise.
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


def normalize(v) -> list:
    n = sum(x * x for x in v) ** 0.5
    if n == 0.0:
        return list(v)
    return [x / n for x in v]


def cosine_pre_normalized(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def _sha(text: str, model: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\n")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


def load_or_embed(host: str, model: str, text: str, cache_dir: Path) -> list:
    key = _sha(text, model)
    cache_file = cache_dir / f"{key}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except Exception:
            pass
    vec = ollama_embed(host, model, text)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(vec))
    return vec


def band(c: float, hi: float, mid: float, lo: float) -> str | None:
    if c >= hi:
        return "HIGH"
    if c >= mid:
        return "MEDIUM"
    if c >= lo:
        return "LOW"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--concepts-dir",
        default=str(
            Path.home() / ".mikai" / "wiki-mikai-parallel-test" / "wiki" / "concepts"
        ),
    )
    ap.add_argument(
        "--cache-dir",
        default=str(
            Path.home()
            / ".mikai"
            / "wiki-mikai-parallel-test"
            / ".embed-cache"
        ),
    )
    ap.add_argument("--report", default="eval/reports/dedup_r5_embed_2026-08-31.md")
    ap.add_argument("--json", default="eval/reports/dedup_r5_embed_2026-08-31.json")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ap.add_argument("--model", default="nomic-embed-text")
    ap.add_argument("--stub-threshold", type=int, default=200)
    ap.add_argument("--hi", type=float, default=0.88)
    ap.add_argument("--mid", type=float, default=0.80)
    ap.add_argument("--lo", type=float, default=0.72)
    ap.add_argument("--max-report-per-band", type=int, default=200)
    args = ap.parse_args()

    concepts_dir = Path(args.concepts_dir)
    cache_dir = Path(args.cache_dir)
    md_paths = sorted(concepts_dir.glob("*.md"))
    pages_raw = [parse_page(p) for p in md_paths]
    pages = [p for p in pages_raw if p["body_len"] >= args.stub_threshold]
    stubs = len(pages_raw) - len(pages)

    print(f"[dedup-embed] {len(pages)} pages to embed (stubs skipped: {stubs})")

    # Embed all pages, with progress + cache
    t0 = time.time()
    for i, p in enumerate(pages, 1):
        try:
            p["vec"] = load_or_embed(args.host, args.model, p["body"], cache_dir)
        except (urllib.error.URLError, RuntimeError) as e:
            print(f"[dedup-embed] FAIL {p['slug']}: {e}", file=sys.stderr)
            p["vec"] = None
        if i % 25 == 0 or i == len(pages):
            print(f"[dedup-embed]   {i}/{len(pages)} embedded ({time.time() - t0:.1f}s)")

    pages_ok = [p for p in pages if p.get("vec")]
    for p in pages_ok:
        p["vec_n"] = normalize(p["vec"])
    print(f"[dedup-embed] cosine over {len(pages_ok)} pages ({len(pages_ok) * (len(pages_ok) - 1) // 2} pairs)")

    banded = {"HIGH": [], "MEDIUM": [], "LOW": []}
    t_pair = time.time()
    for i, (a, b) in enumerate(combinations(pages_ok, 2), 1):
        c = cosine_pre_normalized(a["vec_n"], b["vec_n"])
        band_name = band(c, args.hi, args.mid, args.lo)
        if not band_name:
            continue
        retire_to = a["slug"] if a["body_len"] >= b["body_len"] else b["slug"]
        retire = b["slug"] if a["body_len"] >= b["body_len"] else a["slug"]
        banded[band_name].append(
            {
                "retire": retire,
                "retire_to": retire_to,
                "cosine": round(c, 4),
                "body_a": a["body_len"],
                "body_b": b["body_len"],
            }
        )

    for k in banded:
        banded[k].sort(key=lambda r: r["cosine"], reverse=True)

    payload = {
        "vault": str(concepts_dir),
        "model": args.model,
        "host": args.host,
        "thresholds": {"HIGH": args.hi, "MEDIUM": args.mid, "LOW": args.lo},
        "total_pages": len(pages_raw),
        "analyzed_pages": len(pages),
        "embedded_pages": len(pages_ok),
        "stubs_skipped": stubs,
        "pairs_scored": len(pages_ok) * (len(pages_ok) - 1) // 2,
        "banded_counts": {k: len(v) for k, v in banded.items()},
        "pairs": banded,
    }

    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(payload, indent=2))

    lines = []
    lines.append("# R5 Dedup Report — embedding cosine (Ollama)\n")
    lines.append(f"- **Vault**: `{concepts_dir}`")
    lines.append(f"- **Embedding model**: `{args.model}` via `{args.host}`")
    lines.append(f"- **Concept pages total**: {len(pages_raw)}")
    lines.append(f"- **Pages analyzed (body ≥ {args.stub_threshold} chars)**: {len(pages)}")
    lines.append(f"- **Successfully embedded**: {len(pages_ok)}")
    lines.append(f"- **Stubs skipped**: {stubs}")
    lines.append(f"- **Pairs scored**: {payload['pairs_scored']:,}")
    lines.append("")
    lines.append("## Fable's 3 modifications")
    lines.append("1. **Retire-not-delete** — every proposal names `retire` (smaller/weaker) + `retire_to` (larger/canonical). Nothing mutated.")
    lines.append(f"2. **Confidence-banded** — HIGH ≥ {args.hi}, MEDIUM {args.mid}–{args.hi}, LOW {args.lo}–{args.mid} (cosine).")
    lines.append("3. **Feed bodies** — embedded `## Overview` + `## Notes` sections, not frontmatter descriptions.")
    lines.append("")
    lines.append("## Band counts")
    for k in ("HIGH", "MEDIUM", "LOW"):
        lines.append(f"- **{k}**: {len(banded[k])}")
    lines.append("")

    for k in ("HIGH", "MEDIUM", "LOW"):
        rows = banded[k]
        lines.append(f"## {k} ({len(rows)} pairs)")
        if k == "LOW":
            lines.append("> ⚠️ Manual review only — weak semantic signal.")
        lines.append("")
        if not rows:
            lines.append("_none_\n")
            continue
        lines.append("| retire | retire_to | cosine | body_lens |")
        lines.append("|---|---|---:|---|")
        show = rows[: args.max_report_per_band]
        for r in show:
            lines.append(
                f"| `{r['retire']}` | `{r['retire_to']}` | {r['cosine']:.4f} | {r['body_a']} / {r['body_b']} |"
            )
        if len(rows) > args.max_report_per_band:
            lines.append(f"\n_… {len(rows) - args.max_report_per_band} more {k} pairs elided; see JSON._")
        lines.append("")

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(lines))
    print(f"[dedup-embed] wrote {args.report}")
    print(f"[dedup-embed] wrote {args.json}")
    print(
        f"[dedup-embed] HIGH={len(banded['HIGH'])} MEDIUM={len(banded['MEDIUM'])} LOW={len(banded['LOW'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

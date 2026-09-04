"""Pre-extraction semantic top-K retrieval for MIKAI link-at-birth.

Given a source markdown file, embed its body via Ollama and return the
top-K semantically-similar existing concept/entity/wisdom pages from the
vault. Output is a markdown block that nashsu's extraction prompt can
prepend to its `## Current Wiki Index` section — LLM sees semantic
neighbors upfront and reuses their slugs instead of coining synonyms.

This is Mechanism B (pre-extraction top-K) in Fable's KBP+EL design.
Mechanism A (post-extraction dedup) already runs via `dedup_embed.py`
+ `dedup_r5_verdicts` LLM-judge + retire-not-delete apply as our
safety net. Together they mirror BLINK / LlamaIndex / mem0 patterns.

Reuses `dedup_embed.py`'s Ollama transport, cache format, and
parse_page helper — one cache is shared with post-ingest dedup.

Zero Rust dependency. Local Ollama + JSON blob cache + brute-force
cosine — same architecture that already serves post-ingest dedup.

Usage:
  python3 pre_extract_topk.py \\
    --source ~/.mikai/wiki-mikai-parallel-test/raw/sources/<file>.md \\
    --project ~/.mikai/wiki-mikai-parallel-test \\
    --out-md /tmp/topk-<basename>.md \\
    --top-k 40

Emits a markdown block to `--out-md`:
  ## Semantic Neighbors (top-K by embedding cosine, most-similar first)
  These existing pages are semantically closest to the current source.
  REUSE these slugs when a concept/entity in the source matches — do
  not coin synonym slugs. Rank order = cosine similarity descending.

  - [[concepts/foo]] — Foo Concept (cosine 0.87)
  - [[entities/bar]] — Bar Entity (cosine 0.85)
  ...

If Ollama is unavailable or embedding fails, exits 0 with an EMPTY
output file — nashsu's prompt building degrades gracefully to
lexical-only. Never blocks ingest.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Reuse dedup_embed's helpers so cache format + Ollama transport stay in sync.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dedup_embed import (  # noqa: E402
    ollama_embed,
    load_or_embed,
    cosine_pre_normalized,
    normalize,
)
from dedup_report import parse_page  # noqa: E402


# Same section list nashsu treats as canonical knowledge pages, in the
# same order the CLI's refreshCanonicalDirectory helper enumerates.
CANONICAL_DIRS = ("concepts", "entities", "wisdom")


def chunk_source_body(body: str, max_chars: int = 8000) -> list[str]:
    """Chunk source body for embedding. Ollama's nomic-embed-text has
    ~8K token context; 8000 chars is a safe under-approximation. Chunks
    are then mean-pooled to produce one vector per source.

    If body fits, single chunk. Otherwise splits on paragraph boundaries
    to preserve semantic coherence.
    """
    if len(body) <= max_chars:
        return [body]
    chunks: list[str] = []
    cur = ""
    for para in body.split("\n\n"):
        if len(cur) + len(para) + 2 <= max_chars:
            cur += (para + "\n\n") if cur else para
        else:
            if cur:
                chunks.append(cur)
            if len(para) > max_chars:
                # Single paragraph too long — hard split
                for i in range(0, len(para), max_chars):
                    chunks.append(para[i:i + max_chars])
                cur = ""
            else:
                cur = para
    if cur:
        chunks.append(cur)
    return chunks


def mean_pool(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    out = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            out[i] += x
    n = float(len(vectors))
    return [x / n for x in out]


def embed_source_body(body: str, host: str, model: str) -> list[float] | None:
    """Chunk + embed + mean-pool. No caching for sources — they're
    one-shot per ingest round."""
    chunks = chunk_source_body(body)
    vecs = []
    for chunk in chunks:
        try:
            vec = ollama_embed(host, model, chunk)
            vecs.append(vec)
        except (urllib.error.URLError, RuntimeError) as e:
            print(f"[pre-topk] source-chunk embed FAIL: {e}", file=sys.stderr)
            return None
    return mean_pool(vecs) if vecs else None


def read_source_body(source_path: Path) -> str:
    """Return body text with the ingest header stripped (the '###'
    line and any wiki-raw metadata) — nashsu processes just the body."""
    text = source_path.read_text(encoding="utf-8", errors="replace")
    # Strip a leading "### YYYY-MM-DD... — source: ..." header if present
    if text.startswith("### "):
        newline = text.find("\n")
        if newline >= 0:
            text = text[newline + 1:]
    return text.strip()


def load_page_titles(project_path: Path) -> dict[str, str]:
    """Map "concepts/foo" -> "Foo Title" by reading each page's
    frontmatter title. Skips retired-to redirect stubs (short bodies
    with retired_to: frontmatter). Uses parse_page to be consistent
    with dedup_embed's page-selection semantics."""
    titles: dict[str, str] = {}
    for dir_name in CANONICAL_DIRS:
        dir_path = project_path / "wiki" / dir_name
        if not dir_path.is_dir():
            continue
        for md in sorted(dir_path.glob("*.md")):
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Skip redirects — they carry retired_to: and shouldn't be
            # suggested as canonical neighbors
            if "retired_to:" in text[:400]:
                continue
            # Extract title from YAML frontmatter
            title = md.stem
            if text.startswith("---\n"):
                fm_end = text.find("\n---\n", 4)
                if fm_end > 0:
                    fm = text[4:fm_end]
                    for line in fm.split("\n"):
                        if line.startswith("title:"):
                            title = line.split(":", 1)[1].strip().strip('"').strip("'")
                            break
            slug = f"{dir_name}/{md.stem}"
            titles[slug] = title
    return titles


def collect_page_vectors(
    project_path: Path,
    cache_dir: Path,
    host: str,
    model: str,
    stub_threshold: int = 200,
) -> list[dict]:
    """For each canonical page, load or compute its embedding, normalize,
    return list of {slug, title, vec_n}. Skips stubs + retired
    redirects (parse_page returns them but we filter by body length + fm)."""
    out: list[dict] = []
    for dir_name in CANONICAL_DIRS:
        dir_path = project_path / "wiki" / dir_name
        if not dir_path.is_dir():
            continue
        for md in sorted(dir_path.glob("*.md")):
            page = parse_page(md)
            if page["body_len"] < stub_threshold:
                continue
            # Skip retired redirects
            text_head = md.read_text(encoding="utf-8", errors="replace")[:400]
            if "retired_to:" in text_head:
                continue
            slug = f"{dir_name}/{md.stem}"
            try:
                vec = load_or_embed(host, model, page["body"], cache_dir)
                out.append({"slug": slug, "vec_n": normalize(vec)})
            except (urllib.error.URLError, RuntimeError) as e:
                print(f"[pre-topk] page embed FAIL {slug}: {e}", file=sys.stderr)
    return out


def write_empty(out_path: Path) -> None:
    """Emit an empty file so downstream code can graceful-degrade."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="path to raw/sources/<file>.md")
    ap.add_argument(
        "--project",
        default=str(Path.home() / ".mikai" / "wiki-mikai-parallel-test"),
    )
    ap.add_argument(
        "--cache-dir",
        default=str(Path.home() / ".mikai" / "wiki-mikai-parallel-test" / ".embed-cache"),
    )
    ap.add_argument("--out-md", required=True, help="where to write the topK markdown block")
    ap.add_argument("--top-k", type=int, default=40)
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ap.add_argument("--model", default="nomic-embed-text")
    ap.add_argument("--min-cosine", type=float, default=0.4,
                    help="drop neighbors below this cosine (noise floor)")
    args = ap.parse_args()

    source_path = Path(args.source)
    if not source_path.is_file():
        print(f"[pre-topk] source not found: {source_path}", file=sys.stderr)
        write_empty(Path(args.out_md))
        return 0

    project = Path(args.project)
    cache = Path(args.cache_dir)
    out_md = Path(args.out_md)

    body = read_source_body(source_path)
    if not body:
        write_empty(out_md)
        return 0

    # Embed source body (chunk + mean-pool)
    src_vec = embed_source_body(body, args.host, args.model)
    if not src_vec:
        print(f"[pre-topk] source embedding unavailable; degrading to empty top-K", file=sys.stderr)
        write_empty(out_md)
        return 0
    src_vec_n = normalize(src_vec)

    # Load or compute all canonical page vectors
    pages = collect_page_vectors(project, cache, args.host, args.model)
    if not pages:
        print(f"[pre-topk] no canonical pages found; empty top-K", file=sys.stderr)
        write_empty(out_md)
        return 0

    # Cosine score
    scored: list[tuple[float, str]] = []
    for p in pages:
        c = cosine_pre_normalized(src_vec_n, p["vec_n"])
        if c >= args.min_cosine:
            scored.append((c, p["slug"]))
    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[: args.top_k]

    titles = load_page_titles(project)

    # Emit markdown block
    lines: list[str] = []
    lines.append(f"## Semantic Neighbors (top {len(top)} by embedding cosine, most-similar first)")
    lines.append("")
    lines.append(f"These existing pages are semantically closest to the current source (cosine ≥ {args.min_cosine}).")
    lines.append(
        "REUSE these slugs when a concept/entity in the source matches or is a synonym — do NOT coin new synonym slugs."
    )
    lines.append("The full lexical directory below is a fallback for concepts these neighbors miss.")
    lines.append("")
    for cos, slug in top:
        title = titles.get(slug, slug.split("/")[-1])
        lines.append(f"- [[{slug}]] — {title} (cosine {cos:.3f})")
    lines.append("")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"[pre-topk] wrote {len(top)} neighbors → {out_md} (from {len(pages)} candidates)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

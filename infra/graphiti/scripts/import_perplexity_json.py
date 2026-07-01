"""
import_perplexity_json.py

Ingest Perplexity research threads directly from JSON export files (produced
by browser-extension scrapers, e.g. simwai/perplexity-ai-export, or the
abandoned perplexity-playwright.ts in legacy/sqlite-local lineage).

This BYPASSES ~/.mikai/mikai.db. The mikai.db perplexity table is partially
populated (only 295/1455 rows have raw_content; the other 1160 are empty
stubs from a March 28 metadata-only run that never fetched the answers).
The canonical source of truth is the JSON dump on disk.

JSON shape produced by Perplexity browser-extension exporters:
{
  "title": str,        # ~ the original user query (truncated)
  "slug": str,         # short id used in the URL
  "url": str,          # original perplexity.ai URL
  "source": "perplexity",
  "exported_at": ISO timestamp (when the export tool wrote this file),
  "chat_messages": [
    {"sender": "user"|"assistant", "text": "..."},
    ...
  ]
}

For Perplexity, each "assistant" message's `text` field is itself a
JSON-encoded list of step objects:
  - INITIAL_QUERY  -> content.query  (the user's question for this turn)
  - SEARCH_WEB     -> content.queries (the web queries Perplexity ran)
  - SEARCH_RESULTS -> content.web_results (cited sources, large)
  - FINAL          -> content.answer (synthesized answer, itself JSON-encoded)
  - Other step_types exist; we don't need them for the Q+A signal.

We extract one (query, answer) episode pair per "assistant" message. Most
threads have 1 such message (single-turn); follow-ups stack to 2-4.

Usage:
    python import_perplexity_json.py \\
        --dir ~/Desktop/mikai-backup-2026-04-20/sources/local-files/export/perplexity \\
        --group-id perplexity \\
        [--limit N] [--delay 1] [--skip-existing] \\
        [--max-answer-chars 5000] [--dry-run]

Idempotent: --skip-existing checks Neo4j for the saga name and skips JSONs
already imported under this group_id. Safe to re-run after a kill/restart.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphiti_core.nodes import EpisodeType  # noqa: E402

from sidecar.client import build_graphiti  # noqa: E402


# Truncation: matches the per-episode cap import_sequential.py uses for the
# SQLite path so cost scales linearly. The full SEARCH_RESULTS payload is
# typically tens of KB of citation noise — useful in the original UI but
# poor signal for entity extraction. We keep just the FINAL.answer text.
DEFAULT_MAX_ANSWER_CHARS = 5000
DEFAULT_MAX_QUERY_CHARS = 2000

# Minimum body sizes — below these we skip the episode entirely (matches
# import_sequential.parse_perplexity_threads behavior).
MIN_QUERY_CHARS = 10
MIN_ANSWER_CHARS = 50


def extract_qa(message_text: str) -> tuple[str | None, str | None]:
    """Parse one chat_messages[].text (JSON-encoded steps array) into a
    (user_query, final_answer) pair. Returns (None, None) on parse failure."""
    try:
        steps = json.loads(message_text)
    except (json.JSONDecodeError, TypeError):
        return None, None
    if not isinstance(steps, list):
        return None, None

    query: str | None = None
    answer: str | None = None
    for s in steps:
        if not isinstance(s, dict):
            continue
        st = (s.get("step_type") or "").upper()
        content = s.get("content") or {}
        if not isinstance(content, dict):
            continue
        if st == "INITIAL_QUERY" and query is None:
            q = content.get("query")
            if isinstance(q, str) and q.strip():
                query = q.strip()
        elif st in ("FINAL", "FINAL_ANSWER") and answer is None:
            raw_ans = content.get("answer")
            # FINAL.answer is typically a JSON-encoded string containing
            # another {"answer": "..."} object. Unwrap one level if so.
            if isinstance(raw_ans, str):
                stripped = raw_ans.strip()
                if stripped.startswith("{"):
                    try:
                        inner = json.loads(stripped)
                        if isinstance(inner, dict) and isinstance(inner.get("answer"), str):
                            answer = inner["answer"].strip()
                        else:
                            answer = stripped
                    except json.JSONDecodeError:
                        answer = stripped
                else:
                    answer = stripped
            elif isinstance(raw_ans, dict) and isinstance(raw_ans.get("answer"), str):
                answer = raw_ans["answer"].strip()
    return query, answer


def parse_perplexity_json_file(
    path: str,
    *,
    max_query_chars: int,
    max_answer_chars: int,
    per_saga: bool = False,
    max_saga_chars: int = 100_000,
) -> list[dict]:
    """Parse one Perplexity export JSON into episode dicts.

    Default (per_saga=False): emits 2-N episodes per saga (query + answer per
    turn), matching import_sequential.py behavior.

    per_saga=True: emits ONE episode per saga, concatenating all turns into a
    single body. For Perplexity threads this is preferable because they're
    batched research documents, not real-time conversations — the temporal
    turn structure carries little independent signal, and Graphiti's per-
    episode extraction overhead is much larger than the per-turn LLM cost.
    Batching cuts total episode count ~5.5× (measured on Brian's corpus).
    max_saga_chars is a safety cap for absurd outliers (e.g. the one
    290K-char thread); default 100K is generous."""
    try:
        with open(path, encoding="utf-8") as fp:
            doc = json.load(fp)
    except (OSError, json.JSONDecodeError) as e:
        print(f"  SKIP unreadable: {path} ({e})", file=sys.stderr)
        return []

    title = (doc.get("title") or Path(path).stem)[:200]
    url = doc.get("url") or ""
    exported_at = doc.get("exported_at") or "2026-01-01T00:00:00Z"
    saga_name = f"perplexity: {title[:80]}"

    # Collect (query, answer) pairs first — both modes reuse this.
    pairs: list[tuple[str | None, str | None]] = []
    for msg in doc.get("chat_messages") or []:
        if not isinstance(msg, dict):
            continue
        if msg.get("sender") != "assistant":
            continue
        text = msg.get("text") or ""
        if not isinstance(text, str) or not text:
            continue
        q, a = extract_qa(text)
        pairs.append((q, a))

    # Filter to substantive pairs (query ≥ MIN_QUERY_CHARS OR answer ≥ MIN_ANSWER_CHARS).
    good_pairs = [
        (q, a) for (q, a) in pairs
        if (q and len(q) >= MIN_QUERY_CHARS) or (a and len(a) >= MIN_ANSWER_CHARS)
    ]
    if not good_pairs:
        return []

    if per_saga:
        # One episode per saga: concatenate all turns into a single body.
        # This is preferable for Perplexity content — see docstring.
        turn_texts = []
        for i, (q, a) in enumerate(good_pairs, start=1):
            turn_body = []
            if q and len(q) >= MIN_QUERY_CHARS:
                turn_body.append(f"user: {q[:max_query_chars]}")
            if a and len(a) >= MIN_ANSWER_CHARS:
                turn_body.append(f"assistant: {a[:max_answer_chars]}")
            if not turn_body:
                continue
            if len(good_pairs) > 1:
                turn_texts.append(f"— Turn {i} —\n" + "\n".join(turn_body))
            else:
                turn_texts.append("\n".join(turn_body))
        body = "\n\n".join(turn_texts)
        if len(body) > max_saga_chars:
            body = body[:max_saga_chars] + "\n[…truncated at saga cap]"
        return [{
            "saga": saga_name,
            "name": title[:100],
            "body": body,
            "date": exported_at,
            "turn_index": 0,
            "source_type": "perplexity",
            "source_url": url,
        }]

    # Default mode: one episode per turn (query and answer separately).
    episodes: list[dict] = []
    turn = 0
    for q, a in good_pairs:
        if q and len(q) >= MIN_QUERY_CHARS:
            episodes.append({
                "saga": saga_name,
                "name": "Query" if turn == 0 else f"Query (turn {turn + 1})",
                "body": f"user: {q[:max_query_chars]}",
                "date": exported_at,
                "turn_index": turn,
                "source_type": "perplexity",
                "source_url": url,
            })
            turn += 1
        if a and len(a) >= MIN_ANSWER_CHARS:
            episodes.append({
                "saga": saga_name,
                "name": "Answer" if turn == 1 else f"Answer (turn {turn + 1})",
                "body": f"assistant: {a[:max_answer_chars]}",
                "date": exported_at,
                "turn_index": turn,
                "source_type": "perplexity",
                "source_url": url,
            })
            turn += 1
    return episodes


def fetch_already_imported_sagas(group_id: str) -> set[str]:
    """Query Neo4j for distinct source_description values already in this
    group_id. We match on the `saga` substring of source_description so
    re-runs are idempotent at the thread level, not the episode level."""
    try:
        from neo4j import GraphDatabase
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        user = os.environ.get("NEO4J_USER", "neo4j")
        pw = os.environ.get("NEO4J_PASSWORD", "")
        if not pw:
            return set()
        driver = GraphDatabase.driver(uri, auth=(user, pw))
        try:
            with driver.session() as session:
                rows = session.run(
                    "MATCH (e:Episodic) WHERE e.group_id = $gid "
                    "RETURN DISTINCT e.source_description AS desc",
                    gid=group_id,
                ).data()
        finally:
            driver.close()
        seen: set[str] = set()
        for r in rows:
            desc = r.get("desc") or ""
            # source_description format from add_episode below is
            # "perplexity: <title>" — same shape as saga_name.
            if desc.startswith("perplexity: "):
                seen.add(desc[len("perplexity: "):])
        return seen
    except Exception as e:
        print(f"  WARN: skip-existing query failed: {e} (continuing without dedup)",
              file=sys.stderr)
        return set()


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Direct-from-JSON Perplexity import to Graphiti.",
    )
    parser.add_argument("--dir", required=True,
                        help="Directory containing *.json files exported from Perplexity.")
    parser.add_argument("--group-id", default="perplexity",
                        help="Graphiti group_id for these episodes (default: perplexity).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap on number of JSON FILES to process (not episodes).")
    parser.add_argument("--offset", type=int, default=0,
                        help="Skip the first N files (sorted by name). Combine "
                             "with --limit to run parallel workers over disjoint slices.")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds between add_episode calls (rate limit safety).")
    parser.add_argument("--max-answer-chars", type=int, default=DEFAULT_MAX_ANSWER_CHARS,
                        help=f"Cap on per-answer body length (default {DEFAULT_MAX_ANSWER_CHARS}).")
    parser.add_argument("--max-query-chars", type=int, default=DEFAULT_MAX_QUERY_CHARS,
                        help=f"Cap on per-query body length (default {DEFAULT_MAX_QUERY_CHARS}).")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip JSON files whose saga (title-derived) is already in the graph.")
    parser.add_argument("--per-saga", action="store_true",
                        help="Concatenate all turns of each thread into ONE episode. "
                             "5.5× fewer episodes, ~5× lower cost. Recommended for Perplexity "
                             "(batched research, not real-time conversation).")
    parser.add_argument("--max-saga-chars", type=int, default=100_000,
                        help="Safety cap on per-saga body when --per-saga is set "
                             "(default 100000 — only trims the ~1 outlier at ~290K).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse + print first 10 would-be episodes; don't write to graph.")
    args = parser.parse_args()

    json_dir = Path(args.dir).expanduser()
    if not json_dir.is_dir():
        print(f"ERROR: not a directory: {json_dir}", file=sys.stderr)
        return 2

    files = sorted(glob.glob(str(json_dir / "*.json")))
    total_on_disk = len(files)
    if args.offset:
        files = files[args.offset:]
    print(f"Found {total_on_disk} JSON files in {json_dir}"
          f"{f' (skipping first {args.offset} via --offset)' if args.offset else ''}",
          flush=True)

    if args.skip_existing:
        seen_sagas = fetch_already_imported_sagas(args.group_id)
        print(f"Skip-existing: {len(seen_sagas)} sagas already in group_id={args.group_id!r}",
              flush=True)
    else:
        seen_sagas = set()

    # Parse all JSONs first so we know the total work + skip set.
    all_episodes: list[dict] = []
    files_used = 0
    files_skipped = 0
    files_empty = 0
    for f in files:
        eps = parse_perplexity_json_file(
            f,
            max_query_chars=args.max_query_chars,
            max_answer_chars=args.max_answer_chars,
            per_saga=args.per_saga,
            max_saga_chars=args.max_saga_chars,
        )
        if not eps:
            files_empty += 1
            continue
        saga = eps[0]["saga"][len("perplexity: "):]
        if saga in seen_sagas:
            files_skipped += 1
            continue
        all_episodes.extend(eps)
        files_used += 1
        if args.limit and files_used >= args.limit:
            break

    print(f"Files used: {files_used}  · skipped (already-in-graph): {files_skipped}  "
          f"· empty/unparseable: {files_empty}", flush=True)
    print(f"Episodes to import: {len(all_episodes)}", flush=True)
    sagas = set(e["saga"] for e in all_episodes)
    print(f"Sagas (conversations): {len(sagas)}", flush=True)

    if args.dry_run:
        for ep in all_episodes[:10]:
            saga = ep["saga"][:40]
            print(f"  {ep['name'][:50]} ({len(ep['body'])} chars) [saga: {saga}]",
                  flush=True)
        if len(all_episodes) > 10:
            print(f"  ... and {len(all_episodes) - 10} more", flush=True)
        return 0

    if not all_episodes:
        print("Nothing to import.", flush=True)
        return 0

    if not os.environ.get("DEEPSEEK_API_KEY") or not os.environ.get("VOYAGE_API_KEY"):
        print("ERROR: DEEPSEEK_API_KEY and VOYAGE_API_KEY required.",
              file=sys.stderr)
        return 1

    graphiti = build_graphiti()
    await graphiti.build_indices_and_constraints()

    success = 0
    failed = 0
    start = time.time()
    total = len(all_episodes)

    for i, ep in enumerate(all_episodes):
        name = ep["name"][:50]
        chars = len(ep["body"])
        saga_info = f" [{ep['saga'][:30]}…]"
        print(f"[{i + 1}/{total}] {name} ({chars} chars){saga_info}", flush=True)

        try:
            ref_time = datetime.fromisoformat(ep["date"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            ref_time = datetime.now(timezone.utc)

        try:
            result = await graphiti.add_episode(
                name=ep["name"][:100],
                episode_body=ep["body"],
                source=EpisodeType.message,
                source_description=ep["saga"],
                reference_time=ref_time,
                group_id=args.group_id,
                saga=ep.get("saga"),
            )
            nodes = len(result.nodes) if result and result.nodes else 0
            edges = len(result.edges) if result and result.edges else 0
            print(f"  OK: +{nodes} nodes, +{edges} edges", flush=True)
            success += 1
        except Exception as e:
            print(f"  FAIL: {str(e)[:160]}", flush=True)
            failed += 1

        if (i + 1) % 20 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining_min = ((total - i - 1) / rate / 60) if rate > 0 else 0
            print(f"  --- {i + 1}/{total} | {success} ok, {failed} fail | "
                  f"~{remaining_min:.0f}m left ---", flush=True)

        await asyncio.sleep(args.delay)

    elapsed = time.time() - start
    await graphiti.close()

    print(f"\nDone in {elapsed / 60:.1f} min", flush=True)
    print(f"  Success: {success}/{total}", flush=True)
    print(f"  Failed:  {failed}", flush=True)
    return 0 if failed < total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

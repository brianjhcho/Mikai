#!/usr/bin/env python
"""One-shot historical backfill: Neo4j Episodic nodes → Karpathy wiki.

Context (substrate pivot, 2026-08-05): the wiki at ~/.mikai/wiki/wiki.md
is now the primary L3 substrate (MIKAI_L3_BACKEND=wiki). Neo4j is frozen
but preserved — every episode ever ingested still lives there. This
script migrates that history into the wiki, chronologically, through the
shipped WikiAdapter (no re-implementation of the wiki write path).

Key property: WikiAdapter.ingest_episode() writes the section header
timestamp from `episode.reference_time` — NOT "now" — so historical
episodes keep their real dates. Only the `<!-- ingested=... -->` comment
and the wiki-episodes.log line carry the backfill's wall-clock time,
which is exactly what lets us tell backfilled vs live-ingested content
apart later. Dream's 7-day windowing keys off the header timestamp, so
reference_time preservation is non-negotiable.

Read path: read-only Cypher against Neo4j (`MATCH (e:Episodic) ... ORDER
BY e.valid_at ASC`). graphiti-core's client has no "list all episodes"
primitive (retrieve_episodes is a windowed last-N), so we go straight to
the fallback the runbook allows. No writes, no MERGE, no SET, no DELETE.

Usage:
    .venv/bin/python backfill_to_wiki.py --dry-run          # counts only
    .venv/bin/python backfill_to_wiki.py                    # full backfill
    .venv/bin/python backfill_to_wiki.py --source=gmail     # one source
    .venv/bin/python backfill_to_wiki.py --limit=20         # testing

Idempotency: an episode is skipped only when BOTH its exact section
header line (`### <ref-iso> — <source> — <name>`) already exists in
wiki.md AND a matching `<source_description> <byte-count>` pair appears
in wiki-episodes.log. Requiring both keeps re-runs from double-writing
while still preserving distinct-content episodes that happen to share a
header (e.g. re-synced thread snapshots that grew between ingests).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Make `sidecar.*` importable when run as a script from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent))

ENV_FILE = Path.home() / ".mikai" / "launchd.env"

EPISODE_QUERY = """
MATCH (e:Episodic)
RETURN e.uuid AS uuid,
       e.name AS name,
       e.content AS content,
       e.source_description AS source_description,
       e.valid_at AS valid_at,
       e.group_id AS group_id
ORDER BY e.valid_at ASC, e.uuid ASC
"""


def load_launchd_env(path: Path = ENV_FILE) -> None:
    """Source KEY=VALUE pairs from launchd.env (same secrets file the
    ingestion daemon uses). Existing environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def source_key(source_description: str | None) -> str:
    """Coarse per-source bucket: 'apple-notes: Some title' → 'apple-notes'."""
    return (source_description or "unknown").split(":")[0].strip()


def fetch_episodes(driver, source_filter: str | None, limit: int | None):
    """Read all Episodic nodes chronologically (read-only). Returns a list
    of dicts with valid_at converted to native datetime."""
    episodes = []
    with driver.session() as session:
        for rec in session.run(EPISODE_QUERY):
            sd = rec["source_description"]
            if source_filter and source_key(sd) != source_filter:
                continue
            va = rec["valid_at"]
            ref_time = va.to_native() if hasattr(va, "to_native") else va
            episodes.append(
                {
                    "uuid": rec["uuid"],
                    "name": rec["name"],
                    "content": rec["content"] or "",
                    "source_description": sd or "unknown",
                    "reference_time": ref_time,
                    "group_id": rec["group_id"] or "mikai-default",
                }
            )
            if limit and len(episodes) >= limit:
                break
    return episodes


def header_line(ep: dict) -> str:
    """The exact `###` header WikiAdapter.ingest_episode will write."""
    ref = ep["reference_time"]
    ref_iso = ref.isoformat() if isinstance(ref, datetime) else str(ref)
    title = ep["name"] or "(untitled)"
    return f"### {ref_iso} — {ep['source_description']} — {title}"


def existing_headers(wiki_md: Path) -> set[str]:
    if not wiki_md.exists():
        return set()
    return {
        line.rstrip()
        for line in wiki_md.read_text(errors="replace").splitlines()
        if line.startswith("### ")
    }


def existing_log_pairs(episode_log: Path) -> set[tuple[str, str]]:
    """Parse wiki-episodes.log lines '<iso-ts> <source...> <bytes>' into
    (source, bytes) pairs. Source may contain spaces; ts is the first
    token and bytes the last."""
    pairs: set[tuple[str, str]] = set()
    if not episode_log.exists():
        return pairs
    for line in episode_log.read_text(errors="replace").splitlines():
        tokens = line.strip().split()
        if len(tokens) >= 3 and not line.lstrip().startswith("{"):
            pairs.add((" ".join(tokens[1:-1]), tokens[-1]))
    return pairs


async def run_backfill(episodes: list[dict], wiki_root: Path) -> dict:
    from sidecar.l3.port import Episode
    from sidecar.l3.wiki_adapter import WikiAdapter

    wiki_md = wiki_root / "wiki.md"
    episode_log = wiki_root / "wiki-episodes.log"
    headers = existing_headers(wiki_md)
    log_pairs = existing_log_pairs(episode_log)

    adapter = WikiAdapter()
    written = Counter()
    skipped = 0
    errors: list[tuple[str, str]] = []

    for i, ep in enumerate(episodes, 1):
        hdr = header_line(ep)
        n_bytes = str(len(ep["content"].encode("utf-8")))
        try:
            # Skip only when both signals agree — exact header already in
            # wiki.md AND (source, bytes) already audited in the log.
            if hdr in headers and (ep["source_description"], n_bytes) in log_pairs:
                skipped += 1
                continue
            await adapter.ingest_episode(
                Episode(
                    content=ep["content"],
                    source_description=ep["source_description"],
                    reference_time=ep["reference_time"],
                    group_id=ep["group_id"],
                    name=ep["name"],
                )
            )
            headers.add(hdr)
            log_pairs.add((ep["source_description"], n_bytes))
            written[source_key(ep["source_description"])] += 1
        except Exception as exc:  # continue on error — partial > none
            errors.append((ep["uuid"], f"{type(exc).__name__}: {exc}"))
        if i % 100 == 0:
            print(
                f"  [{i}/{len(episodes)}] written={sum(written.values())} "
                f"skipped={skipped} errors={len(errors)}",
                flush=True,
            )

    await adapter.close()
    return {"written": written, "skipped": skipped, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="read Neo4j, print per-source counts, write nothing")
    parser.add_argument("--source", default=None,
                        help="only backfill episodes whose source key matches (e.g. gmail)")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap the number of episodes processed (testing)")
    args = parser.parse_args()

    load_launchd_env()
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")
    wiki_root = Path(
        os.environ.get("MIKAI_WIKI_ROOT", str(Path.home() / ".mikai" / "wiki"))
    )
    wiki_md = wiki_root / "wiki.md"

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        print(f"Reading episodes from {uri} (read-only)...", flush=True)
        episodes = fetch_episodes(driver, args.source, args.limit)
    finally:
        driver.close()

    by_source = Counter(source_key(ep["source_description"]) for ep in episodes)
    total_bytes = sum(len(ep["content"].encode("utf-8")) for ep in episodes)
    dup_headers = len(episodes) - len({header_line(ep) for ep in episodes})

    print(f"\nEpisodes matched: {len(episodes)} "
          f"({total_bytes:,} content bytes; {dup_headers} duplicate headers)")
    for src, n in by_source.most_common():
        print(f"  {src}: {n}")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0
    if not episodes:
        print("Nothing to backfill.")
        return 0

    # Backup wiki.md before the first append — the rollback path.
    if wiki_md.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = wiki_md.with_name(f"wiki.md.bak-pre-backfill-{ts}")
        shutil.copy2(wiki_md, backup)
        print(f"\nBacked up wiki.md → {backup}")

    size_before = wiki_md.stat().st_size if wiki_md.exists() else 0
    print(f"wiki.md before: {size_before:,} bytes\n", flush=True)

    result = asyncio.run(run_backfill(episodes, wiki_root))

    size_after = wiki_md.stat().st_size if wiki_md.exists() else 0
    total_written = sum(result["written"].values())
    print(f"\nDone. written={total_written} "
          f"skipped={result['skipped']} errors={len(result['errors'])}")
    print(f"wiki.md after: {size_after:,} bytes "
          f"(+{size_after - size_before:,})")
    print("Per-source written:")
    for src, n in result["written"].most_common():
        print(f"  {src}: {n}")
    if result["errors"]:
        print("Failed episodes:")
        for uuid, err in result["errors"]:
            print(f"  {uuid}: {err}")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())

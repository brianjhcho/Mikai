"""
migrate_sqlite_to_graphiti.py

Imports MIKAI's SQLite sources into Graphiti as episodes.
Graphiti handles entity extraction, resolution, and community detection.

Usage:
    python scripts/migrate_sqlite_to_graphiti.py [--db-path PATH] [--limit N] [--dry-run]

Requires:
    - Neo4j running (docker-compose up neo4j)
    - Graphiti sidecar running (docker-compose up graphiti-sidecar)
    OR
    - GRAPHITI_URL env var pointing to the sidecar
"""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import requests

DEFAULT_DB_PATH = Path.home() / ".mikai" / "mikai.db"
DEFAULT_GRAPHITI_URL = "http://localhost:8100"

# Source type → Graphiti episode type mapping
SOURCE_TYPE_MAP = {
    "apple-notes": "text",
    "manual": "text",
    "perplexity": "text",
    "claude-thread": "text",
    "gmail": "message",
    "imessage": "message",
    "mcp-note": "text",
}

# Source types to prioritize (authored content first, then behavioral)
SOURCE_PRIORITY = [
    "apple-notes",
    "manual",
    "perplexity",
    "claude-thread",
    "gmail",
    "imessage",
]


def get_sources(db_path: str, limit: int | None = None, source_type: str | None = None) -> list[dict]:
    """Read sources from SQLite, ordered by priority then date."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    params = []
    query = """
        SELECT id, type, label, raw_content, source, created_at, chunk_count
        FROM sources
        WHERE raw_content IS NOT NULL AND LENGTH(raw_content) > 50
          AND source IS NOT NULL
    """
    if source_type:
        query += " AND source = ?"
        params.append(source_type)

    query += " ORDER BY created_at ASC"

    if limit:
        query += f" LIMIT {limit}"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    # Sort by priority
    def priority_key(row):
        source = row["source"] or "unknown"
        try:
            return SOURCE_PRIORITY.index(source)
        except ValueError:
            return len(SOURCE_PRIORITY)

    sorted_rows = sorted(rows, key=priority_key)
    return [dict(r) for r in sorted_rows]


def migrate_source(graphiti_url: str, source: dict, dry_run: bool = False) -> bool:
    """Send one source to Graphiti as an episode."""
    episode_type = SOURCE_TYPE_MAP.get(source["source"], "text")

    payload = {
        "content": source["raw_content"],
        "source_description": f'{source["source"]}: {source["label"] or "untitled"}',
        "episode_type": episode_type,
        "reference_time": source["created_at"],
        "group_id": "mikai-default",
    }

    if dry_run:
        content_preview = source["raw_content"][:100].replace("\n", " ")
        print(f"  [DRY RUN] Would import: {source['source']}: {source['label']} ({len(source['raw_content'])} chars)")
        print(f"            Preview: {content_preview}...")
        return True

    try:
        resp = requests.post(f"{graphiti_url}/episode", json=payload, timeout=120)
        if resp.status_code == 200:
            return True
        else:
            print(f"  ERROR: {resp.status_code} — {resp.text[:200]}", file=sys.stderr)
            return False
    except requests.exceptions.RequestException as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Migrate MIKAI SQLite → Graphiti")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="Path to mikai.db")
    parser.add_argument("--graphiti-url", default=DEFAULT_GRAPHITI_URL, help="Graphiti sidecar URL")
    parser.add_argument("--limit", type=int, default=None, help="Max sources to import")
    parser.add_argument("--dry-run", action="store_true", help="Preview without importing")
    parser.add_argument("--source-type", default=None, help="Filter by source type (e.g., apple-notes)")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds between episodes (rate limit protection, default 3.0)")
    args = parser.parse_args()

    # Check sidecar health
    if not args.dry_run:
        try:
            resp = requests.get(f"{args.graphiti_url}/health", timeout=5)
            if resp.status_code != 200:
                print(f"Graphiti sidecar not healthy: {resp.status_code}", file=sys.stderr)
                sys.exit(1)
            print(f"Graphiti sidecar OK: {resp.json()}")
        except requests.exceptions.ConnectionError:
            print(f"Cannot connect to Graphiti sidecar at {args.graphiti_url}", file=sys.stderr)
            print("Start it with: cd infra/graphiti && docker-compose up", file=sys.stderr)
            sys.exit(1)

    # Load sources
    sources = get_sources(args.db_path, args.limit, args.source_type)

    print(f"\nSources to import: {len(sources)}")
    by_type = {}
    for s in sources:
        t = s["source"] or "unknown"
        by_type[t] = by_type.get(t, 0) + 1
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")

    if not sources:
        print("No sources to import.")
        return

    # Import
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Starting import...")
    success = 0
    failed = 0
    start = time.time()

    for i, source in enumerate(sources):
        label = source["label"] or "untitled"
        source_type = source["source"] or "unknown"
        chars = len(source["raw_content"])

        print(f"[{i+1}/{len(sources)}] {source_type}: {label[:60]} ({chars} chars)")

        if migrate_source(args.graphiti_url, source, args.dry_run):
            success += 1
        else:
            failed += 1

        # Rate limit protection
        if not args.dry_run and i < len(sources) - 1:
            time.sleep(args.delay)

        # Progress update every 10 sources
        if (i + 1) % 10 == 0:
            elapsed_so_far = time.time() - start
            rate = (i + 1) / elapsed_so_far
            remaining = (len(sources) - i - 1) / rate if rate > 0 else 0
            print(f"  --- Progress: {i+1}/{len(sources)} ({success} ok, {failed} fail) | {elapsed_so_far:.0f}s elapsed | ~{remaining:.0f}s remaining ---")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"  Success: {success}")
    print(f"  Failed: {failed}")
    if success > 0:
        print(f"  Rate: {elapsed/success:.1f}s per episode")
    if not args.dry_run:
        print(f"\nGraph populated. Check Neo4j browser: http://localhost:7474")
        print(f"Graphiti search: curl -X POST {args.graphiti_url}/search -H 'Content-Type: application/json' -d '{{\"query\": \"test\"}}'")


if __name__ == "__main__":
    main()

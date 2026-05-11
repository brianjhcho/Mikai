"""
import_sequential.py

Imports episodes one at a time using add_episode() (singular).
This is Graphiti's intended pattern — scales to any graph size.

Supports:
  - Apple Notes (from dump file)
  - Claude threads (turn-by-turn with saga)
  - Perplexity threads (query + answer with saga)

Usage:
    # Apple Notes (remaining)
    python scripts/import_sequential.py --source notes --dump /tmp/mikai_notes_all.txt --skip-existing

    # Claude threads
    python scripts/import_sequential.py --source claude --db-path ~/.mikai/mikai.db

    # Perplexity threads
    python scripts/import_sequential.py --source perplexity --db-path ~/.mikai/mikai.db --limit 50
"""

import argparse
import asyncio
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Make sibling `sidecar` package importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphiti_core.nodes import EpisodeType

from sidecar.client import build_graphiti
from sidecar.ingest import (
    SKIP_PATTERNS,
    is_sensitive_name,
    parse_claude_turns,
    parse_notes_dump as _parse_notes_dump,
    parse_perplexity_query_and_answer,
)


# ── Parsers (thin wrappers over sidecar.ingest) ──────────────────────────────


def parse_notes_dump(path):
    """Parse Apple Notes dump into episode dicts capped at 5K chars per body."""
    return _parse_notes_dump(path, max_body_chars=5000)


def parse_claude_threads(db_path):
    """Parse Claude threads into turn-by-turn episodes grouped by saga."""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT label, raw_content, created_at FROM sources WHERE source = 'claude-thread' "
        "AND label NOT IN ('users','memories','projects','conversations') "
        "AND LENGTH(raw_content) > 100 ORDER BY created_at"
    ).fetchall()
    db.close()

    all_episodes = []
    for row in rows:
        label = row["label"]
        if is_sensitive_name(label):
            continue

        raw = row["raw_content"]
        created = row["created_at"] or "2026-01-01T00:00:00Z"
        saga_name = f"claude: {label[:80]}"

        turns = parse_claude_turns(raw)

        # Only keep first 20 turns per thread (most substance is early)
        for i, turn in enumerate(turns[:20]):
            if len(turn['content']) < 20:
                continue
            all_episodes.append({
                'saga': saga_name,
                'name': f"Turn {i+1} ({turn['role']})",
                'body': f"{turn['role']}: {turn['content'][:3000]}",
                'date': created,
                'turn_index': i,
                'source_type': 'claude-thread',
            })

    return all_episodes


def parse_perplexity_threads(db_path, limit=None):
    """Parse Perplexity threads into query + answer episodes grouped by saga."""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    query = (
        "SELECT label, raw_content, created_at FROM sources WHERE source = 'perplexity' "
        "AND LENGTH(raw_content) > 200 ORDER BY created_at"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = db.execute(query).fetchall()
    db.close()

    all_episodes = []
    for row in rows:
        label = row["label"]
        if is_sensitive_name(label):
            continue

        raw = row["raw_content"]
        created = row["created_at"] or "2026-01-01T00:00:00Z"
        saga_name = f"perplexity: {label[:80]}"

        user_query, answer = parse_perplexity_query_and_answer(raw)

        if user_query is None and answer is None:
            # Parser gave up — fall back to raw text if it's substantial.
            if len(raw) > 100:
                all_episodes.append({
                    'saga': saga_name,
                    'name': label[:60],
                    'body': raw[:3000],
                    'date': created,
                    'turn_index': 0,
                    'source_type': 'perplexity',
                })
            continue

        if user_query and len(user_query) > 10:
            all_episodes.append({
                'saga': saga_name,
                'name': "Query",
                'body': f"user: {user_query[:2000]}",
                'date': created,
                'turn_index': 0,
                'source_type': 'perplexity',
            })
        if answer and len(answer) > 50:
            all_episodes.append({
                'saga': saga_name,
                'name': "Answer",
                'body': f"assistant: {answer[:3000]}",
                'date': created,
                'turn_index': 1,
                'source_type': 'perplexity',
            })

    return all_episodes


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Sequential Graphiti import")
    parser.add_argument("--source", required=True, choices=["notes", "claude", "perplexity"])
    parser.add_argument("--dump", default="/tmp/mikai_notes_all.txt", help="Notes dump file")
    parser.add_argument("--db-path", default=str(Path.home() / ".mikai" / "mikai.db"))
    parser.add_argument("--skip-existing", action="store_true", help="Skip notes already in graph")
    parser.add_argument("--delay", type=float, default=5.0, help="Seconds between episodes")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--group-id", default="mikai-default")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Parse episodes based on source
    if args.source == "notes":
        raw_notes = parse_notes_dump(args.dump)
        if args.skip_existing:
            # Get existing episode names from Neo4j
            from neo4j import AsyncGraphDatabase
            driver = AsyncGraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "mikai-local-dev"))
            async with driver.session() as session:
                result = await session.run(
                    "MATCH (e:Episodic) WHERE e.group_id = $gid RETURN e.source_description AS desc",
                    gid=args.group_id,
                )
                existing = set()
                async for r in result:
                    existing.add(r["desc"])
            await driver.close()
            print(f"Existing episodes: {len(existing)}", flush=True)
            episodes = []
            for n in raw_notes:
                desc = f"apple-notes: {n['name']}"
                if desc not in existing:
                    episodes.append({
                        'saga': None,
                        'name': n['name'],
                        'body': n['body'],
                        'date': n['date'],
                        'turn_index': 0,
                        'source_type': 'apple-notes',
                    })
        else:
            episodes = [{'saga': None, 'name': n['name'], 'body': n['body'], 'date': n['date'], 'turn_index': 0, 'source_type': 'apple-notes'} for n in raw_notes]
    elif args.source == "claude":
        episodes = parse_claude_threads(args.db_path)
    elif args.source == "perplexity":
        episodes = parse_perplexity_threads(args.db_path, args.limit)

    if args.limit and args.source != "perplexity":
        episodes = episodes[:args.limit]

    print(f"Source: {args.source}", flush=True)
    print(f"Episodes to import: {len(episodes)}", flush=True)
    if args.source in ("claude", "perplexity"):
        sagas = set(e['saga'] for e in episodes if e.get('saga'))
        print(f"Sagas (conversations): {len(sagas)}", flush=True)

    if args.dry_run:
        for ep in episodes[:10]:
            saga = f" [saga: {ep['saga'][:40]}]" if ep.get('saga') else ""
            print(f"  {ep['name'][:50]} ({len(ep['body'])} chars){saga}", flush=True)
        if len(episodes) > 10:
            print(f"  ... and {len(episodes) - 10} more", flush=True)
        return

    # Connect to Graphiti
    if not os.environ.get("DEEPSEEK_API_KEY") or not os.environ.get("VOYAGE_API_KEY"):
        print("Need DEEPSEEK_API_KEY and VOYAGE_API_KEY", file=sys.stderr)
        sys.exit(1)

    graphiti = build_graphiti()
    await graphiti.build_indices_and_constraints()

    # Import sequentially
    success = 0
    failed = 0
    start = time.time()
    current_saga = None

    for i, ep in enumerate(episodes):
        name = ep['name'][:50]
        chars = len(ep['body'])
        saga_info = f" [{ep['saga'][:30]}...]" if ep.get('saga') else ""
        print(f"[{i+1}/{len(episodes)}] {name} ({chars} chars){saga_info}", flush=True)

        try:
            ref_time = datetime.fromisoformat(ep['date'].replace('Z', '+00:00')) if ep['date'] else datetime.now(timezone.utc)
        except ValueError:
            ref_time = datetime.now(timezone.utc)

        try:
            result = await graphiti.add_episode(
                name=ep['name'][:100],
                episode_body=ep['body'],
                source=EpisodeType.message if ep['source_type'] in ('claude-thread', 'perplexity') else EpisodeType.text,
                source_description=f"{ep['source_type']}: {ep['name'][:80]}",
                reference_time=ref_time,
                group_id=args.group_id,
                saga=ep.get('saga'),
            )
            nodes = len(result.nodes) if result and result.nodes else 0
            edges = len(result.edges) if result and result.edges else 0
            print(f"  OK: +{nodes} nodes, +{edges} edges", flush=True)
            success += 1
        except Exception as e:
            err = str(e)[:120]
            print(f"  FAIL: {err}", flush=True)
            failed += 1

        # Progress
        if (i + 1) % 20 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(episodes) - i - 1) / rate / 60 if rate > 0 else 0
            print(f"  --- {i+1}/{len(episodes)} | {success} ok, {failed} fail | ~{remaining:.0f}m left ---", flush=True)

        await asyncio.sleep(args.delay)

    elapsed = time.time() - start
    await graphiti.close()

    print(f"\nDone in {elapsed/60:.1f} min", flush=True)
    print(f"  Success: {success}/{len(episodes)}", flush=True)
    print(f"  Failed: {failed}", flush=True)


if __name__ == "__main__":
    # Load env
    env_path = Path(__file__).parent.parent.parent.parent / '.env.local'
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
            key, _, val = line.partition('=')
            if key and val and key not in os.environ: os.environ[key] = val
    asyncio.run(main())

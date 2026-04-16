"""
bulk_import.py

Reads the Apple Notes dump and sends ALL notes in one bulk request
to Graphiti's add_episode_bulk endpoint. One API call, one batch.

Usage:
    # 1. Dump notes first (if not already done):
    osascript scripts/read_notes.applescript 2>/tmp/mikai_notes_raw.txt

    # 2. Bulk import:
    python scripts/bulk_import.py [--limit N] [--dry-run]
"""

import argparse
import sys
import time
from pathlib import Path

import requests

# Make sibling `sidecar` package importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sidecar.ingest import parse_notes_dump as parse_dump

DEFAULT_GRAPHITI_URL = "http://localhost:8100"
DUMP_FILE = "/tmp/mikai_notes_raw.txt"


def main():
    parser = argparse.ArgumentParser(description="Bulk import Apple Notes → Graphiti")
    parser.add_argument("--graphiti-url", default=DEFAULT_GRAPHITI_URL)
    parser.add_argument("--dump", default=DUMP_FILE)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-chars", type=int, default=5000, help="Max chars per note (default 5000)")
    parser.add_argument("--batch-size", type=int, default=10, help="Episodes per bulk batch (default 10)")
    parser.add_argument("--batch-delay", type=float, default=30.0, help="Seconds between batches for RPM recovery (default 30)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Parse
    notes = parse_dump(args.dump)
    print(f"Parsed {len(notes)} notes from {args.dump}", flush=True)

    if args.limit:
        notes = notes[:args.limit]
        print(f"Limited to {len(notes)} notes", flush=True)

    if not notes:
        print("No notes to import.")
        return

    # Show summary
    total_chars = sum(len(n["body"]) for n in notes)
    total_chars_capped = sum(min(len(n["body"]), args.max_chars) for n in notes)
    print(f"Total content: {total_chars:,} chars ({total_chars_capped:,} after {args.max_chars}-char cap)", flush=True)
    print(f"Estimated tokens: ~{total_chars_capped // 4:,}", flush=True)

    # Preview
    print(f"\nFirst 5 notes:", flush=True)
    for n in notes[:5]:
        capped = " [CAPPED]" if len(n["body"]) > args.max_chars else ""
        print(f"  {n['name'][:60]} ({len(n['body'])} chars{capped}) {n['date'][:10]}", flush=True)

    if args.dry_run:
        print(f"\n[DRY RUN] Would send {len(notes)} episodes in one bulk request.", flush=True)
        return

    # Check sidecar
    try:
        resp = requests.get(f"{args.graphiti_url}/health", timeout=5)
        print(f"\nGraphiti: {resp.json()}", flush=True)
    except Exception:
        print("Graphiti not reachable", file=sys.stderr)
        sys.exit(1)

    # Build bulk request
    episodes = []
    for n in notes:
        episodes.append({
            "content": n["body"][:args.max_chars],
            "name": n["name"],
            "source_description": f"apple-notes: {n['name']}",
            "episode_type": "text",
            "reference_time": n["date"],
        })

    # Import in batches to avoid Voyage AI RPM limits
    batch_size = args.batch_size
    total_episodes = 0
    total_nodes = 0
    total_edges = 0
    total_communities = 0
    failed_batches = 0

    num_batches = (len(episodes) + batch_size - 1) // batch_size
    print(f"\nImporting {len(episodes)} episodes in {num_batches} batches of {batch_size}...", flush=True)
    start = time.time()

    for batch_idx in range(0, len(episodes), batch_size):
        batch = episodes[batch_idx:batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1

        print(f"\n[Batch {batch_num}/{num_batches}] {len(batch)} episodes...", flush=True)

        payload = {
            "episodes": batch,
            "group_id": "mikai-default",
        }

        try:
            resp = requests.post(
                f"{args.graphiti_url}/episode/bulk",
                json=payload,
                timeout=600,  # 10 min per batch
            )

            if resp.status_code == 200:
                result = resp.json()
                ep = result.get('episodes_created', 0)
                nd = result.get('nodes_created', 0)
                ed = result.get('edges_created', 0)
                cm = result.get('communities_created', 0)
                total_episodes += ep
                total_nodes += nd
                total_edges += ed
                total_communities += cm
                elapsed_so_far = time.time() - start
                print(f"  OK: +{ep} episodes, +{nd} nodes, +{ed} edges, +{cm} communities ({elapsed_so_far:.0f}s total)", flush=True)
            else:
                failed_batches += 1
                print(f"  FAILED ({resp.status_code}): {resp.text[:200]}", flush=True)

        except requests.exceptions.ReadTimeout:
            failed_batches += 1
            print(f"  TIMEOUT", flush=True)
        except Exception as e:
            failed_batches += 1
            print(f"  ERROR: {e}", flush=True)

        # Wait between batches to let Voyage RPM window reset
        if batch_idx + batch_size < len(episodes):
            wait = args.batch_delay
            print(f"  Waiting {wait}s before next batch...", flush=True)
            time.sleep(wait)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s ({elapsed/60:.1f} min)", flush=True)
    print(f"  Episodes: {total_episodes}", flush=True)
    print(f"  Nodes:    {total_nodes}", flush=True)
    print(f"  Edges:    {total_edges}", flush=True)
    print(f"  Communities: {total_communities}", flush=True)
    print(f"  Failed batches: {failed_batches}/{num_batches}", flush=True)


if __name__ == "__main__":
    main()

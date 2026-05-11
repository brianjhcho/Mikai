"""
import_from_dump.py

Parses the AppleScript note dump and imports into Graphiti.
Separates note reading (already done) from API calls (rate-limited).

Usage:
    python scripts/import_from_dump.py [--delay 5] [--limit 100] [--skip 0] [--dry-run]
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


def import_note(url: str, note: dict) -> dict | None:
    """Import one note with retry logic."""
    payload = {
        "content": note["body"][:5000],  # cap at 5K chars to stay under Haiku rate limit
        "source_description": f"apple-notes: {note['name']}",
        "episode_type": "text",
        "reference_time": note["date"],
        "group_id": "mikai-default",
    }

    max_retries = 5
    for attempt in range(max_retries):
        try:
            resp = requests.post(f"{url}/episode", json=payload, timeout=180)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 500 and attempt < max_retries - 1:
                wait = 15 * (attempt + 1)
                print(f"  Retry {attempt+1}/{max_retries} in {wait}s...", flush=True)
                time.sleep(wait)
                continue
            else:
                print(f"  ERROR: {resp.status_code}", file=sys.stderr, flush=True)
                return None
        except requests.exceptions.ReadTimeout:
            if attempt < max_retries - 1:
                wait = 20 * (attempt + 1)
                print(f"  Timeout, retry {attempt+1} in {wait}s...", flush=True)
                time.sleep(wait)
                continue
            return None
        except requests.exceptions.RequestException as e:
            print(f"  ERROR: {e}", file=sys.stderr, flush=True)
            return None
    return None


def main():
    parser = argparse.ArgumentParser(description="Import Apple Notes dump → Graphiti")
    parser.add_argument("--graphiti-url", default=DEFAULT_GRAPHITI_URL)
    parser.add_argument("--dump", default=DUMP_FILE, help="Path to note dump file")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--delay", type=float, default=5.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Parse dump
    notes = parse_dump(args.dump)
    print(f"Parsed {len(notes)} notes from dump", flush=True)

    if args.skip > 0:
        notes = notes[args.skip:]
        print(f"Skipped {args.skip}, {len(notes)} remaining", flush=True)

    if args.limit:
        notes = notes[:args.limit]

    if not notes:
        print("No notes to import.")
        return

    # Check sidecar
    if not args.dry_run:
        try:
            resp = requests.get(f"{args.graphiti_url}/health", timeout=5)
            print(f"Graphiti: {resp.json()}", flush=True)
        except Exception:
            print("Graphiti not reachable", file=sys.stderr)
            sys.exit(1)

    # Import
    print(f"\nImporting {len(notes)} notes (delay: {args.delay}s)...\n", flush=True)
    success = 0
    failed = 0
    total_nodes = 0
    total_edges = 0
    start = time.time()

    for i, note in enumerate(notes):
        name = note["name"][:60]
        chars = len(note["body"])
        print(f"[{i+1}/{len(notes)}] {name} ({chars} chars)", flush=True)

        if args.dry_run:
            print(f"  [DRY RUN] {note['body'][:80]}...", flush=True)
            success += 1
        else:
            result = import_note(args.graphiti_url, note)
            if result:
                success += 1
                total_nodes += result.get("nodes_created", 0)
                total_edges += result.get("edges_created", 0)
                print(f"  OK: +{result.get('nodes_created', 0)} nodes, +{result.get('edges_created', 0)} edges", flush=True)
            else:
                failed += 1

        if not args.dry_run and i < len(notes) - 1:
            time.sleep(args.delay)

        if (i + 1) % 10 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(notes) - i - 1) / rate / 60 if rate > 0 else 0
            print(f"  --- {i+1}/{len(notes)} | {success} ok, {failed} fail | ~{remaining:.1f}m left | {total_nodes} nodes, {total_edges} edges ---", flush=True)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed/60:.1f} min", flush=True)
    print(f"  Success: {success}/{len(notes)}", flush=True)
    print(f"  Failed: {failed}", flush=True)
    print(f"  Nodes: {total_nodes}, Edges: {total_edges}", flush=True)


if __name__ == "__main__":
    main()

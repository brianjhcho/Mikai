"""
import_remaining_notes.py

Imports Apple Notes that aren't already in Neo4j.
Reads from the full dump, skips notes already imported (by name match).

Usage:
    python scripts/import_remaining_notes.py [--batch-size 10] [--batch-delay 30]
"""

import argparse
import json
import sys
import time
import requests

GRAPHITI_URL = "http://localhost:8100"
FULL_DUMP = "/tmp/mikai_notes_all.txt"
OLD_DUMP = "/tmp/mikai_notes_raw.txt"
SKIP_PATTERNS = ["api key", "password", "secret", "credential", "token"]


def parse_dump(path):
    notes = []
    current = None
    try:
        with open(path, "r", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if line == "===NOTE_START===":
                    current = {"name": "", "date": "", "body_lines": []}
                elif line == "===NOTE_END===" and current:
                    body = "\n".join(current["body_lines"]).strip()
                    name = current["name"]
                    is_sensitive = any(p in name.lower() for p in SKIP_PATTERNS)
                    if len(body) > 50 and not is_sensitive:
                        notes.append({"name": name, "date": current["date"], "body": body})
                    current = None
                elif current is not None:
                    if line.startswith("NAME:") and not current["name"]:
                        current["name"] = line[5:]
                    elif line.startswith("DATE:") and not current["date"]:
                        current["date"] = line[5:]
                    else:
                        current["body_lines"].append(line)
    except FileNotFoundError:
        return []
    return notes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--batch-delay", type=float, default=30.0)
    parser.add_argument("--max-chars", type=int, default=5000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Parse both dumps
    all_notes = parse_dump(FULL_DUMP)
    old_notes = parse_dump(OLD_DUMP)
    old_names = set(n["name"] for n in old_notes)

    new_notes = [n for n in all_notes if n["name"] not in old_names]
    print(f"Full dump: {len(all_notes)} notes", flush=True)
    print(f"Already imported: {len(old_names)} notes", flush=True)
    print(f"New to import: {len(new_notes)} notes", flush=True)

    if not new_notes:
        print("Nothing to import.")
        return

    total_chars = sum(min(len(n["body"]), args.max_chars) for n in new_notes)
    print(f"Total content: {total_chars:,} chars (capped at {args.max_chars})", flush=True)

    if args.dry_run:
        for n in new_notes[:5]:
            print(f"  {n['name'][:60]} ({len(n['body'])} chars)", flush=True)
        print(f"[DRY RUN] Would import {len(new_notes)} notes in {(len(new_notes) + args.batch_size - 1) // args.batch_size} batches", flush=True)
        return

    # Check sidecar
    try:
        resp = requests.get(f"{GRAPHITI_URL}/health", timeout=5)
        print(f"Graphiti: {resp.json()}", flush=True)
    except Exception:
        print("Graphiti not reachable", file=sys.stderr)
        sys.exit(1)

    # Build episodes
    episodes = []
    for n in new_notes:
        episodes.append({
            "content": n["body"][:args.max_chars],
            "name": n["name"],
            "source_description": f"apple-notes: {n['name']}",
            "episode_type": "text",
            "reference_time": n["date"],
        })

    # Import in batches
    num_batches = (len(episodes) + args.batch_size - 1) // args.batch_size
    print(f"\nImporting {len(episodes)} episodes in {num_batches} batches...\n", flush=True)

    total_ep = total_nd = total_ed = 0
    failed = 0
    start = time.time()

    for batch_idx in range(0, len(episodes), args.batch_size):
        batch = episodes[batch_idx:batch_idx + args.batch_size]
        batch_num = batch_idx // args.batch_size + 1
        print(f"[Batch {batch_num}/{num_batches}] {len(batch)} episodes...", flush=True)

        try:
            resp = requests.post(f"{GRAPHITI_URL}/episode/bulk", json={
                "episodes": batch, "group_id": "mikai-default"
            }, timeout=600)

            if resp.status_code == 200:
                r = resp.json()
                ep, nd, ed = r.get("episodes_created", 0), r.get("nodes_created", 0), r.get("edges_created", 0)
                total_ep += ep; total_nd += nd; total_ed += ed
                elapsed = time.time() - start
                print(f"  OK: +{ep} ep, +{nd} nodes, +{ed} edges ({elapsed:.0f}s)", flush=True)
            else:
                failed += 1
                print(f"  FAILED ({resp.status_code})", flush=True)
        except Exception as e:
            failed += 1
            print(f"  ERROR: {e}", flush=True)

        if batch_idx + args.batch_size < len(episodes):
            print(f"  Waiting {args.batch_delay}s...", flush=True)
            time.sleep(args.batch_delay)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed/60:.1f} min", flush=True)
    print(f"  Episodes: {total_ep}, Nodes: {total_nd}, Edges: {total_ed}, Failed: {failed}/{num_batches}", flush=True)


if __name__ == "__main__":
    main()

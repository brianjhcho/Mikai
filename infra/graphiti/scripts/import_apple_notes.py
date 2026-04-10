"""
import_apple_notes.py

Reads Apple Notes directly via osascript and imports into Graphiti as episodes.
Bypasses SQLite — Graphiti is the L3 backend.

Usage:
    python scripts/import_apple_notes.py [--limit N] [--delay SECS] [--dry-run]
"""

import argparse
import json
import subprocess
import sys
import time

import requests

DEFAULT_GRAPHITI_URL = "http://localhost:8100"


def read_apple_notes(limit: int | None = None) -> list[dict]:
    """Read notes from Apple Notes via osascript."""
    # Get note count first
    count_script = 'tell application "Notes" to count of notes'
    total = int(subprocess.check_output(["osascript", "-e", count_script]).decode().strip())
    print(f"Apple Notes: {total} notes found")

    actual_limit = min(limit, total) if limit else total

    # Read notes in batches (osascript can timeout on large batches)
    notes = []
    batch_size = 50

    for start in range(1, actual_limit + 1, batch_size):
        end = min(start + batch_size - 1, actual_limit)
        print(f"  Reading notes {start}-{end}...")

        script = f'''
        tell application "Notes"
            set output to ""
            repeat with i from {start} to {end}
                set n to note i
                set noteName to name of n
                set noteBody to plaintext of n
                set noteDate to creation date of n
                set dateStr to (year of noteDate as string) & "-" & text -2 thru -1 of ("0" & ((month of noteDate as number) as string)) & "-" & text -2 thru -1 of ("0" & (day of noteDate as string)) & "T00:00:00Z"
                set output to output & "---NOTE_SEPARATOR---" & noteName & "---FIELD_SEP---" & noteBody & "---FIELD_SEP---" & dateStr
            end repeat
            return output
        end tell
        '''

        try:
            result = subprocess.check_output(
                ["osascript", "-e", script],
                timeout=120,
            ).decode("utf-8", errors="replace")

            for entry in result.split("---NOTE_SEPARATOR---"):
                entry = entry.strip()
                if not entry:
                    continue
                parts = entry.split("---FIELD_SEP---")
                if len(parts) >= 3:
                    name = parts[0].strip()
                    body = parts[1].strip()
                    date = parts[2].strip()
                    # Skip very short notes and notes with secrets
                    skip_patterns = ["api key", "password", "secret", "credential", "token"]
                    is_sensitive = any(p in name.lower() for p in skip_patterns)
                    if len(body) > 50 and not is_sensitive:
                        notes.append({
                            "name": name,
                            "body": body,
                            "date": date,
                        })
        except subprocess.TimeoutExpired:
            print(f"  Timeout reading notes {start}-{end}, skipping batch")
        except Exception as e:
            print(f"  Error reading notes {start}-{end}: {e}")

    print(f"  {len(notes)} notes with content > 50 chars")
    return notes


def import_note(graphiti_url: str, note: dict, dry_run: bool = False) -> dict | None:
    """Send one note to Graphiti as an episode."""
    if dry_run:
        preview = note["body"][:80].replace("\n", " ")
        print(f"  [DRY RUN] {note['name'][:60]} ({len(note['body'])} chars): {preview}...")
        return None

    payload = {
        "content": note["body"],
        "source_description": f"apple-notes: {note['name']}",
        "episode_type": "text",
        "reference_time": note["date"],
        "group_id": "mikai-default",
    }

    max_retries = 5
    for attempt in range(max_retries):
        try:
            resp = requests.post(f"{graphiti_url}/episode", json=payload, timeout=180)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 500 and attempt < max_retries - 1:
                # Likely rate limit propagated as 500 from sidecar
                wait = 15 * (attempt + 1)  # 15s, 30s, 45s, 60s
                print(f"  Retry {attempt+1}/{max_retries} in {wait}s (rate limit)")
                time.sleep(wait)
                continue
            else:
                print(f"  ERROR: {resp.status_code} — {resp.text[:200]}", file=sys.stderr)
                return None
        except requests.exceptions.ReadTimeout:
            if attempt < max_retries - 1:
                wait = 20 * (attempt + 1)
                print(f"  Timeout, retry {attempt+1}/{max_retries} in {wait}s")
                time.sleep(wait)
                continue
            print(f"  ERROR: timeout after {max_retries} retries", file=sys.stderr)
            return None
        except requests.exceptions.RequestException as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            return None
    return None


def main():
    parser = argparse.ArgumentParser(description="Import Apple Notes → Graphiti")
    parser.add_argument("--graphiti-url", default=DEFAULT_GRAPHITI_URL)
    parser.add_argument("--limit", type=int, default=None, help="Max notes to import")
    parser.add_argument("--delay", type=float, default=5.0, help="Seconds between episodes (rate limit, default 5s)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip", type=int, default=0, help="Skip first N notes (resume after failure)")
    args = parser.parse_args()

    # Check sidecar
    if not args.dry_run:
        try:
            resp = requests.get(f"{args.graphiti_url}/health", timeout=5)
            if resp.status_code != 200:
                print(f"Graphiti not healthy: {resp.status_code}", file=sys.stderr)
                sys.exit(1)
            print(f"Graphiti OK: {resp.json()}")
        except requests.exceptions.ConnectionError:
            print(f"Cannot connect to Graphiti at {args.graphiti_url}", file=sys.stderr)
            sys.exit(1)

    # Read notes
    notes = read_apple_notes(args.limit)

    if args.skip > 0:
        print(f"Skipping first {args.skip} notes")
        notes = notes[args.skip:]

    if not notes:
        print("No notes to import.")
        return

    # Import
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Importing {len(notes)} notes (delay: {args.delay}s)...")
    success = 0
    failed = 0
    total_nodes = 0
    total_edges = 0
    start = time.time()

    for i, note in enumerate(notes):
        name = note["name"][:60]
        chars = len(note["body"])
        print(f"[{i+1}/{len(notes)}] {name} ({chars} chars)")

        result = import_note(args.graphiti_url, note, args.dry_run)
        if result or args.dry_run:
            success += 1
            if result:
                total_nodes += result.get("nodes_created", 0)
                total_edges += result.get("edges_created", 0)
        else:
            failed += 1

        # Rate limit
        if not args.dry_run and i < len(notes) - 1:
            time.sleep(args.delay)

        # Progress
        if (i + 1) % 10 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed
            remaining = (len(notes) - i - 1) / rate if rate > 0 else 0
            print(f"  --- {i+1}/{len(notes)} ({success} ok, {failed} fail) | {elapsed:.0f}s | ~{remaining/60:.1f}m remaining | {total_nodes} nodes, {total_edges} edges ---")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Success: {success}")
    print(f"  Failed: {failed}")
    print(f"  Nodes created: {total_nodes}")
    print(f"  Edges created: {total_edges}")
    if success > 0:
        print(f"  Rate: {elapsed/success:.1f}s per note")


if __name__ == "__main__":
    main()

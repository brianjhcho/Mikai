"""
export_sqlite_sources.py

Exports perplexity and claude-thread sources from SQLite to a dump file
compatible with bulk_import.py's format.

Usage:
    python scripts/export_sqlite_sources.py --source-type perplexity --output /tmp/mikai_perplexity.txt
    python scripts/export_sqlite_sources.py --source-type claude-thread --output /tmp/mikai_claude.txt
"""

import argparse
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path.home() / ".mikai" / "mikai.db"
SKIP_PATTERNS = ["api key", "password", "secret", "credential", "token"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=str(DEFAULT_DB))
    parser.add_argument("--source-type", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT id, label, raw_content, source, created_at
        FROM sources
        WHERE source = ? AND raw_content IS NOT NULL AND LENGTH(raw_content) > 50
        ORDER BY created_at ASC
    """
    params = [args.source_type]
    if args.limit:
        query += " LIMIT ?"
        params.append(args.limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    count = 0
    with open(args.output, "w") as f:
        for row in rows:
            label = row["label"] or "untitled"
            is_sensitive = any(p in label.lower() for p in SKIP_PATTERNS)
            if is_sensitive:
                continue
            f.write("===NOTE_START===\n")
            f.write(f"NAME:{label}\n")
            f.write(f"DATE:{row['created_at'] or '2026-01-01T00:00:00Z'}\n")
            f.write(row["raw_content"])
            f.write("\n===NOTE_END===\n")
            count += 1

    print(f"Exported {count} {args.source_type} sources to {args.output}", flush=True)


if __name__ == "__main__":
    main()

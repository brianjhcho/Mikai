"""CLI for mikai_ask.

    python3 -m infra.mikai_ask "what's next on the proposal?"
    echo "what's next on the proposal?" | python3 -m infra.mikai_ask
    make ask Q="..."   /   make ask-dry Q="..."

Flags: -v/--verbose (retrieval + prompt-size stats to stderr),
--dry-run (print the composed prompt, no LLM call, no log row).
"""

from __future__ import annotations

import argparse
import sys

from infra.mikai_ask.core import ask


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mikai-ask",
        description="Free text in, substrate-grounded answer out.",
    )
    parser.add_argument("query", nargs="*", help="the question (or pipe via stdin)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print retrieval + prompt-size stats to stderr")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the composed prompt; no LLM call, no log")
    args = parser.parse_args(argv)

    query = " ".join(args.query).strip()
    if not query and not sys.stdin.isatty():
        query = sys.stdin.read().strip()
    if not query:
        parser.error("no query — pass it as an argument or pipe via stdin")

    print(ask(query, verbose=args.verbose, dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

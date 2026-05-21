#!/usr/bin/env python3
"""
eval/label.py — Keyboard-first labeling CLI for Stage-6 eval candidates.

Reads eval/labeled_entities.jsonl and eval/labeled_edges.jsonl, presents each
unlabeled record (is_valid == null) one at a time, and writes the label back
immediately so an interrupt never loses state.

Keys:
  y  — mark valid   (is_valid = true)
  n  — mark invalid (is_valid = false)
  s  — skip for now (leave null, come back later)
  q  — quit (progress saved up to this point)
  ?  — show this help

Invocation:
  python eval/label.py                   # labels both files
  python eval/label.py --entities-only
  python eval/label.py --edges-only
  python eval/label.py --limit 50        # stop after 50 decisions
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import termios
import textwrap
import tty
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "infra" / "graphiti"))

from eval.schemas import EdgeCandidate, EntityCandidate

# ── Terminal helpers ──────────────────────────────────────────────────────────

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_BLUE = "\033[34m"


def _getch() -> str:
    """Read a single character from stdin without requiring Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch


def _clear_line() -> None:
    print("\r\033[K", end="", flush=True)


def _hr(char: str = "─", width: int = 72) -> str:
    return char * width


def _wrap(text: str, width: int = 72, indent: str = "  ") -> str:
    return textwrap.fill(text, width=width, initial_indent=indent, subsequent_indent=indent)


# ── JSONL in-place update ─────────────────────────────────────────────────────


def _rewrite_jsonl(path: Path, records: list) -> None:
    """Atomically rewrite the JSONL file with updated records."""
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(rec.model_dump_json() + "\n")
    tmp.replace(path)


# ── Display helpers ───────────────────────────────────────────────────────────


def _show_entity(rec: EntityCandidate, idx: int, total: int) -> None:
    print()
    print(_hr())
    print(
        f"{_BOLD}[{idx}/{total}]  ENTITY{_RESET}  "
        f"{_CYAN}{rec.entity_type}{_RESET}  "
        f"source={_DIM}{rec.source_tag}{_RESET}"
    )
    print(_hr())
    print(f"  {_BOLD}Name:{_RESET}    {rec.name}")
    print(f"  {_BOLD}Summary:{_RESET} {rec.summary or '(none)'}")
    print()
    if rec.source_excerpt:
        print(f"  {_BOLD}Source excerpt:{_RESET}")
        print(_wrap(rec.source_excerpt))
    else:
        print(f"  {_DIM}(no source excerpt){_RESET}")
    print()
    print(
        f"  {_GREEN}[y]{_RESET} valid  "
        f"{_RED}[n]{_RESET} invalid  "
        f"{_YELLOW}[s]{_RESET} skip  "
        f"{_BLUE}[q]{_RESET} quit  "
        f"[?] help"
    )
    print("  > ", end="", flush=True)


def _show_edge(rec: EdgeCandidate, idx: int, total: int) -> None:
    print()
    print(_hr())
    print(
        f"{_BOLD}[{idx}/{total}]  EDGE{_RESET}  "
        f"{_CYAN}{rec.edge_type}{_RESET}  "
        f"source={_DIM}{rec.source_tag}{_RESET}  "
        f"conf={rec.confidence:.2f}"
    )
    print(_hr())
    print(
        f"  {_BOLD}{rec.source_name}{_RESET} ({_DIM}{rec.source_type}{_RESET})"
        f"  →  "
        f"{_BOLD}{rec.target_name}{_RESET} ({_DIM}{rec.target_type}{_RESET})"
    )
    print()
    if rec.fact:
        print(f"  {_BOLD}Fact:{_RESET}")
        print(_wrap(rec.fact))
    else:
        print(f"  {_DIM}(no fact sentence){_RESET}")
    print()
    if rec.source_excerpt:
        print(f"  {_BOLD}Source excerpt:{_RESET}")
        print(_wrap(rec.source_excerpt))
    print()
    print(
        f"  {_GREEN}[y]{_RESET} valid  "
        f"{_RED}[n]{_RESET} invalid  "
        f"{_YELLOW}[s]{_RESET} skip  "
        f"{_BLUE}[q]{_RESET} quit  "
        f"[?] help"
    )
    print("  > ", end="", flush=True)


def _show_help() -> None:
    print()
    print(_hr("═"))
    print("  Labeling guide")
    print(_hr("─"))
    print("  y — VALID:   the entity/edge is correctly typed and factually accurate.")
    print("  n — INVALID: garbage, mis-typed, hallucinated, or factually wrong.")
    print("  s — SKIP:    unsure; leave null; can revisit with --skip-only flag.")
    print("  q — QUIT:    save progress and exit. Run again to resume.")
    print()
    print("  For entities, ask:")
    print("    • Is the entity type appropriate for what the excerpt describes?")
    print("    • Is the name/summary accurate given the excerpt?")
    print()
    print("  For edges, ask:")
    print("    • Does the relationship type fit the semantic connection?")
    print("    • Is the fact sentence accurate?")
    print(_hr("═"))


# ── Labeling loop ─────────────────────────────────────────────────────────────


def _label_records(
    records: list,
    show_fn,
    path: Path,
    limit: int | None,
) -> tuple[int, int, int]:
    """
    Interactively label records that have is_valid == None.

    Returns (labeled, skipped, quit_early).
    """
    unlabeled_indices = [i for i, r in enumerate(records) if r.is_valid is None]
    total_unlabeled = len(unlabeled_indices)

    if total_unlabeled == 0:
        print(f"  All records in {path.name} are already labeled.")
        return 0, 0, 0

    labeled = 0
    skipped = 0
    quit_early = False

    for seq, idx in enumerate(unlabeled_indices, start=1):
        if limit is not None and labeled >= limit:
            break

        rec = records[idx]
        show_fn(rec, seq, total_unlabeled)

        while True:
            ch = _getch().lower()
            if ch == "y":
                rec.is_valid = True
                labeled += 1
                _clear_line()
                print(f"  {_GREEN}✓ valid{_RESET}")
                break
            elif ch == "n":
                rec.is_valid = False
                labeled += 1
                _clear_line()
                print(f"  {_RED}✗ invalid{_RESET}")
                break
            elif ch == "s":
                skipped += 1
                _clear_line()
                print(f"  {_YELLOW}→ skipped{_RESET}")
                break
            elif ch == "q":
                _clear_line()
                print(f"  {_BLUE}Quitting. Progress saved.{_RESET}")
                quit_early = True
                break
            elif ch == "?":
                _show_help()
                show_fn(rec, seq, total_unlabeled)
            # any other key: re-prompt silently

        # Write after every decision (even skips don't change the file but
        # a label does — write unconditionally for simplicity/safety)
        _rewrite_jsonl(path, records)

        if quit_early:
            break

    return labeled, skipped, quit_early


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Keyboard-first labeling CLI for Stage-6 eval candidates."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--entities-only", action="store_true")
    mode.add_argument("--edges-only", action="store_true")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N label decisions (across both files).",
    )
    parser.add_argument(
        "--data-dir",
        default=str(REPO_ROOT / "eval"),
        metavar="DIR",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    entities_path = data_dir / "labeled_entities.jsonl"
    edges_path = data_dir / "labeled_edges.jsonl"

    # ── Check stdin is a tty ─────────────────────────────────────────────────
    if not sys.stdin.isatty():
        print(
            "ERROR: label.py requires an interactive terminal (stdin is not a tty).",
            file=sys.stderr,
        )
        return 1

    total_labeled = 0
    total_skipped = 0

    # ── Entities ─────────────────────────────────────────────────────────────
    if not args.edges_only:
        if not entities_path.exists():
            print(
                f"  {entities_path} not found. Run seed_candidates.py first."
            )
        else:
            print(f"\n{_BOLD}=== ENTITIES ({entities_path.name}) ==={_RESET}")
            entity_records = _load_entity_records(entities_path)
            remaining_limit = (
                None if args.limit is None else args.limit - total_labeled
            )
            labeled, skipped, quit_early = _label_records(
                entity_records,
                _show_entity,
                entities_path,
                remaining_limit,
            )
            total_labeled += labeled
            total_skipped += skipped
            _print_progress(entities_path, entity_records)
            if quit_early:
                _print_summary(total_labeled, total_skipped)
                return 0

    # ── Edges ────────────────────────────────────────────────────────────────
    if not args.entities_only:
        if not edges_path.exists():
            print(
                f"  {edges_path} not found. Run seed_candidates.py first."
            )
        else:
            print(f"\n{_BOLD}=== EDGES ({edges_path.name}) ==={_RESET}")
            edge_records = _load_edge_records(edges_path)
            remaining_limit = (
                None if args.limit is None else args.limit - total_labeled
            )
            labeled, skipped, quit_early = _label_records(
                edge_records,
                _show_edge,
                edges_path,
                remaining_limit,
            )
            total_labeled += labeled
            total_skipped += skipped
            _print_progress(edges_path, edge_records)

    _print_summary(total_labeled, total_skipped)
    return 0


def _load_entity_records(path: Path) -> list[EntityCandidate]:
    records: list[EntityCandidate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(EntityCandidate.model_validate(json.loads(line)))
    return records


def _load_edge_records(path: Path) -> list[EdgeCandidate]:
    records: list[EdgeCandidate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(EdgeCandidate.model_validate(json.loads(line)))
    return records


def _print_progress(path: Path, records: list) -> None:
    n_valid = sum(1 for r in records if r.is_valid is True)
    n_invalid = sum(1 for r in records if r.is_valid is False)
    n_null = sum(1 for r in records if r.is_valid is None)
    total = len(records)
    print(
        f"\n  {path.name}: "
        f"{_GREEN}{n_valid} valid{_RESET}  "
        f"{_RED}{n_invalid} invalid{_RESET}  "
        f"{_YELLOW}{n_null} unlabeled{_RESET}  "
        f"/ {total} total"
    )


def _print_summary(labeled: int, skipped: int) -> None:
    print()
    print(_hr("═"))
    print(
        f"  Session complete. "
        f"Labeled: {_BOLD}{labeled}{_RESET}  "
        f"Skipped: {_YELLOW}{skipped}{_RESET}"
    )
    print("  Run again to continue where you left off.")
    print(_hr("═"))
    print()


if __name__ == "__main__":
    sys.exit(main())

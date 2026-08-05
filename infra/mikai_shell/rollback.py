"""Undo log for shell mutations.

Every executed move / rename / delete lands as an atomic JSONL row in
~/.mikai/rollback.log. An `undo` command replays a batch in reverse.

Design commitments:
- Append-only. Never rewrite existing rows.
- Batch-scoped. Each shell invocation gets a batch_id; undo takes a
  batch_id and reverses that batch specifically.
- Collision-safe. On move: if the destination exists, MIKAI adds a
  numeric suffix (`file.pdf` → `file (2).pdf`). Never overwrite.
- Recoverable across restarts. The log is the source of truth; the
  shell reads it on demand.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

ROLLBACK_LOG = Path.home() / ".mikai" / "rollback.log"


@dataclass
class MoveRecord:
    """One executed move, journalled to the rollback log."""

    batch_id: str
    op: str                      # "move" | "rename" | "delete"
    src: str                     # absolute path (post-op source, i.e. original location)
    dst: str                     # absolute path (post-op destination, "" for delete)
    ts: str                      # ISO-8601 UTC
    rationale: str = ""          # LLM's reason, for later audit
    # If the destination already existed, this holds the suffix we added.
    collision_suffix: str = ""


@dataclass
class Batch:
    batch_id: str
    started_at: str
    prompt: str = ""             # the original user prompt
    scope: str = ""              # e.g. "~/Desktop"
    records: list[MoveRecord] = field(default_factory=list)
    finished_at: str = ""
    aborted: bool = False
    aborted_reason: str = ""


def new_batch_id() -> str:
    """12-char hex uuid, same shape as notif_id (D-054)."""
    return uuid.uuid4().hex[:12]


def _append(row: dict) -> None:
    ROLLBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ROLLBACK_LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")


def start_batch(prompt: str, scope: str) -> Batch:
    batch = Batch(
        batch_id=new_batch_id(),
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        prompt=prompt,
        scope=scope,
    )
    _append({"kind": "batch_start", **asdict(batch)})
    return batch


def finish_batch(batch: Batch, *, aborted: bool = False, reason: str = "") -> None:
    batch.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    batch.aborted = aborted
    batch.aborted_reason = reason
    _append({
        "kind": "batch_end",
        "batch_id": batch.batch_id,
        "finished_at": batch.finished_at,
        "aborted": aborted,
        "reason": reason,
        "n_records": len(batch.records),
    })


def _next_free(dst: Path) -> tuple[Path, str]:
    """If dst exists, generate `dst (2)`, `dst (3)`, ... until a free path is found.
    Returns (chosen_path, suffix_str) — suffix is '' when no collision."""
    if not dst.exists():
        return dst, ""
    parent = dst.parent
    stem = dst.stem
    ext = dst.suffix
    n = 2
    while True:
        candidate = parent / f"{stem} ({n}){ext}"
        if not candidate.exists():
            return candidate, f" ({n})"
        n += 1
        if n > 999:
            raise RuntimeError(f"Too many collisions for {dst}")


def execute_move(
    batch: Batch,
    src: str,
    dst: str,
    rationale: str = "",
) -> MoveRecord:
    """Execute one file move with collision-safe rename + journalling.
    Raises OSError on filesystem error; caller decides whether to abort."""
    src_path = Path(src)
    dst_path = Path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    chosen, suffix = _next_free(dst_path)
    shutil.move(str(src_path), str(chosen))
    rec = MoveRecord(
        batch_id=batch.batch_id,
        op="move",
        src=str(src_path),
        dst=str(chosen),
        ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        rationale=rationale,
        collision_suffix=suffix,
    )
    batch.records.append(rec)
    _append({"kind": "record", **asdict(rec)})
    return rec


def read_batches() -> list[Batch]:
    """Rehydrate batches from the log. Returns oldest first."""
    if not ROLLBACK_LOG.exists():
        return []
    batches: dict[str, Batch] = {}
    with ROLLBACK_LOG.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = row.get("kind")
            bid = row.get("batch_id")
            if not bid:
                continue
            if kind == "batch_start":
                batches[bid] = Batch(
                    batch_id=bid,
                    started_at=row.get("started_at", ""),
                    prompt=row.get("prompt", ""),
                    scope=row.get("scope", ""),
                )
            elif kind == "batch_end":
                b = batches.get(bid)
                if b is not None:
                    b.finished_at = row.get("finished_at", "")
                    b.aborted = row.get("aborted", False)
                    b.aborted_reason = row.get("reason", "")
            elif kind == "record":
                b = batches.get(bid)
                if b is not None:
                    b.records.append(MoveRecord(
                        batch_id=bid,
                        op=row.get("op", ""),
                        src=row.get("src", ""),
                        dst=row.get("dst", ""),
                        ts=row.get("ts", ""),
                        rationale=row.get("rationale", ""),
                        collision_suffix=row.get("collision_suffix", ""),
                    ))
    # Chronological order by started_at
    return sorted(batches.values(), key=lambda b: b.started_at)


def undo_batch(batch_id: str) -> tuple[int, list[str]]:
    """Reverse every record in the batch. Returns (moves_undone, errors)."""
    batches = read_batches()
    target = next((b for b in batches if b.batch_id == batch_id), None)
    if target is None:
        return (0, [f"batch {batch_id} not found"])
    undone = 0
    errors: list[str] = []
    # Reverse chronological — later moves undo first (in case of dependencies)
    for rec in reversed(target.records):
        if rec.op != "move":
            continue
        try:
            dst_now = Path(rec.dst)
            src_original = Path(rec.src)
            if not dst_now.exists():
                errors.append(f"missing: {rec.dst}")
                continue
            src_original.parent.mkdir(parents=True, exist_ok=True)
            # Undo is itself collision-safe — if the original location was
            # subsequently filled, suffix-rename the un-doing target.
            chosen, _ = _next_free(src_original)
            shutil.move(str(dst_now), str(chosen))
            undone += 1
        except OSError as exc:
            errors.append(f"{rec.dst} → {rec.src}: {exc}")
    # Journal the undo as its own batch marker
    _append({
        "kind": "undo",
        "batch_id": batch_id,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "moves_undone": undone,
        "errors": errors,
    })
    return undone, errors


def latest_batch() -> Batch | None:
    batches = read_batches()
    return batches[-1] if batches else None

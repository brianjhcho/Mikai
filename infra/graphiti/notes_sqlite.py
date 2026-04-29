"""Direct reader for Apple Notes' NoteStore.sqlite — the SQLite + gzip +
protobuf path used by forensic tools (mac_apt, apple_cloud_notes_parser).

Why this exists: enumerating 1,000+ notes via AppleScript takes 10+ minutes
because each `body of n` is a separate Apple Event round-trip. Reading the
underlying database directly takes ~20 seconds for the same corpus and is
the standard production approach.

Trade-off: we depend on Apple's CoreData schema and the embedded protobuf
shape. Both have been stable across macOS Big Sur → Sequoia (the columns
ZICCLOUDSYNCINGOBJECT.ZTITLE1, .ZMODIFICATIONDATE1, .ZIDENTIFIER and
ZICNOTEDATA.ZDATA, .ZCRYPTOINITIALIZATIONVECTOR have not moved). If Apple
changes the schema, callers should fall back to the AppleScript path
(see sync.py --legacy-applescript flag).

Also: ZICNOTEDATA.ZDATA is encrypted for password-locked notes. Those
notes have ZCRYPTOINITIALIZATIONVECTOR set; we skip them rather than try
to decrypt.

Usage:
    from notes_sqlite import iter_notes, copy_note_store

    with copy_note_store() as snapshot_path:
        for note in iter_notes(snapshot_path):
            print(note.title, note.modified_at, len(note.body))
"""

from __future__ import annotations

import contextlib
import gzip
import logging
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("mikai-sync.notes-sqlite")

DEFAULT_NOTE_STORE = (
    Path.home()
    / "Library"
    / "Group Containers"
    / "group.com.apple.notes"
    / "NoteStore.sqlite"
)

# CoreData stores dates as seconds since 2001-01-01 UTC.
_CORE_DATA_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)

# Object replacement character — Apple Notes uses U+FFFC where attachments
# (images, drawings, etc.) sit inline. Strip it; graph extraction does not
# need a placeholder.
_OBJECT_REPLACEMENT = "￼"


@dataclass(frozen=True)
class Note:
    """One note's plain-text content + identifying metadata.

    `body` may include the title as its first line — Apple stores the title
    inline rather than as a separate field. Callers can split on the first
    newline if they want title and body apart, but the dedup hash should
    use the whole thing so renames are detected.
    """

    z_pk: int
    identifier: str
    title: str
    body: str
    modified_at: datetime | None
    created_at: datetime | None


# ── Snapshot helper ──────────────────────────────────────────────────────────


@contextlib.contextmanager
def copy_note_store(
    source: Path = DEFAULT_NOTE_STORE,
) -> Iterator[Path]:
    """Yield a path to a stable read-only copy of NoteStore.sqlite.

    Apple Notes writes via SQLite WAL — opening the live DB while Notes.app
    is running risks SQLITE_BUSY and inconsistent reads of the WAL'd pages.
    Copying the trio (.sqlite, -wal, -shm) to a temp dir gives us a
    point-in-time snapshot we can safely query.
    """
    tmp = Path(tempfile.mkdtemp(prefix="mikai-notestore-"))
    try:
        snapshot = tmp / "NoteStore.sqlite"
        shutil.copy2(source, snapshot)
        for suffix in ("-wal", "-shm"):
            sidecar = source.with_name(source.name + suffix)
            if sidecar.exists():
                shutil.copy2(sidecar, snapshot.with_name(snapshot.name + suffix))
        yield snapshot
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Protobuf wire-format walker ──────────────────────────────────────────────


def _parse_varint(buf: bytes, pos: int) -> tuple[int, int]:
    """Read a protobuf varint. Returns (value, new_pos)."""
    result = 0
    shift = 0
    while pos < len(buf):
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")
    raise ValueError("truncated varint")


def _find_field(buf: bytes, target_field: int) -> bytes | None:
    """Scan a protobuf message and return the bytes of the first field with
    `target_field` whose wire type is length-delimited (the only kind we use).

    Returns None if the field is absent or the message is malformed in a way
    that would mask its presence — caller should treat None as "no body."
    """
    pos = 0
    while pos < len(buf):
        try:
            tag, pos = _parse_varint(buf, pos)
        except ValueError:
            return None
        wire_type = tag & 0x07
        field_num = tag >> 3
        if wire_type == 2:  # length-delimited
            try:
                length, pos = _parse_varint(buf, pos)
            except ValueError:
                return None
            if pos + length > len(buf):
                return None
            if field_num == target_field:
                return buf[pos : pos + length]
            pos += length
        elif wire_type == 0:  # varint
            try:
                _, pos = _parse_varint(buf, pos)
            except ValueError:
                return None
        elif wire_type == 1:  # 64-bit fixed
            pos += 8
        elif wire_type == 5:  # 32-bit fixed
            pos += 4
        else:
            # Groups (deprecated) and unknown — bail out.
            return None
    return None


def extract_note_text(zdata: bytes) -> str:
    """Decompress ZDATA and walk the protobuf to the title+body text field.

    Apple Notes layout (stable across macOS Big Sur → Sequoia):
        root.field2 = document
        document.field3 = note
        note.field2 = text (title + body, separated by '\\n')

    Returns "" if any step fails — keeps callers simple, and the empty
    string naturally drops out of dedup / ingestion downstream.
    """
    try:
        decompressed = gzip.decompress(zdata)
    except (OSError, EOFError) as e:
        logger.debug(f"ZDATA gzip decompress failed: {e}")
        return ""
    document = _find_field(decompressed, 2)
    if document is None:
        return ""
    note = _find_field(document, 3)
    if note is None:
        return ""
    text = _find_field(note, 2)
    if text is None:
        return ""
    return text.decode("utf-8", errors="replace").replace(_OBJECT_REPLACEMENT, "")


# ── Date conversion ──────────────────────────────────────────────────────────


def _coredata_to_utc(seconds: float | None) -> datetime | None:
    if seconds is None:
        return None
    try:
        return _CORE_DATA_EPOCH + timedelta(seconds=float(seconds))
    except (TypeError, ValueError, OverflowError):
        return None


# ── Public reader ────────────────────────────────────────────────────────────


def iter_notes(
    db_path: Path,
    *,
    modified_after: datetime | None = None,
) -> Iterator[Note]:
    """Yield Note records from a NoteStore.sqlite snapshot.

    `modified_after` filters to notes modified strictly after the given UTC
    timestamp — used by the daemon to fetch only deltas after the initial
    seed. None returns every note in the trash-excluded set.

    Skips:
      - notes with no ZICNOTEDATA row (orphans / templates / placeholders)
      - notes whose ZCRYPTOINITIALIZATIONVECTOR is set (password-locked)
      - notes whose ZDATA fails to decompress (corrupt or schema-shifted)
      - notes in the system Trash folder (ZMARKEDFORDELETION = 1)
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT
                o.Z_PK            AS pk,
                o.ZIDENTIFIER     AS identifier,
                o.ZTITLE1         AS title,
                o.ZMODIFICATIONDATE1 AS modified,
                o.ZCREATIONDATE1  AS created,
                d.ZDATA           AS data,
                d.ZCRYPTOINITIALIZATIONVECTOR AS iv
            FROM ZICCLOUDSYNCINGOBJECT o
            JOIN ZICNOTEDATA d ON d.ZNOTE = o.Z_PK
            WHERE o.ZTITLE1 IS NOT NULL
              AND COALESCE(o.ZMARKEDFORDELETION, 0) = 0
        """
        params: list[float] = []
        if modified_after is not None:
            since_seconds = (modified_after - _CORE_DATA_EPOCH).total_seconds()
            sql += " AND o.ZMODIFICATIONDATE1 > ?"
            params.append(since_seconds)

        for row in con.execute(sql, params):
            if row["iv"] is not None:
                continue  # password-locked, skip
            if row["data"] is None:
                continue
            body = extract_note_text(bytes(row["data"]))
            if not body:
                continue
            yield Note(
                z_pk=row["pk"],
                identifier=row["identifier"] or "",
                title=row["title"] or "",
                body=body,
                modified_at=_coredata_to_utc(row["modified"]),
                created_at=_coredata_to_utc(row["created"]),
            )
    finally:
        con.close()


def count_notes(db_path: Path) -> int:
    """How many notes the snapshot contains (after trash exclusion). Useful
    for sanity-checking before a long sync pass."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = con.execute(
            "SELECT count(*) FROM ZICCLOUDSYNCINGOBJECT "
            "WHERE ZTITLE1 IS NOT NULL "
            "AND COALESCE(ZMARKEDFORDELETION, 0) = 0"
        )
        return int(cur.fetchone()[0])
    finally:
        con.close()

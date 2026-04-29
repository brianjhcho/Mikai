"""Behavioral tests for the Apple Notes SQLite reader.

Synthesises gzipped protobuf payloads and a minimal NoteStore.sqlite schema
so the tests run anywhere — no live macOS, no FDA, no real Notes.app.
"""

from __future__ import annotations

import gzip
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import notes_sqlite as ns  # noqa: E402


# ── Protobuf encoding helpers (tests only) ───────────────────────────────────


def _encode_varint(n: int) -> bytes:
    out = bytearray()
    while n > 0x7F:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n & 0x7F)
    return bytes(out)


def _encode_length_delim(field_num: int, payload: bytes) -> bytes:
    tag = (field_num << 3) | 2
    return _encode_varint(tag) + _encode_varint(len(payload)) + payload


def _encode_varint_field(field_num: int, value: int) -> bytes:
    tag = (field_num << 3) | 0
    return _encode_varint(tag) + _encode_varint(value)


def _make_zdata(text: str) -> bytes:
    """Build the protobuf shape Apple Notes uses: root.f2.f3.f2 = text."""
    inner_text = _encode_length_delim(2, text.encode("utf-8"))
    note = _encode_length_delim(3, inner_text)
    document = _encode_length_delim(2, note)
    return gzip.compress(document)


# ── Fixture: minimal NoteStore.sqlite ────────────────────────────────────────


def _build_db(
    path: Path,
    rows: list[dict],
) -> None:
    """Stand up a NoteStore.sqlite-shaped fixture with just the columns the
    reader touches. Apple's real schema has dozens more — we only need
    these for the queries in iter_notes / count_notes."""
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE ZICCLOUDSYNCINGOBJECT (
            Z_PK INTEGER PRIMARY KEY,
            ZIDENTIFIER TEXT,
            ZTITLE1 TEXT,
            ZMODIFICATIONDATE1 REAL,
            ZCREATIONDATE1 REAL,
            ZMARKEDFORDELETION INTEGER
        );
        CREATE TABLE ZICNOTEDATA (
            Z_PK INTEGER PRIMARY KEY,
            ZNOTE INTEGER,
            ZDATA BLOB,
            ZCRYPTOINITIALIZATIONVECTOR BLOB
        );
        """
    )
    for i, row in enumerate(rows, start=1):
        con.execute(
            "INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES (?, ?, ?, ?, ?, ?)",
            (
                i,
                row.get("identifier") or f"id-{i}",
                row.get("title"),
                row.get("modified"),
                row.get("created"),
                row.get("trashed", 0),
            ),
        )
        if "data" in row or "iv" in row:
            con.execute(
                "INSERT INTO ZICNOTEDATA VALUES (?, ?, ?, ?)",
                (i, i, row.get("data"), row.get("iv")),
            )
    con.commit()
    con.close()


# ── varint / find_field ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value", [0, 1, 127, 128, 16383, 16384, 2**21 - 1, 2**21, 2**31, 2**62],
)
def test_parse_varint_round_trips(value: int) -> None:
    encoded = _encode_varint(value)
    decoded, pos = ns._parse_varint(encoded, 0)
    assert decoded == value
    assert pos == len(encoded)


def test_parse_varint_rejects_truncated_input() -> None:
    with pytest.raises(ValueError):
        ns._parse_varint(b"\x80\x80", 0)


def test_find_field_extracts_length_delimited_field() -> None:
    msg = _encode_length_delim(7, b"hello") + _encode_length_delim(2, b"world")
    assert ns._find_field(msg, 7) == b"hello"
    assert ns._find_field(msg, 2) == b"world"
    assert ns._find_field(msg, 99) is None


def test_find_field_skips_varint_fields() -> None:
    msg = _encode_varint_field(1, 42) + _encode_length_delim(2, b"target")
    assert ns._find_field(msg, 2) == b"target"


def test_find_field_returns_none_on_truncated_message() -> None:
    msg = b"\x12\x05hi"  # claims length 5, has only 2 bytes
    assert ns._find_field(msg, 2) is None


# ── extract_note_text ────────────────────────────────────────────────────────


def test_extract_note_text_round_trips() -> None:
    zdata = _make_zdata("My Title\nFirst line\nSecond line")
    assert ns.extract_note_text(zdata) == "My Title\nFirst line\nSecond line"


def test_extract_note_text_strips_object_replacement_char() -> None:
    zdata = _make_zdata("Header\n￼\nbody")
    assert ns.extract_note_text(zdata) == "Header\n\nbody"


def test_extract_note_text_returns_empty_on_bad_gzip() -> None:
    assert ns.extract_note_text(b"not actually gzip") == ""


def test_extract_note_text_returns_empty_when_path_missing() -> None:
    # gzip-valid bytes but no field 2 at root
    payload = gzip.compress(_encode_varint_field(1, 0))
    assert ns.extract_note_text(payload) == ""


# ── iter_notes / count_notes ─────────────────────────────────────────────────


def test_iter_notes_returns_decoded_records(tmp_path: Path) -> None:
    db = tmp_path / "NoteStore.sqlite"
    _build_db(db, [
        {"title": "Alpha", "data": _make_zdata("Alpha\nbody-a"),
         "modified": 0.0, "created": 0.0},
        {"title": "Beta",  "data": _make_zdata("Beta\nbody-b"),
         "modified": 100.0, "created": 0.0},
    ])
    notes = list(ns.iter_notes(db))
    assert [n.title for n in notes] == ["Alpha", "Beta"]
    assert notes[0].body == "Alpha\nbody-a"
    assert notes[1].body == "Beta\nbody-b"


def test_iter_notes_skips_locked_notes(tmp_path: Path) -> None:
    db = tmp_path / "NoteStore.sqlite"
    _build_db(db, [
        {"title": "Locked", "data": _make_zdata("secret"),
         "iv": b"\x01" * 16, "modified": 0.0, "created": 0.0},
        {"title": "Open",   "data": _make_zdata("Open\nbody"),
         "modified": 0.0, "created": 0.0},
    ])
    titles = [n.title for n in ns.iter_notes(db)]
    assert titles == ["Open"]


def test_iter_notes_skips_trashed_notes(tmp_path: Path) -> None:
    db = tmp_path / "NoteStore.sqlite"
    _build_db(db, [
        {"title": "Live",     "data": _make_zdata("Live\nbody"),
         "modified": 0.0, "created": 0.0},
        {"title": "InTrash",  "data": _make_zdata("InTrash\nbody"),
         "modified": 0.0, "created": 0.0, "trashed": 1},
    ])
    titles = [n.title for n in ns.iter_notes(db)]
    assert titles == ["Live"]


def test_iter_notes_skips_orphans_and_corrupt_payloads(tmp_path: Path) -> None:
    db = tmp_path / "NoteStore.sqlite"
    _build_db(db, [
        {"title": "Good",       "data": _make_zdata("Good\nbody"),
         "modified": 0.0, "created": 0.0},
        {"title": "NoData"},                                  # no ZICNOTEDATA row
        {"title": "Corrupt",    "data": b"not gzip",
         "modified": 0.0, "created": 0.0},
    ])
    titles = [n.title for n in ns.iter_notes(db)]
    assert titles == ["Good"]


def test_iter_notes_filters_by_modified_after(tmp_path: Path) -> None:
    db = tmp_path / "NoteStore.sqlite"
    _build_db(db, [
        {"title": "Old", "data": _make_zdata("Old\nbody"),
         "modified": 100.0, "created": 0.0},     # 2001-01-01 + 100s
        {"title": "New", "data": _make_zdata("New\nbody"),
         "modified": 1_000_000.0, "created": 0.0},
    ])
    cutoff = ns._CORE_DATA_EPOCH.replace() + ns.timedelta(seconds=500.0) \
        if hasattr(ns, "timedelta") else None
    # use the public datetime API directly
    from datetime import timedelta
    cutoff = ns._CORE_DATA_EPOCH + timedelta(seconds=500.0)
    titles = [n.title for n in ns.iter_notes(db, modified_after=cutoff)]
    assert titles == ["New"]


def test_iter_notes_decodes_modified_at_to_utc(tmp_path: Path) -> None:
    db = tmp_path / "NoteStore.sqlite"
    # 2024-01-01 00:00:00 UTC = 725846400 seconds after 2001-01-01
    seconds_2024 = (
        datetime(2024, 1, 1, tzinfo=timezone.utc) - ns._CORE_DATA_EPOCH
    ).total_seconds()
    _build_db(db, [
        {"title": "New Year", "data": _make_zdata("New Year\nbody"),
         "modified": seconds_2024, "created": seconds_2024},
    ])
    [n] = list(ns.iter_notes(db))
    assert n.modified_at == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert n.created_at == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_count_notes_excludes_trash(tmp_path: Path) -> None:
    db = tmp_path / "NoteStore.sqlite"
    _build_db(db, [
        {"title": "A"},
        {"title": "B"},
        {"title": "C", "trashed": 1},
    ])
    assert ns.count_notes(db) == 2

"""
Minimal stdlib iCloud CalDAV client (D-055).

Handles the four operations the calendar planner needs:
  1. Discover the user's principal + calendar home + calendar list.
  2. List today's events across editable calendars, with a sole-attendee filter.
  3. Fetch a specific event (with its etag for optimistic concurrency).
  4. PATCH an event's SUMMARY and DESCRIPTION (preserves everything else).

No third-party deps. All I/O is stdlib urllib. XML parsed with ElementTree.
iCal (RFC 5545) is line-unfolded on read and line-folded/escaped on write.

Auth: HTTP Basic with the user's Apple ID + an app-specific password from
appleid.apple.com. Regular iCloud passwords will NOT work here.

Threat model note: we only ever PATCH events we're rewriting a known field
on — SUMMARY (title) and DESCRIPTION. UID, DTSTART, DTEND, ORGANIZER,
ATTENDEE, RRULE, and other lines are preserved verbatim. Optimistic
concurrency via If-Match: <etag> prevents overwriting a mutation from
another client that landed between fetch and PUT.
"""

from __future__ import annotations

import base64
import re
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib import request as urlreq
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

BASE_URL = "https://caldav.icloud.com"
USER_AGENT = "MIKAI-CalDAV/1.0 (personal)"

# XML namespaces used across DAV / CalDAV.
DAV_NS = "DAV:"
CALDAV_NS = "urn:ietf:params:xml:ns:caldav"
NSMAP = {"d": DAV_NS, "c": CALDAV_NS}


# ── Data classes ───────────────────────────────────────────────────────


@dataclass
class Calendar:
    href: str            # absolute URL (host + path) — safe to fetch/PUT against
    displayname: str     # human-readable name ("Home", "Work", …)


@dataclass
class Event:
    calendar_href: str
    event_href: str      # absolute URL to this specific .ics resource
    etag: str
    uid: str             # the VEVENT UID (stable across mutations)
    title: str
    description: str
    dtstart: str         # raw DTSTART line value (e.g. "20260713T170000Z")
    dtend: str
    attendees: list[str] = field(default_factory=list)  # CN or mailto values, sans ORGANIZER
    raw_ics: str = ""    # full VCALENDAR text, needed for PATCH


# ── HTTP layer ─────────────────────────────────────────────────────────


class CalDAVError(RuntimeError):
    pass


def _request(
    method: str,
    url: str,
    user: str,
    password: str,
    body: bytes | None = None,
    headers: dict | None = None,
    timeout: float = 15.0,
    max_redirects: int = 3,
) -> tuple[int, dict, bytes]:
    """Issue a CalDAV request with Basic auth, following redirects while
    PRESERVING the original method (urllib's default handler falls back
    to GET on redirect, which breaks PROPFIND / REPORT / PUT).
    """
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    h = {
        "Authorization": f"Basic {auth}",
        "User-Agent": USER_AGENT,
    }
    if headers:
        h.update(headers)

    ctx = ssl.create_default_context()
    current = url
    for _ in range(max_redirects + 1):
        req = urlreq.Request(current, data=body, method=method, headers=h)
        try:
            with urlreq.urlopen(req, timeout=timeout, context=ctx) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except HTTPError as e:
            if e.code in (301, 302, 307, 308):
                loc = e.headers.get("Location")
                if not loc:
                    raise CalDAVError(f"{method} {current} → {e.code} no Location") from e
                current = urljoin(current, loc)
                continue
            # 401 / 403 / 404 / 5xx surface as CalDAVError so callers see the code.
            raise CalDAVError(f"{method} {current} → HTTP {e.code}: "
                              f"{e.read()[:400].decode('utf-8', errors='replace')}") from e
        except URLError as e:
            raise CalDAVError(f"{method} {current} → network: {e.reason}") from e
    raise CalDAVError(f"{method} {url} → too many redirects")


def _absolute(url_or_path: str, base: str) -> str:
    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        return url_or_path
    parsed = urlparse(base)
    return f"{parsed.scheme}://{parsed.netloc}{url_or_path}"


# ── PROPFIND / REPORT XML helpers ──────────────────────────────────────

_PROPFIND_PRINCIPAL = b"""<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:">
  <d:prop><d:current-user-principal/></d:prop>
</d:propfind>"""

_PROPFIND_HOMESET = b"""<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop><c:calendar-home-set/></d:prop>
</d:propfind>"""

_PROPFIND_CALENDARS = b"""<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:displayname/>
    <d:resourcetype/>
    <c:supported-calendar-component-set/>
  </d:prop>
</d:propfind>"""


def _report_time_range(start_utc: datetime, end_utc: datetime) -> bytes:
    def fmt(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return (
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">\n'
        f'  <d:prop><d:getetag/><c:calendar-data/></d:prop>\n'
        f'  <c:filter>\n'
        f'    <c:comp-filter name="VCALENDAR">\n'
        f'      <c:comp-filter name="VEVENT">\n'
        f'        <c:time-range start="{fmt(start_utc)}" end="{fmt(end_utc)}"/>\n'
        f'      </c:comp-filter>\n'
        f'    </c:comp-filter>\n'
        f'  </c:filter>\n'
        f'</c:calendar-query>'
    ).encode()


# ── iCal (RFC 5545) parsing / manipulation ─────────────────────────────


def _unfold(ics: str) -> list[str]:
    """RFC 5545: continuation lines start with a space or tab. Join them
    into the preceding line so we can key-scan properties atomically.
    """
    out: list[str] = []
    for line in ics.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _fold(line: str, width: int = 74) -> str:
    """Refold a single line to RFC 5545 width, using CRLF + space
    continuation. iCloud accepts LF but the spec is CRLF; emit CRLF.
    """
    if len(line) <= width:
        return line
    parts = [line[:width]]
    i = width
    while i < len(line):
        parts.append("\r\n " + line[i:i + width - 1])
        i += width - 1
    return "".join(parts)


def _escape_text(v: str) -> str:
    """RFC 5545 TEXT escaping: \\, comma, semicolon, and newline."""
    return (
        v.replace("\\", "\\\\")
         .replace("\n", "\\n")
         .replace(",", "\\,")
         .replace(";", "\\;")
    )


def _unescape_text(v: str) -> str:
    # Order matters: unescape \\n before \\.
    out = []
    i = 0
    while i < len(v):
        c = v[i]
        if c == "\\" and i + 1 < len(v):
            nxt = v[i + 1]
            if nxt == "n" or nxt == "N":
                out.append("\n"); i += 2; continue
            if nxt in (",", ";", "\\"):
                out.append(nxt); i += 2; continue
        out.append(c)
        i += 1
    return "".join(out)


def _get_prop(lines: list[str], key: str) -> str | None:
    """Return the value of an iCal property (first match in VEVENT)."""
    inside_vevent = False
    for ln in lines:
        if ln.startswith("BEGIN:VEVENT"):
            inside_vevent = True
        elif ln.startswith("END:VEVENT"):
            inside_vevent = False
        elif inside_vevent:
            # KEY[;params]:value
            colon = ln.find(":")
            semi = ln.find(";")
            if colon == -1:
                continue
            name_end = colon if (semi == -1 or semi > colon) else semi
            if ln[:name_end].upper() == key.upper():
                return ln[colon + 1:]
    return None


def _get_attendees(lines: list[str]) -> list[str]:
    """Return non-organizer attendee identifiers (mailto values) for the
    first VEVENT in the calendar."""
    inside_vevent = False
    result: list[str] = []
    for ln in lines:
        if ln.startswith("BEGIN:VEVENT"):
            inside_vevent = True
        elif ln.startswith("END:VEVENT"):
            break
        elif inside_vevent:
            u = ln.upper()
            if u.startswith("ATTENDEE"):
                colon = ln.find(":")
                if colon != -1:
                    result.append(ln[colon + 1:].strip())
    return result


def _replace_prop_in_vevent(ics: str, key: str, new_value: str) -> str:
    """Replace the first `KEY[;params]:value` line inside the first
    VEVENT block with `KEY:<folded, escaped new_value>`. Preserves
    every other line verbatim. Returns CRLF-joined output.
    """
    lines = _unfold(ics)
    replaced = False
    inside_vevent = False
    out: list[str] = []
    key_upper = key.upper()
    encoded = _fold(f"{key}:{_escape_text(new_value)}")
    for ln in lines:
        if ln.startswith("BEGIN:VEVENT"):
            inside_vevent = True
            out.append(ln)
            continue
        if ln.startswith("END:VEVENT"):
            if inside_vevent and not replaced:
                # Property didn't exist: insert before END:VEVENT.
                out.append(encoded)
                replaced = True
            inside_vevent = False
            out.append(ln)
            continue
        if inside_vevent and not replaced:
            colon = ln.find(":")
            semi = ln.find(";")
            if colon != -1:
                name_end = colon if (semi == -1 or semi > colon) else semi
                if ln[:name_end].upper() == key_upper:
                    out.append(encoded)
                    replaced = True
                    continue
        out.append(ln)
    # RFC 5545 requires CRLF line endings.
    return "\r\n".join(out)


# ── Public client ──────────────────────────────────────────────────────


class ICloudCalDAV:
    def __init__(self, user: str, password: str, base_url: str = BASE_URL):
        if not user or not password:
            raise CalDAVError("MIKAI_ICLOUD_USER and MIKAI_ICLOUD_APP_PASSWORD "
                              "must be set (app-specific password).")
        self.user = user
        self.password = password
        self.base_url = base_url.rstrip("/")

    def _req(self, method: str, url: str, body: bytes | None = None,
             extra_headers: dict | None = None) -> tuple[int, dict, bytes]:
        return _request(method, url, self.user, self.password,
                        body=body, headers=extra_headers)

    def discover_principal(self) -> str:
        """Return absolute URL of the current user's principal resource."""
        headers = {"Depth": "0", "Content-Type": "application/xml; charset=utf-8"}
        _, _, body = self._req("PROPFIND", self.base_url + "/",
                               body=_PROPFIND_PRINCIPAL, extra_headers=headers)
        root = ET.fromstring(body)
        href = root.find(".//d:current-user-principal/d:href", NSMAP)
        if href is None or not href.text:
            raise CalDAVError("no current-user-principal in PROPFIND response")
        return _absolute(href.text.strip(), self.base_url)

    def discover_home_set(self, principal_url: str) -> str:
        headers = {"Depth": "0", "Content-Type": "application/xml; charset=utf-8"}
        _, _, body = self._req("PROPFIND", principal_url,
                               body=_PROPFIND_HOMESET, extra_headers=headers)
        root = ET.fromstring(body)
        href = root.find(".//c:calendar-home-set/d:href", NSMAP)
        if href is None or not href.text:
            raise CalDAVError("no calendar-home-set in PROPFIND response")
        return _absolute(href.text.strip(), principal_url)

    def list_calendars(self, home_url: str) -> list[Calendar]:
        headers = {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"}
        _, _, body = self._req("PROPFIND", home_url,
                               body=_PROPFIND_CALENDARS, extra_headers=headers)
        root = ET.fromstring(body)
        out: list[Calendar] = []
        for resp in root.findall(".//d:response", NSMAP):
            href_el = resp.find("d:href", NSMAP)
            if href_el is None or not href_el.text:
                continue
            href = _absolute(href_el.text.strip(), home_url)
            # Only accept collections whose resourcetype includes <calendar/>.
            rtype = resp.find(".//d:resourcetype", NSMAP)
            is_cal = rtype is not None and rtype.find("c:calendar", NSMAP) is not None
            if not is_cal:
                continue
            name_el = resp.find(".//d:displayname", NSMAP)
            name = (name_el.text.strip() if (name_el is not None and name_el.text) else "")
            out.append(Calendar(href=href, displayname=name))
        return out

    def list_events(self, calendar: Calendar, start: datetime, end: datetime,
                    sole_attendee_only: bool = True) -> list[Event]:
        """REPORT calendar-query for events in [start, end). Optionally
        filter to events with no attendees other than the organizer.
        """
        headers = {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"}
        body = _report_time_range(start, end)
        _, _, xml = self._req("REPORT", calendar.href, body=body, extra_headers=headers)
        root = ET.fromstring(xml)
        events: list[Event] = []
        for resp in root.findall(".//d:response", NSMAP):
            href_el = resp.find("d:href", NSMAP)
            etag_el = resp.find(".//d:getetag", NSMAP)
            data_el = resp.find(".//c:calendar-data", NSMAP)
            if href_el is None or data_el is None or not data_el.text:
                continue
            event_href = _absolute(href_el.text.strip(), calendar.href)
            etag = (etag_el.text.strip().strip('"') if (etag_el is not None and etag_el.text) else "")
            raw = data_el.text
            lines = _unfold(raw)
            uid = _get_prop(lines, "UID") or ""
            summary = _unescape_text(_get_prop(lines, "SUMMARY") or "")
            desc = _unescape_text(_get_prop(lines, "DESCRIPTION") or "")
            dtstart = _get_prop(lines, "DTSTART") or ""
            dtend = _get_prop(lines, "DTEND") or ""
            attendees = _get_attendees(lines)
            if sole_attendee_only and attendees:
                # Any ATTENDEE line means it's shared / invited — skip.
                continue
            events.append(Event(
                calendar_href=calendar.href, event_href=event_href, etag=etag,
                uid=uid, title=summary, description=desc,
                dtstart=dtstart, dtend=dtend,
                attendees=attendees, raw_ics=raw,
            ))
        return events

    def patch_event(self, event: Event, new_title: str, new_description: str) -> str:
        """Rewrite SUMMARY and DESCRIPTION on the event's VEVENT block,
        PUT the resulting VCALENDAR back with If-Match: <etag>. Returns
        the new etag (or empty string if the server didn't send one).
        Raises CalDAVError on 412 (precondition failed = etag drifted)
        so the caller can refetch and retry.
        """
        new_ics = _replace_prop_in_vevent(event.raw_ics, "SUMMARY", new_title)
        new_ics = _replace_prop_in_vevent(new_ics, "DESCRIPTION", new_description)
        # Bump LAST-MODIFIED and DTSTAMP so clients see the change.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        new_ics = _replace_prop_in_vevent(new_ics, "LAST-MODIFIED", stamp)
        new_ics = _replace_prop_in_vevent(new_ics, "DTSTAMP", stamp)
        headers = {
            "Content-Type": "text/calendar; charset=utf-8",
        }
        if event.etag:
            headers["If-Match"] = f'"{event.etag}"' if not event.etag.startswith('"') else event.etag
        status, resp_headers, _ = self._req(
            "PUT", event.event_href, body=new_ics.encode("utf-8"), extra_headers=headers
        )
        if status not in (200, 201, 204):
            raise CalDAVError(f"PUT returned status {status}")
        return resp_headers.get("ETag", resp_headers.get("Etag", "")).strip().strip('"')

    # High-level convenience ────────────────────────────────────────────

    def todays_events(self, sole_attendee_only: bool = True) -> list[Event]:
        """Discover-then-list-then-filter: end-to-end fetch of today's
        events across every calendar in the user's home set.
        """
        principal = self.discover_principal()
        home = self.discover_home_set(principal)
        cals = self.list_calendars(home)
        tz_local = datetime.now().astimezone().tzinfo
        today = datetime.now(tz_local).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        events: list[Event] = []
        for cal in cals:
            try:
                events.extend(self.list_events(
                    cal, today.astimezone(timezone.utc), tomorrow.astimezone(timezone.utc),
                    sole_attendee_only=sole_attendee_only,
                ))
            except CalDAVError:
                # A single calendar failure shouldn't tank the whole planner tick.
                continue
        return events


# ── CLI (diagnostic) ───────────────────────────────────────────────────


def _main() -> int:
    import argparse
    import os
    import sys

    ap = argparse.ArgumentParser(description="iCloud CalDAV diagnostic")
    ap.add_argument("--list-calendars", action="store_true")
    ap.add_argument("--list-today", action="store_true")
    ap.add_argument("--include-shared", action="store_true",
                    help="Include events with other attendees (default: sole-attendee only)")
    args = ap.parse_args()

    user = os.environ.get("MIKAI_ICLOUD_USER", "")
    pw = os.environ.get("MIKAI_ICLOUD_APP_PASSWORD", "")
    if not user or not pw:
        print("Set MIKAI_ICLOUD_USER and MIKAI_ICLOUD_APP_PASSWORD first.", file=sys.stderr)
        return 2

    client = ICloudCalDAV(user, pw)

    if args.list_calendars:
        principal = client.discover_principal()
        home = client.discover_home_set(principal)
        print(f"principal: {principal}")
        print(f"home:      {home}")
        for cal in client.list_calendars(home):
            print(f"  {cal.displayname:<30} {cal.href}")
        return 0

    if args.list_today:
        events = client.todays_events(sole_attendee_only=not args.include_shared)
        if not events:
            print("(no matching events today)")
            return 0
        for e in events:
            print(f"[{e.dtstart} → {e.dtend}] {e.title!r}")
            print(f"  uid={e.uid}")
            print(f"  href={e.event_href}")
            if e.attendees:
                print(f"  attendees={e.attendees}")
            if e.description:
                preview = e.description[:120].replace("\n", " ⏎ ")
                print(f"  desc={preview!r}{'…' if len(e.description) > 120 else ''}")
            print()
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())

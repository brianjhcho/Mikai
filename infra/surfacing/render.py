"""HTML render — monospace, text-first, `git log` aesthetic.

Cream background, ink text, warm hue for overdue/stalled, cool hue for
acting. No JavaScript except a hard-refresh button (`location.reload()`).
Zero external assets — the file opens correctly from `file://`.
"""

from __future__ import annotations

import html
from typing import Iterable


# ── color-token constants (source of truth for the palette) ──────────────
_CREAM = "#F5F3EE"
_INK = "#1B2430"
_MUTED = "#6C7684"
_RULE = "#D9D4C7"
_WARM = "#D4816F"   # overdue, stalled
_COOL = "#5EBFA9"   # acting


def _e(x) -> str:
    """Escape for HTML text content. `None` renders as an em-dash."""
    if x is None or x == "":
        return "—"
    return html.escape(str(x))


def _tone_for_state(state: str) -> str:
    """Inline-style color for a state token in a state cell."""
    if state in ("stalled",):
        return _WARM
    if state == "acting":
        return _COOL
    return _MUTED


def _tone_for_kind(kind: str) -> str:
    if kind in ("stall", "overdue"):
        return _WARM
    if kind == "transition":
        return _COOL
    return _MUTED


def _tone_for_response(resp: str) -> str:
    if resp == "acted":
        return _COOL
    if resp in ("dismissed", "ignored"):
        return _MUTED
    if resp == "pending":
        return _WARM
    return _INK


_CSS = f"""
  :root {{ color-scheme: light; }}
  body {{
    background: {_CREAM};
    color: {_INK};
    font-family: "SF Mono","Menlo","Consolas",ui-monospace,monospace;
    font-size: 13px;
    line-height: 1.55;
    margin: 0;
    padding: 32px 40px 80px;
    max-width: 1080px;
  }}
  header {{ margin-bottom: 28px; }}
  h1 {{
    font-family: "New York","Iowan Old Style","Georgia",serif;
    font-size: 20px;
    font-weight: 500;
    margin: 0 0 4px;
    letter-spacing: -0.01em;
  }}
  .stamp {{ color: {_MUTED}; font-size: 12px; }}
  .stamp button {{
    font-family: inherit; font-size: 11px;
    background: transparent; border: 1px solid {_RULE};
    color: {_MUTED}; padding: 2px 8px; margin-left: 8px;
    cursor: pointer; border-radius: 2px;
  }}
  .stamp button:hover {{ color: {_INK}; border-color: {_INK}; }}

  section {{ margin: 30px 0; }}
  section > h2 {{
    font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.12em; color: {_MUTED};
    margin: 0 0 10px; padding-bottom: 4px;
    border-bottom: 1px solid {_RULE};
  }}

  .head-line {{
    font-family: "New York","Iowan Old Style","Georgia",serif;
    font-size: 22px; line-height: 1.35; margin: 6px 0 4px;
    letter-spacing: -0.01em;
  }}
  .head-line .slug {{ font-family: inherit; }}
  .head-meta {{ color: {_MUTED}; font-size: 12px; }}
  .head-quiet {{
    font-family: "New York","Iowan Old Style","Georgia",serif;
    font-size: 18px; color: {_MUTED}; font-style: italic;
  }}

  table {{
    border-collapse: collapse; width: 100%;
    font-size: 12.5px;
  }}
  th, td {{
    text-align: left; padding: 4px 12px 4px 0;
    vertical-align: top; white-space: pre;
  }}
  th {{
    color: {_MUTED}; font-weight: 500;
    border-bottom: 1px dotted {_RULE};
    padding-bottom: 6px;
  }}
  td.wrap, th.wrap {{ white-space: normal; }}
  td.num {{ text-align: right; padding-right: 20px; width: 5ch; }}
  tbody tr td {{ border-bottom: 1px dotted {_RULE}; }}
  tbody tr:last-child td {{ border-bottom: none; }}

  .muted {{ color: {_MUTED}; }}
  .warm  {{ color: {_WARM}; }}
  .cool  {{ color: {_COOL}; }}

  .empty {{
    color: {_MUTED}; font-style: italic; padding: 6px 0;
  }}
  .quiet-list {{
    color: {_MUTED}; font-size: 12px; padding: 4px 0;
  }}
  .quiet-list .item {{ margin-right: 18px; display: inline-block; }}
"""


# ── section renderers ────────────────────────────────────────────────────


def _render_head(head: dict | None) -> str:
    if head is None:
        return (
            '<div class="head-quiet">All quiet. L4 is owed nothing right now.</div>'
        )
    reason = head.get("reason") or ""
    state = head.get("state") or ""
    nxt = head.get("next_step") or "—"
    slug = head.get("slug") or "?"
    title = head.get("title") or slug
    state_tone = _tone_for_state(state)
    parts = [
        f'<span class="slug muted">{_e(slug)}</span>',
        f'<span style="color:{state_tone}">{_e(state.upper())}</span>',
    ]
    if reason:
        parts.append(f'<span class="warm">{_e(reason)}</span>')
    meta = " · ".join(parts)
    return (
        f'<div class="head-line">{_e(title)}</div>'
        f'<div class="head-meta">{meta}</div>'
        f'<div class="head-meta" style="margin-top:6px">'
        f'  next → <span style="color:{_INK}">{_e(nxt)}</span></div>'
    )


def _render_scored(scored: list[dict]) -> str:
    if not scored:
        return '<div class="empty">Nothing scored above zero.</div>'
    rows = []
    for r in scored:
        rows.append(
            "<tr>"
            f'<td class="num">{int(r["score"])}</td>'
            f'<td>{_e(r["slug"])}</td>'
            f'<td class="warm wrap">{_e(r["reason"])}</td>'
            f'<td class="wrap">{_e(r["next_step"])}</td>'
            "</tr>"
        )
    return (
        '<table>'
        '<thead><tr>'
        '<th class="num">score</th>'
        '<th>slug</th>'
        '<th class="wrap">reason</th>'
        '<th class="wrap">next step</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
    )


def _render_deliveries(rows: list[dict]) -> str:
    if not rows:
        return '<div class="empty">No delivery events yet.</div>'
    body = []
    for r in rows:
        body.append(
            "<tr>"
            f'<td class="muted">{_e(r["ts"])}</td>'
            f'<td>{_e(r["thread"])}</td>'
            f'<td style="color:{_tone_for_kind(r["kind"])}">{_e(r["kind"])}</td>'
            f'<td style="color:{_tone_for_response(r["response"])}">{_e(r["response"])}</td>'
            f'<td class="wrap muted">{_e(r["note"])}</td>'
            "</tr>"
        )
    return (
        '<table>'
        '<thead><tr>'
        '<th>ts</th><th>thread</th><th>kind</th><th>response</th>'
        '<th class="wrap">note</th>'
        '</tr></thead>'
        f'<tbody>{"".join(body)}</tbody>'
        '</table>'
    )


def _render_transitions(rows: list[dict]) -> str:
    if not rows:
        return '<div class="empty">No state transitions recorded.</div>'
    body = []
    for r in rows:
        arrow = f'{_e(r["from"])} → {_e(r["to"])}'
        body.append(
            "<tr>"
            f'<td class="muted">{_e(r["date"])}</td>'
            f'<td>{_e(r["slug"])}</td>'
            f'<td class="cool">{arrow}</td>'
            f'<td class="wrap muted">{_e(r["note"])}</td>'
            "</tr>"
        )
    return (
        '<table>'
        '<thead><tr>'
        '<th>date</th><th>thread</th><th>transition</th>'
        '<th class="wrap">note</th>'
        '</tr></thead>'
        f'<tbody>{"".join(body)}</tbody>'
        '</table>'
    )


def _render_ticks(ticks: list[dict], fallback: list[dict]) -> str:
    """Attention Engine ticks (or standup fallback with a byline)."""
    rows = ticks or fallback
    byline = "" if ticks else (
        '<div class="muted" style="margin-bottom:6px; font-size:11px">'
        'No `decide` mode ticks recorded. Showing `standup` — today\'s '
        'surface-engine heartbeat.</div>'
    )
    if not rows:
        return '<div class="empty">No engine ticks logged.</div>'
    body = []
    for r in rows:
        body.append(
            "<tr>"
            f'<td class="muted">{_e(r["ts"])}</td>'
            f'<td>{_e(r["mode"])}</td>'
            f'<td class="num">{r["surfaced"]}</td>'
            f'<td class="num">{r["acted"]}</td>'
            f'<td class="num">{r["dismissed"]}</td>'
            f'<td class="wrap muted">{_e(r["did"])}</td>'
            "</tr>"
        )
    return byline + (
        '<table>'
        '<thead><tr>'
        '<th>ts</th><th>mode</th>'
        '<th class="num">surf</th>'
        '<th class="num">act</th>'
        '<th class="num">dism</th>'
        '<th class="wrap">summary</th>'
        '</tr></thead>'
        f'<tbody>{"".join(body)}</tbody>'
        '</table>'
    )


def _render_quiet(quiet: list[dict]) -> str:
    if not quiet:
        return '<div class="empty">Everything active is being surfaced.</div>'
    items = []
    for q in quiet:
        state = q.get("state") or ""
        la = q.get("last_activity") or ""
        items.append(
            f'<span class="item">{_e(q["slug"])} '
            f'<span class="muted">({_e(state)}'
            + (f", last {_e(la)}" if la else "")
            + ")</span></span>"
        )
    return '<div class="quiet-list">' + "".join(items) + "</div>"


# ── top-level ────────────────────────────────────────────────────────────


def render_html(view: dict) -> str:
    att = view["attention"]
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        "<title>MIKAI surfacing</title>",
        f"<style>{_CSS}</style>",
        "</head><body>",
        "<header>",
        "<h1>What L4 is surfacing</h1>",
        '<div class="stamp">',
        f'as of {_e(view["generated_at_human"])}',
        '<button onclick="location.reload()">refresh</button>',
        "</div>",
        "</header>",

        '<section id="attention-head">',
        "<h2>Attention head</h2>",
        _render_head(att["head"]),
        "</section>",

        '<section id="scored">',
        "<h2>Also scoring above zero</h2>",
        _render_scored(att["scored"]),
        "</section>",

        '<section id="deliveries">',
        "<h2>Recent deliveries (Sumimasen ledger)</h2>",
        _render_deliveries(view["deliveries"]),
        "</section>",

        '<section id="transitions">',
        "<h2>Recent state transitions</h2>",
        _render_transitions(view["transitions"]),
        "</section>",

        '<section id="engine">',
        "<h2>Attention Engine — last ticks</h2>",
        _render_ticks(view["engine_ticks"], view["standup_ticks"]),
        "</section>",

        '<section id="quiet">',
        "<h2>What MIKAI is choosing to be silent about</h2>",
        _render_quiet(att["quiet"]),
        "</section>",

        "</body></html>",
    ]
    return "\n".join(parts) + "\n"

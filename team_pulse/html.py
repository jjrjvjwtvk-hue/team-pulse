"""Self-contained HTML pages: the board (a wall-planner grid) and a styled table for other reports."""

from __future__ import annotations

from datetime import date, datetime
from html import escape

from .models import Event
from .output import _cell
from .reports import Context, Report

FONTS = (
    "https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700"
    "&family=Big+Shoulders+Display:wght@600;800&family=IBM+Plex+Mono:wght@400;500&display=swap"
)

CSS = """
:root {
  --board: #EEF1EF; --panel: #F8FAF9; --ink: #17233B; --muted: #5A6577;
  --rule: #C6CFCC; --weekend: #E2E7E5; --tape: #2F5FD0; --tape-ink: #FFFFFF;
  --busy: #C9372C; --today: #E3EBFB;
  --display: "Big Shoulders Display", "Arial Narrow", sans-serif;
  --body: "Atkinson Hyperlegible", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, monospace;
  --col: 3.25rem; --name: 11rem;
}
@media (prefers-color-scheme: dark) {
  :root {
    --board: #121A2B; --panel: #18223A; --ink: #E7ECF3; --muted: #9AA6B8;
    --rule: #2D3A55; --weekend: #1B263F; --tape: #5C86F0; --tape-ink: #0D1424;
    --busy: #FF6B5C; --today: #1F2D52;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--board); color: var(--ink);
  font: 400 15px/1.45 var(--body);
}
main { max-width: 1200px; margin: 0 auto; padding: 40px 24px 56px; }
header { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 4px 24px; }
h1 {
  margin: 0; font: 800 clamp(2.5rem, 7vw, 4.25rem)/0.95 var(--display);
  text-transform: uppercase; letter-spacing: 0.01em;
}
.range { font: 600 clamp(1.25rem, 3vw, 1.75rem)/1.1 var(--display); text-transform: uppercase; color: var(--muted); }
.summary { margin: 12px 0 28px; color: var(--muted); }
.summary strong { color: var(--ink); }

.sheet { background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; overflow-x: auto; }
.sheet:focus-visible { outline: 3px solid var(--tape); outline-offset: 3px; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.scroll-hint { display: none; margin: 8px 0 0; font-size: 13px; color: var(--muted); }
.board.overflows .scroll-hint { display: block; }
.grid {
  display: grid; grid-template-columns: var(--name) repeat(var(--days), minmax(var(--col), 1fr));
  min-width: calc(var(--name) + var(--days) * var(--col));
}
.cell { border-left: 1px solid var(--rule); }
.weekend { background: var(--weekend); }
.name {
  position: sticky; left: 0; z-index: 2; background: var(--panel);
  padding: 10px 12px; border-right: 1px solid var(--rule); font-weight: 700;
}
.head .name { font: 500 12px/1.2 var(--mono); color: var(--muted); align-self: end; }
.day { padding: 10px 4px 8px; text-align: center; border-bottom: 2px solid var(--ink); }
.day .dow { display: block; font: 500 11px/1 var(--mono); text-transform: uppercase; color: var(--muted); }
.day .dom { display: block; font: 500 13px/1.3 var(--mono); }
.day .month { display: block; font: 500 10px/1 var(--mono); text-transform: uppercase; color: var(--muted); min-height: 10px; }
.count { display: block; margin-top: 6px; font: 800 1.6rem/1 var(--display); color: var(--muted); }
.count.zero { opacity: 0.35; }
.count.busy { color: var(--busy); }
.today { background: var(--today); }
.day.today .month { color: var(--ink); font-weight: 500; }

.row { border-bottom: 1px solid var(--rule); }
.row:last-child { border-bottom: 0; }
.lanes { display: grid; grid-template-columns: subgrid; grid-column: 2 / -1; padding: 6px 0; row-gap: 4px; position: relative; }
.lanes .cell { grid-row: 1 / -1; margin: -6px 0; }
.tape { container-type: inline-size; }
.tape > .label { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
@container (max-width: 44px) {
  .tape > .label, .tape.part > span:not(.sr) { display: none; }
}
.board.wide { --col: 2.6rem; }
.week-start { border-left: 2px solid var(--muted); }
.tape {
  position: relative; z-index: 1; margin: 0 3px; padding: 4px 8px; min-height: 32px; align-self: center;
  display: flex; align-items: center;
  background: var(--tape); color: var(--tape-ink); border-radius: 3px;
  font: 700 12px/1.2 var(--body); overflow: hidden;
  clip-path: polygon(0 4%, 2% 0, 98% 3%, 100% 0, 100% 96%, 98% 100%, 2% 97%, 0 100%);
}
.tape.part {
  background: repeating-linear-gradient(-45deg, var(--tape) 0 6px, transparent 6px 10px);
  color: var(--ink); outline: 2px solid var(--tape); outline-offset: -2px;
}
.tape.part > span {
  display: flex; flex-direction: column; min-width: 0; background: var(--panel); padding: 2px 5px; border-radius: 2px;
}
.tape.part .time { font: 500 10px/1.2 var(--mono); color: var(--muted); }
.tape.part .what { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }

.legend { display: flex; flex-wrap: wrap; gap: 8px 24px; margin-top: 16px; color: var(--muted); font-size: 13px; }
.legend i { display: inline-block; width: 28px; height: 12px; margin-right: 8px; vertical-align: -1px; border-radius: 2px; }
.legend .k-all { background: var(--tape); }
.legend .k-part { background: repeating-linear-gradient(-45deg, var(--tape) 0 4px, transparent 4px 7px); outline: 1px solid var(--tape); }
.legend b { color: var(--busy); font: 800 15px/1 var(--display); margin-right: 6px; }
.empty { padding: 48px 24px; text-align: center; color: var(--muted); }
footer { margin-top: 32px; font: 400 12px/1.5 var(--mono); color: var(--muted); }

h2 { margin: 40px 0 12px; font: 800 1.5rem/1 var(--display); text-transform: uppercase; letter-spacing: 0.02em; }
td.when { font: 400 13px/1.45 var(--mono); white-space: nowrap; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--rule); vertical-align: top; }
th { font: 500 11px/1.2 var(--mono); text-transform: uppercase; color: var(--muted); border-bottom: 2px solid var(--ink); }
td.num, th.num { font-family: var(--mono); text-align: right; }
tbody tr:last-child td { border-bottom: 0; }

@media (max-width: 640px) {
  main { padding: 24px 16px 40px; }
  :root { --name: 7.5rem; --col: 2.75rem; }
}
@media print {
  @page { size: landscape; margin: 12mm; }
  body { background: #fff; }
  main { max-width: none; padding: 0; }
  .scroll-hint { display: none !important; }
  .sheet { border-color: #999; overflow: visible; }
  .name { position: static; }
}
"""


def render_board(
    events: list[Event], ctx: Context, heading: str, people: list[str] | None = None, today: date | None = None
) -> str:
    days = ctx.all_days()
    col = {d: i for i, d in enumerate(days)}
    today = today or date.today()

    by_person: dict[str, list[Event]] = {p: [] for p in (people or [])}
    for e in events:
        for p in ctx.people(e):
            by_person.setdefault(p, []).append(e)

    out_by_day: dict[date, set[str]] = {d: set() for d in days}
    for p, evs in by_person.items():
        for e in evs:
            for d in ctx.days_in_range(e):
                if d in out_by_day:
                    out_by_day[d].add(p)

    peak = max((len(v) for v in out_by_day.values()), default=0)
    week_starts = {d for i, d in enumerate(days) if i and d.weekday() < days[i - 1].weekday()}

    parts = [f'<div class="grid head" style="--days:{len(days)}">', '<div class="name">People out</div>']
    prev_month = None
    for d in days:
        n = len(out_by_day[d])
        cls = "busy" if n == peak and peak >= 2 else ("zero" if n == 0 else "")
        month = "Today" if d == today else (d.strftime("%b") if d.month != prev_month else "")
        prev_month = d.month
        day_cls = " ".join(c for c in (
            "cell day",
            "weekend" if d.weekday() >= 5 else "",
            "week-start" if d in week_starts else "",
            "today" if d == today else "",
        ) if c)
        label = f"{d:%A %-d %B}: {n} {'person' if n == 1 else 'people'} out"
        parts.append(
            f'<div class="{day_cls}" aria-label="{label}">'
            f'<span class="month">{month}</span><span class="dow">{d:%a}</span>'
            f'<span class="dom">{d.day}</span><span class="count {cls}">{n}</span></div>'
        )
    parts.append("</div>")

    for person in sorted(by_person, key=str.casefold):
        lanes = _lanes(by_person[person], col, ctx)
        parts.append(f'<div class="grid row" style="--days:{len(days)}">')
        parts.append(f'<div class="name">{escape(person)}</div>')
        parts.append(f'<div class="lanes" style="grid-template-rows:repeat({max(len(lanes), 1)}, auto)">')
        for i, d in enumerate(days):
            extra = ((" weekend" if d.weekday() >= 5 else "") + (" week-start" if d in week_starts else "")
                     + (" today" if d == today else ""))
            parts.append(f'<div class="cell{extra}" style="grid-column:{i + 1}"></div>')
        for lane_no, segments in enumerate(lanes, start=1):
            for first, last, e in segments:
                parts.append(_tape(e, first, last, lane_no, person))
        parts.append("</div></div>")

    total_days = sum(len({d for e in evs for d in ctx.days_in_range(e)}) for evs in by_person.values())
    people_out = sum(1 for evs in by_person.values() if evs)
    if people_out:
        summary = (f"<strong>{people_out} {'person' if people_out == 1 else 'people'}</strong> out, "
                   f"<strong>{total_days} {'day' if total_days == 1 else 'days'}</strong> off in total.")
        wide = " wide" if len(days) > 12 else ""
        sheet = (f'<div class="board{wide}">'
                 f'<div class="sheet" tabindex="0" role="region" aria-label="Time off grid, {len(days)} days">'
                 f'{"".join(parts)}</div>'
                 '<p class="scroll-hint">Scroll sideways to see every day.</p></div>'
                 + _SCROLL_HINT_JS
                 + _legend(peak) + _details(by_person, ctx))
    else:
        summary = "Nobody has time off booked in this range."
        sheet = f'<div class="sheet"><p class="empty">No time off between {_fmt(ctx.start)} and {_fmt(ctx.end)}.</p></div>'

    return _page(heading, ctx, summary, sheet)


def render_table(report: Report, ctx: Context, heading: str) -> str:
    if not report.rows:
        body = '<div class="sheet"><p class="empty">No matching events.</p></div>'
        summary = ""
    else:
        numeric = [all(isinstance(r[i], (int, float)) and not isinstance(r[i], bool) for r in report.rows)
                   for i in range(len(report.columns))]
        head = "".join(f"<th>{escape(c)}</th>" for c in report.columns)
        rows = "".join(
            "<tr>" + "".join(
                f'<td class="num">{escape(_cell(v))}</td>' if numeric[i] else f"<td>{escape(_cell(v))}</td>"
                for i, v in enumerate(r)) + "</tr>"
            for r in report.rows)
        body = f'<div class="sheet"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'
        summary = f"{len(report.rows)} {'row' if len(report.rows) == 1 else 'rows'}."
    return _page(heading, ctx, summary, body)


def _lanes(events: list[Event], col: dict[date, int], ctx: Context) -> list[list[tuple[int, int, Event]]]:
    """Split events into contiguous column runs and stack overlapping ones into lanes."""
    segments = []
    for e in sorted(events, key=lambda e: (e.start, e.end)):
        cols = sorted(col[d] for d in ctx.days_in_range(e) if d in col)
        run: list[int] = []
        for c in cols:
            if run and c != run[-1] + 1:
                segments.append((run[0], run[-1], e))
                run = []
            run.append(c)
        if run:
            segments.append((run[0], run[-1], e))

    lanes: list[list[tuple[int, int, Event]]] = []
    for seg in segments:
        for lane in lanes:
            if lane[-1][1] < seg[0]:
                lane.append(seg)
                break
        else:
            lanes.append([seg])
    return lanes


def _tape(e: Event, first: int, last: int, lane: int, person: str) -> str:
    title = escape(e.title or "Time off")
    span = _fmt_span(e)
    style = f"grid-column:{first + 1} / {last + 2};grid-row:{lane}"
    if e.all_day:
        return (f'<div class="tape" style="{style}" title="{title}, {span}">'
                f'<span class="sr">{escape(person)}: </span><span class="label">{title}</span>'
                f'<span class="sr">, {span}</span></div>')
    when = f"{e.start:%H:%M}–{e.end:%H:%M}"
    return (f'<div class="tape part" style="{style}" title="{title}, {span}, {when}">'
            f'<span class="sr">{escape(person)}: </span>'
            f'<span><span class="time">{when}</span><span class="what">{title}</span></span>'
            f'<span class="sr">, {span}</span></div>')


_SCROLL_HINT_JS = """<script>
for (const b of document.querySelectorAll(".board")) {
  const s = b.querySelector(".sheet");
  const check = () => b.classList.toggle("overflows", s.scrollWidth > s.clientWidth + 1);
  addEventListener("resize", check); check();
}
</script>"""


def _details(by_person: dict[str, list[Event]], ctx: Context) -> str:
    """Every absence written out in full, so nothing is lost to a truncated strip."""
    rows = sorted(((e.start, p.casefold(), p, e) for p, evs in by_person.items() for e in evs), key=lambda r: r[:2])
    body = "".join(
        f"<tr><td>{escape(p)}</td><td class=\"when\">{_fmt_span(e, year=ctx.start.year != ctx.end.year)}"
        f"{'' if e.all_day else f'<br>{e.start:%H:%M}–{e.end:%H:%M}'}</td>"
        f"<td class=\"num\">{len(ctx.days_in_range(e))}</td><td>{escape(e.title or 'Time off')}</td></tr>"
        for _, _, p, e in rows)
    return ('<h2>Details</h2><div class="sheet"><table>'
            '<thead><tr><th>Person</th><th>When</th><th class="num">Days</th><th>What</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def _fmt_span(e: Event, year: bool = True) -> str:
    fmt = "%a %-d %b %Y" if year else "%a %-d %b"
    if e.start_date == e.end_date:
        return e.start_date.strftime(fmt)
    return f"{e.start_date.strftime(fmt)} – {e.end_date.strftime(fmt)}"


def _legend(peak: int) -> str:
    busiest = f'<span><b>{peak}</b>Busiest days, with {peak} people out</span>' if peak >= 2 else ""
    return ('<div class="legend">'
            '<span><i class="k-all"></i>All day</span>'
            '<span><i class="k-part"></i>Part of the day</span>'
            f'{busiest}</div>')


def _page(heading: str, ctx: Context, summary: str, body: str) -> str:
    weekends = "weekends shown" if ctx.include_weekends else "weekends hidden"
    generated = datetime.now().strftime("%-d %b %Y, %H:%M")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(heading)}: {_fmt_range(ctx.start, ctx.end)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}</style>
</head>
<body>
<main>
<header><h1>{escape(heading)}</h1><div class="range">{_fmt_range(ctx.start, ctx.end)}</div></header>
<p class="summary">{summary}</p>
{body}
<footer>From Teamup, {generated}. Dates are inclusive; {weekends}.</footer>
</main>
</body>
</html>
"""


def _fmt(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def _fmt_range(start: date, end: date) -> str:
    if start == end:
        return _fmt(start)
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{end.day} {end:%b %Y}"
    if start.year == end.year:
        return f"{start.day} {start:%b} – {end.day} {end:%b %Y}"
    return f"{_fmt(start)} – {_fmt(end)}"

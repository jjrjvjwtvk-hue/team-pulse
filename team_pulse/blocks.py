"""Time-block availability: what share of each work block a rep, or a group of reps, is off.

Blocks are half-open [start, end), so the minute at the boundary belongs to the next block and
there are no gaps. Sunday has no blocks.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from .models import Event
from .reports import Context, Report

WEEKDAY_BLOCKS = [("B1", time(9, 0), time(12, 30)), ("B2", time(12, 30), time(16, 0)), ("B3", time(16, 0), time(19, 30))]
SATURDAY_BLOCKS = [("B1", time(10, 0), time(12, 0)), ("B2", time(12, 0), time(14, 0))]


def blocks_for(day: date) -> list[tuple[str, time, time]]:
    if day.weekday() < 5:
        return WEEKDAY_BLOCKS
    return SATURDAY_BLOCKS if day.weekday() == 5 else []


def group_of(person: str) -> str:
    """'Bathrooms > Ed Wright' -> 'Bathrooms'."""
    return person.split(" > ", 1)[0] if " > " in person else "(ungrouped)"


def _window(block: tuple[str, time, time]) -> str:
    return f"{block[1]:%H:%M}-{block[2]:%H:%M}"


def _intervals(event: Event, day: date) -> tuple[datetime, datetime] | None:
    """The part of an event that falls on this day, or None."""
    day_start = datetime.combine(day, time(0, 0))
    if event.all_day:
        return (day_start, day_start + timedelta(days=1)) if event.start_date <= day <= event.end_date else None
    lo, hi = max(event.start, day_start), min(event.end, day_start + timedelta(days=1))
    return (lo, hi) if lo < hi else None


def person_block_fractions(events: list[Event], ctx: Context) -> dict[tuple[str, date, str], float]:
    """(person, date, block label) -> fraction of that block the person is off, 0 to 1.

    Overlapping events for the same person are merged, so double-booked time is counted once.
    """
    spans: dict[tuple[str, date], list[tuple[datetime, datetime]]] = defaultdict(list)
    for e in events:
        for person in ctx.people(e):
            for day in ctx.range_days(e):
                span = _intervals(e, day)
                if span:
                    spans[(person, day)].append(span)

    result: dict[tuple[str, date, str], float] = {}
    for (person, day), items in spans.items():
        merged: list[list[datetime]] = []
        for lo, hi in sorted(items):
            if merged and lo <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        for block in blocks_for(day):
            b_lo, b_hi = datetime.combine(day, block[1]), datetime.combine(day, block[2])
            off = sum(max(0.0, (min(hi, b_hi) - max(lo, b_lo)).total_seconds()) for lo, hi in merged)
            fraction = off / (b_hi - b_lo).total_seconds()
            if fraction > 0:
                result[(person, day, block[0])] = min(fraction, 1.0)
    return result


def _pct(x: float) -> float:
    return round(x * 100, 1)


def people_blocks_report(events: list[Event], ctx: Context) -> Report:
    fractions = person_block_fractions(events, ctx)
    rows = []
    for (person, day, label), frac in fractions.items():
        block = next(b for b in blocks_for(day) if b[0] == label)
        rows.append([day.isoformat(), day.strftime("%a"), group_of(person), person, label, _window(block), _pct(frac)])
    rows.sort(key=lambda r: (r[0], r[2], r[3], r[4]))
    return Report(["date", "weekday", "group", "person", "block", "window", "off_pct"], rows)


def group_blocks_report(events: list[Event], ctx: Context, threshold: float | None = None) -> Report:
    """Per group, day and block: the share of the group's reps' time that's off."""
    members: dict[str, set[str]] = defaultdict(set)
    for name in ctx.member_names:
        members[group_of(name)].add(name)

    fractions = person_block_fractions(events, ctx)
    off: dict[tuple[date, str, str], float] = defaultdict(float)
    people_off: dict[tuple[date, str, str], int] = defaultdict(int)
    for (person, day, label), frac in fractions.items():
        key = (day, group_of(person), label)
        off[key] += frac
        people_off[key] += 1

    rows = []
    for (day, group, label), total in off.items():
        size = len(members.get(group) or {p for (p, d, _l) in fractions if group_of(p) == group})
        block = next(b for b in blocks_for(day) if b[0] == label)
        off_pct = _pct(total / size)
        rows.append([
            day.isoformat(), day.strftime("%a"), group, label, _window(block),
            size, people_off[(day, group, label)], off_pct, _pct(1 - total / size),
            "OVER" if threshold is not None and off_pct > threshold else "",
        ])
    rows.sort(key=lambda r: (r[0], r[2], r[3]))
    return Report(["date", "weekday", "group", "block", "window", "reps", "reps_off", "off_pct", "available_pct", "flag"], rows)

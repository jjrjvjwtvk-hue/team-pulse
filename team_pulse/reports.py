"""Turn filtered events into report tables: out, coverage, totals, overlaps, changes, raw."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .models import Event

REPORTS = ("out", "coverage", "totals", "overlaps", "changes", "raw")


@dataclass
class Report:
    columns: list[str]
    rows: list[list]


@dataclass
class Context:
    start: date
    end: date
    subcalendar_names: dict[int, str]
    selected_ids: list[int]  # empty = all
    include_weekends: bool = False
    groups: dict[str, list[str]] | None = None  # for overlaps
    field_names: dict[str, str] | None = None  # field id -> display name, for raw

    def people(self, event: Event) -> list[str]:
        ids = event.subcalendar_ids
        if self.selected_ids:
            ids = [i for i in ids if i in self.selected_ids]
        return [self.subcalendar_names.get(i, f"#{i}") for i in ids]

    def days_in_range(self, event: Event) -> list[date]:
        return [d for d in event.days(self.include_weekends) if self.start <= d <= self.end]

    def all_days(self) -> list[date]:
        days, d = [], self.start
        while d <= self.end:
            if self.include_weekends or d.weekday() < 5:
                days.append(d)
            d += timedelta(days=1)
        return days


def _sorted(events: list[Event]) -> list[Event]:
    return sorted(events, key=lambda e: (e.start, e.title))


def out_report(events: list[Event], ctx: Context) -> Report:
    rows = []
    for e in _sorted(events):
        for person in ctx.people(e):
            rows.append([person, e.start_date.isoformat(), e.end_date.isoformat(),
                         len(e.days(ctx.include_weekends)), _when(e), e.title])
    rows.sort(key=lambda r: (r[1], r[0]))
    return Report(["person", "start", "end", "days", "time", "title"], rows)


def coverage_report(events: list[Event], ctx: Context) -> Report:
    out_by_day: dict[date, set[str]] = defaultdict(set)
    for e in events:
        for d in ctx.days_in_range(e):
            out_by_day[d].update(ctx.people(e))
    rows = []
    for d in ctx.all_days():
        people = sorted(out_by_day.get(d, ()))
        rows.append([d.isoformat(), d.strftime("%a"), len(people), ", ".join(people)])
    return Report(["date", "weekday", "out", "people"], rows)


def totals_report(events: list[Event], ctx: Context) -> Report:
    days: dict[str, set[date]] = defaultdict(set)
    counts: dict[str, int] = defaultdict(int)
    for e in events:
        in_range = ctx.days_in_range(e)
        for person in ctx.people(e):
            days[person].update(in_range)
            counts[person] += 1
    rows = [[p, len(days[p]), counts[p]] for p in days]
    rows.sort(key=lambda r: (-r[1], r[0]))
    return Report(["person", "days", "events"], rows)


def overlaps_report(events: list[Event], ctx: Context) -> Report:
    groups = ctx.groups or {"all": sorted(set(ctx.subcalendar_names.values()))}
    out_by_day: dict[date, set[str]] = defaultdict(set)
    for e in events:
        for d in ctx.days_in_range(e):
            out_by_day[d].update(ctx.people(e))

    rows = []
    for d in sorted(out_by_day):
        for group, members in groups.items():
            member_set = {m.casefold() for m in members}
            out = sorted(p for p in out_by_day[d] if p.casefold() in member_set)
            if len(out) >= 2:
                rows.append([d.isoformat(), d.strftime("%a"), group, len(out), ", ".join(out)])
    return Report(["date", "weekday", "group", "out", "people"], rows)


def changes_report(events: list[Event], ctx: Context, since: datetime) -> Report:
    rows = []
    for e in events:
        if e.deleted:
            change, at = "deleted", e.deleted
        elif e.created and e.created >= since:
            change, at = "created", e.created
        else:
            change, at = "edited", e.updated or e.created
        rows.append([
            at.isoformat(sep=" ", timespec="minutes") if at else "",
            change,
            ", ".join(ctx.people(e)),
            e.start_date.isoformat(),
            e.end_date.isoformat(),
            e.title,
        ])
    rows.sort(key=lambda r: r[0], reverse=True)
    return Report(["changed", "change", "person", "start", "end", "title"], rows)


def raw_report(events: list[Event], ctx: Context) -> Report:
    field_names = ctx.field_names or {}
    rows = []
    for e in _sorted(events):
        custom = {field_names.get(k, k): v for k, v in e.custom.items()}
        rows.append([
            e.id,
            e.start.isoformat(timespec="minutes"),
            e.end.isoformat(timespec="minutes"),
            e.all_day,
            ", ".join(ctx.people(e)),
            e.title,
            e.who,
            e.notes,
            custom,
        ])
    return Report(["id", "start", "end", "all_day", "subcalendars", "title", "who", "notes", "custom"], rows)


def _when(e: Event) -> str:
    if e.all_day:
        return "all day"
    return f"{e.start:%H:%M}-{e.end:%H:%M}"

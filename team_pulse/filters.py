"""Filter parsing and the filters applied locally after events come back."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

from .models import Event

PRESETS = ("today", "this-week", "next-week", "this-month", "next-month", "this-quarter", "next-30-days")


class FilterError(Exception):
    pass


# --- Date ranges -------------------------------------------------------------

def preset_range(name: str, today: date) -> tuple[date, date]:
    if name == "today":
        return today, today
    if name == "this-week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if name == "next-week":
        start = today - timedelta(days=today.weekday()) + timedelta(days=7)
        return start, start + timedelta(days=6)
    if name == "this-month":
        return today.replace(day=1), _month_end(today)
    if name == "next-month":
        first = _month_end(today) + timedelta(days=1)
        return first, _month_end(first)
    if name == "this-quarter":
        q_start_month = 3 * ((today.month - 1) // 3) + 1
        start = date(today.year, q_start_month, 1)
        return start, _month_end(date(today.year, q_start_month + 2, 1))
    if name == "next-30-days":
        return today, today + timedelta(days=29)
    raise FilterError(f"Unknown preset {name!r}. Choose from: {', '.join(PRESETS)}")


def resolve_range(date_from: str | None, date_to: str | None, preset: str | None, today: date) -> tuple[date, date]:
    if preset and (date_from or date_to):
        raise FilterError("Use either --preset or --from/--to, not both.")
    if preset:
        return preset_range(preset, today)
    start = _parse_date(date_from, "--from") if date_from else today
    end = _parse_date(date_to, "--to") if date_to else start
    if end < start:
        raise FilterError("--to is before --from.")
    return start, end


def _parse_date(value: str, flag: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise FilterError(f"{flag} must be YYYY-MM-DD, got {value!r}.") from None


def _month_end(d: date) -> date:
    nxt = d.replace(day=28) + timedelta(days=4)
    return nxt - timedelta(days=nxt.day)


# --- Sub-calendars and groups -----------------------------------------------

def load_groups(path: str | Path = "groups.yml") -> dict[str, list[str]]:
    path = Path(path)
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict) or not all(isinstance(v, list) for v in data.values()):
        raise FilterError(f"{path} must map each group name to a list of sub-calendar names.")
    return {str(k): [str(n) for n in v] for k, v in data.items()}


def resolve_subcalendars(
    names: list[str],
    group_names: list[str],
    groups: dict[str, list[str]],
    subcalendars: list[dict],
) -> tuple[list[int], list[str]]:
    """Map --who and --group to sub-calendar ids.

    Returns (ids, leftover_who). A --who that isn't a sub-calendar name is kept
    as a leftover and matched against each event's "who" field instead.
    """
    by_name = {s["name"].casefold(): int(s["id"]) for s in subcalendars}
    ids: list[int] = []
    leftover: list[str] = []

    for g in group_names:
        if g not in groups:
            known = ", ".join(sorted(groups)) or "none defined (create groups.yml)"
            raise FilterError(f"Unknown group {g!r}. Known groups: {known}")
        for member in groups[g]:
            sid = by_name.get(member.casefold())
            if sid is None:
                raise FilterError(f"Group {g!r} lists {member!r}, which isn't a sub-calendar your key can see.")
            ids.append(sid)

    for n in names:
        sid = by_name.get(n.casefold())
        if sid is None:
            leftover.append(n)
        else:
            ids.append(sid)

    return list(dict.fromkeys(ids)), leftover


# --- Custom fields -----------------------------------------------------------

@dataclass
class FieldDef:
    id: str
    name: str
    choices: dict[str, str] = field(default_factory=dict)  # option name (casefolded) -> option id
    option_names: list[str] = field(default_factory=list)


def field_definitions(configuration: dict) -> list[FieldDef]:
    raw = configuration.get("fields") or configuration.get("field_definitions") or []
    defs = []
    for f in raw:
        type_data = f.get("type_data") or {}
        options = f.get("choices") or type_data.get("choices") or f.get("options") or type_data.get("options") or []
        name = f.get("name")
        if isinstance(name, dict):  # localised names
            name = next(iter(name.values()), "")
        defs.append(FieldDef(
            id=str(f.get("id")),
            name=str(name or f.get("id")),
            choices={_option_name(o).casefold(): str(o.get("id")) for o in options if isinstance(o, dict)},
            option_names=[_option_name(o) for o in options if isinstance(o, dict)],
        ))
    return defs


def _option_name(option: dict) -> str:
    name = option.get("name") or ""
    if isinstance(name, dict):
        name = next(iter(name.values()), "")
    return str(name)


@dataclass
class FieldMatch:
    field_id: str
    value: str
    option_id: str | None


def parse_field_filters(specs: list[str], defs: list[FieldDef]) -> list[FieldMatch]:
    by_name = {d.name.casefold(): d for d in defs}
    matches = []
    for spec in specs:
        if "=" not in spec:
            raise FilterError(f"--field must look like Name=Value, got {spec!r}.")
        name, value = (part.strip() for part in spec.split("=", 1))
        d = by_name.get(name.casefold())
        if d is None:
            known = ", ".join(x.name for x in defs) or "none"
            raise FilterError(f"Unknown custom field {name!r}. Known fields: {known}")
        option_id = None
        if d.choices:
            option_id = d.choices.get(value.casefold())
            if option_id is None:
                raise FilterError(f"{d.name!r} has no option {value!r}.")
        matches.append(FieldMatch(d.id, value, option_id))
    return matches


def _field_matches(event: Event, m: FieldMatch) -> bool:
    stored = event.custom.get(m.field_id)
    if stored is None:
        return False
    values = stored if isinstance(stored, list) else [stored]
    if m.option_id is not None:
        return m.option_id in {str(v) for v in values}
    needle = m.value.casefold()
    return any(needle == _strip_html(str(v)).strip().casefold() for v in values)


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


# --- Local filtering ---------------------------------------------------------

@dataclass
class LocalFilters:
    who_text: list[str] = field(default_factory=list)
    fields: list[FieldMatch] = field(default_factory=list)
    min_days: int | None = None
    all_day: bool | None = None  # None = both, True = all-day only, False = timed only
    include_weekends: bool = False

    def matches(self, event: Event) -> bool:
        if self.all_day is not None and event.all_day != self.all_day:
            return False
        if self.min_days is not None and len(event.days(self.include_weekends)) < self.min_days:
            return False
        if self.who_text:
            who = event.who.casefold()
            if not any(w.casefold() in who for w in self.who_text):
                return False
        return all(_field_matches(event, m) for m in self.fields)

    def apply(self, events: list[Event]) -> list[Event]:
        return [e for e in events if self.matches(e)]

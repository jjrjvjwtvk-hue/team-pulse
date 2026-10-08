"""Event and sub-calendar data, normalised from Teamup's JSON."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass
class Event:
    id: str
    title: str
    start: datetime
    end: datetime
    all_day: bool
    subcalendar_ids: list[int]
    who: str = ""
    notes: str = ""
    custom: dict = field(default_factory=dict)
    created: datetime | None = None
    updated: datetime | None = None
    deleted: datetime | None = None
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict, tz: str | None = None) -> "Event":
        ids = data.get("subcalendar_ids") or []
        if not ids and data.get("subcalendar_id") is not None:
            ids = [data["subcalendar_id"]]
        all_day = bool(data.get("all_day"))
        return cls(
            id=str(data.get("id", "")),
            title=data.get("title") or "",
            start=_parse_dt(data["start_dt"], tz, all_day),
            end=_parse_dt(data["end_dt"], tz, all_day),
            all_day=all_day,
            subcalendar_ids=[int(i) for i in ids],
            who=data.get("who") or "",
            notes=data.get("notes") or "",
            custom=data.get("custom") or {},
            created=_parse_optional(data.get("creation_dt"), tz),
            updated=_parse_optional(data.get("update_dt"), tz),
            deleted=_parse_optional(data.get("delete_dt"), tz),
            raw=data,
        )

    @property
    def start_date(self) -> date:
        return self.start.date()

    @property
    def end_date(self) -> date:
        """Last calendar day the event covers (inclusive)."""
        end = self.end
        # An end exactly at midnight means the event finished at the end of the previous day.
        if end.time() == time(0, 0) and end > self.start:
            end -= timedelta(seconds=1)
        return max(end.date(), self.start.date())

    def days(self, include_weekends: bool = True) -> list[date]:
        result = []
        d = self.start_date
        while d <= self.end_date:
            if include_weekends or d.weekday() < 5:
                result.append(d)
            d += timedelta(days=1)
        return result


def _parse_dt(value: str, tz: str | None, all_day: bool) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if all_day:
        # All-day events are calendar dates. Don't shift them across time zones.
        return dt.replace(tzinfo=None)
    if dt.tzinfo is not None and tz:
        dt = dt.astimezone(ZoneInfo(tz))
    return dt.replace(tzinfo=None)


def _parse_optional(value: str | None, tz: str | None) -> datetime | None:
    return _parse_dt(value, tz, all_day=False) if value else None

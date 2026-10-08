"""Command-line entry point: check, subcalendars, fields, report."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import html, output, reports
from .client import TeamupClient, TeamupError
from .config import ConfigError, load_settings
from .filters import (
    PRESETS,
    FilterError,
    LocalFilters,
    field_definitions,
    load_groups,
    parse_field_filters,
    resolve_range,
    resolve_subcalendars,
)
from .models import Event

STATE_FILE = Path(".team_pulse_state.json")
MAX_CHANGE_DAYS = 30


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="team_pulse", description="Read-only time-off reports from Teamup.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Verify credentials and show what the key can see")
    sub.add_parser("subcalendars", help="List sub-calendars")
    sub.add_parser("fields", help="List custom event fields and their options")

    rep = sub.add_parser("report", help="Run a report")
    rep.add_argument("kind", choices=reports.REPORTS)
    rep.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD")
    rep.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD")
    rep.add_argument("--preset", choices=PRESETS)
    rep.add_argument("--who", action="append", default=[], help="Person or sub-calendar name (repeatable)")
    rep.add_argument("--group", action="append", default=[], help="Group from groups.yml (repeatable)")
    rep.add_argument("--field", action="append", default=[], metavar="NAME=VALUE", help="Custom field match (repeatable)")
    rep.add_argument("--search", help="Keyword search, run by Teamup (2-100 characters)")
    rep.add_argument("--min-days", type=int, help="Only absences of at least N days")
    all_day = rep.add_mutually_exclusive_group()
    all_day.add_argument("--include-all-day", dest="all_day", action="store_const", const=True,
                         help="Only all-day events")
    all_day.add_argument("--exclude-all-day", dest="all_day", action="store_const", const=False,
                         help="Only timed events")
    rep.add_argument("--include-weekends", action="store_true",
                     help="Count Saturdays and Sundays as days off (default: weekdays only)")
    rep.add_argument("--since", default="last",
                     help="For 'changes': 7d, 24h, YYYY-MM-DD, or 'last' (since the previous run; default)")
    rep.add_argument("--groups-file", default="groups.yml")
    rep.add_argument("--format", choices=output.FORMATS, default="table")
    rep.add_argument("--out", metavar="FILE", help="Write to a file instead of the terminal")
    return parser


def main(argv: list[str] | None = None, client: TeamupClient | None = None, today: date | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        tz = None
        if client is None:
            settings = load_settings()
            tz = settings.timezone
            client = TeamupClient(settings)
        else:
            tz = client.settings.timezone
        today = today or (datetime.now(ZoneInfo(tz)).date() if tz else date.today())

        if args.command == "check":
            print(cmd_check(client))
        elif args.command == "subcalendars":
            print(cmd_subcalendars(client))
        elif args.command == "fields":
            print(cmd_fields(client))
        elif args.command == "report":
            text = cmd_report(args, client, tz, today)
            if args.out:
                Path(args.out).write_text(text if text.endswith("\n") else text + "\n")
                print(f"Wrote {args.out}", file=sys.stderr)
            else:
                print(text)
        return 0
    except (ConfigError, TeamupError, FilterError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def cmd_check(client: TeamupClient) -> str:
    config = client.configuration()
    subs = client.subcalendars()
    lines = ["Credentials OK."]
    name = (config.get("general_settings") or {}).get("name") or config.get("name")
    if name:
        lines.append(f"Calendar: {name}")
    history = _find_history_setting(config)
    if history:
        lines.append(f"History: {history}")
    active = [s for s in subs if s.get("active", True)]
    lines.append(f"Sub-calendars visible to this key: {len(subs)} ({len(active)} active)")
    lines += [f"  - {s['name']}" for s in sorted(subs, key=lambda s: s["name"].casefold())]
    return "\n".join(lines)


def _find_history_setting(config: dict) -> str | None:
    """The plan's history limit isn't at a documented path, so look for any key mentioning it."""
    stack = [("", config)]
    while stack:
        prefix, node = stack.pop()
        for k, v in node.items():
            if isinstance(v, dict):
                stack.append((f"{prefix}{k}.", v))
            elif "history" in k.lower() and v not in (None, ""):
                return f"{prefix}{k} = {v}"
    return None


def cmd_subcalendars(client: TeamupClient) -> str:
    subs = sorted(client.subcalendars(), key=lambda s: s["name"].casefold())
    rows = [[s["id"], s["name"], s.get("active", True)] for s in subs]
    return output.to_table(reports.Report(["id", "name", "active"], rows))


def cmd_fields(client: TeamupClient) -> str:
    defs = field_definitions(client.configuration())
    if not defs:
        return "No custom fields found in the calendar configuration."
    rows = [[d.name, d.id, ", ".join(d.option_names) or "(free text)"] for d in defs]
    return output.to_table(reports.Report(["field", "id", "options"], rows))


def cmd_report(args, client: TeamupClient, tz: str | None, today: date) -> str:
    if args.search is not None and not 2 <= len(args.search) <= 100:
        raise FilterError("--search must be 2 to 100 characters.")
    if args.min_days is not None and args.min_days < 1:
        raise FilterError("--min-days must be at least 1.")

    groups = load_groups(args.groups_file)
    subcalendars = client.subcalendars()
    selected_ids, who_text = resolve_subcalendars(args.who, args.group, groups, subcalendars)

    field_matches = []
    field_names: dict[str, str] = {}
    if args.field or args.kind == "raw":
        defs = field_definitions(client.configuration())
        field_names = {d.id: d.name for d in defs}
        field_matches = parse_field_filters(args.field, defs)

    local = LocalFilters(
        who_text=who_text,
        fields=field_matches,
        min_days=args.min_days,
        all_day=args.all_day,
        include_weekends=args.include_weekends,
    )

    if args.kind == "changes":
        return _changes(args, client, tz, today, subcalendars, selected_ids, local)

    start, end = resolve_range(args.date_from, args.date_to, args.preset, today)
    raw_events = client.events(start, end, selected_ids, args.search)
    events = local.apply([Event.from_api(e, tz) for e in raw_events if not e.get("delete_dt")])

    report_groups = None
    if args.kind == "overlaps":
        report_groups = {g: groups[g] for g in args.group} if args.group else (groups or None)

    ctx = reports.Context(
        start=start,
        end=end,
        subcalendar_names={int(s["id"]): s["name"] for s in subcalendars},
        selected_ids=selected_ids,
        include_weekends=args.include_weekends,
        groups=report_groups,
        field_names=field_names,
    )
    people = [ctx.subcalendar_names[i] for i in selected_ids if i in ctx.subcalendar_names]
    heading = reports.HEADINGS[args.kind]
    if args.kind == "board":
        if args.format == "html":
            return html.render_board(events, ctx, heading, people)
        return output.render(reports.board_report(events, ctx, people, marks=args.format == "table"), args.format)

    builders = {
        "out": reports.out_report,
        "coverage": reports.coverage_report,
        "totals": reports.totals_report,
        "overlaps": reports.overlaps_report,
        "raw": reports.raw_report,
    }
    report = builders[args.kind](events, ctx)
    if args.format == "html":
        return html.render_table(report, ctx, heading)
    return output.render(report, args.format)


def _changes(args, client, tz, today, subcalendars, selected_ids, local) -> str:
    if args.search:
        raise FilterError("--search can't be combined with the changes report.")
    if args.date_from or args.date_to or args.preset:
        raise FilterError("The changes report uses --since, not a date range.")

    now = datetime.now(ZoneInfo(tz)) if tz else datetime.now().astimezone()
    since_ts = parse_since(args.since, now)
    if since_ts < (now - timedelta(days=MAX_CHANGE_DAYS)).timestamp():
        raise FilterError(f"Teamup only keeps {MAX_CHANGE_DAYS} days of change history.")

    raw_events, server_ts = client.modified_since(since_ts)
    events = [Event.from_api(e, tz) for e in raw_events]
    if selected_ids:
        events = [e for e in events if set(e.subcalendar_ids) & set(selected_ids)]
    events = local.apply(events)

    if server_ts:
        _save_state({"last_changes_timestamp": int(server_ts)})

    since_dt = datetime.fromtimestamp(since_ts, now.tzinfo).replace(tzinfo=None)
    ctx = reports.Context(
        start=since_dt.date(),
        end=today,
        subcalendar_names={int(s["id"]): s["name"] for s in subcalendars},
        selected_ids=selected_ids,
        include_weekends=args.include_weekends,
    )
    report = reports.changes_report(events, ctx, since_dt)
    if args.format == "html":
        return html.render_table(report, ctx, reports.HEADINGS["changes"])
    return output.render(report, args.format)


def parse_since(value: str, now: datetime) -> int:
    if value == "last":
        state = _load_state()
        if "last_changes_timestamp" in state:
            return int(state["last_changes_timestamp"])
        value = "7d"
    m = re.fullmatch(r"(\d+)([dh])", value)
    if m:
        amount, unit = int(m.group(1)), m.group(2)
        delta = timedelta(days=amount) if unit == "d" else timedelta(hours=amount)
        return int((now - delta).timestamp())
    try:
        d = date.fromisoformat(value)
    except ValueError:
        raise FilterError(f"--since must be like 7d, 24h, YYYY-MM-DD or 'last', got {value!r}.") from None
    return int(datetime(d.year, d.month, d.day, tzinfo=now.tzinfo).timestamp())


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def _save_state(update: dict) -> None:
    state = _load_state()
    state.update(update)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")

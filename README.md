# team-pulse

A small command-line tool for pulling time-off reports out of Teamup, filtered however you like.

My team logs time off in a Teamup calendar. This repo turns that calendar into answers: who's out this week, who's out the same days next month, how much time someone has taken this quarter. Run it with a set of filters, get a report back as a table, CSV, or JSON.

> **Status:** Early development. The core commands and reports below are built and tested against a mocked API, but haven't been run against a live calendar yet. What's still to come is in the [Roadmap](#roadmap).

## What it does

- Pulls events from a Teamup calendar through the Teamup API
- Filters by date range, sub-calendar (person, team, or division), keyword, and custom fields
- Shows what changed recently, so you can see new and cancelled time off without rereading the calendar
- Rolls events up into the reports you'd actually look at
- Exports to the terminal, CSV, JSON, or a standalone HTML page
- Read-only. It never creates, edits, or deletes calendar events

## Requirements

- Python 3.11 or newer
- A Teamup calendar key and API key (see [Configuration](#configuration))

## Setup

```bash
git clone <this-repo-url>
cd team-pulse
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
cp groups.example.yml groups.yml   # optional
```

Then fill in `.env`.

## Configuration

Settings live in `.env` (never committed; it's in `.gitignore`).

| Variable | Required | Description |
|---|---|---|
| `TEAMUP_API_KEY` | Yes, unless a network secret supplies it | Sent with every request in the `Teamup-Token` header |
| `TEAMUP_CALENDAR_KEY` | Yes | The calendar key or ID that appears in the API path |
| `TEAMUP_TIMEZONE` | No | IANA time zone for returned dates, e.g. `America/Chicago`. Defaults to the calendar's own setting |
| `TEAMUP_BASE_URL` | No | Defaults to `https://api.teamup.com` |
| `TEAMUP_BEARER_TOKEN` | No | Only needed if your calendar key can't see everything you want. See below |

### Running in a Claude Code cloud session

In a cloud session, keep the API key out of the session entirely by storing it as a network secret. The agent proxy adds the header to requests for `api.teamup.com` after they leave the session, so the key never appears in the environment or any file. Leave `TEAMUP_API_KEY` unset and the tool sends no `Teamup-Token` header of its own.

In the environment's **Edit environment** dialog at claude.ai/code, under **Network secrets**, select **Add secret**:

- **Credential type:** Bearer (the default)
- **Name:** `Teamup`
- **Allowed websites:** `api.teamup.com`
- **Custom headers:** change the header **Name** from `Authorization` to `Teamup-Token`, clear the **Prefix**, and paste the key as the **Value**

`TEAMUP_CALENDAR_KEY` and `TEAMUP_TIMEZONE` aren't secrets the proxy can attach (the calendar key goes in the URL path), so set them as ordinary environment variables in the same dialog. Network secrets are only on Pro and Max plans.

### Key permissions

Use a key with **`read_only`** permission. This tool only reads, so it shouldn't hold a key that can write.

Don't use a `read_only_without_details` key. Teamup has a "without details" version of each permission level, which presumably hides event details such as the title and notes. The spec doesn't say which fields, so test it before relying on it. Reports built on `who` or the title could come back blank.

A key's permissions can be set per sub-calendar, and `no_access` is one of the levels. If the key can't see a sub-calendar, its events won't show up in reports, and no error tells you so. Inactive sub-calendars are only returned to keys with administrator permission.

If a calendar key doesn't have the access you need, Teamup also accepts a logged-in user's bearer token, which you get from `POST /auth/tokens` with an email and password. Put the resulting token in `TEAMUP_BEARER_TOKEN`. Don't store the password in this repo.

Check that your credentials work:

```bash
python -m team_pulse check
```

`check` loads the calendar configuration and prints the sub-calendars your key can see.

## Usage

```bash
python -m team_pulse report [filters] [--format table|csv|json|html] [--out FILE]
```

### Filters

Filters combine. An event has to match all of them to appear.

| Option | Example | Meaning |
|---|---|---|
| `--from`, `--to` | `--from 2026-10-01 --to 2026-10-31` | Date range (`YYYY-MM-DD`, inclusive) |
| `--preset` | `--preset this-week` | Shortcut: `today`, `this-week`, `next-week`, `this-month`, `next-month`, `this-quarter`, `next-30-days` |
| `--who` | `--who "Josh Ballinger"` | Person or sub-calendar name (repeatable) |
| `--group` | `--group bath` | A named set of sub-calendars defined in `groups.yml` |
| `--field` | `--field "Reason=Vacation"` | Match a custom event field by its display name and value (repeatable). Run `team_pulse fields` to list them |
| `--search` | `--search "dentist"` | Keyword search, 2 to 100 characters. Teamup runs the search, see [Search syntax](#search-syntax) |
| `--min-days` | `--min-days 3` | Only absences of at least N days |
| `--include-all-day / --exclude-all-day` | | Limit to all-day or timed events |
| `--include-weekends` | | Count Saturdays and Sundays as days off. By default only weekdays are counted |

### Reports

| Report | Command | What you get |
|---|---|---|
| Board | `report board` | A person-by-day grid of who's out. In the terminal it's a block chart; as HTML it's a wall-planner page with each absence drawn across its days and the busiest days flagged |
| Who's out | `report out` | Everyone off during the range, with dates |
| Coverage | `report coverage` | Headcount out per day, so you can see thin days at a glance |
| Totals | `report totals` | Days off per person for the range |
| Overlaps | `report overlaps` | Days when two or more people in the same group are out |
| Changes | `report changes --since 7d` | Events created, edited, or deleted since a point in time (`7d`, `24h`, `YYYY-MM-DD`, or `last`, the default, which picks up where the previous run stopped). Teamup only tracks 30 days |
| Raw | `report raw` | Every matching event, unaggregated |

### Examples

A page showing who's out over the next 30 days, to open in a browser, print, or email:

```bash
python -m team_pulse report board --preset next-30-days --format html --out board.html
```

Who's out next week?

```bash
python -m team_pulse report out --preset next-week
```

Days off per rep this quarter, saved to CSV:

```bash
python -m team_pulse report totals --preset this-quarter --group sales --format csv --out q4-time-off.csv
```

Days in the next 30 where two or more people in the same division are out:

```bash
python -m team_pulse report overlaps --preset next-30-days --group bath
```

Anything mentioning "sick" for one person, as JSON:

```bash
python -m team_pulse report raw --who "Zeke Henson" --search sick --format json
```

What changed on the calendar in the last week, including cancellations:

```bash
python -m team_pulse report changes --since 7d
```

## Groups

`groups.yml` maps a name to a list of sub-calendars, so you don't retype team rosters. It's optional and not committed; start from `groups.example.yml`.

```yaml
sales:
  - Josh Ballinger
  - Edward Wright
  - Maddy Carney
bath:
  - Josh Ballinger
  - Nathan Smith
```

Names must match the sub-calendar names in Teamup (case doesn't matter). Run `python -m team_pulse subcalendars` to list them.

## How it works

The tool calls Teamup's REST API directly:

| Purpose | Request |
|---|---|
| Events in a range | `GET /{calendarKey}/events?startDate=…&endDate=…` |
| Filter by sub-calendar | `subcalendarId[]=…` on the events request, repeated per sub-calendar |
| Keyword search | `GET /{calendarKey}/events?query=…` with the same date and sub-calendar filters, paged with `limit` and `offset` |
| What changed | `GET /{calendarKey}/events?modifiedSince=<unix timestamp>` |
| List sub-calendars | `GET /{calendarKey}/subcalendars` |
| Calendar settings and custom fields | `GET /{calendarKey}/configuration` |

Every request carries the `Teamup-Token` header, and sends `Authorization: Bearer …` too if `TEAMUP_BEARER_TOKEN` is set. Only `GET` requests are used.

Date range, sub-calendar, and keyword filters go to Teamup with the request. The rest (`--min-days`, `--field`, `--include-all-day`) are applied here after the events come back. A `--who` that doesn't match a sub-calendar name is matched against each event's "who" field instead.

**Custom fields:** an event stores custom values under each field's internal id, and choice fields store option ids, not the names you see in Teamup. The tool reads the field definitions from the `configuration` response and translates names to ids, so `--field "Reason=Vacation"` works. If a field or option is renamed in Teamup, the id stays the same and the filter keeps working.

**Recurring events:** the events endpoint evaluates recurrence rules and returns each instance inside the date range, so a weekly day off shows up as separate events. Nothing here needs to expand them.

**Multi-day events:** a Monday-to-Friday absence arrives as one event, and the tool splits it into days before counting totals, coverage, and overlaps. Days outside the requested range aren't counted, and a timed event (a two-hour appointment) counts as a day out.

**Changes:** the `modifiedSince` response includes deleted events (their `delete_dt` is set) and returns only the master event for a recurring series, not each instance. Teamup keeps at most 30 days of change history. The response carries a `timestamp`, which the tool saves to `.team_pulse_state.json` and uses as the next `--since` so nothing is missed between runs.

### Search syntax

Keyword search is handled by Teamup, not by this tool, so it follows Teamup's own [search rules](https://calendar.teamup.com/kb/searching-teamup-calendar/). Search is also paged, and the tool keeps requesting pages until it has everything.

Official reference: <https://apidocs.teamup.com>

## Project layout

```
team-pulse/
├── team_pulse/
│   ├── config.py        # Settings from .env
│   ├── client.py        # Teamup API calls (GET only)
│   ├── models.py        # Event parsing and day splitting
│   ├── filters.py       # Filter parsing and local filtering
│   ├── reports.py       # out, coverage, totals, overlaps, changes, raw
│   ├── output.py        # table, CSV, JSON writers
│   ├── html.py          # HTML pages: the board and styled tables
│   └── cli.py           # Command-line entry point
├── groups.example.yml   # Copy to groups.yml for your named sub-calendar groups
├── .env.example
├── requirements.txt
├── requirements-dev.txt
└── tests/
```

Run the tests with:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Not covered

Teamup's OpenAPI spec has data models for webhook notifications and an activity stream, but no endpoints for either. Because of that, `report changes` polls with `modifiedSince` and doesn't use push notifications. If Teamup's docs show real endpoints for those, a push-based digest would be a better fit than polling.

## Roadmap

- [x] Client, auth, and `check` command
- [x] Date-range and sub-calendar filters
- [x] `out` and `raw` reports
- [x] `totals`, `coverage`, and `overlaps` reports
- [x] `changes` report using `modifiedSince`
- [x] CSV and JSON export
- [x] `board` report and HTML export
- [x] Local filters and `groups.yml`
- [x] Verify against a live calendar: credentials, all-day end times, search paging, and the custom field layout (fixed: the API nests fields under `fields.definitions`). This calendar defines no custom fields, so `--field` is untested live
- [ ] Separate time off from meetings and partial-day entries ("Nothing after 1", "Outdoor Meeting") so `out` and `totals` stop counting them
- [ ] Weekly digest: a scheduled run that emails or posts "who's out this week"
- [ ] Time-off balances, if allowances can be stored somewhere

## Notes and limits

- Teamup's spec lists an HTTP 429 (too many requests) response for logging in and for copying a calendar, and says nothing about the events endpoints or any numeric limit. The tool still treats a 429 from any endpoint as "wait and retry" (using `Retry-After` when it's sent), but don't hammer the API in a loop.
- How far back you can look depends on your Teamup plan, which keeps a set number of months of history. `team_pulse check` prints it, taken from the configuration response.
- Reports are only as good as the calendar. If people log time off inconsistently (different titles, wrong sub-calendar, custom field left blank), keyword and field filters will miss entries. Agreeing on a naming convention with the team helps more than any code change.
- Dates are shown in `TEAMUP_TIMEZONE`. Teamup sends all-day events in UTC, so the tool treats them as calendar dates and does not shift them.
- Change history is capped at 30 days, so `report changes` can't look back further than that.

## Security

- Keep `.env` out of version control.
- Don't paste API keys into issues, logs, or screenshots.
- If a key leaks, revoke it in Teamup and issue a new one.

## License

Private repository. All rights reserved.

import json
from datetime import date

import pytest

from team_pulse import cli
from team_pulse.client import TeamupClient, TeamupError
from team_pulse.config import Settings
from team_pulse.filters import FilterError, preset_range, resolve_range
from team_pulse.models import Event

SETTINGS = Settings(api_key="k", calendar_key="cal", timezone="America/Chicago")
TODAY = date(2026, 10, 8)  # a Thursday

SUBCALENDARS = [
    {"id": 1, "name": "Alex Example", "active": True},
    {"id": 2, "name": "Sam Example", "active": True},
    {"id": 3, "name": "Jordan Example", "active": True},
]
CONFIG = {
    "general_settings": {"name": "Team Time Off"},
    "fields": [
        {"id": "f_reason", "name": "Reason", "type": "choice",
         "type_data": {"choices": [{"id": "c1", "name": "Vacation"}, {"id": "c2", "name": "Sick"}]}},
    ],
}


def ev(id, sub, start, end, title="Off", all_day=True, custom=None, **extra):
    return {"id": id, "subcalendar_ids": [sub], "start_dt": start, "end_dt": end,
            "all_day": all_day, "title": title, "who": "", "notes": "", "custom": custom or {}, **extra}


EVENTS = [
    # Mon-Fri vacation, Teamup-style all-day end at 23:59 of the last day
    ev("e1", 1, "2026-10-12T00:00:00", "2026-10-16T23:59:00", "Vacation", custom={"f_reason": ["c1"]}),
    ev("e2", 2, "2026-10-14T00:00:00", "2026-10-14T23:59:00", "Dentist", custom={"f_reason": ["c2"]}),
    ev("e3", 3, "2026-10-15T14:00:00-05:00", "2026-10-15T15:00:00-05:00", "Appointment", all_day=False),
]


class FakeClient:
    def __init__(self, events=EVENTS, changed=None):
        self.settings = SETTINGS
        self._events = events
        self._changed = changed or []
        self.calls = []

    def configuration(self):
        return CONFIG

    def subcalendars(self):
        return SUBCALENDARS

    def events(self, start, end, subcalendar_ids=(), query=None):
        self.calls.append((start, end, list(subcalendar_ids), query))
        ids = set(subcalendar_ids)
        return [e for e in self._events if not ids or ids & set(e["subcalendar_ids"])]

    def modified_since(self, since_ts):
        self.calls.append(("modified_since", since_ts))
        return self._changed, 1_800_000_000


def run(capsys, *argv, client=None):
    code = cli.main(list(argv), client=client or FakeClient(), today=TODAY)
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "STATE_FILE", tmp_path / ".team_pulse_state.json")
    (tmp_path / "groups.yml").write_text("sales:\n  - Alex Example\n  - Sam Example\n")


# --- dates -------------------------------------------------------------------

def test_presets():
    assert preset_range("this-week", TODAY) == (date(2026, 10, 5), date(2026, 10, 11))
    assert preset_range("next-week", TODAY) == (date(2026, 10, 12), date(2026, 10, 18))
    assert preset_range("next-month", TODAY) == (date(2026, 11, 1), date(2026, 11, 30))
    assert preset_range("this-quarter", TODAY) == (date(2026, 10, 1), date(2026, 12, 31))
    assert preset_range("next-30-days", TODAY) == (TODAY, date(2026, 11, 6))


def test_range_validation():
    with pytest.raises(FilterError):
        resolve_range("2026-10-10", "2026-10-01", None, TODAY)
    with pytest.raises(FilterError):
        resolve_range("2026-10-01", None, "this-week", TODAY)


def test_event_days_all_day_and_midnight_end():
    e = Event.from_api(EVENTS[0])
    assert e.end_date == date(2026, 10, 16)
    assert len(e.days()) == 5
    midnight = Event.from_api(ev("x", 1, "2026-10-17T00:00:00", "2026-10-19T00:00:00"))
    assert midnight.days(include_weekends=True) == [date(2026, 10, 17), date(2026, 10, 18)]
    assert midnight.days(include_weekends=False) == []


def test_timed_event_converted_to_timezone():
    e = Event.from_api(ev("t", 1, "2026-10-15T19:00:00Z", "2026-10-15T20:00:00Z", all_day=False), "America/Chicago")
    assert e.start.hour == 14


# --- reports -----------------------------------------------------------------

def test_out_report_json(capsys):
    code, out, _ = run(capsys, "report", "out", "--preset", "next-week", "--format", "json")
    assert code == 0
    rows = json.loads(out)
    assert [r["person"] for r in rows] == ["Alex Example", "Sam Example", "Jordan Example"]
    assert rows[0]["days"] == 5
    assert rows[2]["time"] == "14:00-15:00"


def test_group_filter_sends_subcalendar_ids(capsys):
    client = FakeClient()
    run(capsys, "report", "out", "--preset", "next-week", "--group", "sales", client=client)
    assert client.calls[0][2] == [1, 2]


def test_unknown_group_is_an_error(capsys):
    code, _, err = run(capsys, "report", "out", "--group", "nope")
    assert code == 1 and "Unknown group" in err


def test_field_filter_translates_names_to_ids(capsys):
    _, out, _ = run(capsys, "report", "out", "--preset", "next-week", "--field", "reason=vacation", "--format", "json")
    assert [r["title"] for r in json.loads(out)] == ["Vacation"]


def test_min_days_and_all_day_filters(capsys):
    _, out, _ = run(capsys, "report", "out", "--preset", "next-week", "--min-days", "2", "--format", "json")
    assert [r["person"] for r in json.loads(out)] == ["Alex Example"]
    _, out, _ = run(capsys, "report", "out", "--preset", "next-week", "--exclude-all-day", "--format", "json")
    assert [r["person"] for r in json.loads(out)] == ["Jordan Example"]


def test_totals_clip_to_range(capsys):
    _, out, _ = run(capsys, "report", "totals", "--from", "2026-10-14", "--to", "2026-10-31", "--format", "json")
    totals = {r["person"]: r["days"] for r in json.loads(out)}
    assert totals == {"Alex Example": 3, "Sam Example": 1, "Jordan Example": 1}


def test_coverage_lists_every_weekday(capsys):
    _, out, _ = run(capsys, "report", "coverage", "--preset", "next-week", "--format", "json")
    rows = json.loads(out)
    assert len(rows) == 5
    assert {r["date"]: r["out"] for r in rows}["2026-10-14"] == 2


def test_overlaps_by_group(capsys):
    _, out, _ = run(capsys, "report", "overlaps", "--preset", "next-week", "--group", "sales", "--format", "json")
    rows = json.loads(out)
    assert [(r["date"], r["people"]) for r in rows] == [("2026-10-14", "Alex Example, Sam Example")]


def test_csv_output_to_file(capsys, tmp_path):
    code, _, err = run(capsys, "report", "totals", "--preset", "next-week", "--format", "csv", "--out", "t.csv")
    assert code == 0 and "Wrote t.csv" in err
    assert (tmp_path / "t.csv").read_text().splitlines()[0] == "person,days,events"


def test_raw_report_names_custom_fields(capsys):
    _, out, _ = run(capsys, "report", "raw", "--preset", "next-week", "--format", "json")
    assert json.loads(out)[0]["custom"] == {"Reason": ["c1"]}


def test_search_length_validated(capsys):
    code, _, err = run(capsys, "report", "raw", "--search", "x")
    assert code == 1 and "2 to 100" in err


def test_changes_report_and_saved_timestamp(capsys, tmp_path):
    changed = [
        ev("n1", 1, "2026-11-02T00:00:00", "2026-11-02T23:59:00", "New",
           creation_dt="2026-10-07T10:00:00-05:00", update_dt="2026-10-07T10:00:00-05:00"),
        ev("d1", 2, "2026-11-03T00:00:00", "2026-11-03T23:59:00", "Cancelled",
           creation_dt="2026-09-01T10:00:00-05:00", delete_dt="2026-10-06T09:00:00-05:00"),
    ]
    client = FakeClient(changed=changed)
    code, out, _ = run(capsys, "report", "changes", "--since", "7d", "--format", "json", client=client)
    assert code == 0
    assert {r["title"]: r["change"] for r in json.loads(out)} == {"New": "created", "Cancelled": "deleted"}
    assert json.loads((tmp_path / ".team_pulse_state.json").read_text()) == {"last_changes_timestamp": 1_800_000_000}

    run(capsys, "report", "changes", client=client)  # default --since last
    assert client.calls[-1] == ("modified_since", 1_800_000_000)


def test_changes_limited_to_30_days(capsys):
    code, _, err = run(capsys, "report", "changes", "--since", "45d")
    assert code == 1 and "30 days" in err


def test_check(capsys):
    code, out, _ = run(capsys, "check")
    assert code == 0 and "Team Time Off" in out and "Sub-calendars visible to this key: 3" in out


def test_fields(capsys):
    _, out, _ = run(capsys, "fields")
    assert "Reason" in out and "Vacation, Sick" in out


# --- HTTP client -------------------------------------------------------------

class FakeResponse:
    def __init__(self, status, body, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.requests.append((url, params, headers))
        return self.responses.pop(0)


def test_client_sends_auth_headers_and_params():
    s = Settings(api_key="k", calendar_key="cal", bearer_token="b")
    session = FakeSession([FakeResponse(200, {"events": []})])
    TeamupClient(s, session).events(date(2026, 10, 1), date(2026, 10, 2), [1, 2])
    url, params, headers = session.requests[0]
    assert url == "https://api.teamup.com/cal/events"
    assert ("subcalendarId[]", 1) in params and ("subcalendarId[]", 2) in params
    assert headers["Teamup-Token"] == "k" and headers["Authorization"] == "Bearer b"


def test_client_retries_429_with_retry_after():
    slept = []
    session = FakeSession([FakeResponse(429, {}, {"Retry-After": "3"}), FakeResponse(200, {"subcalendars": []})])
    TeamupClient(SETTINGS, session, sleep=slept.append).subcalendars()
    assert slept == [3.0]


def test_client_pages_search_results():
    page = [{"id": str(i)} for i in range(100)]
    session = FakeSession([FakeResponse(200, {"events": page}), FakeResponse(200, {"events": [{"id": "x"}]})])
    result = TeamupClient(SETTINGS, session).events(date(2026, 1, 1), date(2026, 1, 2), query="sick")
    assert len(result) == 101
    assert ("offset", 100) in session.requests[1][1]


def test_client_error_message():
    session = FakeSession([FakeResponse(401, {"error": {"message": "Invalid token"}})])
    with pytest.raises(TeamupError, match="Invalid token.*TEAMUP_API_KEY"):
        TeamupClient(SETTINGS, session).subcalendars()


# --- board and HTML ----------------------------------------------------------

def test_board_terminal_marks(capsys):
    _, out, _ = run(capsys, "report", "board", "--preset", "next-week")
    lines = out.splitlines()
    assert lines[0].split()[:3] == ["person", "Mon", "12"]
    assert "██" in next(l for l in lines if l.startswith("Alex Example"))
    assert "▒▒" in next(l for l in lines if l.startswith("Jordan Example"))


def test_board_json_uses_titles_and_lists_selected_people(capsys):
    _, out, _ = run(capsys, "report", "board", "--preset", "next-week", "--group", "sales", "--format", "json")
    rows = {r["person"]: r for r in json.loads(out)}
    assert set(rows) == {"Alex Example", "Sam Example"}
    assert rows["Sam Example"]["2026-10-14"] == "Dentist"


def test_board_html(capsys):
    _, out, _ = run(capsys, "report", "board", "--preset", "next-week", "--format", "html")
    assert out.startswith("<!doctype html>")
    assert "12–18 Oct 2026" in out
    assert out.count('class="tape"') == 2 and out.count('class="tape part"') == 1
    assert 'class="count busy">2<' in out  # Wed and Thu are the busiest days


def test_board_html_escapes_titles(capsys):
    client = FakeClient(events=[ev("x", 1, "2026-10-12T00:00:00", "2026-10-12T23:59:00", "<b>Off</b>")])
    _, out, _ = run(capsys, "report", "board", "--preset", "next-week", "--format", "html", client=client)
    assert "<b>Off</b>" not in out and "&lt;b&gt;Off&lt;/b&gt;" in out


def test_board_html_empty(capsys):
    _, out, _ = run(capsys, "report", "board", "--preset", "next-week", "--format", "html", client=FakeClient(events=[]))
    assert "No time off between 12 Oct 2026 and 18 Oct 2026." in out


def test_other_reports_render_as_html_table(capsys):
    _, out, _ = run(capsys, "report", "totals", "--preset", "next-week", "--format", "html")
    assert "<h1>Days off</h1>" in out and '<td class="num">5</td>' in out


def test_board_html_details_and_accessibility(capsys):
    _, out, _ = run(capsys, "report", "board", "--from", "2026-10-05", "--to", "2026-10-16", "--format", "html")
    # Full text for every absence, since strips can be too narrow to label
    assert "<h2>Details</h2>" in out and "Mon 12 Oct – Fri 16 Oct" in out and "Thu 15 Oct<br>14:00–15:00" in out
    # Today (8 Oct) is marked, using the report's date rather than the machine clock
    assert '<span class="month">Today</span>' in out
    # Screen readers get who and when for each strip; the grid can be scrolled by keyboard
    assert '<span class="sr">Alex Example: </span>' in out
    assert 'tabindex="0" role="region"' in out


def test_client_omits_token_header_when_network_secret_supplies_it():
    session = FakeSession([FakeResponse(200, {"subcalendars": []})])
    TeamupClient(Settings(api_key=None, calendar_key="cal"), session).subcalendars()
    assert "Teamup-Token" not in session.requests[0][2]


def test_only_calendar_key_is_required(monkeypatch):
    from team_pulse.config import ConfigError, load_settings
    monkeypatch.delenv("TEAMUP_API_KEY", raising=False)
    monkeypatch.setenv("TEAMUP_CALENDAR_KEY", "cal")
    assert load_settings(env_file=None).api_key is None
    monkeypatch.delenv("TEAMUP_CALENDAR_KEY")
    with pytest.raises(ConfigError, match="TEAMUP_CALENDAR_KEY"):
        load_settings(env_file=None)

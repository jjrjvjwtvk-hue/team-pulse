"""Teamup API calls. GET only: this tool never changes the calendar."""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Iterable

import requests

from .config import Settings

SEARCH_PAGE_SIZE = 100
MAX_RETRIES = 3


class TeamupError(Exception):
    pass


class TeamupClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None, sleep=time.sleep):
        self.settings = settings
        self.session = session or requests.Session()
        self._sleep = sleep

    def _headers(self) -> dict[str, str]:
        headers = {"Teamup-Token": self.settings.api_key, "Accept": "application/json"}
        if self.settings.bearer_token:
            headers["Authorization"] = f"Bearer {self.settings.bearer_token}"
        return headers

    def _get(self, path: str, params: list[tuple[str, Any]] | None = None) -> dict:
        url = f"{self.settings.base_url}/{self.settings.calendar_key}/{path}"
        params = list(params or [])
        if self.settings.timezone:
            params.append(("tz", self.settings.timezone))

        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, params=params, headers=self._headers(), timeout=30)
            except requests.RequestException as exc:
                raise TeamupError(f"Could not reach Teamup: {exc}") from exc

            if resp.status_code == 429 and attempt < MAX_RETRIES:
                self._sleep(_retry_delay(resp.headers.get("Retry-After"), attempt))
                continue
            if resp.status_code >= 400:
                raise TeamupError(_error_message(resp))
            try:
                return resp.json()
            except ValueError as exc:
                raise TeamupError(f"Teamup returned a non-JSON response for {path}") from exc

        raise TeamupError("Teamup kept answering 429 (too many requests). Try again later.")

    def configuration(self) -> dict:
        data = self._get("configuration")
        return data.get("configuration", data)

    def subcalendars(self) -> list[dict]:
        return self._get("subcalendars").get("subcalendars", [])

    def events(
        self,
        start: date,
        end: date,
        subcalendar_ids: Iterable[int] = (),
        query: str | None = None,
    ) -> list[dict]:
        params: list[tuple[str, Any]] = [("startDate", start.isoformat()), ("endDate", end.isoformat())]
        params += [("subcalendarId[]", sid) for sid in subcalendar_ids]

        if not query:
            return self._get("events", params).get("events", [])

        params.append(("query", query))
        events: list[dict] = []
        offset = 0
        while True:
            page = self._get("events", params + [("limit", SEARCH_PAGE_SIZE), ("offset", offset)]).get("events", [])
            events.extend(page)
            if len(page) < SEARCH_PAGE_SIZE:
                return events
            offset += SEARCH_PAGE_SIZE

    def modified_since(self, since_ts: int) -> tuple[list[dict], int | None]:
        """Events created, edited or deleted since a unix timestamp, plus the server timestamp."""
        data = self._get("events", [("modifiedSince", int(since_ts))])
        return data.get("events", []), data.get("timestamp")


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    return 2.0 ** (attempt + 1)


def _error_message(resp: requests.Response) -> str:
    detail = ""
    try:
        body = resp.json()
        err = body.get("error", body) if isinstance(body, dict) else {}
        detail = err.get("message") or err.get("title") or ""
    except ValueError:
        pass
    hints = {
        401: "Check TEAMUP_API_KEY.",
        403: "The key doesn't have permission for this. Check its access level in Teamup.",
        404: "Check TEAMUP_CALENDAR_KEY.",
    }
    parts = [f"Teamup returned HTTP {resp.status_code}."]
    if detail:
        parts.append(str(detail))
    if resp.status_code in hints:
        parts.append(hints[resp.status_code])
    return " ".join(parts)

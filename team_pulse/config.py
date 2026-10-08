"""Settings loaded from the environment (and .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://api.teamup.com"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    api_key: str | None  # None when a network secret adds the Teamup-Token header outside the VM
    calendar_key: str
    timezone: str | None = None
    base_url: str = DEFAULT_BASE_URL
    bearer_token: str | None = None


def load_settings(env_file: str | None = ".env") -> Settings:
    if env_file:
        load_dotenv(env_file)

    def get(name: str) -> str | None:
        value = os.environ.get(name, "").strip()
        return value or None

    api_key = get("TEAMUP_API_KEY")
    calendar_key = get("TEAMUP_CALENDAR_KEY")
    if not calendar_key:
        raise ConfigError("Missing TEAMUP_CALENDAR_KEY. Copy .env.example to .env and fill it in.")

    return Settings(
        api_key=api_key,
        calendar_key=calendar_key,
        timezone=get("TEAMUP_TIMEZONE"),
        base_url=(get("TEAMUP_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
        bearer_token=get("TEAMUP_BEARER_TOKEN"),
    )

"""Thin typed wrapper around the public MLB StatsAPI.

We hit the HTTP endpoints directly (not the `MLB-StatsAPI` library) so we can
parse responses through our Pydantic wire models and keep full control of
caching + retries. Everything here returns validated Pydantic objects; no
raw dicts escape.
"""

from __future__ import annotations

import logging
import time
from datetime import date

import requests

from src.ingestion.wire_models import (
    ScheduleResponse,
    TeamsResponse,
    Venue,
    VenuesResponse,
)

_BASE_URL = "https://statsapi.mlb.com/api/v1"
_DEFAULT_TIMEOUT = 20.0

_log = logging.getLogger(__name__)


class StatsAPIError(RuntimeError):
    """Raised when the StatsAPI call fails after retries."""


def _get(path: str, params: dict, *, retries: int = 3, backoff: float = 1.5) -> dict:
    url = f"{_BASE_URL}{path}"
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=_DEFAULT_TIMEOUT)
            if r.status_code == 429:
                sleep_for = backoff ** (attempt + 1)
                _log.warning(
                    "statsapi 429, backing off",
                    extra={"path": path, "attempt": attempt, "sleep": sleep_for},
                )
                time.sleep(sleep_for)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            last_exc = exc
            sleep_for = backoff ** (attempt + 1)
            _log.warning(
                "statsapi error, retrying",
                extra={"path": path, "attempt": attempt, "sleep": sleep_for, "err": str(exc)},
            )
            time.sleep(sleep_for)
    raise StatsAPIError(f"{path} failed after {retries} attempts: {last_exc!r}")


def fetch_venues(season: int) -> list[Venue]:
    """Return every venue in StatsAPI for a given MLB season with location hydrated."""
    payload = _get("/venues", {"sportId": 1, "season": season, "hydrate": "location"})
    return VenuesResponse.model_validate(payload).venues


def fetch_venue(venue_id: int) -> Venue | None:
    """Return a single venue by id (with location), or None if missing."""
    payload = _get(f"/venues/{venue_id}", {"hydrate": "location"})
    venues = VenuesResponse.model_validate(payload).venues
    return venues[0] if venues else None


def fetch_teams(season: int) -> TeamsResponse:
    payload = _get("/teams", {"sportId": 1, "season": season})
    return TeamsResponse.model_validate(payload)


def fetch_schedule(start: date, end: date) -> ScheduleResponse:
    """Return all regular / post-season / spring MLB games in a date range."""
    payload = _get(
        "/schedule",
        {
            "sportId": 1,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
        },
    )
    return ScheduleResponse.model_validate(payload)

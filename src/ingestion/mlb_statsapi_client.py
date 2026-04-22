"""Thin typed wrapper around the public MLB StatsAPI.

We hit the HTTP endpoints directly (not the `MLB-StatsAPI` library) so we can
parse responses through our Pydantic wire models and keep full control of
caching + retries. Everything here returns validated Pydantic objects; no
raw dicts escape.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from datetime import date

import requests

from src.ingestion.wire_models import (
    BoxscoreResponse,
    ScheduleGameWithProbables,
    ScheduleResponse,
    ScheduleWithProbablesResponse,
    TeamsResponse,
    Venue,
    VenuesResponse,
)

_BASE_URL = "https://statsapi.mlb.com/api/v1"
_BASE_URL_V1_1 = "https://statsapi.mlb.com/api/v1.1"
_DEFAULT_TIMEOUT = 20.0

_log = logging.getLogger(__name__)


class StatsAPIError(RuntimeError):
    """Raised when the StatsAPI call fails after retries."""


def _get(
    path: str,
    params: dict,
    *,
    retries: int = 3,
    backoff: float = 1.5,
    base_url: str = _BASE_URL,
) -> dict:
    url = f"{base_url}{path}"
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


def fetch_schedule_with_probables(start: date, end: date) -> Iterator[ScheduleGameWithProbables]:
    """Schedule with `probablePitcher` hydrated on each team side.

    Yields `ScheduleGameWithProbables`. Separate entry point from
    `fetch_schedule` so callers that don't need probables aren't forced
    to pay the hydration cost.
    """
    payload = _get(
        "/schedule",
        {
            "sportId": 1,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "hydrate": "probablePitcher,linescore",
        },
    )
    parsed = ScheduleWithProbablesResponse.model_validate(payload)
    yield from parsed.iter_games()


def fetch_boxscore(game_pk: int) -> BoxscoreResponse:
    """Live boxscore; `battingOrder` is empty until the lineup is posted."""
    payload = _get(f"/game/{game_pk}/boxscore", {})
    return BoxscoreResponse.model_validate(payload)


def fetch_game_content(game_pk: int) -> str | None:
    """Return roof_status string for retractable-roof games, else None.

    StatsAPI exposes roof status under `gameData.weather.condition` for
    some roof games and under `gameData.venue.roofType` for others; we
    probe both and return the first non-empty value.
    """
    payload = _get(f"/game/{game_pk}/feed/live", {}, base_url=_BASE_URL_V1_1)
    game_data = payload.get("gameData") or {}
    weather = game_data.get("weather") or {}
    cond = (weather.get("condition") or "").strip().lower()
    if cond in {"roof closed", "dome"}:
        return "closed"
    if cond in {"roof open"}:
        return "open"
    # Fallback: venue-level roof flag (rarely populated for fixed parks).
    venue = game_data.get("venue") or {}
    roof_type = (venue.get("roofType") or "").strip().lower() or None
    return roof_type

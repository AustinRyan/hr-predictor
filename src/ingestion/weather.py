"""Open-Meteo hourly-forecast ingestion.

HTTP client: ``requests`` wrapped in ``requests-cache`` with a 1h TTL
(Open-Meteo updates hourly; hammering is unnecessary and rude).

Unit conventions
----------------
* Open-Meteo returns: Celsius, km/h, hPa, percent.
* Our schema stores: Fahrenheit, mph, hPa, percent.
* Wind direction: Open-Meteo uses meteorological standard (direction
  wind comes FROM, clockwise from true north) -- matches our schema. No
  conversion needed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import requests
import requests_cache
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from src.core.db import get_engine
from src.core.models import DailySchedule, Park, WeatherForecast
from src.ingestion.wire_models import OpenMeteoForecastResponse

_log = logging.getLogger(__name__)

_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_HOURLY_VARS = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "precipitation_probability",
    "cloud_cover",
)
_CACHE_NAME = "openmeteo-cache"
_CACHE_SECONDS = 3600  # 1h per PROMPT / Open-Meteo refresh cadence

# Cached session: instantiate once per process.
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests_cache.CachedSession(
            cache_name=_CACHE_NAME,
            backend="memory",
            expire_after=_CACHE_SECONDS,
        )
    return _session


def _celsius_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


def _kmh_to_mph(kmh: float) -> float:
    return kmh * 0.621371


def _pick_hour_nearest(times: list[str], target: datetime) -> int:
    """Return the index in ``times`` whose naive-UTC hour is closest to ``target``."""
    target_utc = target.astimezone(UTC).replace(tzinfo=None)
    best_i = 0
    best_delta: float | None = None
    for i, t in enumerate(times):
        # Open-Meteo returns naive timestamps in the requested timezone.
        dt = datetime.fromisoformat(t)
        delta = abs((dt - target_utc).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_i = i
    return best_i


def fetch_weather_forecast(
    park_id: int,
    latitude: float,
    longitude: float,
    forecast_for_utc: datetime,
) -> dict[str, Any]:
    """Return a single forecast dict in our storage units, keyed to the nearest hour."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(_HOURLY_VARS),
        "timezone": "GMT",
        "wind_speed_unit": "kmh",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
    }
    r = _get_session().get(_BASE_URL, params=params, timeout=20.0)
    r.raise_for_status()
    parsed = OpenMeteoForecastResponse.model_validate(r.json())

    idx = _pick_hour_nearest(parsed.hourly.time, forecast_for_utc)

    def _at(arr: list[float]) -> float | None:
        return arr[idx] if idx < len(arr) else None

    temp_c = _at(parsed.hourly.temperature_2m)
    feels_c = _at(parsed.hourly.apparent_temperature)
    wind_kmh = _at(parsed.hourly.wind_speed_10m)

    return {
        "park_id": park_id,
        "forecast_for_utc": forecast_for_utc,
        "temperature_f": _celsius_to_f(temp_c) if temp_c is not None else None,
        "feels_like_f": _celsius_to_f(feels_c) if feels_c is not None else None,
        "humidity_pct": _at(parsed.hourly.relative_humidity_2m),
        "pressure_hpa": _at(parsed.hourly.surface_pressure),
        "wind_speed_mph": _kmh_to_mph(wind_kmh) if wind_kmh is not None else None,
        "wind_direction_deg": _at(parsed.hourly.wind_direction_10m),
        "precipitation_pct": _at(parsed.hourly.precipitation_probability),
        "cloud_cover_pct": _at(parsed.hourly.cloud_cover),
        "fetched_at": datetime.now(UTC),
    }


def persist_weather_for_today(*, engine: Engine | None = None) -> int:
    """For every non-dome game in today's daily_schedule, fetch + upsert a forecast."""
    engine = engine or get_engine()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    today = datetime.now(UTC).date()
    with session_factory() as session:
        stmt = (
            select(
                DailySchedule.game_pk,
                DailySchedule.venue_id,
                DailySchedule.game_start_utc,
                Park.roof_type,
                Park.latitude,
                Park.longitude,
            )
            .join(Park, Park.park_id == DailySchedule.venue_id)
            .where(DailySchedule.game_date == today)
        )
        todays = session.execute(stmt).all()

    rows: list[dict[str, Any]] = []
    for game_pk, venue_id, game_start_utc, roof_type, lat, lon in todays:
        if roof_type == "dome":
            _log.info("skip dome", extra={"game_pk": game_pk, "park_id": venue_id})
            continue
        if lat is None or lon is None:
            _log.warning("park missing coordinates", extra={"park_id": venue_id})
            continue
        try:
            row = fetch_weather_forecast(venue_id, lat, lon, game_start_utc)
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "weather fetch failed",
                extra={"game_pk": game_pk, "err": str(exc)},
            )
            continue
        rows.append(row)

    if not rows:
        return 0

    with session_factory() as session:
        stmt = pg_insert(WeatherForecast).values(rows)
        # (park_id, forecast_for_utc, fetched_at) is unique -- fetched_at
        # advances each run, so each call writes a new row (the spec
        # preserves forecast-revision history).
        session.execute(stmt)
        session.commit()

    _log.info("weather rows written", extra={"count": len(rows)})
    return len(rows)

"""Open-Meteo hourly-forecast and historical-archive ingestion.

HTTP client: ``requests`` wrapped in ``requests-cache`` with a 1h TTL
(Open-Meteo updates hourly; hammering is unnecessary and rude). Archive
calls go through a plain ``requests.Session`` — they're one-shot
bulk historical pulls, not the repeated polling the forecast client
serves, so caching there only adds complexity.

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
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

import requests
import requests_cache
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from src.core.db import get_engine
from src.core.models import DailySchedule, Park, WeatherArchive, WeatherForecast
from src.features.weather_physics import (
    air_density_relative,
    apply_roof_gating,
    wind_carry_components,
)
from src.ingestion.wire_models import (
    OpenMeteoArchiveResponse,
    OpenMeteoForecastResponse,
)

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


# ---------------------------------------------------------------------------
# Historical archive ingestion (Open-Meteo /v1/archive).
# ---------------------------------------------------------------------------

_ARCHIVE_BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
_ARCHIVE_HOURLY_VARS = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "precipitation",
    "cloud_cover",
)


def _fetch_archive_with_retry(
    params: dict[str, Any],
    *,
    max_attempts: int = 6,
    backoff_base: float = 3.0,
) -> dict[str, Any]:
    """Call the archive endpoint with exponential backoff on transient failures.

    Open-Meteo's archive endpoint tolerates short bursts but trips 429 on
    sustained per-minute pressure. Six attempts with base=3 gives us
    3, 9, 27, 81, 243s of sleep (~6 minutes max) before giving up --
    long enough to ride through the per-minute rate limiter.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            r = requests.get(_ARCHIVE_BASE_URL, params=params, timeout=60.0)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"transient status {r.status_code}")
            r.raise_for_status()
            return r.json()
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt == max_attempts:
                break
            sleep_s = backoff_base**attempt
            _log.warning(
                "archive fetch retrying",
                extra={"attempt": attempt, "sleep_s": sleep_s, "err_msg": str(exc)},
            )
            time.sleep(sleep_s)
    assert last_exc is not None  # invariant: only reach here if all attempts failed
    raise last_exc


def fetch_archive_range(
    park_id: int,
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Pull hourly historical weather for ``[start_date, end_date]`` (inclusive).

    Returns a list of row dicts matching the ``weather_archive`` schema,
    units converted to US (Fahrenheit + mph). Empty list if Open-Meteo
    returns no hourly block (e.g. date range in the future).
    """
    params: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "hourly": ",".join(_ARCHIVE_HOURLY_VARS),
        "timezone": "GMT",
        "wind_speed_unit": "kmh",
        "temperature_unit": "celsius",
    }
    payload = _fetch_archive_with_retry(params)
    parsed = OpenMeteoArchiveResponse.model_validate(payload)
    h = parsed.hourly

    rows: list[dict[str, Any]] = []
    for i, ts in enumerate(h.time):
        # Archive returns naive ISO strings in the requested timezone (GMT here).
        dt = datetime.fromisoformat(ts).replace(tzinfo=UTC)

        def _at(arr: list[float | None], idx: int = i) -> float | None:
            return arr[idx] if idx < len(arr) else None

        temp_c = _at(h.temperature_2m)
        feels_c = _at(h.apparent_temperature)
        wind_kmh = _at(h.wind_speed_10m)

        rows.append(
            {
                "park_id": park_id,
                "valid_hour_utc": dt,
                "temperature_f": _celsius_to_f(temp_c) if temp_c is not None else None,
                "feels_like_f": _celsius_to_f(feels_c) if feels_c is not None else None,
                "humidity_pct": _at(h.relative_humidity_2m),
                "pressure_hpa": _at(h.surface_pressure),
                "wind_speed_mph": _kmh_to_mph(wind_kmh) if wind_kmh is not None else None,
                "wind_direction_deg": _at(h.wind_direction_10m),
                "precipitation_mm": _at(h.precipitation),
                "cloud_cover_pct": _at(h.cloud_cover),
            }
        )
    return rows


def _upsert_archive_rows(rows: list[dict[str, Any]], *, engine: Engine) -> int:
    if not rows:
        return 0
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    # Chunk inserts so we don't blow past Postgres's ~65k parameter cap on
    # large multi-year pulls (~44k hours/park × 10 params = 440k > 65k).
    written = 0
    chunk_size = 2000
    with session_factory() as session:
        for start in range(0, len(rows), chunk_size):
            chunk = rows[start : start + chunk_size]
            stmt = pg_insert(WeatherArchive).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["park_id", "valid_hour_utc"],
                set_={
                    "temperature_f": stmt.excluded.temperature_f,
                    "feels_like_f": stmt.excluded.feels_like_f,
                    "humidity_pct": stmt.excluded.humidity_pct,
                    "pressure_hpa": stmt.excluded.pressure_hpa,
                    "wind_speed_mph": stmt.excluded.wind_speed_mph,
                    "wind_direction_deg": stmt.excluded.wind_direction_deg,
                    "precipitation_mm": stmt.excluded.precipitation_mm,
                    "cloud_cover_pct": stmt.excluded.cloud_cover_pct,
                },
            )
            session.execute(stmt)
            written += len(chunk)
        session.commit()
    return written


def persist_weather_archive_for_park(
    park_id: int,
    *,
    start_date: date,
    end_date: date,
    engine: Engine | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> int:
    """Fetch + upsert hourly archive rows for one park across ``[start_date, end_date]``.

    ``latitude`` / ``longitude`` are optional; if omitted we look them
    up from the ``parks`` table. Returns the number of rows upserted.
    """
    engine = engine or get_engine()
    if latitude is None or longitude is None:
        session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        with session_factory() as session:
            park = session.get(Park, park_id)
            if park is None:
                _log.warning("unknown park_id", extra={"park_id": park_id})
                return 0
            latitude = park.latitude
            longitude = park.longitude
    if latitude is None or longitude is None:
        _log.warning("park missing coordinates", extra={"park_id": park_id})
        return 0

    rows = fetch_archive_range(park_id, latitude, longitude, start_date, end_date)
    written = _upsert_archive_rows(rows, engine=engine)
    _log.info(
        "archive rows written",
        extra={
            "park_id": park_id,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "count": written,
        },
    )
    return written


def persist_weather_archive_all_parks(
    start_date: date,
    end_date: date,
    *,
    engine: Engine | None = None,
    sleep_between_parks_s: float = 1.0,
) -> int:
    """Iterate all parks with lat/lon populated and pull archive for each.

    Filters to parks that actually host games in ``matchup_features`` by
    presence of lat/lon; exhibition venues without coords are skipped
    (they can't have weather anyway). Returns total rows written.
    """
    engine = engine or get_engine()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with session_factory() as session:
        stmt = select(Park.park_id, Park.latitude, Park.longitude, Park.name).where(
            Park.latitude.is_not(None), Park.longitude.is_not(None)
        )
        parks = session.execute(stmt).all()

    total = 0
    for i, (park_id, lat, lon, name) in enumerate(parks):
        try:
            written = persist_weather_archive_for_park(
                park_id,
                start_date=start_date,
                end_date=end_date,
                engine=engine,
                latitude=lat,
                longitude=lon,
            )
        except Exception as exc:  # noqa: BLE001
            _log.error(
                "archive fetch failed",
                extra={"park_id": park_id, "park_name": name, "err_msg": str(exc)},
            )
            continue
        total += written
        if sleep_between_parks_s > 0 and i < len(parks) - 1:
            time.sleep(sleep_between_parks_s)
    return total


# ---------------------------------------------------------------------------
# Historical `matchup_features.wx_*` backfill from weather_archive.
# ---------------------------------------------------------------------------


_WX_UPDATE_ONE_SQL = """
    UPDATE matchup_features
       SET wx_temperature_f = :wx_temperature_f,
           wx_humidity_pct = :wx_humidity_pct,
           wx_pressure_hpa = :wx_pressure_hpa,
           wx_air_density_relative = :wx_air_density_relative,
           wx_wind_speed_mph = :wx_wind_speed_mph,
           wx_wind_carry_lf = :wx_wind_carry_lf,
           wx_wind_carry_cf = :wx_wind_carry_cf,
           wx_wind_carry_rf = :wx_wind_carry_rf,
           wx_is_roof_closed = :wx_is_roof_closed
     WHERE game_date = :game_date
       AND game_pk = :game_pk
       AND is_historical
"""


def backfill_wx_for_historical(
    start_date: date,
    end_date: date,
    *,
    engine: Engine | None = None,
    batch_size: int = 500,
) -> int:
    """Fill ``wx_*`` columns on historical matchup_features rows from weather_archive.

    Matches each game to the nearest hourly archive row at the park's
    ``game_start_utc`` hour. Computes air density + wind carry via the
    Phase 3 physics helpers. Roof-closed baseline applies when
    ``parks.roof_type = 'dome'`` (retractable-roof historical status is
    unavailable pre-Phase 2; default is "open").

    Issues a per-``game_pk`` UPDATE that affects all matchup_features
    rows for the game -- every matchup in one game shares the same
    weather and context.

    Returns the total number of ``matchup_features`` rows touched.
    """
    from sqlalchemy import text

    engine = engine or get_engine()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    # One SELECT gathers every game on the date range that has weather_archive
    # coverage and a resolvable park orientation. The nearest-hour match uses
    # Postgres `date_trunc` + a correlated subquery ordered by abs(interval).
    select_sql = text("""
        SELECT
            g.game_pk,
            g.game_date,
            g.game_start_utc,
            p.park_id,
            p.orientation_deg,
            p.roof_type,
            wa.temperature_f,
            wa.humidity_pct,
            wa.pressure_hpa,
            wa.wind_speed_mph,
            wa.wind_direction_deg
        FROM games g
        JOIN parks p ON p.park_id = g.venue_id
        JOIN LATERAL (
            SELECT w.temperature_f, w.humidity_pct, w.pressure_hpa,
                   w.wind_speed_mph, w.wind_direction_deg
            FROM weather_archive w
            WHERE w.park_id = p.park_id
              AND w.valid_hour_utc BETWEEN g.game_start_utc - INTERVAL '3 hours'
                                       AND g.game_start_utc + INTERVAL '3 hours'
            ORDER BY ABS(EXTRACT(EPOCH FROM (w.valid_hour_utc - g.game_start_utc)))
            LIMIT 1
        ) wa ON true
        WHERE g.game_date BETWEEN :start_date AND :end_date
          AND g.game_start_utc IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM matchup_features mf
              WHERE mf.game_pk = g.game_pk AND mf.is_historical
          )
        ORDER BY g.game_date, g.game_pk
    """)

    with session_factory() as session:
        candidates = session.execute(
            select_sql, {"start_date": start_date, "end_date": end_date}
        ).all()

    _log.info(
        "wx backfill candidates",
        extra={
            "count": len(candidates),
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
    )

    total_touched = 0
    batch: list[dict[str, Any]] = []
    with session_factory() as session:
        for row in candidates:
            # Build raw physics features.
            raw: dict[str, Any] = {
                "wx_temperature_f": row.temperature_f,
                "wx_humidity_pct": row.humidity_pct,
                "wx_pressure_hpa": row.pressure_hpa,
                "wx_wind_speed_mph": row.wind_speed_mph,
            }
            if (
                row.temperature_f is not None
                and row.humidity_pct is not None
                and row.pressure_hpa is not None
            ):
                raw["wx_air_density_relative"] = air_density_relative(
                    row.temperature_f, row.humidity_pct, row.pressure_hpa
                )
            else:
                raw["wx_air_density_relative"] = None

            if (
                row.wind_direction_deg is not None
                and row.wind_speed_mph is not None
                and row.orientation_deg is not None
            ):
                lf, cf, rf = wind_carry_components(
                    row.wind_direction_deg, row.wind_speed_mph, row.orientation_deg
                )
                raw["wx_wind_carry_lf"] = lf
                raw["wx_wind_carry_cf"] = cf
                raw["wx_wind_carry_rf"] = rf
            else:
                raw["wx_wind_carry_lf"] = None
                raw["wx_wind_carry_cf"] = None
                raw["wx_wind_carry_rf"] = None

            is_roof_closed = row.roof_type == "dome"
            gated = apply_roof_gating(raw, is_roof_closed)

            batch.append(
                {
                    "game_date": row.game_date,
                    "game_pk": row.game_pk,
                    "wx_temperature_f": gated["wx_temperature_f"],
                    "wx_humidity_pct": gated["wx_humidity_pct"],
                    "wx_pressure_hpa": gated["wx_pressure_hpa"],
                    "wx_air_density_relative": gated["wx_air_density_relative"],
                    "wx_wind_speed_mph": gated["wx_wind_speed_mph"],
                    "wx_wind_carry_lf": gated["wx_wind_carry_lf"],
                    "wx_wind_carry_cf": gated["wx_wind_carry_cf"],
                    "wx_wind_carry_rf": gated["wx_wind_carry_rf"],
                    "wx_is_roof_closed": gated["wx_is_roof_closed"],
                }
            )

            if len(batch) >= batch_size:
                total_touched += _flush_wx_batch(session, batch)
                batch.clear()

        if batch:
            total_touched += _flush_wx_batch(session, batch)
        session.commit()

    _log.info("wx backfill complete", extra={"updated_rows": total_touched})
    return total_touched


def _flush_wx_batch(session: Any, batch: list[dict[str, Any]]) -> int:
    """Issue one UPDATE per game, accumulating true per-row counts.

    Each batch entry corresponds to one (game_date, game_pk) game; each
    UPDATE touches every historical matchup row in that game (typically
    ~70-80 per game for a full pair of 9-batter lineups × one starter
    each side + inferred matchups). Single-statement execution gives
    us a reliable `result.rowcount` to aggregate.
    """
    from sqlalchemy import text

    stmt = text(_WX_UPDATE_ONE_SQL)
    total = 0
    for params in batch:
        result = session.execute(stmt, params)
        if result.rowcount is not None and result.rowcount > 0:
            total += result.rowcount
    return total


__all__ = [
    "_celsius_to_f",
    "_kmh_to_mph",
    "_pick_hour_nearest",
    "backfill_wx_for_historical",
    "fetch_archive_range",
    "fetch_weather_forecast",
    "persist_weather_archive_all_parks",
    "persist_weather_archive_for_park",
    "persist_weather_for_today",
]


# Keep `timedelta` importable-by-other-modules expectation stable (unused here).
_ = timedelta

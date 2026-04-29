"""Admin endpoints — run the daily ingest + inference pipeline on demand.

INTENTIONALLY UNAUTHENTICATED: these endpoints execute real ingestion jobs
and ML inference. Fine for local-first personal use (API bound to
127.0.0.1). Do NOT expose to the public internet. If this service is
ever put behind a real deployment, gate this router on an admin-only
auth check or remove it.

The shape is fire-and-forget: POST /admin/refresh-picks kicks off the
pipeline in a worker thread, GET /admin/refresh-status returns the
current phase so the UI can show progress and auto-reload when done.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime
from threading import Lock
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from src.core.time import current_mlb_date

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

_state: dict[str, Any] = {
    "status": "idle",  # idle | running | done | error
    "phase": None,  # ingest | inference | flush_cache | done
    "started_at": None,
    "finished_at": None,
    "target_date": None,
    "rows_written": None,
    "report": None,
    "error": None,
}
_lock = Lock()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _set_state(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


_PROXY_LINEUPS_SQL = text("""
    WITH today_teams AS (
        SELECT game_pk, home_team_id AS team_id FROM daily_schedule WHERE game_date = :d
        UNION ALL
        SELECT game_pk, away_team_id AS team_id FROM daily_schedule WHERE game_date = :d
    ),
    teams_needing_proxy AS (
        SELECT tt.game_pk, tt.team_id
        FROM today_teams tt
        LEFT JOIN projected_lineups pl
          ON pl.game_pk = tt.game_pk AND pl.team_id = tt.team_id
        WHERE pl.id IS NULL
        GROUP BY tt.game_pk, tt.team_id
    ),
    recent_src AS (
        SELECT DISTINCT ON (pl.team_id)
            pl.team_id,
            pl.game_pk AS src_game_pk
        FROM projected_lineups pl
        JOIN daily_schedule ds ON ds.game_pk = pl.game_pk
        WHERE ds.game_date < :d
          AND pl.team_id IN (SELECT team_id FROM teams_needing_proxy)
        ORDER BY pl.team_id, ds.game_date DESC, pl.fetched_at DESC
    )
    INSERT INTO projected_lineups (game_pk, team_id, batter_id, batting_order, is_confirmed)
    SELECT tn.game_pk, tn.team_id, src.batter_id, src.batting_order, FALSE
    FROM teams_needing_proxy tn
    JOIN recent_src rs ON rs.team_id = tn.team_id
    JOIN projected_lineups src
        ON src.game_pk = rs.src_game_pk AND src.team_id = rs.team_id
""")


def _fill_proxy_lineups(target_date: date) -> int:
    """Populate missing projected_lineups from each team's most recent prior
    game. Marks the rows is_confirmed=False so a subsequent refresh (after
    MLB posts actual lineups) will clearly replace them."""
    from src.core.db import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(_PROXY_LINEUPS_SQL, {"d": target_date})
        return int(result.rowcount or 0)


def _flush_picks_cache() -> None:
    """Drop every picks:today:* Redis key so the next API call hits Postgres."""
    try:
        from src.core.redis_client import get_redis

        r = get_redis()
        if r is None:
            return
        deleted = 0
        for key in r.scan_iter("picks:today:*"):
            r.delete(key)
            deleted += 1
        _log.info("flushed picks cache", extra={"deleted": deleted})
    except Exception:  # noqa: BLE001
        _log.warning("failed to flush redis cache", exc_info=True)


def _run_pipeline(target_date: date) -> None:
    """Invoke ingest → feature build → inference. Runs in a worker thread."""
    from src.features.builder import build_features_for_date
    from src.ingestion.daily_runner import run_daily
    from src.models.inference import generate_predictions_for_date

    try:
        _set_state(phase="ingest")
        _log.info("refresh: running daily ingest", extra={"date": target_date.isoformat()})
        report = run_daily(target_date=target_date)

        # Always run the proxy filler: the SQL only inserts for teams that
        # don't already have a lineup today, so it's idempotent. When
        # actual lineups have already been posted, proxy_rows = 0 and we
        # move straight to features. When they haven't, we copy each
        # team's most recent lineup as a proxy (is_confirmed=False) so
        # the pipeline keeps going.
        _log.info("refresh: filling proxy lineups for teams missing today's lineup")
        proxy_rows = _fill_proxy_lineups(target_date)
        _log.info("refresh: proxy lineup rows inserted", extra={"rows": proxy_rows})

        _set_state(
            phase="features",
            report={
                "games": report.games,
                "proxy_lineup_rows": proxy_rows,
                "weather_rows": report.weather_rows,
                "statcast_pitches": getattr(report, "statcast_pitches", None),
                "park_factors_refreshed": getattr(report, "park_factors_refreshed", None),
                "failures": list(report.failures),
            },
        )

        _log.info("refresh: building matchup_features", extra={"date": target_date.isoformat()})
        feature_rows = build_features_for_date(target_date)
        _set_state(
            phase="inference",
            rows_written=None,
            report={**(_state.get("report") or {}), "matchup_features_rows": int(feature_rows)},
        )

        if feature_rows == 0:
            msg = (
                "No matchup features could be built for today (no lineups or "
                "no qualifying batters). Retry after MLB publishes lineups."
            )
            _set_state(status="error", phase="error", error=msg, finished_at=_now_iso())
            return

        _log.info("refresh: running inference", extra={"date": target_date.isoformat()})
        rows = generate_predictions_for_date(target_date)

        _set_state(phase="flush_cache", rows_written=int(rows))
        _flush_picks_cache()

        _set_state(status="done", phase="done", finished_at=_now_iso())
        _log.info("refresh: complete", extra={"rows_written": rows})
    except Exception as exc:  # noqa: BLE001
        _log.exception("refresh pipeline failed")
        _set_state(status="error", phase="error", error=str(exc), finished_at=_now_iso())


@router.post("/refresh-picks")
async def refresh_picks() -> dict[str, Any]:
    """Kick off the daily ingest + inference pipeline.

    Returns 202 immediately (via asyncio.to_thread). Poll
    `/admin/refresh-status` for progress. 409 if a refresh is already
    running.
    """
    with _lock:
        if _state["status"] == "running":
            raise HTTPException(409, "refresh already in progress")
        target = current_mlb_date()
        _state.update(
            status="running",
            phase="starting",
            started_at=_now_iso(),
            finished_at=None,
            target_date=target.isoformat(),
            rows_written=None,
            report=None,
            error=None,
        )

    # Schedule the blocking work on the default thread pool so the event
    # loop stays responsive for the status-polling requests.
    asyncio.create_task(asyncio.to_thread(_run_pipeline, target))
    return {"status": "started", "target_date": target.isoformat()}


@router.get("/refresh-status")
async def refresh_status() -> dict[str, Any]:
    """Return the current refresh state. Safe to poll at ~1Hz."""
    with _lock:
        return dict(_state)

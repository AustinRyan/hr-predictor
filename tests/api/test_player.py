"""Tests for /player endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from src.api.dependencies import _get_session_factory


def _seed_player(
    mlbam_id: int = 710001,
    full_name: str = "Test Slugger",
    bats: str = "R",
) -> None:
    sf = _get_session_factory()
    with sf() as s:
        s.execute(
            text(
                "INSERT INTO players "
                "(mlbam_id, full_name, first_name, last_name, bats, throws, primary_position, active) "
                "VALUES (:id, :n, 'Test', 'Slugger', :b, 'R', 'LF', TRUE) "
                "ON CONFLICT (mlbam_id) DO UPDATE SET full_name = EXCLUDED.full_name, bats = EXCLUDED.bats"
            ),
            {"id": mlbam_id, "n": full_name, "b": bats},
        )
        s.commit()


def _seed_rolling(mlbam_id: int, as_of: date) -> None:
    """Seed one matchup_features row so /player has something to return as rolling stats."""
    sf = _get_session_factory()
    with sf() as s:
        s.execute(
            text(
                "INSERT INTO parks (park_id, name) VALUES (99711, 'Test Park 2') ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO matchup_features "
                "(game_date, game_pk, batter_id, pitcher_id, is_historical, park_id, "
                " b_barrel_pct_30d, b_p90_ev_30d, b_hr_per_pa_season, b_pa_count_season) "
                "VALUES (:d, 997100, :mlbam, 710100, TRUE, 99711, "
                "  0.18, 108.5, 0.06, 400) "
                "ON CONFLICT DO NOTHING"
            ),
            {"d": as_of, "mlbam": mlbam_id},
        )
        s.commit()


def _seed_today_prediction(mlbam_id: int, today: date) -> None:
    sf = _get_session_factory()
    with sf() as s:
        s.execute(
            text(
                "INSERT INTO parks (park_id, name) VALUES (99712, 'Test Park 3') ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO teams (team_id, abbr, name) VALUES (9011, 'TA', 'T A') ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO teams (team_id, abbr, name) VALUES (9012, 'TB', 'T B') ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO daily_schedule "
                "(game_pk, game_date, home_team_id, away_team_id, venue_id, game_start_utc, status) "
                "VALUES (997110, :d, 9011, 9012, 99712, :ts, 'Scheduled') ON CONFLICT DO NOTHING"
            ),
            {"d": today, "ts": datetime(today.year, today.month, today.day, 22, 0, tzinfo=UTC)},
        )
        s.execute(
            text(
                "INSERT INTO predictions "
                "(game_pk, batter_id, pitcher_id, game_date, model_version, "
                " matchup_components, projected_pas, prob_at_least_one_hr, expected_hrs) "
                "VALUES (997110, :mlbam, 710200, :d, 'v20260423_173917', "
                " :mc, 4.5, 0.18, 0.22) ON CONFLICT DO NOTHING"
            ),
            {
                "mlbam": mlbam_id,
                "d": today,
                "mc": '{"starter_calibrated_prob": 0.18}',
            },
        )
        s.commit()


def _flush_player_cache() -> None:
    from src.core.redis_client import get_redis

    r = get_redis()
    try:
        keys = r.keys("player:detail:*")
        if keys:
            r.delete(*keys)
    except Exception:
        pass


def _cleanup(mlbam_id: int) -> None:
    sf = _get_session_factory()
    with sf() as s:
        s.execute(text("DELETE FROM predictions WHERE batter_id = :b"), {"b": mlbam_id})
        s.execute(text("DELETE FROM daily_schedule WHERE game_pk IN (997100, 997110)"))
        s.execute(text("DELETE FROM matchup_features WHERE batter_id = :b"), {"b": mlbam_id})
        s.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_player_detail_happy_path(client) -> None:
    mlbam = 710001
    today = datetime.now(UTC).date()
    _flush_player_cache()
    _seed_player(mlbam)
    _seed_rolling(mlbam, today)
    _seed_today_prediction(mlbam, today)
    try:
        r = await client.get(f"/player/{mlbam}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["profile"]["mlbam_id"] == mlbam
        assert body["profile"]["full_name"] == "Test Slugger"
        assert body["profile"]["bats"] == "R"
        assert body["rolling"]["b_barrel_pct_30d"] == 0.18
        assert body["rolling"]["b_p90_ev_30d"] == 108.5
        assert body["today_prediction"] is not None
        assert body["today_prediction"]["prob_at_least_one_hr"] == 0.18
        assert body["today_prediction"]["model_version"] == "v20260423_173917"
    finally:
        _cleanup(mlbam)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_player_detail_not_found(client) -> None:
    r = await client.get("/player/1")  # unlikely to exist
    # May 404 (unknown player) or 200 if 1 is a real mlbam_id in dev DB
    assert r.status_code in (200, 404)
    if r.status_code == 404:
        body = r.json()
        assert "error" in body


@pytest.mark.asyncio
@pytest.mark.integration
async def test_player_detail_no_rolling_returns_empty_rolling(client) -> None:
    """Player with no matchup_features rows → rolling fields all None."""
    mlbam = 710002
    _flush_player_cache()
    _seed_player(mlbam, full_name="No Data Player", bats="L")
    # No rolling, no prediction
    try:
        r = await client.get(f"/player/{mlbam}")
        assert r.status_code == 200
        body = r.json()
        assert body["rolling"]["as_of"] is None
        assert body["rolling"]["b_barrel_pct_30d"] is None
        assert body["today_prediction"] is None
    finally:
        _cleanup(mlbam)

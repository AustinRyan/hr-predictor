"""Tests for recent top-pick history settlement."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text
from src.api.dependencies import _get_session_factory
from src.models.artifacts import load_model

_GAME_PK = 999301
_BATTERS = (731001, 731002, 731003)
_PITCHER = 731100
_GAME_DATE = date(2026, 2, 3)


def _cleanup_history_rows() -> None:
    sf = _get_session_factory()
    with sf() as s:
        s.execute(text("DELETE FROM odds_snapshots WHERE game_pk = :gp"), {"gp": _GAME_PK})
        s.execute(text("DELETE FROM predictions WHERE game_pk = :gp"), {"gp": _GAME_PK})
        s.execute(text("DELETE FROM statcast_pitches WHERE game_pk = :gp"), {"gp": _GAME_PK})
        s.execute(text("DELETE FROM daily_schedule WHERE game_pk = :gp"), {"gp": _GAME_PK})
        s.execute(text("DELETE FROM players WHERE mlbam_id BETWEEN 731001 AND 731100"))
        s.execute(text("DELETE FROM teams WHERE team_id IN (731, 732)"))
        s.execute(text("DELETE FROM parks WHERE park_id = 7391"))
        s.commit()


def _seed_history_rows(model_version: str) -> None:
    game_start = datetime.combine(_GAME_DATE, datetime.min.time(), tzinfo=UTC).replace(hour=23)
    sf = _get_session_factory()
    with sf() as s:
        s.execute(text("INSERT INTO parks (park_id, name) VALUES (7391, 'History Park')"))
        s.execute(
            text(
                "INSERT INTO teams (team_id, abbr, name) VALUES "
                "(731, 'HIS', 'History Home'), (732, 'AWY', 'History Away')"
            )
        )
        s.execute(
            text(
                "INSERT INTO daily_schedule "
                "(game_pk, game_date, home_team_id, away_team_id, venue_id, game_start_utc, status) "
                "VALUES (:gp, :d, 731, 732, 7391, :start, 'Final')"
            ),
            {"gp": _GAME_PK, "d": _GAME_DATE, "start": game_start},
        )
        s.execute(
            text(
                "INSERT INTO players (mlbam_id, full_name, active) VALUES "
                "(731001, 'History One', true), "
                "(731002, 'History Two', true), "
                "(731003, 'History Three', true), "
                "(731100, 'History Pitcher', true)"
            )
        )
        probs = {731001: 0.21, 731002: 0.17, 731003: 0.11}
        for batter_id, prob in probs.items():
            s.execute(
                text(
                    "INSERT INTO predictions "
                    "(game_pk, batter_id, pitcher_id, game_date, model_version, "
                    " matchup_components, prob_at_least_one_hr, expected_hrs, generated_at) "
                    "VALUES (:gp, :b, :p, :d, :mv, :mc, :prob, :prob, :gen)"
                ),
                {
                    "gp": _GAME_PK,
                    "b": batter_id,
                    "p": _PITCHER,
                    "d": _GAME_DATE,
                    "mv": model_version,
                    "mc": f'{{"full_game_raw_prob": {prob + 0.01}}}',
                    "prob": prob,
                    "gen": game_start - timedelta(hours=6),
                },
            )

        # Any Statcast row for the game marks the outcome as settled. Only
        # History Two homers, so the endpoint must use full-game HR actuals
        # rather than starter-only matchup labels.
        for i, batter_id in enumerate(_BATTERS, start=1):
            event = "home_run" if batter_id == 731002 else "strikeout"
            s.execute(
                text(
                    "INSERT INTO statcast_pitches "
                    "(game_date, game_pk, at_bat_number, pitch_number, batter, pitcher, events) "
                    "VALUES (:d, :gp, :ab, 1, :b, :p, :event)"
                ),
                {
                    "d": _GAME_DATE,
                    "gp": _GAME_PK,
                    "ab": i,
                    "b": batter_id,
                    "p": _PITCHER,
                    "event": event,
                },
            )

        s.execute(
            text(
                "INSERT INTO odds_snapshots "
                "(snapshot_key, provider, sport_key, event_id, game_pk, game_date, commence_time, "
                " home_team, away_team, bookmaker_key, bookmaker_title, market_key, outcome_name, "
                " player_name, batter_id, price_american, point, implied_probability, fetched_at, raw_outcome) "
                "VALUES "
                "('hist-one', 'the_odds_api', 'baseball_mlb', 'evt', :gp, :d, :start, "
                " 'History Home', 'History Away', 'draftkings', 'DraftKings', 'batter_home_runs', "
                " 'Over', 'History One', 731001, 500, 0.5, 0.1666667, :fetch, '{\"name\":\"Over\"}'), "
                "('hist-two', 'the_odds_api', 'baseball_mlb', 'evt', :gp, :d, :start, "
                " 'History Home', 'History Away', 'fanduel', 'FanDuel', 'batter_home_runs', "
                " 'Over', 'History Two', 731002, 700, 0.5, 0.125, :fetch, '{\"name\":\"Over\"}')"
            ),
            {
                "gp": _GAME_PK,
                "d": _GAME_DATE,
                "start": game_start,
                "fetch": game_start - timedelta(hours=4),
            },
        )
        s.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_history_returns_top_picks_with_full_game_results(client) -> None:
    model_version = load_model().version
    _cleanup_history_rows()
    _seed_history_rows(model_version)
    try:
        r = await client.get(f"/picks/history?days=1&limit_per_day=2&end_date={_GAME_DATE}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["model_version"] == model_version
        assert body["summary"]["picks"] == 2
        assert body["summary"]["hits"] == 1
        assert body["summary"]["hit_rate"] == pytest.approx(0.5)
        assert body["summary"]["expected_hits"] == pytest.approx(0.38)
        assert body["summary"]["picks_with_odds"] == 2

        rows = body["items"]
        assert [row["daily_rank"] for row in rows] == [1, 2]
        assert rows[0]["batter_name"] == "History One"
        assert rows[0]["actual_hr"] is False
        assert rows[0]["actual_hrs"] == 0
        assert rows[0]["settled_profit_units"] == pytest.approx(-1.0)
        assert rows[1]["batter_name"] == "History Two"
        assert rows[1]["actual_hr"] is True
        assert rows[1]["actual_hrs"] == 1
        assert rows[1]["settled_profit_units"] == pytest.approx(7.0)
    finally:
        _cleanup_history_rows()

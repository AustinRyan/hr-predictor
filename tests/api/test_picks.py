"""Tests for /picks endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from src.api.dependencies import _get_session_factory
from src.core.redis_client import get_redis
from src.core.time import current_mlb_date
from src.models.artifacts import load_model

_TEST_GAME_PK = 997001
_TEST_BATTER_IDS = (700001, 700002, 700003, 700004, 700005)
_STALE_BATTER_ID = 700099
_TEST_PITCHER_ID = 700100


def _active_model_version() -> str:
    return load_model().version


def _flush_picks_cache() -> None:
    """Drop all `picks:today:*` keys so the test sees live DB state, not
    a stale cache from a prior run."""
    try:
        r = get_redis()
        keys = r.keys("picks:today*")
        if keys:
            r.delete(*keys)
    except Exception:  # noqa: BLE001
        # Redis unreachable: endpoint degrades to direct-DB, tests still valid
        pass


def _seed_predictions(game_date: date, model_version: str) -> None:
    """Seed 5 prediction rows against the live dev DB."""
    _flush_picks_cache()
    sf = _get_session_factory()
    with sf() as s:
        # Clean only this synthetic game; never wipe the real slate date.
        s.execute(text("DELETE FROM predictions WHERE game_pk = :gp"), {"gp": _TEST_GAME_PK})
        s.execute(
            text("DELETE FROM projected_lineups WHERE game_pk = :gp"),
            {"gp": _TEST_GAME_PK},
        )
        # Park + schedule for FK context
        s.execute(
            text(
                "INSERT INTO parks (park_id, name) VALUES (99701, 'Test Park') "
                "ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO teams (team_id, abbr, name) VALUES (9001, 'TST', 'Test Home') "
                "ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO teams (team_id, abbr, name) VALUES (9002, 'VIS', 'Test Away') "
                "ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO daily_schedule "
                "(game_pk, game_date, home_team_id, away_team_id, venue_id, "
                " game_start_utc, status) "
                "VALUES (:gp, :d, 9001, 9002, 99701, :ts, 'Scheduled') "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "gp": _TEST_GAME_PK,
                "d": game_date,
                "ts": datetime(game_date.year, game_date.month, game_date.day, 23, 0, tzinfo=UTC),
            },
        )
        # Players
        for pid, name in [
            (700001, "Test Batter A"),
            (700002, "Test Batter B"),
            (700003, "Test Batter C"),
            (700004, "Test Batter D"),
            (700005, "Test Batter E"),
            (_STALE_BATTER_ID, "Stale Model Batter"),
            (_TEST_PITCHER_ID, "Test Pitcher"),
        ]:
            s.execute(
                text(
                    "INSERT INTO players (mlbam_id, full_name, throws) "
                    "VALUES (:id, :n, 'R') ON CONFLICT DO NOTHING"
                ),
                {"id": pid, "n": name},
            )
        # 5 predictions with descending prob
        for i, pid in enumerate(_TEST_BATTER_IDS):
            s.execute(
                text(
                    "INSERT INTO projected_lineups "
                    "(game_pk, team_id, batter_id, batting_order, is_confirmed) "
                    "VALUES (:gp, 9001, :b, :ord, true) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"gp": _TEST_GAME_PK, "b": pid, "ord": i + 1},
            )
            s.execute(
                text(
                    "INSERT INTO predictions "
                    "(game_pk, batter_id, pitcher_id, game_date, model_version, "
                    " matchup_components, projected_pas, prob_at_least_one_hr, "
                    " prob_at_least_two_hr, expected_hrs, feature_contributions) "
                    "VALUES (:gp, :b, :p, :d, :mv, "
                    " :mc, 4.29, :prob, 0.01, :eh, :fc) "
                    "ON CONFLICT (game_pk, batter_id, model_version) DO UPDATE SET "
                    "pitcher_id = EXCLUDED.pitcher_id, "
                    "game_date = EXCLUDED.game_date, "
                    "matchup_components = EXCLUDED.matchup_components, "
                    "projected_pas = EXCLUDED.projected_pas, "
                    "prob_at_least_one_hr = EXCLUDED.prob_at_least_one_hr, "
                    "prob_at_least_two_hr = EXCLUDED.prob_at_least_two_hr, "
                    "expected_hrs = EXCLUDED.expected_hrs, "
                    "feature_contributions = EXCLUDED.feature_contributions"
                ),
                {
                    "gp": _TEST_GAME_PK,
                    "b": pid,
                    "p": _TEST_PITCHER_ID,
                    "d": game_date,
                    "mv": model_version,
                    "mc": '{"starter_raw_prob": 0.2, "starter_calibrated_prob": 0.2}',
                    "prob": 0.99 - i * 0.01,
                    "eh": 1.04 - i * 0.01,
                    "fc": (
                        '{"b_barrel_pct_season": 0.05, '
                        '"park_hr_factor_hand": 0.03, '
                        '"b_p90_ev_season": 0.02, '
                        '"wx_wind_carry_cf": 0.01}'
                    ),
                },
            )
        s.execute(
            text(
                "INSERT INTO predictions "
                "(game_pk, batter_id, pitcher_id, game_date, model_version, "
                " matchup_components, projected_pas, prob_at_least_one_hr, "
                " prob_at_least_two_hr, expected_hrs, feature_contributions) "
                "VALUES (:gp, :b, :p, :d, 'v_stale_regression', "
                " :mc, 4.29, 1.0, 0.50, 1.20, :fc) "
                "ON CONFLICT (game_pk, batter_id, model_version) DO UPDATE SET "
                "game_date = EXCLUDED.game_date, "
                "prob_at_least_one_hr = EXCLUDED.prob_at_least_one_hr"
            ),
            {
                "gp": _TEST_GAME_PK,
                "b": _STALE_BATTER_ID,
                "p": _TEST_PITCHER_ID,
                "d": game_date,
                "mc": '{"starter_raw_prob": 1.0, "starter_calibrated_prob": 1.0}',
                "fc": '{"stale_model_feature": 1.0}',
            },
        )
        s.commit()
    _flush_picks_cache()


def _seed_odds(game_date: date) -> None:
    sf = _get_session_factory()
    with sf() as s:
        s.execute(
            text(
                "INSERT INTO odds_snapshots "
                "(snapshot_key, provider, sport_key, event_id, game_pk, game_date, commence_time, "
                " home_team, away_team, bookmaker_key, bookmaker_title, market_key, outcome_name, "
                " player_name, batter_id, price_american, point, implied_probability, "
                " no_vig_probability, market_last_update, fetched_at, raw_outcome) "
                "VALUES "
                "('test-odds-a', 'prop_line', 'baseball_mlb', 'evt_test', :gp, :d, :ts, "
                " 'Test Home', 'Test Away', 'draftkings', 'DraftKings', 'batter_home_runs', "
                " 'Over', 'Test Batter A', 700001, 700, 0.5, 0.125, 0.121, :lu, :fa, "
                " '{}'::jsonb), "
                "('test-odds-a-under', 'prop_line', 'baseball_mlb', 'evt_test', :gp, :d, :ts, "
                " 'Test Home', 'Test Away', 'draftkings', 'DraftKings', 'batter_home_runs', "
                " 'Under', 'Test Batter A', 700001, -1000, 0.5, 0.90909, 0.879, :lu, :fa, "
                ' \'{"name":"Under"}\'::jsonb), '
                "('test-odds-a-2hr', 'prop_line', 'baseball_mlb', 'evt_test', :gp, :d, :ts, "
                " 'Test Home', 'Test Away', 'draftkings', 'DraftKings', 'batter_home_runs', "
                " 'Yes', 'Test Batter A', 700001, 5000, NULL, 0.0196, NULL, :lu, :fa, "
                ' \'{"name":"2+ Home Runs","description":"Test Batter A"}\'::jsonb) '
                "ON CONFLICT (snapshot_key) DO UPDATE SET "
                "price_american = EXCLUDED.price_american, "
                "implied_probability = EXCLUDED.implied_probability, "
                "no_vig_probability = EXCLUDED.no_vig_probability, "
                "fetched_at = EXCLUDED.fetched_at"
            ),
            {
                "gp": _TEST_GAME_PK,
                "d": game_date,
                "ts": datetime(game_date.year, game_date.month, game_date.day, 23, 0, tzinfo=UTC),
                "lu": datetime(game_date.year, game_date.month, game_date.day, 16, 0, tzinfo=UTC),
                "fa": datetime(game_date.year, game_date.month, game_date.day, 16, 2, tzinfo=UTC),
            },
        )
        s.commit()
    _flush_picks_cache()


def _seed_matchup_feature_context(game_date: date) -> None:
    sf = _get_session_factory()
    with sf() as s:
        s.execute(
            text(
                "INSERT INTO matchup_features "
                "(game_date, game_pk, batter_id, pitcher_id, is_historical, "
                " opp_team_id, opp_bp_hr_per_pa_30d, opp_bp_hr_per_pa_season, "
                " opp_bp_barrel_pct_allowed_30d, opp_bp_barrel_pct_allowed_season, "
                " opp_bp_hardhit_pct_allowed_30d, opp_bp_hardhit_pct_allowed_season, "
                " opp_bp_lhb_hr_per_pa_season, opp_bp_rhb_hr_per_pa_season, "
                " opp_bp_pitches_last_3d, ctx_projected_pa, ctx_batting_order) "
                "VALUES "
                "(:d, :gp, 700001, :p, false, "
                " 9002, 0.041, 0.033, 0.122, 0.101, "
                " 0.488, 0.451, 0.037, 0.029, 142.0, 4.7, 1) "
                "ON CONFLICT (game_date, game_pk, batter_id, pitcher_id) "
                "DO UPDATE SET "
                "opp_team_id = EXCLUDED.opp_team_id, "
                "opp_bp_hr_per_pa_30d = EXCLUDED.opp_bp_hr_per_pa_30d, "
                "opp_bp_hr_per_pa_season = EXCLUDED.opp_bp_hr_per_pa_season, "
                "opp_bp_barrel_pct_allowed_30d = EXCLUDED.opp_bp_barrel_pct_allowed_30d, "
                "opp_bp_barrel_pct_allowed_season = EXCLUDED.opp_bp_barrel_pct_allowed_season, "
                "opp_bp_hardhit_pct_allowed_30d = EXCLUDED.opp_bp_hardhit_pct_allowed_30d, "
                "opp_bp_hardhit_pct_allowed_season = EXCLUDED.opp_bp_hardhit_pct_allowed_season, "
                "opp_bp_lhb_hr_per_pa_season = EXCLUDED.opp_bp_lhb_hr_per_pa_season, "
                "opp_bp_rhb_hr_per_pa_season = EXCLUDED.opp_bp_rhb_hr_per_pa_season, "
                "opp_bp_pitches_last_3d = EXCLUDED.opp_bp_pitches_last_3d, "
                "ctx_projected_pa = EXCLUDED.ctx_projected_pa, "
                "ctx_batting_order = EXCLUDED.ctx_batting_order"
            ),
            {"gp": _TEST_GAME_PK, "d": game_date, "p": _TEST_PITCHER_ID},
        )
        s.commit()
    _flush_picks_cache()


def _cleanup_predictions() -> None:
    sf = _get_session_factory()
    with sf() as s:
        s.execute(text("DELETE FROM odds_snapshots WHERE game_pk = :gp"), {"gp": _TEST_GAME_PK})
        s.execute(text("DELETE FROM predictions WHERE game_pk = :gp"), {"gp": _TEST_GAME_PK})
        s.execute(text("DELETE FROM matchup_features WHERE game_pk = :gp"), {"gp": _TEST_GAME_PK})
        s.execute(text("DELETE FROM projected_lineups WHERE game_pk = :gp"), {"gp": _TEST_GAME_PK})
        s.execute(text("DELETE FROM daily_schedule WHERE game_pk = :gp"), {"gp": _TEST_GAME_PK})
        s.commit()
    _flush_picks_cache()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_today_returns_sorted_by_prob(client) -> None:
    today = current_mlb_date()
    model_version = _active_model_version()
    _seed_predictions(today, model_version)
    try:
        r = await client.get("/picks/today")
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) >= 5
        # Top-5 we seeded are intentionally high-prob rows.
        top5 = [row for row in body if row["batter_id"] in _TEST_BATTER_IDS]
        assert len(top5) == 5
        probs = [row["prob_at_least_one_hr"] for row in top5]
        assert probs == sorted(probs, reverse=True)
        assert _STALE_BATTER_ID not in {row["batter_id"] for row in body}
        assert {row["model_version"] for row in top5} == {model_version}
        # Enrichment
        first = top5[0]
        assert first["batter_name"] == "Test Batter A"
        assert first["team_abbr"] == "TST"
        assert first["pitcher_name"] == "Test Pitcher"
        assert first["pitcher_throws"] == "R"
        assert first["park_name"] == "Test Park"
        assert len(first["top_contributing_features"]) >= 3
        assert "pitcher_hr_per_9_season" in first
        assert "wind_carry_cf" in first
    finally:
        _cleanup_predictions()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_today_respects_limit(client) -> None:
    today = current_mlb_date()
    _seed_predictions(today, _active_model_version())
    try:
        r = await client.get("/picks/today?limit=2")
        assert r.status_code == 200
        # Seeded 5; limit 2 → at most 2 for OUR seeds (other real rows may be
        # present; filter by id)
        body = r.json()
        our_rows = [b for b in body if b["batter_id"] in _TEST_BATTER_IDS]
        assert len(our_rows) <= 2
    finally:
        _cleanup_predictions()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_today_min_prob_filter(client) -> None:
    today = current_mlb_date()
    _seed_predictions(today, _active_model_version())
    try:
        r = await client.get("/picks/today?min_prob=0.15")
        assert r.status_code == 200
        body = r.json()
        for row in body:
            assert row["prob_at_least_one_hr"] >= 0.15
    finally:
        _cleanup_predictions()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_today_team_filter(client) -> None:
    today = current_mlb_date()
    _seed_predictions(today, _active_model_version())
    try:
        r = await client.get("/picks/today?team=TST")
        assert r.status_code == 200
        body = r.json()
        # Our seeded batters are in the TST lineup.
        our_rows = [b for b in body if b["batter_id"] in _TEST_BATTER_IDS]
        assert len(our_rows) == 5
        assert {row["team_abbr"] for row in our_rows} == {"TST"}

        r = await client.get("/picks/today?team=VIS")
        assert r.status_code == 200
        body = r.json()
        our_rows = [b for b in body if b["batter_id"] in _TEST_BATTER_IDS]
        assert our_rows == []
    finally:
        _cleanup_predictions()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_today_includes_latest_best_odds_edge_and_ev(client) -> None:
    today = current_mlb_date()
    _seed_predictions(today, _active_model_version())
    _seed_odds(today)
    try:
        r = await client.get("/picks/today?limit=10")
        assert r.status_code == 200, r.text
        pick = next(row for row in r.json() if row["batter_id"] == 700001)

        assert pick["odds_bookmaker"] == "DraftKings"
        assert pick["odds_price_american"] == 700
        assert pick["fair_odds_american"] == -9900
        assert pick["market_implied_probability"] == pytest.approx(0.125)
        assert pick["market_no_vig_probability"] == pytest.approx(0.121)
        assert pick["model_edge"] == pytest.approx(pick["prob_at_least_one_hr"] - 0.125)
        assert pick["expected_value_per_unit"] == pytest.approx(
            pick["prob_at_least_one_hr"] * 7 - (1 - pick["prob_at_least_one_hr"])
        )
    finally:
        _cleanup_predictions()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_today_exposes_full_game_probability_and_bullpen_context(client) -> None:
    today = current_mlb_date()
    model_version = _active_model_version()
    _seed_predictions(today, model_version)
    _seed_matchup_feature_context(today)
    sf = _get_session_factory()
    with sf() as s:
        s.execute(
            text(
                "UPDATE predictions "
                "SET prob_at_least_one_hr = 0.42, expected_hrs = 0.42, "
                "    matchup_components = :mc "
                "WHERE game_pk = :gp AND batter_id = 700001 AND model_version = :mv"
            ),
            {
                "gp": _TEST_GAME_PK,
                "mv": model_version,
                "mc": (
                    '{"probability_semantics": "full_game_hr", '
                    '"full_game_raw_prob": 0.39, '
                    '"full_game_calibrated_prob": 0.42, '
                    '"starter_raw_prob": 0.11, '
                    '"starter_calibrated_prob": 0.12}'
                ),
            },
        )
        s.commit()
    _flush_picks_cache()
    try:
        r = await client.get("/picks/today?limit=10")
        assert r.status_code == 200, r.text
        pick = next(row for row in r.json() if row["batter_id"] == 700001)

        assert pick["probability_semantics"] == "full_game_hr"
        assert pick["full_game_probability"] == pytest.approx(0.42)
        assert pick["starter_matchup_probability"] == pytest.approx(0.12)
        assert pick["model_rank_score"] == pytest.approx(0.39)
        assert pick["opp_team_id"] == 9002
        assert pick["opp_bp_hr_per_pa_30d"] == pytest.approx(0.041)
        assert pick["opp_bp_barrel_pct_allowed_30d"] == pytest.approx(0.122)
        assert pick["opp_bp_hardhit_pct_allowed_30d"] == pytest.approx(0.488)
        assert pick["opp_bp_pitches_last_3d"] == pytest.approx(142.0)
    finally:
        _cleanup_predictions()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_today_breaks_probability_ties_with_raw_model_score(client) -> None:
    today = current_mlb_date()
    model_version = _active_model_version()
    _seed_predictions(today, model_version)
    sf = _get_session_factory()
    with sf() as s:
        s.execute(
            text(
                "UPDATE predictions "
                "SET prob_at_least_one_hr = 0.75, expected_hrs = 0.75, "
                "    matchup_components = :mc "
                "WHERE game_pk = :gp AND batter_id = :b AND model_version = :mv"
            ),
            {
                "gp": _TEST_GAME_PK,
                "b": 700001,
                "mv": model_version,
                "mc": '{"starter_raw_prob": 0.10, "starter_calibrated_prob": 0.75}',
            },
        )
        s.execute(
            text(
                "UPDATE predictions "
                "SET prob_at_least_one_hr = 0.75, expected_hrs = 0.75, "
                "    matchup_components = :mc "
                "WHERE game_pk = :gp AND batter_id = :b AND model_version = :mv"
            ),
            {
                "gp": _TEST_GAME_PK,
                "b": 700002,
                "mv": model_version,
                "mc": '{"starter_raw_prob": 0.20, "starter_calibrated_prob": 0.75}',
            },
        )
        s.commit()
    _flush_picks_cache()
    try:
        r = await client.get("/picks/today?limit=10")
        assert r.status_code == 200, r.text
        tied = [row for row in r.json() if row["batter_id"] in {700001, 700002}]

        assert [row["batter_id"] for row in tied] == [700002, 700001]
        assert [row["model_rank_score"] for row in tied] == pytest.approx([0.20, 0.10])
    finally:
        _cleanup_predictions()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_picks_today_invalid_limit_returns_422(client) -> None:
    _flush_picks_cache()
    r = await client.get("/picks/today?limit=0")
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"

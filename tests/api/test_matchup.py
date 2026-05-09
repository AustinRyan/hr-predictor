"""Tests for /matchup endpoint."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from src.api.dependencies import _get_session_factory
from src.core.time import current_mlb_date
from src.models.artifacts import load_model


def _active_model_version() -> str:
    return load_model().version


def _seed_full_matchup(game_pk: int, batter_id: int, pitcher_id: int, game_date: date) -> None:
    sf = _get_session_factory()
    with sf() as s:
        s.execute(
            text(
                "INSERT INTO parks (park_id, name, elevation_ft, roof_type) "
                "VALUES (99721, 'Test Park MU', 500, 'open') ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO teams (team_id, abbr, name) "
                "VALUES (9021, 'HOM', 'Test Home') ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO teams (team_id, abbr, name) "
                "VALUES (9022, 'AWY', 'Test Away') ON CONFLICT DO NOTHING"
            )
        )
        s.execute(
            text(
                "INSERT INTO daily_schedule "
                "(game_pk, game_date, home_team_id, away_team_id, venue_id, game_start_utc, status) "
                "VALUES (:gp, :d, 9021, 9022, 99721, :ts, 'Scheduled') ON CONFLICT DO NOTHING"
            ),
            {
                "gp": game_pk,
                "d": game_date,
                "ts": datetime(game_date.year, game_date.month, game_date.day, 23, 0, tzinfo=UTC),
            },
        )
        s.execute(
            text(
                "INSERT INTO players (mlbam_id, full_name, bats) "
                "VALUES (:id, 'MU Batter', 'R') ON CONFLICT DO NOTHING"
            ),
            {"id": batter_id},
        )
        s.execute(
            text(
                "INSERT INTO players (mlbam_id, full_name, throws) "
                "VALUES (:id, 'MU Pitcher', 'R') ON CONFLICT DO NOTHING"
            ),
            {"id": pitcher_id},
        )
        s.execute(
            text(
                "INSERT INTO matchup_features "
                "(game_date, game_pk, batter_id, pitcher_id, is_historical, park_id, "
                " b_barrel_pct_season, b_p90_ev_season, b_hr_per_pa_season, b_pa_count_season, "
                " b_pulled_fb_pct_season, p_hr_per_9_season, p_barrel_pct_allowed_season, "
                " p_tto_penalty, park_hr_factor_hand, park_hr_factor_hand_3yr, "
                " wx_temperature_f, wx_humidity_pct, wx_wind_speed_mph, "
                " wx_air_density_relative, wx_wind_carry_cf, wx_is_roof_closed, "
                " ctx_batting_order, ctx_projected_pa, ctx_is_home, ctx_day_night, ctx_same_hand) "
                "VALUES (:d, :gp, :b, :p, FALSE, 99721, "
                " 0.18, 108.5, 0.08, 120, 0.42, 1.2, 0.09, 1.0833, "
                " 112.0, 108.0, 78.0, 45.0, 270.0, 0.94, 3.2, FALSE, "
                " 3, 4.4, TRUE, 'N', TRUE) ON CONFLICT DO NOTHING"
            ),
            {"gp": game_pk, "d": game_date, "b": batter_id, "p": pitcher_id},
        )
        s.commit()


def _seed_prediction(
    game_pk: int,
    batter_id: int,
    pitcher_id: int,
    game_date: date,
    model_version: str,
) -> None:
    sf = _get_session_factory()
    with sf() as s:
        s.execute(
            text(
                "INSERT INTO predictions "
                "(game_pk, batter_id, pitcher_id, game_date, model_version, "
                " matchup_components, projected_pas, prob_at_least_one_hr, "
                " prob_at_least_two_hr, expected_hrs, feature_contributions, generated_at) "
                "VALUES (:gp, :b, :p, :d, :mv, "
                " :mc, 4.4, 0.22, 0.018, 0.27, :fc, NOW()) "
                "ON CONFLICT (game_pk, batter_id, model_version) DO UPDATE SET "
                "game_date = EXCLUDED.game_date, "
                "prob_at_least_one_hr = EXCLUDED.prob_at_least_one_hr, "
                "matchup_components = EXCLUDED.matchup_components, "
                "feature_contributions = EXCLUDED.feature_contributions, "
                "generated_at = EXCLUDED.generated_at"
            ),
            {
                "gp": game_pk,
                "b": batter_id,
                "p": pitcher_id,
                "d": game_date,
                "mv": model_version,
                "mc": (
                    '{"probability_semantics": "full_game_hr", '
                    '"full_game_raw_prob": 0.25, '
                    '"full_game_calibrated_prob": 0.22, '
                    '"starter_raw_prob": 0.24, '
                    '"starter_calibrated_prob": 0.19, '
                    '"starter_signal_source": "full_game_artifact_starter_row", '
                    '"bullpen_raw_prob": null, "bullpen_calibrated_prob": null}'
                ),
                "fc": '{"b_barrel_pct_season": 0.05, "park_hr_factor_hand": 0.04, "wx_wind_carry_cf": 0.03, "b_p90_ev_season": 0.02, "p_tto_penalty": 0.01, "ctx_same_hand": -0.01, "b_pulled_fb_pct_season": 0.01, "p_hr_per_9_season": 0.008, "b_hr_per_pa_season": 0.007, "ctx_batting_order": 0.005, "ctx_projected_pa": 0.004}',
            },
        )
        s.execute(
            text(
                "INSERT INTO predictions "
                "(game_pk, batter_id, pitcher_id, game_date, model_version, "
                " matchup_components, projected_pas, prob_at_least_one_hr, "
                " prob_at_least_two_hr, expected_hrs, feature_contributions, generated_at) "
                "VALUES (:gp, :b, :p, :d, 'v_stale_regression', "
                " :mc, 4.4, 0.99, 0.50, 1.10, :fc, NOW() + INTERVAL '1 second') "
                "ON CONFLICT (game_pk, batter_id, model_version) DO UPDATE SET "
                "game_date = EXCLUDED.game_date, "
                "prob_at_least_one_hr = EXCLUDED.prob_at_least_one_hr, "
                "matchup_components = EXCLUDED.matchup_components, "
                "feature_contributions = EXCLUDED.feature_contributions, "
                "generated_at = EXCLUDED.generated_at"
            ),
            {
                "gp": game_pk,
                "b": batter_id,
                "p": pitcher_id,
                "d": game_date,
                "mc": '{"starter_raw_prob": 0.99, "starter_calibrated_prob": 0.99}',
                "fc": '{"stale_model_feature": 1.0}',
            },
        )
        s.commit()


def _cleanup(game_pk: int, batter_id: int) -> None:
    sf = _get_session_factory()
    with sf() as s:
        s.execute(text("DELETE FROM predictions WHERE game_pk = :gp"), {"gp": game_pk})
        s.execute(text("DELETE FROM matchup_features WHERE game_pk = :gp"), {"gp": game_pk})
        s.execute(text("DELETE FROM daily_schedule WHERE game_pk = :gp"), {"gp": game_pk})
        s.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_matchup_detail_full(client) -> None:
    gp, b, p = 998001, 720001, 720100
    today = current_mlb_date()
    model_version = _active_model_version()
    _seed_full_matchup(gp, b, p, today)
    _seed_prediction(gp, b, p, today, model_version)
    try:
        r = await client.get(f"/matchup/{gp}/{b}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["game"]["game_pk"] == gp
        assert body["game"]["ctx_batting_order"] == 3
        assert body["batter"]["mlbam_id"] == b
        assert body["batter"]["b_barrel_pct_season"] == 0.18
        assert body["pitcher"]["mlbam_id"] == p
        assert body["pitcher"]["p_tto_penalty"] == 1.0833
        assert body["park"]["park_name"] == "Test Park MU"
        assert body["weather"]["temperature_f"] == 78.0
        assert body["weather"]["wind_carry_cf"] == 3.2
        assert body["prediction"] is not None
        assert body["prediction"]["prob_at_least_one_hr"] == 0.22
        assert body["prediction"]["probability_semantics"] == "full_game_hr"
        assert body["prediction"]["full_game_calibrated_prob"] == 0.22
        assert body["prediction"]["starter_calibrated_prob"] == 0.19
        assert body["prediction"]["starter_signal_source"] == "full_game_artifact_starter_row"
        assert body["prediction"]["model_version"] == model_version
        assert len(body["prediction"]["top_contributing_features"]) == 10
        # Order: top feature has largest absolute contribution
        first = body["prediction"]["top_contributing_features"][0]
        assert first["name"] == "b_barrel_pct_season"
        assert first["contribution"] == 0.05
    finally:
        _cleanup(gp, b)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_matchup_detail_404(client) -> None:
    r = await client.get("/matchup/0/0")
    assert r.status_code == 404
    assert r.json()["error"].startswith("no matchup_features")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_matchup_detail_no_prediction(client) -> None:
    """Matchup row exists, no prediction yet → prediction field is null."""
    gp, b, p = 998002, 720002, 720101
    today = current_mlb_date()
    _seed_full_matchup(gp, b, p, today)
    try:
        r = await client.get(f"/matchup/{gp}/{b}")
        assert r.status_code == 200
        body = r.json()
        assert body["prediction"] is None
        assert body["batter"]["full_name"] == "MU Batter"
    finally:
        _cleanup(gp, b)

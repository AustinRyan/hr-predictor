"""/matchup endpoint."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_model
from src.api.schemas.matchup import (
    BatterProfile,
    FeatureContribution,
    GameContext,
    MatchupDetail,
    ParkContext,
    PitcherProfile,
    PredictionBreakdown,
    WeatherContext,
)
from src.models.artifacts import LoadedModel

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/matchup", tags=["matchup"])


_MATCHUP_SQL = text("""
    SELECT
        mf.*,
        ds.game_start_utc,
        ds.home_team_id,
        ds.away_team_id,
        pk.name AS park_name,
        pk.elevation_ft AS park_elev_ft,
        pk.roof_type AS park_roof_type,
        bp.full_name AS batter_full_name,
        bp.bats AS batter_bats,
        pp.full_name AS pitcher_full_name,
        pp.throws AS pitcher_throws,
        tm_home.abbr AS home_abbr,
        tm_away.abbr AS away_abbr
    FROM matchup_features mf
    LEFT JOIN daily_schedule ds ON ds.game_pk = mf.game_pk
    LEFT JOIN parks pk ON pk.park_id = mf.park_id
    LEFT JOIN players bp ON bp.mlbam_id = mf.batter_id
    LEFT JOIN players pp ON pp.mlbam_id = mf.pitcher_id
    LEFT JOIN teams tm_home ON tm_home.team_id = ds.home_team_id
    LEFT JOIN teams tm_away ON tm_away.team_id = ds.away_team_id
    WHERE mf.game_pk = :game_pk AND mf.batter_id = :batter_id
    ORDER BY mf.game_date DESC
    LIMIT 1
    """)

_PREDICTION_SQL = text("""
    SELECT prob_at_least_one_hr, prob_at_least_two_hr, expected_hrs,
           matchup_components, feature_contributions, model_version, generated_at
    FROM predictions
    WHERE game_pk = :game_pk
      AND batter_id = :batter_id
      AND model_version = :model_version
    ORDER BY generated_at DESC
    LIMIT 1
    """)


def _prediction_from_row(row) -> PredictionBreakdown:
    mc = row["matchup_components"] or {}
    fc_raw = row["feature_contributions"] or {}
    sorted_items = sorted(fc_raw.items(), key=lambda kv: -abs(kv[1]))[:10]
    contributions = [FeatureContribution(name=k, contribution=float(v)) for k, v in sorted_items]
    return PredictionBreakdown(
        prob_at_least_one_hr=(
            float(row["prob_at_least_one_hr"]) if row["prob_at_least_one_hr"] is not None else None
        ),
        prob_at_least_two_hr=(
            float(row["prob_at_least_two_hr"]) if row["prob_at_least_two_hr"] is not None else None
        ),
        expected_hrs=float(row["expected_hrs"]) if row["expected_hrs"] is not None else None,
        starter_raw_prob=mc.get("starter_raw_prob"),
        starter_calibrated_prob=mc.get("starter_calibrated_prob"),
        bullpen_raw_prob=mc.get("bullpen_raw_prob"),
        bullpen_calibrated_prob=mc.get("bullpen_calibrated_prob"),
        top_contributing_features=contributions,
        model_version=row["model_version"],
        generated_at=row["generated_at"],
    )


@router.get("/{game_pk}/{batter_id}", response_model=MatchupDetail)
def matchup_detail(
    game_pk: int,
    batter_id: int,
    db: Annotated[Session, Depends(get_db)],
    loaded: Annotated[LoadedModel, Depends(get_model)],
) -> MatchupDetail:
    row = db.execute(_MATCHUP_SQL, {"game_pk": game_pk, "batter_id": batter_id}).mappings().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no matchup_features for game_pk={game_pk}, batter_id={batter_id}",
        )

    pred_row = (
        db.execute(
            _PREDICTION_SQL,
            {"game_pk": game_pk, "batter_id": batter_id, "model_version": loaded.version},
        )
        .mappings()
        .first()
    )
    prediction = _prediction_from_row(pred_row) if pred_row else None

    game = GameContext(
        game_pk=int(row["game_pk"]),
        game_date=row["game_date"],
        game_start_utc=row["game_start_utc"],
        home_team_abbr=row["home_abbr"],
        away_team_abbr=row["away_abbr"],
        ctx_batting_order=row.get("ctx_batting_order"),
        ctx_projected_pa=row.get("ctx_projected_pa"),
        ctx_is_home=row.get("ctx_is_home"),
        ctx_day_night=row.get("ctx_day_night"),
        ctx_same_hand=row.get("ctx_same_hand"),
    )
    batter = BatterProfile(
        mlbam_id=int(row["batter_id"]),
        full_name=row["batter_full_name"],
        bats=row["batter_bats"],
        b_barrel_pct_season=row.get("b_barrel_pct_season"),
        b_p90_ev_season=row.get("b_p90_ev_season"),
        b_avg_ev_season=row.get("b_avg_ev_season"),
        b_pulled_fb_pct_season=row.get("b_pulled_fb_pct_season"),
        b_hr_per_pa_season=row.get("b_hr_per_pa_season"),
        b_vs_lhp_hr_per_pa_reg=row.get("b_vs_lhp_hr_per_pa_reg"),
        b_vs_rhp_hr_per_pa_reg=row.get("b_vs_rhp_hr_per_pa_reg"),
        b_pa_count_season=row.get("b_pa_count_season"),
    )
    pitcher = PitcherProfile(
        mlbam_id=int(row["pitcher_id"]),
        full_name=row["pitcher_full_name"],
        throws=row["pitcher_throws"],
        p_hr_per_9_season=row.get("p_hr_per_9_season"),
        p_barrel_pct_allowed_season=row.get("p_barrel_pct_allowed_season"),
        p_vs_lhb_hr_rate=row.get("p_vs_lhb_hr_rate"),
        p_vs_rhb_hr_rate=row.get("p_vs_rhb_hr_rate"),
        p_primary_pitch=row.get("p_primary_pitch"),
        p_ff_velo_avg=row.get("p_ff_velo_avg"),
        p_tto_penalty=row.get("p_tto_penalty"),
    )
    park = ParkContext(
        park_id=row.get("park_id"),
        park_name=row["park_name"],
        elevation_ft=row["park_elev_ft"],
        roof_type=row["park_roof_type"],
        park_hr_factor_hand=row.get("park_hr_factor_hand"),
        park_hr_factor_hand_3yr=row.get("park_hr_factor_hand_3yr"),
    )
    # Note: matchup_features stores wind as speed + three `wx_wind_carry_*`
    # components (LF/CF/RF); raw wind_direction_deg is not persisted.
    weather = WeatherContext(
        temperature_f=row.get("wx_temperature_f"),
        humidity_pct=row.get("wx_humidity_pct"),
        wind_speed_mph=row.get("wx_wind_speed_mph"),
        wind_direction_deg=None,
        air_density_relative=row.get("wx_air_density_relative"),
        wind_carry_lf=row.get("wx_wind_carry_lf"),
        wind_carry_cf=row.get("wx_wind_carry_cf"),
        wind_carry_rf=row.get("wx_wind_carry_rf"),
        is_roof_closed=row.get("wx_is_roof_closed"),
    )

    return MatchupDetail(
        game=game,
        batter=batter,
        pitcher=pitcher,
        park=park,
        weather=weather,
        prediction=prediction,
    )

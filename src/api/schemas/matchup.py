"""Response models for /matchup endpoint."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class BatterProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    mlbam_id: int
    full_name: str | None
    bats: str | None
    # Rolling + splits from the matchup_features row
    b_barrel_pct_season: float | None = None
    b_p90_ev_season: float | None = None
    b_avg_ev_season: float | None = None
    b_pulled_fb_pct_season: float | None = None
    b_hr_per_pa_season: float | None = None
    b_vs_lhp_hr_per_pa_reg: float | None = None
    b_vs_rhp_hr_per_pa_reg: float | None = None
    b_pa_count_season: int | None = None


class PitcherProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    mlbam_id: int
    full_name: str | None
    throws: str | None
    p_hr_per_9_season: float | None = None
    p_barrel_pct_allowed_season: float | None = None
    p_vs_lhb_hr_rate: float | None = None
    p_vs_rhb_hr_rate: float | None = None
    p_primary_pitch: str | None = None
    p_ff_velo_avg: float | None = None
    p_tto_penalty: float | None = None


class ParkContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    park_id: int | None
    park_name: str | None
    elevation_ft: int | None
    roof_type: str | None
    park_hr_factor_hand: float | None
    park_hr_factor_hand_3yr: float | None


class WeatherContext(BaseModel):
    """Weather at game start. NULL for dome games (climate-controlled) and
    for historical games where no archive was backfilled in reach."""

    model_config = ConfigDict(frozen=True)

    temperature_f: float | None = None
    humidity_pct: float | None = None
    wind_speed_mph: float | None = None
    wind_direction_deg: float | None = None
    air_density_relative: float | None = None
    wind_carry_lf: float | None = None
    wind_carry_cf: float | None = None
    wind_carry_rf: float | None = None
    is_roof_closed: bool | None = None


class GameContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    game_pk: int
    game_date: date
    game_start_utc: datetime | None
    home_team_abbr: str | None
    away_team_abbr: str | None
    ctx_batting_order: int | None
    ctx_projected_pa: float | None
    ctx_is_home: bool | None
    ctx_day_night: str | None
    ctx_same_hand: bool | None


class FeatureContribution(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    contribution: float


class PredictionBreakdown(BaseModel):
    """The headline probability + audit info."""

    model_config = ConfigDict(frozen=True)

    prob_at_least_one_hr: float | None
    prob_at_least_two_hr: float | None
    expected_hrs: float | None
    starter_raw_prob: float | None
    starter_calibrated_prob: float | None
    bullpen_raw_prob: float | None
    bullpen_calibrated_prob: float | None
    top_contributing_features: list[FeatureContribution]
    model_version: str | None
    generated_at: datetime | None


class MatchupDetail(BaseModel):
    """Full GET /matchup/{game_pk}/{batter_id} response."""

    model_config = ConfigDict(frozen=True)

    game: GameContext
    batter: BatterProfile
    pitcher: PitcherProfile
    park: ParkContext
    weather: WeatherContext
    prediction: PredictionBreakdown | None  # None if no prediction exists yet

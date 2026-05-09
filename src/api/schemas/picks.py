"""Pydantic response models for /picks endpoints."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class FeatureContribution(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    contribution: float  # signed SHAP value


class PickSummary(BaseModel):
    """One pick displayed on the ranked today-list."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    batter_id: int
    batter_name: str | None
    batter_bats: str | None = None  # L / R / S
    batter_position: str | None = None  # 1B / 2B / ...
    team_abbr: str | None

    game_pk: int
    game_date: date
    game_start_utc: datetime | None
    park_name: str | None
    home_team_abbr: str | None = None
    away_team_abbr: str | None = None

    pitcher_id: int
    pitcher_name: str | None
    pitcher_throws: str | None

    prob_at_least_one_hr: float = Field(ge=0.0, le=1.0)
    expected_hrs: float | None = None
    model_rank_score: float | None = None
    probability_semantics: str | None = None
    full_game_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    starter_matchup_probability: float | None = Field(default=None, ge=0.0, le=1.0)

    # Latest best available batter-HR Over odds, if sportsbook odds have
    # been ingested for this slate/player.
    odds_bookmaker: str | None = None
    odds_bookmaker_key: str | None = None
    odds_price_american: int | None = None
    odds_point: float | None = None
    market_implied_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    market_no_vig_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    fair_odds_american: int | None = None
    model_edge: float | None = None
    expected_value_per_unit: float | None = None
    odds_fetched_at: datetime | None = None

    # Headline stats surfaced on the hero pick card — pulled from the
    # matchup_features row that drove the prediction so the UI shows
    # per-batter values instead of hardcoded placeholders.
    barrel_pct_season: float | None = None  # 0..1
    p90_ev_season: float | None = None  # mph
    park_hr_factor_hand: float | None = None  # 100 = neutral
    pitcher_hr_per_9_season: float | None = None
    pitcher_barrel_pct_allowed_season: float | None = None
    batting_order: int | None = None
    projected_pas: float | None = None
    wind_carry_cf: float | None = None
    temperature_f: float | None = None
    air_density_relative: float | None = None

    # Opposing team bullpen context used by full-game model artifacts.
    opp_team_id: int | None = None
    opp_bp_hr_per_pa_30d: float | None = None
    opp_bp_hr_per_pa_season: float | None = None
    opp_bp_barrel_pct_allowed_30d: float | None = None
    opp_bp_barrel_pct_allowed_season: float | None = None
    opp_bp_hardhit_pct_allowed_30d: float | None = None
    opp_bp_hardhit_pct_allowed_season: float | None = None
    opp_bp_lhb_hr_per_pa_season: float | None = None
    opp_bp_rhb_hr_per_pa_season: float | None = None
    opp_bp_pitches_last_3d: float | None = None

    top_contributing_features: list[FeatureContribution] = Field(default_factory=list)

    model_version: str

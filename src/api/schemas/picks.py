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

    top_contributing_features: list[FeatureContribution] = Field(default_factory=list)

    model_version: str

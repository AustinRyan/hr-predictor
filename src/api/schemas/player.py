"""Pydantic response models for /player endpoints."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class PlayerProfile(BaseModel):
    """Core identity + physical profile."""

    model_config = ConfigDict(frozen=True)

    mlbam_id: int
    full_name: str | None
    first_name: str | None
    last_name: str | None
    bats: str | None  # L / R / S
    throws: str | None  # L / R
    primary_position: str | None
    active: bool


class PlayerRollingStats(BaseModel):
    """Most-recent matchup_features row for this player as batter (last 30d window).

    All fields nullable; a player with no recent at-bats returns all None.
    """

    model_config = ConfigDict(frozen=True)

    as_of: date | None
    b_barrel_pct_30d: float | None = None
    b_hardhit_pct_30d: float | None = None
    b_avg_ev_30d: float | None = None
    b_p90_ev_30d: float | None = None
    b_avg_la_30d: float | None = None
    b_pulled_fb_pct_30d: float | None = None
    b_xwobacon_30d: float | None = None
    b_hr_per_pa_30d: float | None = None
    b_pa_count_30d: int | None = None
    b_barrel_pct_season: float | None = None
    b_hr_per_pa_season: float | None = None
    b_pa_count_season: int | None = None


class PlayerTodayPrediction(BaseModel):
    """A prediction for today, if any (null if player isn't in a game today)."""

    model_config = ConfigDict(frozen=True)

    game_pk: int
    pitcher_id: int
    prob_at_least_one_hr: float
    expected_hrs: float | None
    projected_pas: float | None
    model_version: str


class PlayerDetail(BaseModel):
    """Full response for GET /player/{mlbam_id}."""

    model_config = ConfigDict(frozen=True)

    profile: PlayerProfile
    rolling: PlayerRollingStats
    today_prediction: PlayerTodayPrediction | None

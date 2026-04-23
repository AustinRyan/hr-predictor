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
    team_abbr: str | None

    game_pk: int
    game_date: date
    game_start_utc: datetime | None
    park_name: str | None

    pitcher_id: int
    pitcher_name: str | None
    pitcher_throws: str | None

    prob_at_least_one_hr: float = Field(ge=0.0, le=1.0)
    expected_hrs: float | None = None

    top_contributing_features: list[FeatureContribution] = Field(default_factory=list)

    model_version: str

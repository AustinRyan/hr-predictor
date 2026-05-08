"""Full-game home-run training data loader.

This dataset has one row per batter-game. The feature snapshot comes from
the starter matchup row in ``matchup_features``; the label is whether the
batter homered anywhere in that game, including against relievers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy import Engine, text

from src.core.db import get_engine
from src.models.data import FEATURE_COLUMNS

FULL_GAME_FEATURE_COLUMNS: list[str] = [c for c in FEATURE_COLUMNS if c != "opp_team_id"]


@dataclass(slots=True, frozen=True)
class FullGameFeatureFrame:
    """A full-game HR modeling slice."""

    X: pd.DataFrame
    y: pd.Series
    dates: pd.Series
    metadata: pd.DataFrame


@dataclass(slots=True, frozen=True)
class FullGameTrainValTest:
    """Three non-overlapping full-game training slices."""

    train: FullGameFeatureFrame
    val: FullGameFeatureFrame
    test: FullGameFeatureFrame


_TRAIN_START = date(2021, 4, 1)
_TRAIN_END = date(2023, 10, 31)
_VAL_START = date(2024, 4, 1)
_VAL_END = date(2024, 10, 31)
_TEST_START = date(2025, 4, 1)


def _coerce_dates(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.date
    return series.map(lambda v: v if isinstance(v, date) else pd.Timestamp(v).date())


def _build_query() -> str:
    feature_select = ",\n        ".join(f"mf.{column}" for column in FULL_GAME_FEATURE_COLUMNS)
    return f"""
    WITH batter_opponents AS (
        SELECT DISTINCT
            sp.game_pk,
            sp.batter AS batter_id,
            CASE
                WHEN sp.inning_topbot = 'Top' THEN g.home_team_id
                WHEN sp.inning_topbot = 'Bot' THEN g.away_team_id
                ELSE NULL
            END AS opp_team_id
        FROM statcast_pitches sp
        JOIN games g ON g.game_pk = sp.game_pk
        WHERE sp.game_date BETWEEN :start AND :end
          AND sp.inning_topbot IN ('Top', 'Bot')
    ),
    historical_pitch_teams AS (
        SELECT
            sp.game_pk,
            sp.at_bat_number,
            sp.pitch_number,
            sp.pitcher AS pitcher_id,
            sp.inning,
            CASE
                WHEN sp.inning_topbot = 'Top' THEN g.home_team_id
                WHEN sp.inning_topbot = 'Bot' THEN g.away_team_id
                ELSE NULL
            END AS pitcher_team_id
        FROM statcast_pitches sp
        JOIN games g ON g.game_pk = sp.game_pk
        WHERE sp.game_date BETWEEN :start AND :end
          AND sp.inning_topbot IN ('Top', 'Bot')
    ),
    team_game_starters AS (
        SELECT DISTINCT ON (game_pk, pitcher_team_id)
            game_pk,
            pitcher_team_id,
            pitcher_id AS starter_pitcher_id
        FROM historical_pitch_teams
        WHERE pitcher_team_id IS NOT NULL
          AND inning = 1
        ORDER BY game_pk, pitcher_team_id, at_bat_number, pitch_number
    )
    SELECT
        mf.game_date,
        mf.game_pk,
        mf.batter_id,
        mf.pitcher_id AS starter_pitcher_id,
        EXISTS (
            SELECT 1
            FROM statcast_pitches sp_hr
            WHERE sp_hr.game_pk = mf.game_pk
              AND sp_hr.batter = mf.batter_id
              AND sp_hr.events = 'home_run'
        ) AS full_game_hr,
        {feature_select}
    FROM matchup_features mf
    JOIN batter_opponents bo
      ON bo.game_pk = mf.game_pk
     AND bo.batter_id = mf.batter_id
    JOIN team_game_starters tgs
      ON tgs.game_pk = mf.game_pk
     AND tgs.pitcher_team_id = bo.opp_team_id
     AND tgs.starter_pitcher_id = mf.pitcher_id
    WHERE mf.is_historical = TRUE
      AND mf.game_date BETWEEN :start AND :end
    ORDER BY mf.game_date, mf.game_pk, mf.batter_id
    """


def _frame_from_rows(rows: pd.DataFrame) -> FullGameFeatureFrame:
    dates = _coerce_dates(rows["game_date"]).reset_index(drop=True)
    y = rows["full_game_hr"].reset_index(drop=True).astype(int)
    features = rows.loc[:, FULL_GAME_FEATURE_COLUMNS].reset_index(drop=True)
    metadata = rows.loc[
        :,
        ["game_date", "game_pk", "batter_id", "starter_pitcher_id"],
    ].reset_index(drop=True)
    metadata["game_date"] = _coerce_dates(metadata["game_date"])
    return FullGameFeatureFrame(X=features, y=y, dates=dates, metadata=metadata)


def load_full_game_training_data(
    start_date: date,
    end_date: date,
    *,
    engine: Engine | None = None,
) -> FullGameFeatureFrame:
    """Pull one full-game training row per batter-game in ``[start_date, end_date]``."""
    engine = engine or get_engine()
    with engine.connect() as conn:
        rows = pd.read_sql(
            text(_build_query()),
            conn,
            params={"start": start_date, "end": end_date},
        )
    return _frame_from_rows(rows)


def full_game_time_based_split(*, engine: Engine | None = None) -> FullGameTrainValTest:
    """Return full-game train/val/test slices using the project date boundaries."""
    engine = engine or get_engine()
    with engine.connect() as conn:
        latest_row = conn.execute(
            text(
                "SELECT MAX(game_date) AS max_date FROM matchup_features "
                "WHERE is_historical = TRUE"
            )
        ).one()
    latest_date: date | None = latest_row.max_date
    test_end = latest_date if latest_date is not None else _TEST_START

    return FullGameTrainValTest(
        train=load_full_game_training_data(_TRAIN_START, _TRAIN_END, engine=engine),
        val=load_full_game_training_data(_VAL_START, _VAL_END, engine=engine),
        test=load_full_game_training_data(_TEST_START, test_end, engine=engine),
    )

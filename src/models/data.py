"""Feature loader and time-based train/val/test splitter.

Reads historical rows from ``matchup_features`` (populated by the Phase 3
builder) and hands them to downstream model training + evaluation.

``FEATURE_COLUMNS`` is enumerated at module-load time from the
``MatchupFeature`` SQLAlchemy table. It is the single source of truth for
every downstream consumer — training, evaluation, inference, and
artifact persistence all import this list to guarantee a stable,
identical column order. Do not hand-maintain a parallel list anywhere.

Excluded columns fall in four categories:

* Composite-PK keys: ``game_date``, ``game_pk``, ``batter_id``,
  ``pitcher_id`` — identifiers, not features.
* Label: ``hr_on_pa``.
* Metadata: ``is_historical`` (filter column), ``built_at`` (audit
  timestamp).
* String columns we haven't encoded yet: ``p_primary_pitch``,
  ``ctx_day_night``. These would need categorical handling before
  XGBoost can consume them; deferred.

Everything else on ``MatchupFeature`` — numeric rolling windows,
handedness splits, pitch-type matrix, bat tracking, pitcher profile,
bullpen, park factors, weather, remaining context (``ctx_is_home``,
``ctx_same_hand``, ``ctx_batting_order``, etc.) — is kept. Booleans are
fine; XGBoost treats them as 0/1 natively.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import (
    BigInteger,
    Boolean,
    Engine,
    Float,
    Integer,
    SmallInteger,
    text,
)

from src.core.db import get_engine
from src.core.models import MatchupFeature

_EXCLUDED_COLUMNS: frozenset[str] = frozenset(
    {
        # Composite-PK / identifier columns.
        "game_date",
        "game_pk",
        "batter_id",
        "pitcher_id",
        # Label.
        "hr_on_pa",
        # Metadata.
        "is_historical",
        "built_at",
        # String columns requiring encoding we're not doing yet.
        "p_primary_pitch",
        "ctx_day_night",
    }
)

_NUMERIC_TYPES: tuple[type, ...] = (
    Integer,
    SmallInteger,
    BigInteger,
    Float,
    Boolean,
)


def _enumerate_feature_columns() -> list[str]:
    """Return the ordered list of numeric feature columns from ``MatchupFeature``.

    Iterates in the order declared on the SQLAlchemy table (which mirrors
    the ORM class definition), skips excluded names, and keeps only
    columns whose type is an instance of one of the numeric-ish types
    XGBoost can ingest directly.
    """
    names: list[str] = []
    for column in MatchupFeature.__table__.columns:
        if column.name in _EXCLUDED_COLUMNS:
            continue
        if not isinstance(column.type, _NUMERIC_TYPES):
            continue
        names.append(column.name)
    return names


FEATURE_COLUMNS: list[str] = _enumerate_feature_columns()


@dataclass(slots=True)
class FeatureFrame:
    """A loaded slice of ``matchup_features`` ready for modeling.

    Attributes
    ----------
    X:
        Feature matrix, rows x ``FEATURE_COLUMNS`` (same order).
    y:
        Binary label (``hr_on_pa``) as 0/1 integers.
    dates:
        ``pd.Series[datetime.date]`` — one Python ``date`` per row. Kept
        as native ``date`` (not pandas datetime) because
        ``precision_at_top_k`` groups by raw date.
    metadata:
        Summary of the slice: at minimum ``row_count``, ``hr_rate``,
        ``date_range`` ``(min_date, max_date)``.
    """

    X: pd.DataFrame
    y: pd.Series
    dates: pd.Series
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TrainValTest:
    """Three non-overlapping time-ordered slices."""

    train: FeatureFrame
    val: FeatureFrame
    test: FeatureFrame


# Split boundaries (locked in PROMPT.md § 2). Train goes through the end
# of the 2023 regular season; validation is 2024; test is 2025 onward
# up to whatever the most recent historical row is.
_TRAIN_START = date(2021, 4, 1)
_TRAIN_END = date(2023, 10, 31)
_VAL_START = date(2024, 4, 1)
_VAL_END = date(2024, 10, 31)
_TEST_START = date(2025, 4, 1)


def _build_query() -> str:
    """SQL template: select the label + feature columns + date for a window.

    Returns a single ``SELECT`` string parameterized on ``:start`` and
    ``:end``. Ordering by ``game_date`` keeps the resulting frames
    deterministic and friendly to per-date groupings downstream.
    """
    col_list = ", ".join(FEATURE_COLUMNS)
    return (
        "SELECT game_date, hr_on_pa, "
        f"{col_list} "
        "FROM matchup_features "
        "WHERE is_historical = TRUE "
        "AND hr_on_pa IS NOT NULL "
        "AND game_date BETWEEN :start AND :end "
        "ORDER BY game_date"
    )


def _coerce_dates(series: pd.Series) -> pd.Series:
    """Return a ``Series`` of python ``datetime.date`` objects.

    pandas may read ``DATE`` columns as ``datetime64[ns]`` or as object
    dtype depending on driver/version. Normalize to native
    ``datetime.date`` so callers can compare/group by raw date.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.date
    return series.map(lambda v: v if isinstance(v, date) else pd.Timestamp(v).date())


def _frame_from_rows(rows: pd.DataFrame) -> FeatureFrame:
    """Split a raw query result into ``FeatureFrame`` components.

    ``rows`` must contain ``game_date``, ``hr_on_pa``, and every
    ``FEATURE_COLUMNS`` entry (in that order is fine; we re-select).
    """
    dates = _coerce_dates(rows["game_date"]).reset_index(drop=True)

    # Label: may come back as bool or 0/1 int; cast to int for XGBoost.
    # `.astype(int)` on a bool-dtype Series produces 0/1 just the same
    # as on a numeric Series, so one path handles both.
    y = rows["hr_on_pa"].reset_index(drop=True).astype(int)

    # Feature matrix — reselect in FEATURE_COLUMNS order to be explicit
    # about ordering even if the query's ordering drifts. `X` is the
    # conventional ML capitalization for a feature matrix; we allow the
    # N806 uppercase-local-variable warning here.
    features = rows.loc[:, FEATURE_COLUMNS].reset_index(drop=True)

    if len(dates) == 0:
        date_range: tuple[date | None, date | None] = (None, None)
    else:
        date_range = (dates.min(), dates.max())

    metadata: dict[str, Any] = {
        "row_count": int(len(features)),
        "hr_rate": float(y.mean()) if len(y) else 0.0,
        "date_range": date_range,
    }

    return FeatureFrame(X=features, y=y, dates=dates, metadata=metadata)


def load_training_data(
    start_date: date,
    end_date: date,
    *,
    engine: Engine | None = None,
) -> FeatureFrame:
    """Pull historical ``matchup_features`` in ``[start_date, end_date]``.

    Only rows with ``is_historical = TRUE`` and non-null ``hr_on_pa`` are
    returned. Both bounds are inclusive.
    """
    if engine is None:
        engine = get_engine()

    sql = _build_query()
    with engine.connect() as conn:
        rows = pd.read_sql(
            text(sql),
            conn,
            params={"start": start_date, "end": end_date},
        )
    return _frame_from_rows(rows)


def time_based_split(*, engine: Engine | None = None) -> TrainValTest:
    """Return train/val/test slices with the phase-locked date bounds.

    * Train: 2021-04-01 .. 2023-10-31
    * Val:   2024-04-01 .. 2024-10-31
    * Test:  2025-04-01 .. most recent historical date

    Three separate queries — simpler, parallelizable later if needed,
    and avoids loading a 600k-row frame only to slice it. Absolutely no
    random shuffle.
    """
    if engine is None:
        engine = get_engine()

    # Test's upper bound is the most recent historical date in the
    # table. Query it once so that slice is always bounded correctly.
    with engine.connect() as conn:
        latest_row = conn.execute(
            text(
                "SELECT MAX(game_date) AS max_date FROM matchup_features "
                "WHERE is_historical = TRUE AND hr_on_pa IS NOT NULL"
            )
        ).one()
    latest_date: date | None = latest_row.max_date
    test_end: date = latest_date if latest_date is not None else _TEST_START

    train = load_training_data(_TRAIN_START, _TRAIN_END, engine=engine)
    val = load_training_data(_VAL_START, _VAL_END, engine=engine)
    test = load_training_data(_TEST_START, test_end, engine=engine)
    return TrainValTest(train=train, val=val, test=test)

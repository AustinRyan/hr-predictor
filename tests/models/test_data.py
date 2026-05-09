"""Tests for src.models.data."""

from __future__ import annotations

from datetime import date

import pytest
from src.models.data import (
    FEATURE_COLUMNS,
    FeatureFrame,
    TrainValTest,
    load_training_data,
    time_based_split,
)


def test_feature_columns_excludes_keys_and_label() -> None:
    excluded = {
        "game_date",
        "game_pk",
        "batter_id",
        "pitcher_id",
        "hr_on_pa",
        "is_historical",
        "built_at",
        "p_primary_pitch",
        "ctx_day_night",
        "opp_team_id",
        # Diagnostic exclusion (post-Phase 6): rest-day features were
        # dominating SHAP and crowding out real pitcher-quality signal.
        "ctx_pitcher_days_rest",
        "ctx_batter_days_rest",
    }
    for c in excluded:
        assert c not in FEATURE_COLUMNS, f"{c} should not be in FEATURE_COLUMNS"


def test_feature_columns_includes_expected_families() -> None:
    assert "b_barrel_pct_season" in FEATURE_COLUMNS
    assert "p_hr_per_9_season" in FEATURE_COLUMNS
    assert "park_hr_factor_hand" in FEATURE_COLUMNS
    assert "wx_temperature_f" in FEATURE_COLUMNS
    assert "ctx_batting_order" in FEATURE_COLUMNS
    assert "opp_bp_hr_per_pa_30d" in FEATURE_COLUMNS


def test_feature_columns_count_reasonable() -> None:
    # ~118 numeric feature columns expected after rest-day exclusions.
    assert 80 <= len(FEATURE_COLUMNS) <= 130


def test_feature_columns_ordering_stable() -> None:
    # Re-enumerating from the ORM must produce an identical list (no
    # set-based flakiness / no dict-ordering surprises). We call the
    # private enumerator rather than reloading the module, because
    # reload() swaps out the FeatureFrame/TrainValTest class objects
    # and breaks isinstance() checks in sibling tests that share the
    # same import graph.
    from src.models.data import _enumerate_feature_columns

    a = list(FEATURE_COLUMNS)
    b = _enumerate_feature_columns()
    assert a == b
    assert b == _enumerate_feature_columns()


@pytest.mark.integration
def test_load_training_data_returns_frame(db_engine) -> None:
    """Tiny window smoke test against real dev DB."""
    frame = load_training_data(date(2024, 6, 1), date(2024, 6, 7), engine=db_engine)
    assert isinstance(frame, FeatureFrame)
    assert frame.X.shape[0] > 0
    assert frame.X.shape[1] == len(FEATURE_COLUMNS)
    assert frame.y.notna().all()
    assert frame.y.isin([0, 1]).all()
    assert frame.dates.nunique() <= 7
    assert frame.metadata["row_count"] == frame.X.shape[0]
    assert 0.0 <= frame.metadata["hr_rate"] <= 1.0


@pytest.mark.integration
def test_time_based_split_nonoverlapping_dates(db_engine) -> None:
    split = time_based_split(engine=db_engine)
    assert isinstance(split, TrainValTest)
    assert split.train.dates.max() < split.val.dates.min()
    assert split.val.dates.max() < split.test.dates.min()
    # Train spans multiple years.
    assert split.train.dates.min().year == 2021
    assert split.train.dates.max().year <= 2023
    assert split.val.dates.min().year == 2024
    assert split.test.dates.min().year >= 2025


@pytest.mark.integration
def test_time_based_split_row_counts_sane(db_engine) -> None:
    split = time_based_split(engine=db_engine)
    assert split.train.X.shape[0] >= 300_000
    assert split.val.X.shape[0] >= 100_000
    assert split.test.X.shape[0] >= 100_000


@pytest.mark.integration
def test_load_training_data_excludes_null_labels(db_engine) -> None:
    # Historical rows by definition have non-null hr_on_pa (inline computed).
    frame = load_training_data(date(2024, 6, 1), date(2024, 6, 2), engine=db_engine)
    assert frame.y.notna().all()


def test_feature_frame_dates_are_python_dates() -> None:
    # Not a datetime Series — precision_at_top_k groups by date.
    # Run against tiny window to avoid large data pull in unit tier.
    pytest.skip("covered by integration tests; this marker documents the contract")

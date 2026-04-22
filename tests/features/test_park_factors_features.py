"""Unit + integration tests for Phase 3 park-factor joiners."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.features.park_factors_features import (
    THREE_YEAR_WEIGHTS,
    park_elevation_ft,
    park_hr_factor_3yr_weighted,
    park_hr_factor_for,
)


def test_three_year_weights_sum_to_one() -> None:
    assert sum(THREE_YEAR_WEIGHTS) == pytest.approx(1.0, abs=1e-9)
    assert len(THREE_YEAR_WEIGHTS) == 3
    # Descending: most recent weighted most.
    assert THREE_YEAR_WEIGHTS[0] > THREE_YEAR_WEIGHTS[1] > THREE_YEAR_WEIGHTS[2]


@pytest.fixture()
def seeded_park_factors(test_engine: Engine, clean_tables) -> Engine:
    """Seed one park (Coors, id=19) with factors for 3 seasons + an opposite-hand value."""
    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text(
                "INSERT INTO parks (park_id, name, elevation_ft) "
                "VALUES (19, 'Coors Field', 5190) ON CONFLICT DO NOTHING"
            )
        )
        rows = [
            (19, 2024, "R", "hr", 110.0),
            (19, 2023, "R", "hr", 118.0),
            (19, 2022, "R", "hr", 115.0),
            (19, 2024, "L", "hr", 105.0),
            (19, 2021, "R", "hr", 112.0),  # outside 3yr window for ref=2024
        ]
        for pid, season, hand, metric, value in rows:
            s.execute(
                text(
                    "INSERT INTO park_factors "
                    "(park_id, season, batter_handedness, metric, value, updated_at) "
                    "VALUES (:p, :s, :h, :m, :v, :ts)"
                ),
                {
                    "p": pid,
                    "s": season,
                    "h": hand,
                    "m": metric,
                    "v": value,
                    "ts": datetime.now(UTC),
                },
            )
        s.commit()
    return test_engine


@pytest.mark.integration
def test_park_hr_factor_for_single_season(seeded_park_factors: Engine) -> None:
    session_factory = sessionmaker(bind=seeded_park_factors, future=True, expire_on_commit=False)
    with session_factory() as s:
        assert park_hr_factor_for("R", 19, 2024, s) == pytest.approx(110.0)
        assert park_hr_factor_for("L", 19, 2024, s) == pytest.approx(105.0)


@pytest.mark.integration
def test_park_hr_factor_for_missing_returns_none(seeded_park_factors: Engine) -> None:
    session_factory = sessionmaker(bind=seeded_park_factors, future=True, expire_on_commit=False)
    with session_factory() as s:
        # No data for park_id=19, season=2030 → None.
        assert park_hr_factor_for("R", 19, 2030, s) is None
        # No data for Fenway — not seeded.
        assert park_hr_factor_for("R", 3, 2024, s) is None


@pytest.mark.integration
def test_3yr_weighted_full_three_seasons(seeded_park_factors: Engine) -> None:
    """Coors R, ref=2024: seasons [2024, 2023, 2022] with weights [0.5, 0.3, 0.2].
    expected = 110*0.5 + 118*0.3 + 115*0.2 = 55.0 + 35.4 + 23.0 = 113.4
    """
    session_factory = sessionmaker(bind=seeded_park_factors, future=True, expire_on_commit=False)
    with session_factory() as s:
        val = park_hr_factor_3yr_weighted("R", 19, 2024, s)
    assert val == pytest.approx(113.4, abs=0.01)


@pytest.mark.integration
def test_3yr_weighted_falls_back_to_two_seasons(seeded_park_factors: Engine) -> None:
    """Coors L, ref=2024: only 2024 data exists. Weights re-normalize from [0.5] → [1.0].
    expected = 105.0.
    """
    session_factory = sessionmaker(bind=seeded_park_factors, future=True, expire_on_commit=False)
    with session_factory() as s:
        val = park_hr_factor_3yr_weighted("L", 19, 2024, s)
    assert val == pytest.approx(105.0, abs=0.01)


@pytest.mark.integration
def test_3yr_weighted_returns_none_when_nothing(seeded_park_factors: Engine) -> None:
    session_factory = sessionmaker(bind=seeded_park_factors, future=True, expire_on_commit=False)
    with session_factory() as s:
        assert park_hr_factor_3yr_weighted("R", 999, 2024, s) is None


@pytest.mark.integration
def test_park_elevation_ft(seeded_park_factors: Engine) -> None:
    session_factory = sessionmaker(bind=seeded_park_factors, future=True, expire_on_commit=False)
    with session_factory() as s:
        assert park_elevation_ft(19, s) == 5190
        assert park_elevation_ft(99999, s) is None

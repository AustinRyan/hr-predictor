"""Tests for sportsbook odds math."""

from __future__ import annotations

import pytest
from src.models.odds import (
    american_to_implied_probability,
    edge_probability,
    expected_value_per_unit,
    probability_to_fair_american,
)


def test_american_to_implied_probability_positive_odds() -> None:
    assert american_to_implied_probability(700) == pytest.approx(0.125)


def test_american_to_implied_probability_negative_odds() -> None:
    assert american_to_implied_probability(-150) == pytest.approx(0.6)


def test_american_zero_is_invalid() -> None:
    with pytest.raises(ValueError, match="American odds cannot be 0"):
        american_to_implied_probability(0)


def test_probability_to_fair_american_positive_side() -> None:
    assert probability_to_fair_american(0.125) == 700


def test_probability_to_fair_american_negative_side() -> None:
    assert probability_to_fair_american(0.6) == -150


def test_edge_probability_is_model_minus_market() -> None:
    assert edge_probability(model_probability=0.15, market_probability=0.125) == pytest.approx(
        0.025
    )


def test_expected_value_per_unit_positive_odds() -> None:
    # At +700, a 15% true probability returns 0.15 * 7 - 0.85 = +0.20 units.
    assert expected_value_per_unit(model_probability=0.15, american_odds=700) == pytest.approx(0.2)


def test_expected_value_per_unit_negative_odds() -> None:
    # At -150, a 65% true probability returns 0.65 * (100/150) - 0.35.
    assert expected_value_per_unit(model_probability=0.65, american_odds=-150) == pytest.approx(
        0.08333333333333337
    )

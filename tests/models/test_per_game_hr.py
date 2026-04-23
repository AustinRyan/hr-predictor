"""Tests for per_game_hr_distribution."""

from __future__ import annotations

import dataclasses

import pytest
from src.models.per_game_hr import GameMatchupInputs, per_game_hr_distribution


def test_starter_only_uses_prob_as_game_level() -> None:
    """With only starter prob, P(>=1) equals starter prob directly."""
    inputs = GameMatchupInputs(starter_prob=0.25)
    dist = per_game_hr_distribution(inputs)
    assert dist.prob_at_least_one == pytest.approx(0.25, abs=1e-6)
    assert dist.pmf == pytest.approx((0.75, 0.25))


def test_starter_plus_bullpen_combined() -> None:
    """P(>=1) = 1 - (1 - 0.25)(1 - 0.15) = 1 - 0.6375 = 0.3625"""
    inputs = GameMatchupInputs(starter_prob=0.25, bullpen_prob=0.15)
    dist = per_game_hr_distribution(inputs)
    assert dist.prob_at_least_one == pytest.approx(0.3625, abs=1e-6)


def test_zero_starter_prob() -> None:
    inputs = GameMatchupInputs(starter_prob=0.0)
    dist = per_game_hr_distribution(inputs)
    assert dist.prob_at_least_one == 0.0


def test_composition_bounded_in_zero_one() -> None:
    """Combined prob never exceeds 1."""
    inputs = GameMatchupInputs(starter_prob=0.9, bullpen_prob=0.9)
    dist = per_game_hr_distribution(inputs)
    assert dist.prob_at_least_one <= 1.0
    assert dist.prob_at_least_one == pytest.approx(1 - 0.01, abs=1e-6)  # 1 - 0.1*0.1


def test_monotone_in_each_component() -> None:
    """P(>=1) increases when either starter or bullpen prob increases."""
    low = per_game_hr_distribution(GameMatchupInputs(starter_prob=0.1, bullpen_prob=0.1))
    high_starter = per_game_hr_distribution(GameMatchupInputs(starter_prob=0.3, bullpen_prob=0.1))
    high_bullpen = per_game_hr_distribution(GameMatchupInputs(starter_prob=0.1, bullpen_prob=0.3))
    assert low.prob_at_least_one < high_starter.prob_at_least_one
    assert low.prob_at_least_one < high_bullpen.prob_at_least_one


def test_no_double_count_with_bullpen_none() -> None:
    """Passing bullpen_prob=None is not the same as passing 0; composition
    must degenerate to just the starter case."""
    d_none = per_game_hr_distribution(GameMatchupInputs(starter_prob=0.25, bullpen_prob=None))
    d_zero = per_game_hr_distribution(GameMatchupInputs(starter_prob=0.25, bullpen_prob=0.0))
    assert d_none.prob_at_least_one == pytest.approx(d_zero.prob_at_least_one)


def test_multi_hr_probs_monotone() -> None:
    """P(>=1) >= P(>=2) >= P(>=3) always."""
    inputs = GameMatchupInputs(starter_prob=0.5, bullpen_prob=0.5)
    dist = per_game_hr_distribution(inputs)
    assert dist.prob_at_least_one >= dist.prob_at_least_two
    assert dist.prob_at_least_two >= dist.prob_at_least_three


def test_frozen_dataclass_inputs() -> None:
    inputs = GameMatchupInputs(starter_prob=0.1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        inputs.starter_prob = 0.2  # type: ignore[misc]

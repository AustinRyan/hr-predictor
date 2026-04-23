"""Tests for the Poisson binomial per-game rollup."""

from __future__ import annotations

import pytest
from src.models.rollup import (
    per_game_probability,
    poisson_binomial_pmf,
)

# ---------- poisson_binomial_pmf ----------


def test_pmf_empty_returns_singleton_one() -> None:
    assert poisson_binomial_pmf([]) == [1.0]


def test_pmf_single_pa() -> None:
    pmf = poisson_binomial_pmf([0.3])
    assert pmf == pytest.approx([0.7, 0.3])
    assert sum(pmf) == pytest.approx(1.0)


def test_pmf_two_fair_coins_matches_pascal() -> None:
    # [0.5, 0.5] -> Pascal row 2: [1, 2, 1] / 4 = [0.25, 0.5, 0.25]
    pmf = poisson_binomial_pmf([0.5, 0.5])
    assert pmf == pytest.approx([0.25, 0.5, 0.25])


def test_pmf_four_identical_probs() -> None:
    # Binomial(4, 0.1) exact values:
    # P(0) = 0.9^4 = 0.6561
    # P(1) = C(4,1) * 0.1 * 0.9^3 = 0.2916
    # P(2) = C(4,2) * 0.01 * 0.81 = 0.0486
    # P(3) = C(4,3) * 0.001 * 0.9 = 0.0036
    # P(4) = 0.0001
    pmf = poisson_binomial_pmf([0.1] * 4)
    assert pmf == pytest.approx([0.6561, 0.2916, 0.0486, 0.0036, 0.0001], abs=1e-6)
    assert sum(pmf) == pytest.approx(1.0)


def test_pmf_all_zeros() -> None:
    pmf = poisson_binomial_pmf([0.0, 0.0, 0.0])
    assert pmf == pytest.approx([1.0, 0.0, 0.0, 0.0])


def test_pmf_all_ones() -> None:
    pmf = poisson_binomial_pmf([1.0, 1.0, 1.0])
    assert pmf == pytest.approx([0.0, 0.0, 0.0, 1.0])


def test_pmf_mixed_varied_probs() -> None:
    # Non-identical probs: Poisson binomial (not regular binomial).
    # [0.1, 0.5, 0.9]:
    # P(0) = 0.9 * 0.5 * 0.1 = 0.045
    # P(1) = 0.1*0.5*0.1 + 0.9*0.5*0.1 + 0.9*0.5*0.9 = 0.005 + 0.045 + 0.405 = 0.455
    # P(2) = 0.1*0.5*0.1 + 0.1*0.5*0.9 + 0.9*0.5*0.9 = 0.005 + 0.045 + 0.405 = 0.455
    # Wait let me recompute: probs=[0.1, 0.5, 0.9], so (1-p) = [0.9, 0.5, 0.1]
    # P(sum=0) = 0.9 * 0.5 * 0.1 = 0.045
    # P(sum=1) = 0.1*0.5*0.1 + 0.9*0.5*0.1 + 0.9*0.5*0.9 = 0.005 + 0.045 + 0.405 = 0.455
    # P(sum=2) = 0.1*0.5*0.1 + 0.1*0.5*0.9 + 0.9*0.5*0.9 = 0.005 + 0.045 + 0.405 = 0.455
    # Wait, that's wrong too. Let me list outcomes (x1, x2, x3) explicitly:
    # (0,0,0): q1*q2*q3 = 0.9*0.5*0.1 = 0.045 -> sum=0
    # (1,0,0): p1*q2*q3 = 0.1*0.5*0.1 = 0.005 -> sum=1
    # (0,1,0): q1*p2*q3 = 0.9*0.5*0.1 = 0.045 -> sum=1
    # (0,0,1): q1*q2*p3 = 0.9*0.5*0.9 = 0.405 -> sum=1
    # (1,1,0): p1*p2*q3 = 0.1*0.5*0.1 = 0.005 -> sum=2
    # (1,0,1): p1*q2*p3 = 0.1*0.5*0.9 = 0.045 -> sum=2
    # (0,1,1): q1*p2*p3 = 0.9*0.5*0.9 = 0.405 -> sum=2
    # (1,1,1): p1*p2*p3 = 0.1*0.5*0.9 = 0.045 -> sum=3
    # P(0)=0.045, P(1)=0.455, P(2)=0.455, P(3)=0.045
    pmf = poisson_binomial_pmf([0.1, 0.5, 0.9])
    assert pmf == pytest.approx([0.045, 0.455, 0.455, 0.045], abs=1e-6)


def test_pmf_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        poisson_binomial_pmf([0.5, 1.2])
    with pytest.raises(ValueError):
        poisson_binomial_pmf([-0.1, 0.5])


def test_pmf_sums_to_one_random() -> None:
    import random

    rng = random.Random(42)
    probs = [rng.uniform(0, 1) for _ in range(8)]
    pmf = poisson_binomial_pmf(probs)
    assert sum(pmf) == pytest.approx(1.0, abs=1e-10)


# ---------- per_game_probability ----------


def test_per_game_empty_input() -> None:
    dist = per_game_probability([])
    assert dist.prob_at_least_one == 0.0
    assert dist.prob_at_least_two == 0.0
    assert dist.prob_at_least_three == 0.0
    assert dist.expected_hrs == 0.0
    assert dist.pmf == (1.0,)


def test_per_game_four_pas_at_5_percent() -> None:
    # PROMPT acceptance bar: 4 PAs × 0.05 → P(≥1) ≈ 0.185
    dist = per_game_probability([0.05] * 4)
    assert dist.prob_at_least_one == pytest.approx(1.0 - 0.95**4, abs=1e-10)
    assert dist.prob_at_least_one == pytest.approx(0.18549375, abs=1e-6)
    assert dist.expected_hrs == pytest.approx(0.20)


def test_per_game_prob_at_least_one_plus_p_zero_is_one() -> None:
    dist = per_game_probability([0.1, 0.2, 0.3, 0.4])
    # P(≥1) + P(0) = 1 exactly.
    assert dist.prob_at_least_one + dist.pmf[0] == pytest.approx(1.0, abs=1e-12)


def test_per_game_ordering_monotone() -> None:
    # P(≥1) ≥ P(≥2) ≥ P(≥3)
    dist = per_game_probability([0.3, 0.3, 0.3, 0.3, 0.3])
    assert dist.prob_at_least_one >= dist.prob_at_least_two
    assert dist.prob_at_least_two >= dist.prob_at_least_three


def test_per_game_expected_hrs_is_sum() -> None:
    probs = [0.05, 0.10, 0.15]
    dist = per_game_probability(probs)
    assert dist.expected_hrs == pytest.approx(sum(probs))


def test_per_game_single_pa_all_in_one_bucket() -> None:
    dist = per_game_probability([0.3])
    assert dist.pmf == pytest.approx((0.7, 0.3))
    assert dist.prob_at_least_one == pytest.approx(0.3)
    assert dist.prob_at_least_two == 0.0
    assert dist.prob_at_least_three == 0.0


def test_per_game_dataclass_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    dist = per_game_probability([0.1, 0.2])
    with pytest.raises(FrozenInstanceError):
        dist.prob_at_least_one = 0.5  # type: ignore[misc]

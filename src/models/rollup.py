"""Per-game HR probability via Poisson binomial PMF.

Given per-PA HR probabilities (p_1, p_2, ..., p_n) for a batter's
projected PAs in a game, we roll up to game-level outputs:

  - P(≥1 HR) = 1 - ∏(1 - p_i)           (the prop-bet "Hit a HR" market)
  - P(exactly k HR) via Poisson binomial PMF (convolution-based, exact)
  - E[HR]     = ∑ p_i
  - P(≥2), P(≥3) for multi-HR prop markets

N is small (≤10 PAs per game in baseball), so exact convolution is
O(n²) and near-instant. Do NOT Poisson-approximate — per-PA
probabilities can vary enough across PA slots (TTO penalty for starter
vs bullpen) that the Poisson assumption breaks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class GameHRDistribution:
    prob_at_least_one: float
    prob_at_least_two: float
    prob_at_least_three: float
    expected_hrs: float
    pmf: tuple[float, ...]  # (P(HR=0), P(HR=1), ..., P(HR=n))


def poisson_binomial_pmf(probs: Sequence[float]) -> list[float]:
    """Exact PMF of the sum of independent Bernoulli trials via convolution.

    Returns list of length len(probs) + 1, where index k is P(sum == k).
    Empty input returns [1.0] (zero trials, always zero events).
    """
    pmf: list[float] = [1.0]
    for p in probs:
        if p < 0.0 or p > 1.0:
            raise ValueError(f"probability must be in [0, 1], got {p}")
        new_pmf = [0.0] * (len(pmf) + 1)
        for i, v in enumerate(pmf):
            new_pmf[i] += v * (1.0 - p)
            new_pmf[i + 1] += v * p
        pmf = new_pmf
    return pmf


def per_game_probability(per_pa_probs: Sequence[float]) -> GameHRDistribution:
    """Roll per-PA probabilities up to game-level distribution.

    Args:
        per_pa_probs: list of per-PA HR probabilities for one batter's
            projected PAs in a game.

    Returns:
        GameHRDistribution with P(≥1), P(≥2), P(≥3), E[HR], and full PMF.

    Empty input: P(≥anything) = 0, E[HR] = 0, PMF = (1.0,).
    """
    probs = [float(p) for p in per_pa_probs]
    pmf = poisson_binomial_pmf(probs)

    # P(sum >= k) = 1 - P(sum < k) = 1 - sum(pmf[0..k-1])
    p0 = pmf[0]  # P(HR=0) — always exists; pmf is at least [1.0]
    p1_or_less = p0 + (pmf[1] if len(pmf) > 1 else 0.0)
    p2_or_less = p1_or_less + (pmf[2] if len(pmf) > 2 else 0.0)

    prob_at_least_one = 1.0 - p0
    prob_at_least_two = 1.0 - p1_or_less
    prob_at_least_three = 1.0 - p2_or_less

    expected_hrs = sum(probs)

    return GameHRDistribution(
        prob_at_least_one=prob_at_least_one,
        prob_at_least_two=prob_at_least_two,
        prob_at_least_three=prob_at_least_three,
        expected_hrs=expected_hrs,
        pmf=tuple(pmf),
    )

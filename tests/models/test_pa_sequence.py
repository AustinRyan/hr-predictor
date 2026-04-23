"""Tests for build_pa_probability_sequence."""

from __future__ import annotations

import pytest
from src.models.pa_sequence import (
    PaSequenceInputs,
    _bullpen_adjustment,
    build_pa_probability_sequence,
)


def test_length_matches_rounded_projected_pa() -> None:
    inputs = PaSequenceInputs(
        base_prob=0.05,
        p_tto_penalty=1.0833,
        p_hr_per_9_season=1.2,
        bp_hr_per_9_season=1.2,
        projected_pa_count=4.29,  # round -> 4
    )
    seq = build_pa_probability_sequence(inputs)
    assert len(seq) == 4


def test_pa_1_2_3_increase_with_tto() -> None:
    """Against an average starter (TTO curve 1.00/1.05/1.20), PAs 1→3
    should have strictly increasing per-PA prob."""
    inputs = PaSequenceInputs(
        base_prob=0.05,
        p_tto_penalty=1.0833,
        p_hr_per_9_season=1.2,
        bp_hr_per_9_season=1.2,
        projected_pa_count=3.0,
    )
    seq = build_pa_probability_sequence(inputs)
    assert seq[0] < seq[1] < seq[2]
    # Ratios match TTO multipliers.
    assert seq[1] / seq[0] == pytest.approx(1.05, abs=0.001)
    assert seq[2] / seq[0] == pytest.approx(1.20, abs=0.001)


def test_pa_4_uses_bullpen_adjustment() -> None:
    """PA 4 picks up bullpen_adj = bp/p = 2.0 (weaker bullpen)."""
    inputs = PaSequenceInputs(
        base_prob=0.05,
        p_tto_penalty=1.0833,
        p_hr_per_9_season=1.0,
        bp_hr_per_9_season=2.0,  # bullpen is 2x HR-rate
        projected_pa_count=4.0,
    )
    seq = build_pa_probability_sequence(inputs)
    pure = 0.05 / 1.0833
    assert seq[3] == pytest.approx(pure * 2.0, abs=1e-6)


def test_bullpen_adj_clipped_upper_bound() -> None:
    """bp/p = 5.0 clips to 2.0."""
    assert _bullpen_adjustment(1.0, 5.0) == 2.0


def test_bullpen_adj_clipped_lower_bound() -> None:
    """bp/p = 0.1 clips to 0.5."""
    assert _bullpen_adjustment(2.0, 0.2) == 0.5


def test_bullpen_adj_null_inputs() -> None:
    assert _bullpen_adjustment(None, 1.0) == 1.0
    assert _bullpen_adjustment(1.0, None) == 1.0
    assert _bullpen_adjustment(None, None) == 1.0


def test_bullpen_adj_zero_starter_rate() -> None:
    """Division-by-zero guard."""
    assert _bullpen_adjustment(0.0, 1.0) == 1.0


def test_null_tto_penalty_uses_default() -> None:
    """When p_tto_penalty is None (historical pinch-hitter row), the
    default 1.0833 is used so we still produce a sane sequence."""
    inputs = PaSequenceInputs(
        base_prob=0.05,
        p_tto_penalty=None,
        p_hr_per_9_season=1.2,
        bp_hr_per_9_season=1.2,
        projected_pa_count=3.0,
    )
    seq = build_pa_probability_sequence(inputs)
    expected_pure = 0.05 / 1.0833
    assert seq[0] == pytest.approx(expected_pure * 1.00, abs=1e-6)


def test_output_clipped_to_valid_prob_range() -> None:
    """Extreme base_prob gets clipped away from exact 0 and 1."""
    # Very small base_prob
    inputs_low = PaSequenceInputs(
        base_prob=1e-10,
        p_tto_penalty=1.0833,
        p_hr_per_9_season=1.0,
        bp_hr_per_9_season=1.0,
        projected_pa_count=1.0,
    )
    assert build_pa_probability_sequence(inputs_low)[0] >= 1e-6

    # base_prob near 1
    inputs_high = PaSequenceInputs(
        base_prob=0.99,
        p_tto_penalty=1.0833,
        p_hr_per_9_season=1.0,
        bp_hr_per_9_season=1.0,
        projected_pa_count=3.0,
    )
    # PA 3 gets 1.20 mult × pure(0.99/1.08) ≈ 1.10 → clipped to 1 - 1e-6
    seq = build_pa_probability_sequence(inputs_high)
    assert seq[2] <= 1.0 - 1e-6


def test_single_pa_minimum() -> None:
    """projected_pa_count = 0.0 still returns at least one PA (edge case)."""
    inputs = PaSequenceInputs(
        base_prob=0.05,
        p_tto_penalty=1.0833,
        p_hr_per_9_season=1.0,
        bp_hr_per_9_season=1.0,
        projected_pa_count=0.0,
    )
    seq = build_pa_probability_sequence(inputs)
    assert len(seq) >= 1


def test_integrates_with_rollup() -> None:
    """Pipe the per-PA sequence into per_game_probability → sane game-level numbers."""
    from src.models.rollup import per_game_probability

    inputs = PaSequenceInputs(
        base_prob=0.04,
        p_tto_penalty=1.0833,
        p_hr_per_9_season=1.0,
        bp_hr_per_9_season=1.5,
        projected_pa_count=4.3,
    )
    seq = build_pa_probability_sequence(inputs)
    dist = per_game_probability(seq)
    # Sanity: P(≥1) should be realistic-HR-ish (5-20% for a 4% base per-PA)
    assert 0.10 < dist.prob_at_least_one < 0.30
    assert dist.expected_hrs > 0.0
    assert dist.prob_at_least_one >= dist.prob_at_least_two

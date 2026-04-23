"""Unit tests for src.models.eval metrics."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest
from src.models.eval import (
    ReliabilityCurve,
    auc,
    brier_score,
    expected_calibration_error,
    log_loss,
    naive_baseline_log_loss,
    precision_at_top_k,
    reliability_curve,
)

# ---------- log_loss ----------


def test_log_loss_perfect_prediction_is_near_zero() -> None:
    y_true = np.array([1, 0, 1, 0])
    y_prob = np.array([1.0, 0.0, 1.0, 0.0])
    # eps clipping makes this ~1e-15 * 4 / 4 → basically zero.
    assert log_loss(y_true, y_prob) < 1e-10


def test_log_loss_random_on_balanced_data_is_ln2() -> None:
    y_true = np.array([1, 0, 1, 0, 1, 0, 1, 0])
    y_prob = np.full(8, 0.5)
    assert log_loss(y_true, y_prob) == pytest.approx(math.log(2), abs=1e-6)


def test_log_loss_worst_case_is_huge() -> None:
    # Pred 0 when truth is 1 -> log(eps) ≈ -34.5 per row.
    y_true = np.array([1, 1])
    y_prob = np.array([0.0, 0.0])
    assert log_loss(y_true, y_prob) > 30


def test_log_loss_raises_on_shape_mismatch() -> None:
    with pytest.raises(ValueError):
        log_loss(np.array([1, 0]), np.array([0.5, 0.5, 0.5]))


# ---------- brier_score ----------


def test_brier_perfect_is_zero() -> None:
    y_true = np.array([1, 0, 1, 0])
    y_prob = np.array([1.0, 0.0, 1.0, 0.0])
    assert brier_score(y_true, y_prob) == 0.0


def test_brier_constant_half_on_balanced_data() -> None:
    y_true = np.array([1, 0, 1, 0])
    y_prob = np.full(4, 0.5)
    assert brier_score(y_true, y_prob) == 0.25


# ---------- ECE ----------


def test_ece_perfect_calibration_is_zero() -> None:
    # 10 predictions, each with prob matching the true rate at that level.
    # Simple version: every bin has prob==rate. Use identical predictions
    # all at 0.0 with all-zero labels → ECE = 0.
    y_true = np.array([0, 0, 0, 0])
    y_prob = np.array([0.0, 0.0, 0.0, 0.0])
    assert expected_calibration_error(y_true, y_prob, n_bins=10) == 0.0


def test_ece_known_miscalibration_two_bins() -> None:
    # 10 predictions: 5 at 0.1 but actual rate 0.4; 5 at 0.9 but actual rate 0.6.
    # Each bin has 5 rows (5/10 weight). Bin 0 (0.0-0.1]:
    #   avg_pred=0.1, avg_actual=0.4 → |0.1-0.4| = 0.3
    # Bin 9 (0.9-1.0]: avg_pred=0.9, avg_actual=0.6 → 0.3
    # ECE = (0.5)(0.3) + (0.5)(0.3) = 0.3
    y_prob = np.concatenate([np.full(5, 0.1), np.full(5, 0.9)])
    y_true = np.concatenate([[1, 1, 0, 0, 0], [1, 1, 1, 0, 0]])  # 2/5 and 3/5 positive
    result = expected_calibration_error(y_true, y_prob, n_bins=10)
    assert result == pytest.approx(0.3, abs=0.01)


def test_ece_empty_bins_contribute_zero() -> None:
    # All predictions in one bin only. Perfect calibration within that bin.
    y_prob = np.full(20, 0.05)
    y_true = np.zeros(20, dtype=int)  # bin rate 0, bin avg 0.05 → |0.05-0| = 0.05
    # ECE with weight 1.0 = 0.05.
    result = expected_calibration_error(y_true, y_prob, n_bins=10)
    assert result == pytest.approx(0.05, abs=1e-6)


# ---------- reliability_curve ----------


def test_reliability_curve_returns_n_bins_values() -> None:
    y_prob = np.linspace(0.0, 1.0, 100)
    y_true = (y_prob > 0.5).astype(int)
    curve = reliability_curve(y_true, y_prob, n_bins=10)
    assert isinstance(curve, ReliabilityCurve)
    assert len(curve.mean_pred) == 10
    assert len(curve.actual_rate) == 10
    assert len(curve.counts) == 10


def test_reliability_curve_empty_bins_emit_nan() -> None:
    # Only predictions in bin 0.
    y_prob = np.full(10, 0.05)
    y_true = np.zeros(10, dtype=int)
    curve = reliability_curve(y_true, y_prob, n_bins=10)
    assert curve.counts[0] == 10
    # Other bins empty -> count 0, means NaN.
    for i in range(1, 10):
        assert curve.counts[i] == 0
        assert math.isnan(curve.mean_pred[i])
        assert math.isnan(curve.actual_rate[i])


# ---------- precision_at_top_k ----------


def test_precision_at_top_k_simple_case() -> None:
    # 2 days, 5 predictions each. k=2.
    # Day A: probs [0.9, 0.8, 0.3, 0.2, 0.1], labels [1, 0, 1, 0, 0]
    #   top 2: 0.9 (1), 0.8 (0) → precision = 1/2 = 0.5
    # Day B: probs [0.95, 0.85, 0.5, 0.1, 0.05], labels [1, 1, 0, 0, 0]
    #   top 2: 0.95 (1), 0.85 (1) → precision = 2/2 = 1.0
    # Mean = 0.75
    dates = np.array([date(2024, 6, 1)] * 5 + [date(2024, 6, 2)] * 5)
    y_prob = np.array([0.9, 0.8, 0.3, 0.2, 0.1, 0.95, 0.85, 0.5, 0.1, 0.05])
    y_true = np.array([1, 0, 1, 0, 0, 1, 1, 0, 0, 0])
    result = precision_at_top_k(y_true, y_prob, dates, k=2)
    assert result == pytest.approx(0.75, abs=1e-6)


def test_precision_at_top_k_skips_dates_with_fewer_than_k() -> None:
    # Day with only 1 row, k=3. Should be skipped.
    dates = np.array([date(2024, 6, 1), date(2024, 6, 2), date(2024, 6, 2), date(2024, 6, 2)])
    y_prob = np.array([0.9, 0.9, 0.8, 0.1])
    y_true = np.array([1, 1, 1, 0])
    # Only day 2024-06-02 has >=3 rows. Top 3: 0.9 (1), 0.8 (1), 0.1 (0) → 2/3
    result = precision_at_top_k(y_true, y_prob, dates, k=3)
    assert result == pytest.approx(2 / 3, abs=1e-6)


def test_precision_at_top_k_returns_nan_when_no_dates_qualify() -> None:
    dates = np.array([date(2024, 6, 1), date(2024, 6, 1)])
    y_prob = np.array([0.5, 0.5])
    y_true = np.array([0, 0])
    # k=10, but only 2 rows per date → no qualifying dates.
    result = precision_at_top_k(y_true, y_prob, dates, k=10)
    assert math.isnan(result)


# ---------- auc ----------


def test_auc_perfect_predictions_is_one() -> None:
    y_true = np.array([1, 1, 0, 0])
    y_prob = np.array([0.9, 0.8, 0.2, 0.1])
    assert auc(y_true, y_prob) == 1.0


def test_auc_inverted_predictions_is_zero() -> None:
    y_true = np.array([1, 1, 0, 0])
    y_prob = np.array([0.1, 0.2, 0.8, 0.9])
    assert auc(y_true, y_prob) == 0.0


def test_auc_random_predictions_near_half() -> None:
    rng = np.random.default_rng(seed=42)
    y_true = rng.integers(0, 2, size=1000)
    y_prob = rng.random(size=1000)
    result = auc(y_true, y_prob)
    assert 0.45 <= result <= 0.55


def test_auc_single_class_returns_nan() -> None:
    y_true = np.zeros(10, dtype=int)
    y_prob = np.random.rand(10)
    result = auc(y_true, y_prob)
    assert math.isnan(result)


# ---------- naive_baseline_log_loss ----------


def test_naive_baseline_matches_log_loss_of_constant() -> None:
    y_true = np.array([1, 0, 1, 0, 0, 0])
    rate = 1 / 3
    direct = naive_baseline_log_loss(y_true, rate)
    indirect = log_loss(y_true, np.full_like(y_true, rate, dtype=float))
    assert direct == pytest.approx(indirect, abs=1e-10)

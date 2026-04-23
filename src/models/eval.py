"""Evaluation metrics for binary classification models.

All functions are pure (no I/O), accept arrays or Series, and validate inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import roc_auc_score


@dataclass(slots=True)
class ReliabilityCurve:
    """Binned reliability diagram data.

    Attributes:
        mean_pred: Mean predicted probability per bin (NaN for empty bins).
        actual_rate: Empirical positive rate per bin (NaN for empty bins).
        counts: Number of samples per bin (0 for empty bins).
    """

    mean_pred: list[float]
    actual_rate: list[float]
    counts: list[int]


def log_loss(
    y_true: NDArray[np.bool_] | NDArray[np.int_] | Any,
    y_prob: NDArray[np.float64] | Any,
    eps: float = 1e-15,
) -> float:
    """Binary cross-entropy loss.

    Clips predicted probabilities to [eps, 1-eps] to avoid log(0).

    Args:
        y_true: Binary labels (0 or 1).
        y_prob: Predicted probabilities in [0, 1].
        eps: Clipping epsilon (default 1e-15, sklearn convention).

    Returns:
        Mean binary cross-entropy loss.

    Raises:
        ValueError: If input shapes don't match.
    """
    y_true = np.asarray(y_true, dtype=np.float64)
    y_prob = np.asarray(y_prob, dtype=np.float64)

    if y_true.shape != y_prob.shape:
        raise ValueError(f"Shape mismatch: y_true {y_true.shape} vs y_prob {y_prob.shape}")

    y_prob_clipped = np.clip(y_prob, eps, 1 - eps)
    loss = -(y_true * np.log(y_prob_clipped) + (1 - y_true) * np.log(1 - y_prob_clipped))
    return float(np.mean(loss))


def brier_score(
    y_true: NDArray[np.bool_] | NDArray[np.int_] | Any,
    y_prob: NDArray[np.float64] | Any,
) -> float:
    """Brier score (mean squared error).

    Args:
        y_true: Binary labels (0 or 1).
        y_prob: Predicted probabilities in [0, 1].

    Returns:
        Mean squared error between probabilities and labels.

    Raises:
        ValueError: If input shapes don't match.
    """
    y_true = np.asarray(y_true, dtype=np.float64)
    y_prob = np.asarray(y_prob, dtype=np.float64)

    if y_true.shape != y_prob.shape:
        raise ValueError(f"Shape mismatch: y_true {y_true.shape} vs y_prob {y_prob.shape}")

    return float(np.mean((y_prob - y_true) ** 2))


def expected_calibration_error(
    y_true: NDArray[np.bool_] | NDArray[np.int_] | Any,
    y_prob: NDArray[np.float64] | Any,
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error (ECE).

    Divides predictions into equal-width bins over [0, 1], computes
    |avg_pred - avg_actual| per bin, and weights by bin size.
    Empty bins contribute 0.

    Args:
        y_true: Binary labels (0 or 1).
        y_prob: Predicted probabilities in [0, 1].
        n_bins: Number of equal-width bins (default 10).

    Returns:
        Weighted average calibration error.

    Raises:
        ValueError: If input shapes don't match.
    """
    y_true = np.asarray(y_true, dtype=np.float64)
    y_prob = np.asarray(y_prob, dtype=np.float64)

    if y_true.shape != y_prob.shape:
        raise ValueError(f"Shape mismatch: y_true {y_true.shape} vs y_prob {y_prob.shape}")

    # Bin edges: [0, 1/n_bins], (1/n_bins, 2/n_bins], ..., ((n_bins-1)/n_bins, 1]
    # digitize returns bin index (1 to n_bins for values in range).
    bin_indices = np.digitize(y_prob, bins=np.linspace(0, 1, n_bins + 1), right=False)
    # digitize uses 1-indexed; clip to [1, n_bins]
    bin_indices = np.clip(bin_indices, 1, n_bins)

    ece = 0.0
    n_total = len(y_true)

    for bin_idx in range(1, n_bins + 1):
        mask = bin_indices == bin_idx
        if not np.any(mask):
            # Empty bin contributes 0
            continue

        bin_size = np.sum(mask)
        avg_pred = np.mean(y_prob[mask])
        avg_actual = np.mean(y_true[mask])
        bin_weight = bin_size / n_total

        ece += bin_weight * np.abs(avg_pred - avg_actual)

    return float(ece)


def reliability_curve(
    y_true: NDArray[np.bool_] | NDArray[np.int_] | Any,
    y_prob: NDArray[np.float64] | Any,
    n_bins: int = 10,
) -> ReliabilityCurve:
    """Reliability (calibration) curve data.

    Bins predictions into equal-width intervals over [0, 1] and computes
    mean predicted probability and empirical positive rate per bin.
    Empty bins have NaN for means and 0 for counts.

    Args:
        y_true: Binary labels (0 or 1).
        y_prob: Predicted probabilities in [0, 1].
        n_bins: Number of equal-width bins (default 10).

    Returns:
        ReliabilityCurve with per-bin statistics.

    Raises:
        ValueError: If input shapes don't match.
    """
    y_true = np.asarray(y_true, dtype=np.float64)
    y_prob = np.asarray(y_prob, dtype=np.float64)

    if y_true.shape != y_prob.shape:
        raise ValueError(f"Shape mismatch: y_true {y_true.shape} vs y_prob {y_prob.shape}")

    # Bin using same logic as ECE
    bin_indices = np.digitize(y_prob, bins=np.linspace(0, 1, n_bins + 1), right=False)
    bin_indices = np.clip(bin_indices, 1, n_bins)

    mean_pred_list: list[float] = []
    actual_rate_list: list[float] = []
    counts_list: list[int] = []

    for bin_idx in range(1, n_bins + 1):
        mask = bin_indices == bin_idx
        bin_count = np.sum(mask)

        if bin_count == 0:
            mean_pred_list.append(float("nan"))
            actual_rate_list.append(float("nan"))
            counts_list.append(0)
        else:
            mean_pred = float(np.mean(y_prob[mask]))
            actual_rate = float(np.mean(y_true[mask]))
            mean_pred_list.append(mean_pred)
            actual_rate_list.append(actual_rate)
            counts_list.append(int(bin_count))

    return ReliabilityCurve(
        mean_pred=mean_pred_list,
        actual_rate=actual_rate_list,
        counts=counts_list,
    )


def precision_at_top_k(
    y_true: NDArray[np.bool_] | NDArray[np.int_] | Any,
    y_prob: NDArray[np.float64] | Any,
    dates: NDArray[Any] | Any,
    k: int = 20,
) -> float:
    """Precision at top-k predictions, averaged per date.

    For each unique date in `dates`:
      1. Select all (y_true, y_prob) pairs for that date.
      2. If fewer than k pairs, skip that date.
      3. Sort by y_prob descending, take top k.
      4. Compute precision = sum(y_true for top k) / k.

    Returns the mean precision across included dates.
    If no dates have >= k predictions, returns NaN.

    Args:
        y_true: Binary labels (0 or 1).
        y_prob: Predicted probabilities in [0, 1].
        dates: Date array (one per sample), used as grouping key.
        k: Number of top predictions per date (default 20).

    Returns:
        Mean precision@k across dates, or NaN if no qualifying dates.

    Raises:
        ValueError: If input shapes don't match.
    """
    y_true = np.asarray(y_true, dtype=np.float64)
    y_prob = np.asarray(y_prob, dtype=np.float64)
    dates = np.asarray(dates)

    if y_true.shape != y_prob.shape or y_true.shape != dates.shape:
        raise ValueError(
            f"Shape mismatch: y_true {y_true.shape}, y_prob {y_prob.shape}, dates {dates.shape}"
        )

    # Group by date
    unique_dates = np.unique(dates)
    precisions: list[float] = []

    for d in unique_dates:
        mask = dates == d
        date_y_true = y_true[mask]
        date_y_prob = y_prob[mask]

        # Skip dates with fewer than k samples
        if len(date_y_true) < k:
            continue

        # Sort by probability descending, take top k
        top_k_indices = np.argsort(-date_y_prob)[:k]
        top_k_y_true = date_y_true[top_k_indices]

        # Precision = fraction of top k that are positive
        precision = float(np.sum(top_k_y_true) / k)
        precisions.append(precision)

    if len(precisions) == 0:
        return float("nan")

    return float(np.mean(precisions))


def auc(
    y_true: NDArray[np.bool_] | NDArray[np.int_] | Any,
    y_prob: NDArray[np.float64] | Any,
) -> float:
    """ROC-AUC score.

    Uses sklearn.metrics.roc_auc_score. Returns NaN if single-class input.

    Args:
        y_true: Binary labels (0 or 1).
        y_prob: Predicted probabilities in [0, 1].

    Returns:
        ROC-AUC score in [0, 1], or NaN if single class.

    Raises:
        ValueError: If input shapes don't match.
    """
    y_true = np.asarray(y_true, dtype=np.float64)
    y_prob = np.asarray(y_prob, dtype=np.float64)

    if y_true.shape != y_prob.shape:
        raise ValueError(f"Shape mismatch: y_true {y_true.shape} vs y_prob {y_prob.shape}")

    # Check for single class
    if len(np.unique(y_true)) < 2:
        return float("nan")

    try:
        return float(roc_auc_score(y_true, y_prob))
    except ValueError:
        # In case sklearn raises for any other reason
        return float("nan")


def naive_baseline_log_loss(
    y_true: NDArray[np.bool_] | NDArray[np.int_] | Any,
    train_rate: float,
    eps: float = 1e-15,
) -> float:
    """Log loss when always predicting a constant probability.

    Computes the log loss of predicting `train_rate` for every sample.
    Useful for validating that a model beats the naive baseline.

    Args:
        y_true: Binary labels (0 or 1).
        train_rate: The constant probability to predict everywhere.
        eps: Clipping epsilon (default 1e-15, sklearn convention).

    Returns:
        Log loss of the constant prediction.
    """
    y_true = np.asarray(y_true, dtype=np.float64)
    # Create constant predictions
    y_prob = np.full_like(y_true, train_rate, dtype=np.float64)
    return log_loss(y_true, y_prob, eps=eps)

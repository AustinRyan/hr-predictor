"""Evaluation metrics for binary classification models.

All functions are pure (no I/O), accept arrays or Series, and validate inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # Headless backend for server/CI runs
import matplotlib.pyplot as plt
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


def plot_reliability(
    curves: dict[str, ReliabilityCurve],
    save_path: Path,
    title: str = "Reliability",
) -> None:
    """Overlay train/val/test reliability curves with y=x diagonal reference.

    X-axis: mean predicted probability per bin.
    Y-axis: actual positive rate per bin.
    Skip NaN points (empty bins). Size: (8, 8).

    Args:
        curves: Dictionary mapping split name (e.g., "train", "val", "test")
            to ReliabilityCurve.
        save_path: Path to save PNG.
        title: Plot title (default "Reliability").
    """
    save_path = Path(save_path)

    fig, ax = plt.subplots(figsize=(8, 8))

    # Diagonal reference line (perfect calibration)
    ax.plot([0, 1], [0, 1], "k--", alpha=0.3, label="Perfect calibration", linewidth=2)

    # Plot each split's curve
    for split_name, curve in curves.items():
        # Skip NaN points (empty bins)
        mask = ~(np.isnan(curve.mean_pred) | np.isnan(curve.actual_rate))
        x = np.array(curve.mean_pred)[mask]
        y = np.array(curve.actual_rate)[mask]

        ax.plot(x, y, marker="o", label=split_name, linewidth=2, markersize=6)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Mean Predicted Probability", fontsize=12)
    ax.set_ylabel("Actual Positive Rate", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="upper left", fontsize=11)
    ax.grid(True, alpha=0.3)

    fig.savefig(save_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_feature_importance(
    model: Any,  # xgboost.Booster or xgboost.XGBModel
    feature_names: list[str],
    save_path: Path,
    top_n: int = 30,
    importance_type: str = "gain",
) -> None:
    """Horizontal bar plot of top_n features by importance.

    Uses matplotlib only (no xgboost.plot_importance for more control).

    Args:
        model: XGBoost Booster or XGBModel (XGBClassifier, etc.).
        feature_names: Ordered list of feature names matching model columns.
        save_path: Path to save PNG.
        top_n: Number of top features to display (default 30).
        importance_type: One of "gain", "weight", "cover" (default "gain").
    """
    save_path = Path(save_path)

    # Handle both Booster and sklearn-style wrapper
    if hasattr(model, "get_booster"):
        # sklearn wrapper (XGBClassifier, XGBRegressor)
        booster = model.get_booster()
    else:
        # Already a Booster
        booster = model

    scores = booster.get_score(importance_type=importance_type)

    # Map feature indices to names
    importance_dict = {}
    for f_name_idx, score in scores.items():
        # f_name_idx is like "f0", "f1", etc.
        try:
            f_idx = int(f_name_idx[1:])
            if 0 <= f_idx < len(feature_names):
                importance_dict[feature_names[f_idx]] = score
        except (ValueError, IndexError):
            # In case of unexpected format, skip
            pass

    if not importance_dict:
        # Fallback: if model has feature_names set
        importance_dict = {name: scores.get(f"f{i}", 0) for i, name in enumerate(feature_names)}

    # Sort by importance (descending) and take top_n
    sorted_features = sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)
    top_features = sorted_features[:top_n]

    if not top_features:
        # No features to plot
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.text(0.5, 0.5, "No features with importance", ha="center", va="center")
        fig.savefig(save_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        return

    names, values = zip(*top_features, strict=True)

    fig, ax = plt.subplots(figsize=(10, max(6, len(top_features) * 0.25)))
    y_pos = np.arange(len(names))
    ax.barh(y_pos, values, color="steelblue")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names)
    ax.set_xlabel(f"Importance ({importance_type})", fontsize=12)
    ax.set_title(
        f"Top {len(top_features)} Features by {importance_type.capitalize()}",
        fontsize=14,
        fontweight="bold",
    )
    ax.invert_yaxis()  # Top feature at top
    fig.tight_layout()

    fig.savefig(save_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_shap_summary(
    model: Any,  # xgboost.Booster or xgboost.XGBModel
    x_sample: Any,  # pd.DataFrame
    save_path: Path,
    max_display: int = 30,
    random_state: int = 42,
) -> None:
    """SHAP TreeExplainer summary plot.

    If x_sample has >5000 rows, sample 5000 deterministically via random_state
    for tractability. Uses shap.summary_plot and saves to save_path.

    Falls back to KernelExplainer if TreeExplainer fails (e.g., due to version
    incompatibilities with xgboost).

    Args:
        model: XGBoost Booster or XGBModel.
        x_sample: DataFrame of features (will be sampled down if > 5000 rows).
        save_path: Path to save PNG.
        max_display: Max features to display in summary plot (default 30).
        random_state: Random seed for sampling (default 42).
    """
    import shap
    import xgboost as xgb

    save_path = Path(save_path)

    # Downsample if needed
    if len(x_sample) > 5000:
        x_sample = x_sample.sample(5000, random_state=random_state)

    # Get SHAP values - try TreeExplainer first, fall back to KernelExplainer
    explainer = None
    try:
        if hasattr(model, "get_booster"):
            # sklearn wrapper
            explainer = shap.TreeExplainer(model)
        else:
            # Booster object
            explainer = shap.TreeExplainer(model)
    except (ValueError, KeyError, AttributeError):
        # Fallback: use KernelExplainer if TreeExplainer fails
        # Sample background data for efficiency
        background = shap.sample(x_sample, min(50, len(x_sample)))
        if hasattr(model, "predict_proba"):
            # sklearn wrapper
            explainer = shap.KernelExplainer(model.predict_proba, background)
        else:
            # Booster - wrap predict to accept DataFrame/array and convert to DMatrix
            # Get feature names from x_sample if available
            feature_names = None
            if hasattr(x_sample, "columns"):
                feature_names = list(x_sample.columns)

            def booster_predict(x):
                dmat = xgb.DMatrix(x, feature_names=feature_names)
                return model.predict(dmat)

            explainer = shap.KernelExplainer(booster_predict, background)

    shap_values = explainer.shap_values(x_sample)

    # shap_values can be a 2D array or list (for multi-class)
    # For binary classification, typically a 2D array (n_samples, n_features)
    # If it's a list of 2 arrays, take the second one (positive class)
    if isinstance(shap_values, list):
        if len(shap_values) > 1:
            shap_values = shap_values[1]
        else:
            shap_values = shap_values[0]

    # Create summary plot
    fig = plt.figure(figsize=(10, max(6, max_display * 0.3)))
    shap.summary_plot(shap_values, x_sample, max_display=max_display, show=False, plot_type="bar")

    fig.savefig(save_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def plot_prediction_histogram(
    predictions: dict[str, Any],  # "train" / "val" / "test" mapping to np.ndarray
    save_path: Path,
    bins: int = 50,
) -> None:
    """Overlay train/val/test prediction distributions.

    X-axis: predicted probability 0-1. Y-axis: density (normalized).

    Args:
        predictions: Dictionary mapping split name (e.g., "train", "val", "test")
            to numpy array of predicted probabilities.
        save_path: Path to save PNG.
        bins: Number of histogram bins (default 50).
    """
    save_path = Path(save_path)

    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot each split's distribution
    for split_name, preds in predictions.items():
        preds = np.asarray(preds)
        ax.hist(preds, bins=bins, alpha=0.4, label=split_name, density=True)

    ax.set_xlim(0, 1)
    ax.set_xlabel("Predicted Probability", fontsize=12)
    ax.set_ylabel("Density", fontsize=12)
    ax.set_title("Prediction Distribution", fontsize=14, fontweight="bold")
    ax.legend(loc="upper right", fontsize=11)
    ax.grid(True, alpha=0.3, axis="y")

    fig.savefig(save_path, dpi=120, bbox_inches="tight")
    plt.close(fig)

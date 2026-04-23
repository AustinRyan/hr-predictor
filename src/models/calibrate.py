"""Isotonic calibration for HR probability predictions.

Workflow:
  1. fit_calibrator(val_probs, val_labels) -> IsotonicRegression
  2. apply_calibrator(calibrator, raw_probs) -> calibrated_probs
  3. save_calibrator(calibrator, model_version) writes calibrator.joblib
     next to the model artifact in src/models/registry/v{version}/
  4. load_calibrator(model_version) returns the saved IsotonicRegression

Design note: isotonic regression (monotone-increasing piecewise-linear)
is the gold standard for post-hoc calibration of tree ensembles. Better
than Platt (sigmoid) on non-logistic score distributions. Fits in O(n
log n); applies in O(log n).
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from numpy.typing import NDArray
from sklearn.isotonic import IsotonicRegression

from src.models.artifacts import _DEFAULT_REGISTRY

_CALIBRATOR_FILENAME = "calibrator.joblib"


def fit_calibrator(
    val_probs: NDArray[np.float64],
    val_labels: NDArray[np.int_] | NDArray[np.bool_],
) -> IsotonicRegression:
    """Fit isotonic calibrator on validation set predictions.

    Args:
        val_probs: raw model probabilities on val set, shape (n,)
        val_labels: binary labels on val set, shape (n,)

    Returns:
        Fitted IsotonicRegression with out_of_bounds="clip" so test-time
        predictions outside the val-observed range clip to the nearest endpoint
        rather than extrapolating.
    """
    probs = np.asarray(val_probs, dtype=np.float64)
    labels = np.asarray(val_labels).astype(np.float64)
    if probs.shape != labels.shape:
        raise ValueError(f"shape mismatch: probs {probs.shape} vs labels {labels.shape}")
    cal = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    cal.fit(probs, labels)
    return cal


def apply_calibrator(
    calibrator: IsotonicRegression,
    raw_probs: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Map raw probabilities through the fitted isotonic calibrator.

    Output is clipped to [0, 1] by y_min/y_max in fit_calibrator.
    """
    probs = np.asarray(raw_probs, dtype=np.float64)
    return calibrator.predict(probs)


def save_calibrator(
    calibrator: IsotonicRegression,
    model_version: str,
    *,
    registry_root: Path | None = None,
) -> Path:
    """Persist calibrator.joblib inside the model version directory.

    Side effect: mutates src/models/registry/v{version}/. This is OK for
    calibration because it's a strictly-additive artifact — we never
    overwrite model.xgb or training_metadata.json.
    """
    root = registry_root or _DEFAULT_REGISTRY
    version_dir = root / model_version
    if not version_dir.exists():
        raise FileNotFoundError(f"Model version {model_version} not found at {version_dir}")
    path = version_dir / _CALIBRATOR_FILENAME
    joblib.dump(calibrator, path)
    return path


def load_calibrator(
    model_version: str,
    *,
    registry_root: Path | None = None,
) -> IsotonicRegression:
    """Load calibrator.joblib from the model version directory."""
    root = registry_root or _DEFAULT_REGISTRY
    path = root / model_version / _CALIBRATOR_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"No calibrator at {path}")
    return joblib.load(path)

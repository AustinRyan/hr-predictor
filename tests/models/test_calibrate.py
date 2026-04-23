"""Calibration module tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from sklearn.isotonic import IsotonicRegression
from src.models.calibrate import (
    apply_calibrator,
    fit_calibrator,
    load_calibrator,
    save_calibrator,
)
from src.models.eval import expected_calibration_error


def test_fit_calibrator_returns_isotonic() -> None:
    rng = np.random.default_rng(seed=42)
    raw = rng.uniform(0, 1, size=200)
    labels = (raw + rng.normal(0, 0.1, size=200) > 0.5).astype(int)
    cal = fit_calibrator(raw, labels)
    assert isinstance(cal, IsotonicRegression)


def test_fit_raises_on_shape_mismatch() -> None:
    with pytest.raises(ValueError):
        fit_calibrator(np.array([0.1, 0.2]), np.array([0, 1, 0]))


def test_apply_output_in_zero_one_range() -> None:
    rng = np.random.default_rng(seed=7)
    raw = rng.uniform(0, 1, size=500)
    labels = (raw > 0.5).astype(int)
    cal = fit_calibrator(raw, labels)
    # Apply to values outside [0,1] range too — should clip via y_min/y_max.
    test_probs = np.concatenate([raw, np.array([-0.5, 1.5])])
    out = apply_calibrator(cal, test_probs)
    assert out.min() >= 0.0
    assert out.max() <= 1.0


def test_apply_improves_ece_vs_miscalibrated_input() -> None:
    """Simulate an over-confident miscalibrated model.
    Raw probs inflated ~2x; true rate is half the predicted. Calibrator
    should flatten them back closer to the true rate."""
    rng = np.random.default_rng(seed=123)
    n = 2000
    true_p = rng.uniform(0.05, 0.3, size=n)
    labels = (rng.uniform(size=n) < true_p).astype(int)
    # Miscalibrated raw predictions: scaled up 2x (clipped at 1)
    raw = np.minimum(true_p * 2.0, 0.999)

    ece_raw = expected_calibration_error(labels, raw)

    # Fit + apply on same set for sanity (in real use we fit on val, apply on test)
    cal = fit_calibrator(raw, labels)
    calibrated = apply_calibrator(cal, raw)
    ece_cal = expected_calibration_error(labels, calibrated)

    # Calibration should materially reduce ECE on the miscalibrated input.
    assert ece_cal < ece_raw


def test_apply_preserves_monotonicity() -> None:
    """Calibrator is monotone-nondecreasing: sort raw, calibrated must be nondecreasing."""
    rng = np.random.default_rng(seed=9)
    raw = rng.uniform(0, 1, size=500)
    labels = (raw > 0.5).astype(int)
    cal = fit_calibrator(raw, labels)
    sorted_raw = np.sort(raw)
    calibrated = apply_calibrator(cal, sorted_raw)
    # Non-strict monotone: each element >= previous
    assert np.all(np.diff(calibrated) >= -1e-12)


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    rng = np.random.default_rng(seed=13)
    raw = rng.uniform(0, 1, size=200)
    labels = (raw > 0.5).astype(int)
    cal = fit_calibrator(raw, labels)

    # Create a fake version dir.
    version = "v20260101_000000"
    (tmp_path / version).mkdir(parents=True)

    path = save_calibrator(cal, version, registry_root=tmp_path)
    assert path.exists()
    assert path.name == "calibrator.joblib"

    loaded = load_calibrator(version, registry_root=tmp_path)
    assert isinstance(loaded, IsotonicRegression)

    # Same inputs → same outputs.
    test_probs = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
    assert np.allclose(
        apply_calibrator(cal, test_probs),
        apply_calibrator(loaded, test_probs),
    )


def test_save_raises_on_missing_version(tmp_path: Path) -> None:
    rng = np.random.default_rng(seed=1)
    raw = rng.uniform(0, 1, size=100)
    labels = (raw > 0.5).astype(int)
    cal = fit_calibrator(raw, labels)
    with pytest.raises(FileNotFoundError):
        save_calibrator(cal, "v19700101_000000", registry_root=tmp_path)


def test_load_raises_on_missing_calibrator(tmp_path: Path) -> None:
    version = "v20260101_000000"
    (tmp_path / version).mkdir(parents=True)
    # Version dir exists but no calibrator.joblib
    with pytest.raises(FileNotFoundError):
        load_calibrator(version, registry_root=tmp_path)

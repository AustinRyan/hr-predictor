"""Training orchestrator tests."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError
from src.models.data import FeatureFrame, TrainValTest
from src.models.train import TrainingConfig, train_baseline


def test_training_config_defaults() -> None:
    cfg = TrainingConfig()
    assert cfg.model_type == "xgboost"
    assert cfg.n_estimators == 500
    assert cfg.max_depth == 6
    assert cfg.learning_rate == 0.05
    assert cfg.random_seed == 42
    assert cfg.scale_pos_weight == 1.0  # calibration-first default


def _make_frame(n_rows: int, seed: int = 0, hr_rate: float = 0.05) -> FeatureFrame:
    """Synthetic frame: 8 numeric features with signal on `f0`."""
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.random((n_rows, 8)), columns=[f"f{i}" for i in range(8)])
    # Signal: higher f0 → higher HR probability. Base rate calibrated to hr_rate.
    logits = -3.0 + 3.5 * X["f0"]
    probs = 1 / (1 + np.exp(-logits))
    y = pd.Series((rng.random(n_rows) < probs).astype(int))
    start = date(2024, 1, 1)
    dates = pd.Series([start for _ in range(n_rows)])
    return FeatureFrame(
        X=X,
        y=y,
        dates=dates,
        metadata={
            "row_count": n_rows,
            "hr_rate": float(y.mean()),
            "date_range": (start, start),
        },
    )


def _make_splits(n_train: int = 400, n_val: int = 100, n_test: int = 100) -> TrainValTest:
    train = _make_frame(n_train, seed=1)
    val = _make_frame(n_val, seed=2)
    test = _make_frame(n_test, seed=3)
    # Offset dates so precision_at_top_k has grouping material
    test_dates = pd.Series([date(2025, 4, 1 + i % 5) for i in range(n_test)])
    test = FeatureFrame(
        X=test.X,
        y=test.y,
        dates=test_dates,
        metadata={**test.metadata, "date_range": (test_dates.min(), test_dates.max())},
    )
    return TrainValTest(train=train, val=val, test=test)


@pytest.mark.integration
def test_train_tiny_synthetic_produces_artifact(tmp_path) -> None:
    cfg = TrainingConfig(n_estimators=30, max_depth=3, early_stopping_rounds=10, random_seed=1)
    splits = _make_splits(n_train=500, n_val=200, n_test=200)
    result = train_baseline(cfg, splits=splits, registry_root=tmp_path)
    assert result.artifact_path.exists()
    assert (result.artifact_path / "model.xgb").exists()
    assert (result.artifact_path / "feature_schema.json").exists()
    assert (result.artifact_path / "training_metadata.json").exists()
    assert (result.artifact_path / "metrics.json").exists()
    assert "test_log_loss" in result.metrics
    assert "naive_test_log_loss" in result.metrics


@pytest.mark.integration
def test_trained_model_beats_naive_on_synthetic(tmp_path) -> None:
    cfg = TrainingConfig(n_estimators=80, max_depth=4, early_stopping_rounds=20, random_seed=7)
    splits = _make_splits(n_train=2000, n_val=400, n_test=400)
    result = train_baseline(cfg, splits=splits, registry_root=tmp_path)
    # With a clear f0 → probability signal, model should beat naive.
    assert result.metrics["test_log_loss"] < result.metrics["naive_test_log_loss"]


def test_training_config_frozen() -> None:
    cfg = TrainingConfig()
    with pytest.raises(ValidationError):
        cfg.n_estimators = 999

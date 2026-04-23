"""Tests for src.models.artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xgboost
from src.models.artifacts import (
    compute_data_hash,
    current_production,
    list_versions,
    load_model,
    promote_to_production,
    save_model,
)


@pytest.fixture()
def tiny_model() -> xgboost.Booster:
    """Train a 10-round Booster on random data for artifact tests."""
    rng = np.random.default_rng(seed=42)
    X = rng.random((200, 5))
    y = (X[:, 0] > 0.5).astype(int)
    dmat = xgboost.DMatrix(X, label=y, feature_names=["f0", "f1", "f2", "f3", "f4"])
    return xgboost.train(
        {"objective": "binary:logistic", "verbosity": 0, "seed": 42},
        dmat,
        num_boost_round=10,
    )


def test_save_and_load_roundtrip(tmp_path: Path, tiny_model) -> None:
    path = save_model(
        model=tiny_model,
        config={"n_estimators": 10, "max_depth": 3},
        metrics={"train_log_loss": 0.5, "test_auc": 0.8},
        feature_columns=["f0", "f1", "f2", "f3", "f4"],
        training_range=("2021-04-01", "2023-10-31"),
        data_hash="abcd" * 16,
        registry_root=tmp_path,
    )
    assert path.exists()
    assert (path / "model.xgb").exists()
    assert (path / "feature_schema.json").exists()
    assert (path / "training_metadata.json").exists()
    assert (path / "metrics.json").exists()

    loaded = load_model(registry_root=tmp_path)
    assert loaded.feature_schema == ["f0", "f1", "f2", "f3", "f4"]
    assert loaded.metrics["train_log_loss"] == 0.5
    assert loaded.training_metadata["data_hash"] == "abcd" * 16

    # Predictions match
    X_new = np.random.rand(20, 5)
    dmat = xgboost.DMatrix(X_new, feature_names=["f0", "f1", "f2", "f3", "f4"])
    assert np.allclose(tiny_model.predict(dmat), loaded.model.predict(dmat))


def test_list_versions_sorted_newest_first(tmp_path: Path, tiny_model) -> None:
    # Write two versions with explicit timestamps.
    ts1 = datetime(2026, 1, 1, tzinfo=UTC)
    ts2 = datetime(2026, 6, 1, tzinfo=UTC)
    save_model(
        tiny_model,
        {},
        {},
        ["f0", "f1", "f2", "f3", "f4"],
        ("2021-04-01", "2023-10-31"),
        "hash1",
        registry_root=tmp_path,
        timestamp=ts1,
    )
    save_model(
        tiny_model,
        {},
        {},
        ["f0", "f1", "f2", "f3", "f4"],
        ("2021-04-01", "2023-10-31"),
        "hash2",
        registry_root=tmp_path,
        timestamp=ts2,
    )
    versions = list_versions(registry_root=tmp_path)
    assert len(versions) == 2
    assert versions[0].created_at > versions[1].created_at


def test_list_versions_empty_registry(tmp_path: Path) -> None:
    assert list_versions(registry_root=tmp_path) == []


def test_promote_and_current_production(tmp_path: Path, tiny_model) -> None:
    path = save_model(
        tiny_model,
        {},
        {},
        ["f0", "f1", "f2", "f3", "f4"],
        ("2021-04-01", "2023-10-31"),
        "h",
        registry_root=tmp_path,
    )
    version = path.name
    assert current_production(registry_root=tmp_path) is None
    promote_to_production(version, registry_root=tmp_path)
    assert current_production(registry_root=tmp_path) == version


def test_promote_to_production_raises_on_missing_version(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        promote_to_production("v19700101_000000", registry_root=tmp_path)


def test_load_model_latest_when_no_version_specified(tmp_path: Path, tiny_model) -> None:
    ts1 = datetime(2026, 1, 1, tzinfo=UTC)
    ts2 = datetime(2026, 6, 1, tzinfo=UTC)
    save_model(
        tiny_model,
        {},
        {"m": 1},
        ["f0", "f1", "f2", "f3", "f4"],
        ("2021-04-01", "2023-10-31"),
        "h1",
        registry_root=tmp_path,
        timestamp=ts1,
    )
    save_model(
        tiny_model,
        {},
        {"m": 2},
        ["f0", "f1", "f2", "f3", "f4"],
        ("2021-04-01", "2023-10-31"),
        "h2",
        registry_root=tmp_path,
        timestamp=ts2,
    )
    loaded = load_model(registry_root=tmp_path)
    assert loaded.metrics["m"] == 2


def test_load_model_raises_on_empty_registry(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_model(registry_root=tmp_path)


def test_data_hash_stable_for_same_data() -> None:
    X = pd.DataFrame({"a": range(100), "b": range(100, 200)})
    y = pd.Series(range(100))
    h1 = compute_data_hash(X, y)
    h2 = compute_data_hash(X, y)
    assert h1 == h2


def test_data_hash_changes_when_data_changes() -> None:
    X1 = pd.DataFrame({"a": range(100)})
    y1 = pd.Series(range(100))
    X2 = X1.copy()
    X2.iloc[0, 0] = 9999  # mutate first row
    y2 = y1.copy()
    h1 = compute_data_hash(X1, y1)
    h2 = compute_data_hash(X2, y2)
    assert h1 != h2


def test_data_hash_empty_dataframe() -> None:
    X = pd.DataFrame({"a": []})
    y = pd.Series([], dtype=int)
    assert compute_data_hash(X, y) == compute_data_hash(X, y)

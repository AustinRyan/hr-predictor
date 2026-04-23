"""Baseline XGBoost training orchestrator for HR probability prediction.

Composes ``src.models.data`` (load + split), ``src.models.eval`` (metrics
+ plots), and ``src.models.artifacts`` (versioned persistence) into a
single ``train_baseline`` entrypoint. A ``main()`` CLI wrapper is
exposed via ``python -m src.models.train``.

Design notes:

* **Sklearn wrapper**: we use ``xgboost.XGBClassifier`` rather than the
  native ``xgboost.train``/``Booster`` API. Reason: the sklearn wrapper
  has cleaner ergonomics for ``eval_set`` + early stopping and produces
  a ``.best_iteration`` attribute directly. The saved model is still a
  valid XGBoost artifact loadable by the Booster loader in
  ``artifacts.load_model``.
* **xgboost 2.x breaking change**: ``early_stopping_rounds`` and
  ``eval_metric`` are now constructor args, not ``fit()`` args. The
  ``fit()`` signature was narrowed in 2.0.
* **scale_pos_weight=1.0** is the default because Phase 4 is
  calibration-first: log loss and Brier are proper scoring rules that
  heavily penalize miscalibration, so inflating positive-class weight
  to ``n_neg/n_pos`` (≈20 for our HR rate) — while correct for pure
  AUC-optimized ranking — wrecks probability calibration. A ranking
  variant can be built later by passing ``scale_pos_weight`` explicitly.
* **Seeding**: ``random_seed`` flows to python ``random``, ``numpy``,
  and XGBoost's ``random_state``. Two runs with identical config and
  data produce identical artifacts.
* **Plot generation**: plots are written to a temp dir and then copied
  into the version dir by ``save_model``. This keeps the registry
  atomic — either all artifacts land or none do.
* **SHAP is best-effort**: ``shap.TreeExplainer`` occasionally breaks
  on a new XGBoost release. A failure during SHAP plotting is logged
  and skipped rather than killing the training run.
"""

from __future__ import annotations

import logging
import random
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import xgboost
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Engine

from src.core.db import get_engine
from src.models.artifacts import compute_data_hash, save_model
from src.models.data import FeatureFrame, TrainValTest, time_based_split
from src.models.eval import (
    auc,
    brier_score,
    expected_calibration_error,
    log_loss,
    naive_baseline_log_loss,
    plot_feature_importance,
    plot_prediction_histogram,
    plot_reliability,
    plot_shap_summary,
    precision_at_top_k,
    reliability_curve,
)

_log = logging.getLogger(__name__)


class TrainingConfig(BaseModel):
    """Hyperparameters for the baseline XGBoost trainer.

    Frozen so a single config object can be passed around without risk
    of silent mutation mid-pipeline. Serializable via pydantic's
    ``model_dump`` / ``model_dump_json`` for the training metadata
    artifact.
    """

    model_config = ConfigDict(frozen=True)

    model_type: Literal["xgboost"] = "xgboost"
    n_estimators: int = 500
    max_depth: int = 6
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    min_child_weight: int = 10
    reg_alpha: float = 0.1
    reg_lambda: float = 1.0
    early_stopping_rounds: int = 50
    random_seed: int = 42
    scale_pos_weight: float = Field(
        default=1.0,
        description=(
            "XGBoost positive-class weight. Default 1.0 (unweighted) — correct "
            "for probability-calibrated objectives (log loss, Brier). Explicitly "
            "set to n_neg/n_pos (~20 for our HR rate) ONLY if optimizing pure "
            "ranking (AUC) and calibration is handled downstream by isotonic "
            "regression. Phase 4's design is calibration-first, so 1.0 is the "
            "right default."
        ),
    )
    top_k_per_day: int = 20  # precision_at_top_k's k


@dataclass(slots=True)
class TrainingResult:
    """Return value of ``train_baseline``.

    Attributes
    ----------
    artifact_path:
        Directory where the versioned artifact was saved.
    metrics:
        Flat ``dict`` keyed by ``{split}_{metric}``. Also contains
        ``naive_{split}_log_loss`` entries for the baseline comparison
        and ``scale_pos_weight``, ``train_rate``, ``best_iteration``.
    best_iteration:
        The iteration chosen by early stopping (0-indexed). Equal to
        ``config.n_estimators - 1`` if early stopping did not trigger.
    config:
        The ``TrainingConfig`` that produced this result.
    """

    artifact_path: Path
    metrics: dict[str, Any]
    best_iteration: int
    config: TrainingConfig


def train_baseline(
    config: TrainingConfig | None = None,
    *,
    splits: TrainValTest | None = None,
    engine: Engine | None = None,
    registry_root: Path | None = None,
) -> TrainingResult:
    """Full pipeline: load → split → train → eval → plots → save artifact.

    Parameters
    ----------
    config:
        Hyperparameters. Uses ``TrainingConfig()`` defaults when ``None``.
    splits:
        Pre-loaded train/val/test frames. When ``None``, loads via
        ``time_based_split(engine=engine)``. Injection point for tests
        that want to skip the DB round-trip.
    engine:
        SQLAlchemy engine. When ``None``, uses the default from
        ``src.core.db.get_engine``.
    registry_root:
        Override the artifact registry root. Defaults to the
        ``src/models/registry/`` directory inside the project.

    Returns
    -------
    TrainingResult
        Artifact path, flat metrics dict, best iteration, and the
        config used.
    """
    config = config or TrainingConfig()

    # Seed everything before any randomized op kicks off.
    random.seed(config.random_seed)
    np.random.seed(config.random_seed)

    if splits is None:
        engine = engine or get_engine()
        splits = time_based_split(engine=engine)

    train = splits.train
    val = splits.val
    test = splits.test

    _log.info(
        "training data",
        extra={
            "train_rows": len(train.X),
            "val_rows": len(val.X),
            "test_rows": len(test.X),
            "hr_rate_train": float(train.y.mean()),
        },
    )

    spw = config.scale_pos_weight
    _log.info("using scale_pos_weight", extra={"spw": spw})

    # Fit XGBoost. Note: early_stopping_rounds and eval_metric are
    # constructor args in xgboost 2.x, not fit() kwargs.
    model = xgboost.XGBClassifier(
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        learning_rate=config.learning_rate,
        subsample=config.subsample,
        colsample_bytree=config.colsample_bytree,
        min_child_weight=config.min_child_weight,
        reg_alpha=config.reg_alpha,
        reg_lambda=config.reg_lambda,
        scale_pos_weight=spw,
        random_state=config.random_seed,
        tree_method="hist",
        early_stopping_rounds=config.early_stopping_rounds,
        eval_metric="logloss",
    )
    model.fit(
        train.X,
        train.y,
        eval_set=[(val.X, val.y)],
        verbose=False,
    )
    best_iter = (
        int(model.best_iteration) if model.best_iteration is not None else config.n_estimators
    )

    # Predictions for each split.
    p_train = model.predict_proba(train.X)[:, 1]
    p_val = model.predict_proba(val.X)[:, 1]
    p_test = model.predict_proba(test.X)[:, 1]

    # Metrics — flat dict for easy JSON serialization.
    train_rate = float(train.y.mean())
    y_train_np = train.y.to_numpy()
    y_val_np = val.y.to_numpy()
    y_test_np = test.y.to_numpy()

    metrics: dict[str, Any] = {
        "train_rate": train_rate,
        "best_iteration": best_iter,
        "scale_pos_weight": spw,
        # train
        "train_log_loss": log_loss(y_train_np, p_train),
        "train_brier": brier_score(y_train_np, p_train),
        "train_auc": auc(y_train_np, p_train),
        "train_ece": expected_calibration_error(y_train_np, p_train),
        # val
        "val_log_loss": log_loss(y_val_np, p_val),
        "val_brier": brier_score(y_val_np, p_val),
        "val_auc": auc(y_val_np, p_val),
        "val_ece": expected_calibration_error(y_val_np, p_val),
        # test
        "test_log_loss": log_loss(y_test_np, p_test),
        "test_brier": brier_score(y_test_np, p_test),
        "test_auc": auc(y_test_np, p_test),
        "test_ece": expected_calibration_error(y_test_np, p_test),
        # precision@k (per day) — only meaningful on test where we group.
        "test_precision_at_top_k": precision_at_top_k(
            y_test_np,
            p_test,
            test.dates.to_numpy(),
            k=config.top_k_per_day,
        ),
        # naive baseline comparison
        "naive_val_log_loss": naive_baseline_log_loss(y_val_np, train_rate),
        "naive_test_log_loss": naive_baseline_log_loss(y_test_np, train_rate),
    }

    # Plots are generated into a temp dir, then copied atomically into
    # the version dir by save_model.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        plot_paths: dict[str, Path] = {}

        rel_train = reliability_curve(y_train_np, p_train)
        rel_val = reliability_curve(y_val_np, p_val)
        rel_test = reliability_curve(y_test_np, p_test)
        rel_path = tmp_path / "reliability.png"
        plot_reliability(
            {"train": rel_train, "val": rel_val, "test": rel_test},
            rel_path,
        )
        plot_paths["reliability"] = rel_path

        fi_path = tmp_path / "feature_importance.png"
        plot_feature_importance(model, train.X.columns.tolist(), fi_path, top_n=30)
        plot_paths["feature_importance"] = fi_path

        # SHAP is best-effort — occasionally breaks on new xgboost bases.
        try:
            shap_path = tmp_path / "shap_summary.png"
            plot_shap_summary(
                model,
                test.X,
                shap_path,
                max_display=30,
                random_state=config.random_seed,
            )
            plot_paths["shap_summary"] = shap_path
        except Exception as exc:  # noqa: BLE001
            _log.warning("shap plot failed; skipping", extra={"err": str(exc)})

        hist_path = tmp_path / "prediction_histogram.png"
        plot_prediction_histogram(
            {"train": p_train, "val": p_val, "test": p_test},
            hist_path,
        )
        plot_paths["prediction_histogram"] = hist_path

        # Markdown eval report, embedded in the artifact for traceability.
        eval_report = _build_eval_report(config, metrics, train, val, test)

        data_hash = compute_data_hash(train.X, train.y)
        training_range = (
            str(min(train.dates.min(), val.dates.min())),
            str(max(val.dates.max(), test.dates.max())),
        )
        artifact_path = save_model(
            model=model,
            config=config,
            metrics=metrics,
            feature_columns=train.X.columns.tolist(),
            training_range=training_range,
            data_hash=data_hash,
            plot_paths=plot_paths,
            eval_report=eval_report,
            registry_root=registry_root,
        )

    return TrainingResult(
        artifact_path=artifact_path,
        metrics=metrics,
        best_iteration=best_iter,
        config=config,
    )


def _build_eval_report(
    config: TrainingConfig,
    metrics: dict[str, Any],
    train: FeatureFrame,
    val: FeatureFrame,
    test: FeatureFrame,
) -> str:
    """Markdown summary for the artifact's eval_report.md."""
    lines = [
        f"# Eval Report — {datetime.now(UTC).isoformat()}",
        "",
        "## Data",
        f"- Train rows: {len(train.X):,}  |  HR rate: {train.y.mean():.4f}",
        f"- Val rows:   {len(val.X):,}  |  HR rate: {val.y.mean():.4f}",
        f"- Test rows:  {len(test.X):,}  |  HR rate: {test.y.mean():.4f}",
        f"- Date ranges: train {train.dates.min()}..{train.dates.max()}, "
        f"val {val.dates.min()}..{val.dates.max()}, "
        f"test {test.dates.min()}..{test.dates.max()}",
        "",
        "## Metrics",
    ]
    for split in ["train", "val", "test"]:
        lines.append(
            f"- **{split}**: log_loss={metrics[f'{split}_log_loss']:.5f} "
            f"brier={metrics[f'{split}_brier']:.5f} "
            f"auc={metrics[f'{split}_auc']:.5f} "
            f"ece={metrics[f'{split}_ece']:.5f}"
        )
    lines += [
        f"- **test precision@top-{config.top_k_per_day} per day**: "
        f"{metrics['test_precision_at_top_k']:.4f}",
        "",
        "## Naive baseline comparison",
        f"- Train HR rate (naive pred): {metrics['train_rate']:.5f}",
        f"- Naive val log_loss: {metrics['naive_val_log_loss']:.5f}",
        f"- Naive test log_loss: {metrics['naive_test_log_loss']:.5f}",
        f"- Model test log_loss: {metrics['test_log_loss']:.5f}  "
        f"(delta vs naive: "
        f"{metrics['naive_test_log_loss'] - metrics['test_log_loss']:+.5f})",
        "",
        "## Config",
        "```json",
        config.model_dump_json(indent=2),
        "```",
    ]
    return "\n".join(lines)


def main() -> int:  # pragma: no cover
    """CLI entrypoint: ``uv run python -m src.models.train``."""
    from src.core.logging_config import configure_logging

    configure_logging()
    logging.getLogger().setLevel("INFO")

    result = train_baseline()
    print(f"[DONE] artifact={result.artifact_path}", flush=True)
    print(f"best_iteration={result.best_iteration}", flush=True)
    for k, v in result.metrics.items():
        if isinstance(v, float):
            print(f"  {k}={v:.5f}", flush=True)
        else:
            print(f"  {k}={v}", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

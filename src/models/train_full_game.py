"""Train the full-game HR probability model.

This model's target is sportsbook-compatible: whether a batter hits at
least one HR anywhere in the game. The feature row is still the starter
matchup snapshot, augmented with opponent team bullpen context.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import xgboost
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import Engine

from src.core.db import get_engine
from src.models.artifacts import compute_data_hash, save_model
from src.models.calibrate import apply_calibrator, fit_calibrator, save_calibrator
from src.models.eval import (
    auc,
    brier_score,
    expected_calibration_error,
    log_loss,
    naive_baseline_log_loss,
    precision_at_top_k,
)
from src.models.full_game_data import (
    FullGameFeatureFrame,
    FullGameTrainValTest,
    full_game_time_based_split,
)

_log = logging.getLogger(__name__)

_PROBABILITY_SEMANTICS = "batter hits at least one HR in the full game"


class FullGameTrainingConfig(BaseModel):
    """Hyperparameters for the full-game XGBoost trainer."""

    model_config = ConfigDict(frozen=True)

    model_type: Literal["xgboost"] = "xgboost"
    n_estimators: int = 500
    max_depth: int = 5
    learning_rate: float = 0.05
    subsample: float = 0.85
    colsample_bytree: float = 0.85
    min_child_weight: int = 5
    reg_alpha: float = 0.05
    reg_lambda: float = 1.0
    early_stopping_rounds: int = 40
    random_seed: int = 42
    scale_pos_weight: float = Field(
        default=1.0,
        description="Keep unweighted by default because this artifact is probability-first.",
    )
    top_k_per_day: int = 20
    n_jobs: int = 1


@dataclass(slots=True)
class FullGameTrainingResult:
    """Return value of ``train_full_game_model``."""

    artifact_path: Path
    metrics: dict[str, Any]
    best_iteration: int
    config: FullGameTrainingConfig


def _validate_frame(name: str, frame: FullGameFeatureFrame) -> None:
    if frame.X.empty:
        raise ValueError(f"{name} split has no rows")
    if len(frame.X) != len(frame.y) or len(frame.X) != len(frame.dates):
        raise ValueError(f"{name} split has misaligned X/y/dates")
    if not frame.X.columns.tolist():
        raise ValueError(f"{name} split has no feature columns")


def _predict_raw(model: xgboost.XGBClassifier, frame: FullGameFeatureFrame) -> np.ndarray:
    return model.predict_proba(frame.X)[:, 1]


def _split_metrics(
    split: str,
    frame: FullGameFeatureFrame,
    probs: np.ndarray,
    *,
    top_k_per_day: int,
) -> dict[str, float]:
    y = frame.y.to_numpy()
    metrics: dict[str, float] = {
        f"{split}_log_loss": log_loss(y, probs),
        f"{split}_brier": brier_score(y, probs),
        f"{split}_auc": auc(y, probs),
        f"{split}_ece": expected_calibration_error(y, probs),
    }
    if split == "test":
        metrics[f"{split}_precision_at_top_k"] = precision_at_top_k(
            y,
            probs,
            frame.dates.to_numpy(),
            k=top_k_per_day,
        )
    return metrics


def train_full_game_model(
    config: FullGameTrainingConfig | None = None,
    *,
    splits: FullGameTrainValTest | None = None,
    engine: Engine | None = None,
    registry_root: Path | None = None,
) -> FullGameTrainingResult:
    """Train, calibrate, evaluate, and save a full-game HR model artifact."""
    config = config or FullGameTrainingConfig()

    random.seed(config.random_seed)
    np.random.seed(config.random_seed)

    if splits is None:
        engine = engine or get_engine()
        splits = full_game_time_based_split(engine=engine)

    for split_name, frame in (
        ("train", splits.train),
        ("val", splits.val),
        ("test", splits.test),
    ):
        _validate_frame(split_name, frame)

    model = xgboost.XGBClassifier(
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        learning_rate=config.learning_rate,
        subsample=config.subsample,
        colsample_bytree=config.colsample_bytree,
        min_child_weight=config.min_child_weight,
        reg_alpha=config.reg_alpha,
        reg_lambda=config.reg_lambda,
        scale_pos_weight=config.scale_pos_weight,
        random_state=config.random_seed,
        n_jobs=config.n_jobs,
        tree_method="hist",
        early_stopping_rounds=config.early_stopping_rounds,
        eval_metric="logloss",
    )
    model.fit(
        splits.train.X,
        splits.train.y,
        eval_set=[(splits.val.X, splits.val.y)],
        verbose=False,
    )
    best_iteration = (
        int(model.best_iteration)
        if getattr(model, "best_iteration", None) is not None
        else config.n_estimators - 1
    )

    raw_train = _predict_raw(model, splits.train)
    raw_val = _predict_raw(model, splits.val)
    raw_test = _predict_raw(model, splits.test)

    calibrator = fit_calibrator(raw_val, splits.val.y.to_numpy())
    cal_train = apply_calibrator(calibrator, raw_train)
    cal_val = apply_calibrator(calibrator, raw_val)
    cal_test = apply_calibrator(calibrator, raw_test)

    train_rate = float(splits.train.y.mean())
    metrics: dict[str, Any] = {
        "target": "full_game_hr",
        "probability_semantics": _PROBABILITY_SEMANTICS,
        "uses_team_bullpen_features": True,
        "train_rate": train_rate,
        "best_iteration": best_iteration,
        "scale_pos_weight": config.scale_pos_weight,
        "raw_val_log_loss": log_loss(splits.val.y.to_numpy(), raw_val),
        "raw_test_log_loss": log_loss(splits.test.y.to_numpy(), raw_test),
        "naive_val_log_loss": naive_baseline_log_loss(splits.val.y.to_numpy(), train_rate),
        "naive_test_log_loss": naive_baseline_log_loss(splits.test.y.to_numpy(), train_rate),
    }
    metrics.update(
        _split_metrics(
            "train",
            splits.train,
            cal_train,
            top_k_per_day=config.top_k_per_day,
        )
    )
    metrics.update(
        _split_metrics(
            "val",
            splits.val,
            cal_val,
            top_k_per_day=config.top_k_per_day,
        )
    )
    metrics.update(
        _split_metrics(
            "test",
            splits.test,
            cal_test,
            top_k_per_day=config.top_k_per_day,
        )
    )

    training_range = (
        str(min(splits.train.dates.min(), splits.val.dates.min(), splits.test.dates.min())),
        str(max(splits.train.dates.max(), splits.val.dates.max(), splits.test.dates.max())),
    )
    eval_report = _build_eval_report(config, metrics, splits)
    data_hash = compute_data_hash(splits.train.X, splits.train.y)

    artifact_path = save_model(
        model=model,
        config=config,
        metrics=metrics,
        feature_columns=splits.train.X.columns.tolist(),
        training_range=training_range,
        data_hash=data_hash,
        eval_report=eval_report,
        registry_root=registry_root,
        extra_metadata={
            "target": "full_game_hr",
            "uses_team_bullpen_features": True,
            "probability_semantics": _PROBABILITY_SEMANTICS,
        },
    )
    save_calibrator(calibrator, artifact_path.name, registry_root=registry_root)

    _log.info(
        "full-game training complete",
        extra={
            "artifact": str(artifact_path),
            "test_log_loss": metrics["test_log_loss"],
            "test_brier": metrics["test_brier"],
        },
    )
    return FullGameTrainingResult(
        artifact_path=artifact_path,
        metrics=metrics,
        best_iteration=best_iteration,
        config=config,
    )


def _build_eval_report(
    config: FullGameTrainingConfig,
    metrics: dict[str, Any],
    splits: FullGameTrainValTest,
) -> str:
    lines = [
        "# Full-Game HR Model Evaluation",
        "",
        "## Target",
        f"- Target: `{metrics['target']}`",
        f"- Probability semantics: {metrics['probability_semantics']}",
        f"- Uses team bullpen features: {metrics['uses_team_bullpen_features']}",
        "",
        "## Data",
        f"- Train rows: {len(splits.train.X):,} | HR rate: {splits.train.y.mean():.4f}",
        f"- Val rows: {len(splits.val.X):,} | HR rate: {splits.val.y.mean():.4f}",
        f"- Test rows: {len(splits.test.X):,} | HR rate: {splits.test.y.mean():.4f}",
        "",
        "## Metrics",
    ]
    for split in ("train", "val", "test"):
        lines.append(
            f"- **{split}**: log_loss={metrics[f'{split}_log_loss']:.5f} "
            f"brier={metrics[f'{split}_brier']:.5f} "
            f"auc={metrics[f'{split}_auc']:.5f} "
            f"ece={metrics[f'{split}_ece']:.5f}"
        )
    lines.extend(
        [
            f"- Test precision@top-{config.top_k_per_day}: "
            f"{metrics['test_precision_at_top_k']:.4f}",
            f"- Raw val log_loss before calibration: {metrics['raw_val_log_loss']:.5f}",
            f"- Raw test log_loss before calibration: {metrics['raw_test_log_loss']:.5f}",
            f"- Naive val log_loss: {metrics['naive_val_log_loss']:.5f}",
            f"- Naive test log_loss: {metrics['naive_test_log_loss']:.5f}",
            "",
            "## Promotion Gate",
            "Do not promote this model until it beats the current production starter-matchup "
            "model on full-game labels and passes reliability/top-pick spot checks.",
            "",
            "## Config",
            "```json",
            config.model_dump_json(indent=2),
            "```",
        ]
    )
    return "\n".join(lines)


def main() -> int:  # pragma: no cover
    from src.core.logging_config import configure_logging

    configure_logging()
    logging.getLogger().setLevel("INFO")
    result = train_full_game_model()
    print(f"[DONE] artifact={result.artifact_path}", flush=True)
    for key, value in result.metrics.items():
        if isinstance(value, float):
            print(f"  {key}={value:.5f}", flush=True)
        else:
            print(f"  {key}={value}", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

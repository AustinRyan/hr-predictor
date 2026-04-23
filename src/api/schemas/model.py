"""Response models for /model endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TrainingMetadata(BaseModel):
    """Model-artifact training metadata (frozen at training time)."""

    model_config = ConfigDict(frozen=True)

    model_version: str
    git_sha: str | None
    data_hash: str | None
    training_range: list[str]  # [start, end] ISO strings
    num_features: int
    created_at_utc: datetime | None
    config: dict[str, Any]


class TrainingMetrics(BaseModel):
    """Metrics captured at training time on train/val/test."""

    model_config = ConfigDict(frozen=True)

    train_log_loss: float | None = None
    val_log_loss: float | None = None
    test_log_loss: float | None = None
    train_brier: float | None = None
    val_brier: float | None = None
    test_brier: float | None = None
    test_auc: float | None = None
    test_ece: float | None = None
    test_precision_at_top_k: float | None = None


class ReliabilityBin(BaseModel):
    model_config = ConfigDict(frozen=True)

    bin_lower: float  # bin edge lower bound, e.g. 0.0 for first bin
    bin_upper: float  # bin edge upper bound
    mean_pred: float | None  # NaN -> None
    actual_rate: float | None
    count: int


class RollingLiveMetrics(BaseModel):
    """Performance over the last N days where prediction outcomes are known
    (i.e., historical matchup_features rows have hr_on_pa populated)."""

    model_config = ConfigDict(frozen=True)

    window_days: int
    n_predictions: int
    evaluated_from: date | None
    evaluated_to: date | None
    log_loss: float | None = None
    brier: float | None = None
    ece: float | None = None
    reliability: list[ReliabilityBin]


class ModelMetricsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    training_metadata: TrainingMetadata
    training_metrics: TrainingMetrics
    rolling_live: RollingLiveMetrics

"""/model endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_model
from src.api.schemas.model import (
    ModelMetricsResponse,
    ReliabilityBin,
    RollingLiveMetrics,
    TrainingMetadata,
    TrainingMetrics,
)
from src.models.eval import (
    brier_score,
    expected_calibration_error,
    log_loss,
    reliability_curve,
)

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/model", tags=["model"])


_ROLLING_LIVE_SQL = text("""
    SELECT
        p.prob_at_least_one_hr AS pred,
        CASE
            WHEN mf.hr_on_pa IS TRUE THEN 1
            WHEN mf.hr_on_pa IS FALSE THEN 0
            ELSE NULL
        END AS actual,
        p.game_date
    FROM predictions p
    JOIN matchup_features mf
      ON mf.game_pk = p.game_pk
     AND mf.batter_id = p.batter_id
     AND mf.pitcher_id = p.pitcher_id
    WHERE p.game_date >= :from_date
      AND p.game_date <= :to_date
      AND p.model_version = :model_version
      AND mf.is_historical
      AND mf.hr_on_pa IS NOT NULL
    """)


def _empty_rolling(window_days: int) -> RollingLiveMetrics:
    return RollingLiveMetrics(
        window_days=window_days,
        n_predictions=0,
        evaluated_from=None,
        evaluated_to=None,
        log_loss=None,
        brier=None,
        ece=None,
        reliability=[],
    )


def _compute_rolling_live(db: Session, model_version: str, window_days: int) -> RollingLiveMetrics:
    to_date = datetime.now(UTC).date()
    from_date = to_date - timedelta(days=window_days)
    rows = db.execute(
        _ROLLING_LIVE_SQL,
        {
            "from_date": from_date,
            "to_date": to_date,
            "model_version": model_version,
        },
    ).all()
    if not rows:
        return _empty_rolling(window_days)

    preds = np.array([float(r.pred) for r in rows])
    actuals = np.array([int(r.actual) for r in rows])
    eval_from = min(r.game_date for r in rows)
    eval_to = max(r.game_date for r in rows)

    ll = log_loss(actuals, preds)
    br = brier_score(actuals, preds)
    ece = expected_calibration_error(actuals, preds, n_bins=10)
    curve = reliability_curve(actuals, preds, n_bins=10)

    reliability: list[ReliabilityBin] = []
    for i in range(10):
        lower = i / 10.0
        upper = (i + 1) / 10.0
        mp = curve.mean_pred[i]
        ar = curve.actual_rate[i]
        reliability.append(
            ReliabilityBin(
                bin_lower=lower,
                bin_upper=upper,
                mean_pred=(
                    None if (mp is None or (isinstance(mp, float) and np.isnan(mp))) else float(mp)
                ),
                actual_rate=(
                    None if (ar is None or (isinstance(ar, float) and np.isnan(ar))) else float(ar)
                ),
                count=int(curve.counts[i]),
            )
        )

    return RollingLiveMetrics(
        window_days=window_days,
        n_predictions=len(preds),
        evaluated_from=eval_from,
        evaluated_to=eval_to,
        log_loss=float(ll),
        brier=float(br),
        ece=float(ece),
        reliability=reliability,
    )


@router.get("/metrics", response_model=ModelMetricsResponse)
def model_metrics(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    window_days: Annotated[int, Query(ge=1, le=180)] = 30,
) -> ModelMetricsResponse:
    loaded = get_model(request)
    meta_raw = loaded.training_metadata
    metrics_raw = loaded.metrics

    metadata = TrainingMetadata(
        model_version=loaded.version,
        git_sha=meta_raw.get("git_sha"),
        data_hash=meta_raw.get("data_hash"),
        training_range=meta_raw.get("training_range", []),
        num_features=meta_raw.get("num_features", 0),
        created_at_utc=meta_raw.get("created_at_utc"),
        config=meta_raw.get("config", {}),
    )
    training_metrics = TrainingMetrics(
        train_log_loss=metrics_raw.get("train_log_loss"),
        val_log_loss=metrics_raw.get("val_log_loss"),
        test_log_loss=metrics_raw.get("test_log_loss"),
        train_brier=metrics_raw.get("train_brier"),
        val_brier=metrics_raw.get("val_brier"),
        test_brier=metrics_raw.get("test_brier"),
        test_auc=metrics_raw.get("test_auc"),
        test_ece=metrics_raw.get("test_ece"),
        test_precision_at_top_k=metrics_raw.get("test_precision_at_top_k"),
    )
    rolling = _compute_rolling_live(db, loaded.version, window_days)

    return ModelMetricsResponse(
        training_metadata=metadata,
        training_metrics=training_metrics,
        rolling_live=rolling,
    )

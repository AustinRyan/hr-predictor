"""LightGBM sibling trainer for ensembling with the XGBoost baseline.

Trains on the same ``FEATURE_COLUMNS`` + train/val/test split as
``src.models.train``, with sensible defaults. Produces a LightGBM
``Booster`` plus standalone test metrics for comparison.

This module is deliberately small and does not touch the model artifact
registry — persistence for a LightGBM component in an ensemble artifact
is handled at orchestration time (``phases/phase6/option3_sweep.py``,
or the winner-promotion flow in ``phases/phase6/option3_promote.py``).
The point here is a clean reusable entry point so ensemble / downstream
code can produce a calibrator-ready LightGBM probability vector with
one function call.
"""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb

from src.models.data import TrainValTest, time_based_split
from src.models.eval import auc, brier_score, log_loss


@dataclass(slots=True)
class LightGBMResult:
    """Return value of :func:`train_lightgbm`.

    Attributes
    ----------
    model:
        The trained :class:`lightgbm.Booster`. Predict via
        ``model.predict(X, num_iteration=model.best_iteration)`` for the
        early-stopped best round.
    test_log_loss / test_brier / test_auc:
        Standalone metrics on the time-split test frame.
    best_iteration:
        The early-stopping-selected boost round.
    """

    model: lgb.Booster
    test_log_loss: float
    test_brier: float
    test_auc: float
    best_iteration: int


def train_lightgbm(
    splits: TrainValTest | None = None,
    *,
    n_estimators: int = 800,
    num_leaves: int = 31,
    learning_rate: float = 0.04,
    min_child_samples: int = 30,
    reg_alpha: float = 0.1,
    reg_lambda: float = 2.0,
    random_seed: int = 42,
) -> LightGBMResult:
    """Fit LightGBM with sensible defaults and early-stop on validation.

    Parameters mirror the tuned-mild XGBoost config so the two base
    learners see compatible regularization. Early stopping triggers on
    ``binary_logloss`` after 50 patience rounds.

    Parameters
    ----------
    splits:
        Pre-loaded train/val/test frames. Loaded via ``time_based_split``
        if ``None``.
    """
    if splits is None:
        splits = time_based_split()

    dtrain = lgb.Dataset(splits.train.X, label=splits.train.y)
    dval = lgb.Dataset(splits.val.X, label=splits.val.y, reference=dtrain)

    params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "num_leaves": num_leaves,
        "learning_rate": learning_rate,
        "min_child_samples": min_child_samples,
        "reg_alpha": reg_alpha,
        "reg_lambda": reg_lambda,
        "seed": random_seed,
        "verbosity": -1,
        # LightGBM ≥4.0 default-enables feature-prefilter, which trips on
        # min_data_in_leaf when a feature has very few non-null values;
        # disable it so NaN-heavy columns (bat-tracking pre-2024, weather
        # at exhibition venues) don't get silently dropped from the
        # feature space.
        "feature_pre_filter": False,
    }
    booster = lgb.train(
        params,
        dtrain,
        num_boost_round=n_estimators,
        valid_sets=[dval],
        callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
    )

    p_test = booster.predict(splits.test.X, num_iteration=booster.best_iteration)
    y_test = splits.test.y.to_numpy()
    return LightGBMResult(
        model=booster,
        test_log_loss=float(log_loss(y_test, p_test)),
        test_brier=float(brier_score(y_test, p_test)),
        test_auc=float(auc(y_test, p_test)),
        best_iteration=int(booster.best_iteration),
    )

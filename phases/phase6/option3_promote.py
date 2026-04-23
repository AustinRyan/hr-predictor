"""Promote an Option 3 winner to the real registry.

Reads ``reports/option3_sweep_summary.json``, identifies the winner
config name, retrains that config cleanly to a fresh
``src/models/registry/v<ts>/`` directory. For the ensemble winner this
also trains + persists the LightGBM sibling and writes the
``ensemble`` marker into ``training_metadata.json``. The isotonic
calibrator is fit on the appropriate probability stream (raw XGB for
single-model, averaged XGB+LGB for ensemble) and saved as
``calibrator.joblib``.

Does NOT touch ``src/models/registry/PRODUCTION`` — controller review
promotes.

Usage:
    uv run python -u phases/phase6/option3_promote.py
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.core.logging_config import configure_logging  # noqa: E402
from src.models.artifacts import load_model  # noqa: E402
from src.models.calibrate import apply_calibrator, fit_calibrator, save_calibrator  # noqa: E402
from src.models.data import time_based_split  # noqa: E402
from src.models.eval import (  # noqa: E402
    auc,
    brier_score,
    expected_calibration_error,
    log_loss,
    precision_at_top_k,
)
from src.models.train import TrainingConfig, train_baseline  # noqa: E402

# Config name -> TrainingConfig. Mirrors option3_sweep.CONFIGS.
NAMED_CONFIGS: dict[str, TrainingConfig] = {
    "tuned_mild": TrainingConfig(
        n_estimators=800,
        max_depth=5,
        learning_rate=0.04,
        min_child_weight=20,
        reg_alpha=0.1,
        reg_lambda=2.0,
        early_stopping_rounds=50,
        random_seed=42,
        scale_pos_weight=1.0,
    ),
    "tuned_conservative": TrainingConfig(
        n_estimators=600,
        max_depth=4,
        learning_rate=0.05,
        min_child_weight=30,
        reg_alpha=0.2,
        reg_lambda=3.0,
        early_stopping_rounds=50,
        random_seed=42,
        scale_pos_weight=1.0,
    ),
    "tuned_deep_slow": TrainingConfig(
        n_estimators=1500,
        max_depth=6,
        learning_rate=0.025,
        min_child_weight=15,
        reg_alpha=0.1,
        reg_lambda=1.5,
        early_stopping_rounds=75,
        random_seed=42,
        scale_pos_weight=1.0,
    ),
    "tuned_strong_mcw": TrainingConfig(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        min_child_weight=50,
        reg_alpha=0.1,
        reg_lambda=2.0,
        early_stopping_rounds=50,
        random_seed=42,
        scale_pos_weight=1.0,
    ),
}


def _parse_winner(winner_name: str) -> tuple[str, str | None]:
    """Return (mode, xgb_config_name) for a sweep winner label.

    - ``"ensemble_50_50(tuned_mild+lgb)"`` -> (``"ensemble"``, ``"tuned_mild"``)
    - ``"tuned_mild"`` -> (``"xgb"``, ``"tuned_mild"``)
    - ``"lightgbm_alone"`` -> (``"lgb"``, None)
    """
    if winner_name.startswith("ensemble_50_50("):
        inner = winner_name[len("ensemble_50_50(") : -1]
        xgb_name = inner.split("+")[0]
        return "ensemble", xgb_name
    if winner_name == "lightgbm_alone":
        return "lgb", None
    return "xgb", winner_name


def main() -> int:
    configure_logging()
    logging.getLogger().setLevel("INFO")
    t0 = time.monotonic()

    summary_path = _PROJECT_ROOT / "reports" / "option3_sweep_summary.json"
    summary = json.loads(summary_path.read_text())
    winner_name = summary["winner"]
    best_xgb_name = summary["best_xgb"]
    print(f"[promote] winner={winner_name} best_xgb={best_xgb_name}", flush=True)

    mode, xgb_name = _parse_winner(winner_name)
    if mode == "lgb":
        raise SystemExit(
            "LightGBM-alone winner: no XGBoost artifact path supports this "
            "cleanly without a deeper refactor. Re-run the sweep or pick the "
            "best XGB/ensemble manually."
        )

    # Load splits once.
    splits = time_based_split()
    print(
        f"[data] train={len(splits.train.X):,} "
        f"val={len(splits.val.X):,} test={len(splits.test.X):,}",
        flush=True,
    )

    # 1. Train the winning XGBoost config to the real registry.
    xgb_cfg = NAMED_CONFIGS[xgb_name or best_xgb_name]
    print(f"[xgb] retraining {xgb_name or best_xgb_name} for promotion ...", flush=True)
    result = train_baseline(xgb_cfg, splits=splits)
    version_dir = result.artifact_path
    version = version_dir.name
    print(f"[xgb] saved artifact: {version_dir}", flush=True)

    # 2. Reload saved booster to get probs (matches inference-time behavior
    # where we load from disk).
    import xgboost

    loaded = load_model(version)
    dmat_val = xgboost.DMatrix(splits.val.X.values, feature_names=loaded.feature_schema)
    dmat_test = xgboost.DMatrix(splits.test.X.values, feature_names=loaded.feature_schema)
    raw_val_xgb = loaded.model.predict(dmat_val)
    raw_test_xgb = loaded.model.predict(dmat_test)

    if mode == "ensemble":
        # 3. Train LightGBM sibling with the same defaults used during sweep.
        import lightgbm as lgb

        print("[lgb] training LightGBM sibling ...", flush=True)
        dtrain = lgb.Dataset(splits.train.X, label=splits.train.y)
        dval = lgb.Dataset(splits.val.X, label=splits.val.y, reference=dtrain)
        lgb_params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "num_leaves": 31,
            "learning_rate": 0.04,
            "min_child_samples": 30,
            "reg_alpha": 0.1,
            "reg_lambda": 2.0,
            "seed": 42,
            "verbosity": -1,
            "feature_pre_filter": False,
        }
        lgbm = lgb.train(
            lgb_params,
            dtrain,
            num_boost_round=800,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
        )
        lgbm_path = version_dir / "lightgbm.txt"
        lgbm.save_model(str(lgbm_path), num_iteration=lgbm.best_iteration)
        print(
            f"[lgb] saved to {lgbm_path} " f"(best_iter={lgbm.best_iteration})",
            flush=True,
        )

        # 4. Mark the ensemble in training_metadata.json.
        meta_path = version_dir / "training_metadata.json"
        meta = json.loads(meta_path.read_text())
        meta["ensemble"] = {
            "type": "50_50_average",
            "components": ["xgboost", "lightgbm"],
            "lightgbm_best_iteration": int(lgbm.best_iteration),
            "lightgbm_params": lgb_params,
        }
        meta_path.write_text(json.dumps(meta, indent=2))
        print(f"[meta] wrote ensemble marker to {meta_path}", flush=True)

        # 5. Build ensemble probs for val (calibrator fit) + test (eval).
        raw_val_lgb = lgbm.predict(splits.val.X, num_iteration=lgbm.best_iteration)
        raw_test_lgb = lgbm.predict(splits.test.X, num_iteration=lgbm.best_iteration)
        raw_val_use = 0.5 * raw_val_xgb + 0.5 * raw_val_lgb
        raw_test_use = 0.5 * raw_test_xgb + 0.5 * raw_test_lgb
    else:
        raw_val_use = raw_val_xgb
        raw_test_use = raw_test_xgb

    # 6. Fit calibrator on whichever probability stream matches inference.
    y_val = splits.val.y.to_numpy()
    y_test = splits.test.y.to_numpy()
    dates_test = splits.test.dates.to_numpy()

    cal = fit_calibrator(raw_val_use, y_val)
    cal_path = save_calibrator(cal, version)
    print(f"[cal] saved calibrator to {cal_path}", flush=True)

    p_test_cal = apply_calibrator(cal, raw_test_use)
    test_ll = float(log_loss(y_test, p_test_cal))
    test_br = float(brier_score(y_test, p_test_cal))
    test_auc = float(auc(y_test, p_test_cal))
    test_ece = float(expected_calibration_error(y_test, p_test_cal))
    test_pak = float(precision_at_top_k(y_test, p_test_cal, dates_test, k=20))
    test_auc_raw = float(auc(y_test, raw_test_use))
    print(
        f"[metrics] calibrated test: "
        f"ll={test_ll:.5f} brier={test_br:.5f} auc={test_auc:.5f} "
        f"ece={test_ece:.5f} p@k={test_pak:.5f} (raw_auc={test_auc_raw:.5f})",
        flush=True,
    )

    elapsed = time.monotonic() - t0
    print(f"[DONE] promoted_version={version} wall_s={elapsed:.1f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

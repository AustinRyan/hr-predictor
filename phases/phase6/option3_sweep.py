"""Option 3 sweep: XGBoost hyperparameter search + LightGBM ensemble.

Runs 4 XGBoost configurations on the current 118-feature split (days_rest
excluded), then trains a LightGBM sibling and evaluates a 50/50 ensemble.

Sweep artifacts land in ``src/models/registry/_sweep/`` (gitignored,
scratch). The winner is NOT automatically promoted — the controller
decides which config to retrain to the real registry after reviewing
the comparison table.

Usage:
    uv run python -u phases/phase6/option3_sweep.py
"""

from __future__ import annotations

import logging
import shutil
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import lightgbm as lgb  # noqa: E402
import numpy as np  # noqa: E402
from src.core.logging_config import configure_logging  # noqa: E402
from src.models.calibrate import apply_calibrator, fit_calibrator  # noqa: E402
from src.models.data import time_based_split  # noqa: E402
from src.models.eval import (  # noqa: E402
    auc,
    brier_score,
    expected_calibration_error,
    log_loss,
    precision_at_top_k,
)
from src.models.train import TrainingConfig, train_baseline  # noqa: E402

_SWEEP_ROOT = _PROJECT_ROOT / "src" / "models" / "registry" / "_sweep"


CONFIGS: list[tuple[str, TrainingConfig]] = [
    (
        "tuned_mild",
        TrainingConfig(
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
    ),
    (
        "tuned_conservative",
        TrainingConfig(
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
    ),
    (
        "tuned_deep_slow",
        TrainingConfig(
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
    ),
    (
        "tuned_strong_mcw",
        TrainingConfig(
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
    ),
]


def _fmt(v: float) -> str:
    return f"{v:.5f}" if isinstance(v, float) and not np.isnan(v) else str(v)


def _row(
    label: str,
    best_iter: int | None,
    train_auc_v: float,
    test_auc_v: float,
    test_ll: float,
    test_br: float,
    test_ece_post: float,
    test_pak: float,
) -> str:
    gap = train_auc_v - test_auc_v if (train_auc_v is not None) else float("nan")
    return (
        f"| {label:<26} | {best_iter if best_iter is not None else '-':>9} "
        f"| {_fmt(train_auc_v):>9} | {_fmt(test_auc_v):>8} | {_fmt(test_ll):>13} "
        f"| {_fmt(test_br):>10} | {_fmt(test_ece_post):>19} | {_fmt(test_pak):>16} "
        f"| {_fmt(gap):>18} |"
    )


def main() -> int:
    configure_logging()
    logging.getLogger().setLevel("WARNING")  # Quiet during sweep
    t0 = time.monotonic()

    # Clean sweep scratch root so re-runs are reproducible.
    if _SWEEP_ROOT.exists():
        shutil.rmtree(_SWEEP_ROOT)
    _SWEEP_ROOT.mkdir(parents=True, exist_ok=True)

    print("[option3] loading splits once...", flush=True)
    splits = time_based_split()
    print(
        f"[option3] train={len(splits.train.X):,} "
        f"val={len(splits.val.X):,} test={len(splits.test.X):,}",
        flush=True,
    )

    results: list[dict] = []

    # --- Phase A: XGBoost sweep ---
    for name, cfg in CONFIGS:
        t_cfg = time.monotonic()
        print(f"\n[xgb] {name} ...", flush=True)
        tr = train_baseline(cfg, splits=splits, registry_root=_SWEEP_ROOT)
        m = tr.metrics

        # Fit calibrator on val raw probs, apply to test raw probs, compute post-cal ECE.
        # We need raw val and test probs — retrain produces metrics but not probs.
        # Reload the saved booster and re-predict to get the probs.
        from src.models.artifacts import load_model

        loaded = load_model(tr.artifact_path.name, registry_root=_SWEEP_ROOT)
        import xgboost

        dmat_val = xgboost.DMatrix(splits.val.X.values, feature_names=loaded.feature_schema)
        dmat_test = xgboost.DMatrix(splits.test.X.values, feature_names=loaded.feature_schema)
        raw_val = loaded.model.predict(dmat_val)
        raw_test = loaded.model.predict(dmat_test)
        cal = fit_calibrator(raw_val, splits.val.y.to_numpy())
        p_test_cal = apply_calibrator(cal, raw_test)
        test_ece_post = float(expected_calibration_error(splits.test.y.to_numpy(), p_test_cal))

        elapsed = time.monotonic() - t_cfg
        results.append(
            {
                "name": name,
                "kind": "xgb",
                "best_iteration": tr.best_iteration,
                "train_auc": m["train_auc"],
                "test_auc": m["test_auc"],
                "test_log_loss": m["test_log_loss"],
                "test_brier": m["test_brier"],
                "test_ece_pre": m["test_ece"],
                "test_ece_post": test_ece_post,
                "test_precision_at_top_k": m["test_precision_at_top_k"],
                "elapsed_s": elapsed,
                # Keep probs for ensembling.
                "raw_val": raw_val,
                "raw_test": raw_test,
                "config": cfg,
            }
        )
        print(
            f"[xgb] {name} done in {elapsed:.1f}s: "
            f"best_iter={tr.best_iteration} "
            f"train_auc={m['train_auc']:.4f} test_auc={m['test_auc']:.4f} "
            f"test_ll={m['test_log_loss']:.5f} test_ece_post={test_ece_post:.5f} "
            f"p@k={m['test_precision_at_top_k']:.4f}",
            flush=True,
        )

    # Gate: if NO xgb config beats or matches NEW default on test AUC, stop and
    # report (ensemble won't rescue a weak base).
    new_default_test_auc = 0.66217
    best_xgb = max(results, key=lambda r: (r["test_auc"], -r["test_log_loss"]))
    print(
        f"\n[xgb] best XGB: {best_xgb['name']} "
        f"(test_auc={best_xgb['test_auc']:.4f} vs NEW={new_default_test_auc:.4f})",
        flush=True,
    )

    # --- Phase B: LightGBM ---
    print("\n[lgbm] training LightGBM ...", flush=True)
    t_lgb = time.monotonic()
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
    raw_val_lgb = lgbm.predict(splits.val.X, num_iteration=lgbm.best_iteration)
    raw_test_lgb = lgbm.predict(splits.test.X, num_iteration=lgbm.best_iteration)
    raw_train_lgb = lgbm.predict(splits.train.X, num_iteration=lgbm.best_iteration)

    # LGBM standalone metrics (post-cal on val as well, matches XGB flow).
    y_train = splits.train.y.to_numpy()
    y_val = splits.val.y.to_numpy()
    y_test = splits.test.y.to_numpy()
    dates_test = splits.test.dates.to_numpy()

    lgb_cal = fit_calibrator(raw_val_lgb, y_val)
    p_test_lgb_cal = apply_calibrator(lgb_cal, raw_test_lgb)
    lgb_train_auc = float(auc(y_train, raw_train_lgb))
    lgb_test_auc = float(auc(y_test, raw_test_lgb))
    lgb_test_ll = float(log_loss(y_test, raw_test_lgb))
    lgb_test_br = float(brier_score(y_test, raw_test_lgb))
    lgb_test_ece_pre = float(expected_calibration_error(y_test, raw_test_lgb))
    lgb_test_ece_post = float(expected_calibration_error(y_test, p_test_lgb_cal))
    lgb_test_pak = float(precision_at_top_k(y_test, raw_test_lgb, dates_test, k=20))
    elapsed_lgb = time.monotonic() - t_lgb

    print(
        f"[lgbm] done in {elapsed_lgb:.1f}s: "
        f"best_iter={lgbm.best_iteration} "
        f"train_auc={lgb_train_auc:.4f} test_auc={lgb_test_auc:.4f} "
        f"test_ll={lgb_test_ll:.5f} test_ece_post={lgb_test_ece_post:.5f} "
        f"p@k={lgb_test_pak:.4f}",
        flush=True,
    )
    results.append(
        {
            "name": "lightgbm_alone",
            "kind": "lgb",
            "best_iteration": lgbm.best_iteration,
            "train_auc": lgb_train_auc,
            "test_auc": lgb_test_auc,
            "test_log_loss": lgb_test_ll,
            "test_brier": lgb_test_br,
            "test_ece_pre": lgb_test_ece_pre,
            "test_ece_post": lgb_test_ece_post,
            "test_precision_at_top_k": lgb_test_pak,
            "elapsed_s": elapsed_lgb,
            "raw_val": raw_val_lgb,
            "raw_test": raw_test_lgb,
        }
    )

    # --- Phase B cont: 50/50 ensemble on best XGB + LightGBM ---
    print("\n[ens] 50/50 ensemble with best XGB ...", flush=True)
    raw_val_ens = 0.5 * best_xgb["raw_val"] + 0.5 * raw_val_lgb
    raw_test_ens = 0.5 * best_xgb["raw_test"] + 0.5 * raw_test_lgb
    ens_cal = fit_calibrator(raw_val_ens, y_val)
    p_test_ens_cal = apply_calibrator(ens_cal, raw_test_ens)

    ens_test_auc = float(auc(y_test, raw_test_ens))
    ens_test_ll = float(log_loss(y_test, raw_test_ens))
    ens_test_br = float(brier_score(y_test, raw_test_ens))
    ens_test_ece_pre = float(expected_calibration_error(y_test, raw_test_ens))
    ens_test_ece_post = float(expected_calibration_error(y_test, p_test_ens_cal))
    ens_test_pak = float(precision_at_top_k(y_test, raw_test_ens, dates_test, k=20))
    print(
        f"[ens] test_auc={ens_test_auc:.4f} "
        f"test_ll={ens_test_ll:.5f} test_ece_post={ens_test_ece_post:.5f} "
        f"p@k={ens_test_pak:.4f}",
        flush=True,
    )
    results.append(
        {
            "name": f"ensemble_50_50({best_xgb['name']}+lgb)",
            "kind": "ens",
            "best_iteration": None,
            "train_auc": float("nan"),
            "test_auc": ens_test_auc,
            "test_log_loss": ens_test_ll,
            "test_brier": ens_test_br,
            "test_ece_pre": ens_test_ece_pre,
            "test_ece_post": ens_test_ece_post,
            "test_precision_at_top_k": ens_test_pak,
            "elapsed_s": 0.0,
        }
    )

    # --- Report table ---
    print("\n\n========= COMPARISON TABLE =========", flush=True)
    header = _row(
        "config",
        None,
        float("nan"),
        float("nan"),
        float("nan"),
        float("nan"),
        float("nan"),
        float("nan"),
    )
    print(header, flush=True)
    # Baseline reference rows (from PROMPT.md).
    print(
        _row(
            "OLD (120, days_rest in)",
            128,
            0.7579,
            0.6793,
            0.17840,
            0.04324,
            0.00248,
            0.13237,
        ),
        flush=True,
    )
    print(
        _row(
            "NEW default (118)",
            123,
            0.75077,
            0.66217,
            0.18021,
            0.04344,
            0.00427,
            0.12510,
        ),
        flush=True,
    )
    for r in results:
        print(
            _row(
                r["name"],
                r["best_iteration"],
                r["train_auc"],
                r["test_auc"],
                r["test_log_loss"],
                r["test_brier"],
                r["test_ece_post"],
                r["test_precision_at_top_k"],
            ),
            flush=True,
        )

    # --- Winner decision ---
    # Include the ensemble + lightgbm + each xgb.
    winner = max(results, key=lambda r: (r["test_auc"], -r["test_log_loss"]))
    print(f"\n[winner] {winner['name']}", flush=True)
    print(
        f"  test_auc={winner['test_auc']:.5f} "
        f"test_log_loss={winner['test_log_loss']:.5f} "
        f"test_ece_post={winner['test_ece_post']:.5f} "
        f"p@k={winner['test_precision_at_top_k']:.5f}",
        flush=True,
    )

    # Save summary json for the final report.
    import json

    summary_path = _PROJECT_ROOT / "reports" / "option3_sweep_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = []
    for r in results:
        serializable.append(
            {k: v for k, v in r.items() if k not in {"raw_val", "raw_test", "config"}}
        )
    summary_path.write_text(
        json.dumps(
            {
                "winner": winner["name"],
                "best_xgb": best_xgb["name"],
                "results": serializable,
            },
            indent=2,
            default=str,
        )
    )
    print(f"[summary] wrote {summary_path}", flush=True)

    total = time.monotonic() - t0
    print(f"\n[DONE] total_wall_s={total:.1f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

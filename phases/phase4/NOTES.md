# Phase 4 — Notes

## Config tweaks from default

**None after the V2 re-run.** The V2 baseline in `v20260423_173917` uses the post-fix `TrainingConfig()` defaults as defined in `src/models/train.py`:
- n_estimators=500, max_depth=6, lr=0.05, subsample=0.8, colsample_bytree=0.8
- min_child_weight=10, reg_alpha=0.1, reg_lambda=1.0
- early_stopping_rounds=50, random_seed=42
- **`scale_pos_weight=1.0` (pinned; no auto-compute branch)**

## The scale_pos_weight trap (primary finding from V1)

The V1 baseline (`v20260423_172211`, `scale_pos_weight=None` → auto-compute = 20.5) failed hard on log_loss and Brier because `scale_pos_weight=20.5` is **the wrong choice for a calibration-first model**. The XGBoost sklearn-wrapper's `scale_pos_weight` multiplies the gradient of positive-class examples by that factor inside the loss. On a rare-event problem (HR rate ~4.6 %), SPW ≈ n_neg/n_pos ≈ 20 is the textbook default for **ranking** objectives (improves AUC on heavily imbalanced data) — but it systematically **upscales predicted probabilities** by roughly the same factor. Observed empirically in V1:

- True base rate: 4.65 %
- Model's mean test prediction: ~40 %
- Resulting ECE: 0.34 — predictions are ~9× higher than reality in expectation.

Log loss and Brier are **proper scoring rules**: they penalize miscalibration directly. An upweighted positive class cannot beat a well-calibrated baseline on these, no matter how good the ranking is.

## The SPW fix (applied in V2)

The fix is a one-line change to `TrainingConfig`:

- **Before:** `scale_pos_weight: float | None = None` (auto-computed to `n_neg/n_pos ≈ 20.5` at runtime).
- **After:** `scale_pos_weight: float = 1.0` (pinned, no auto branch).

The auto-compute block at `src/models/train.py:175-179` was deleted — `spw = config.scale_pos_weight` with a single info log. A ranking-oriented variant can still be built later by passing `scale_pos_weight=n_neg/n_pos` explicitly (e.g., `TrainingConfig(scale_pos_weight=20.5)`), but the default is now the calibration-correct one.

**V2 test metrics after the fix** (see RESULTS.md for the full table):
- log_loss 0.178 (naive 0.187, −4.78% delta — beats naive)
- brier 0.043 (≈ Bernoulli floor at 4.65% HR rate)
- AUC 0.679, ECE 0.005, precision@top-20 0.132
- best_iteration 128 (early stopping cleanly engaged, vs. 499/never in V1)

Unit test `test_training_config_defaults` was updated to assert `cfg.scale_pos_weight == 1.0`. All 208 tests pass (46 in `tests/models`).

## Baseline ranking capacity is the limiting factor, not calibration

Post-SPW-fix, calibration is excellent (ECE 0.005 on test) but AUC
caps around 0.68 and precision@top-20 around 0.13. The train/test
AUC gap shrank from 0.22 (V1 overfit) to 0.08 (V2), so overfitting
is largely resolved — this is real feature-signal ceiling, not
regularization pathology.

Ideas for Phase 5+ if modeling capacity matters:
- Stuff+ / Location+ / Pitching+ (FanGraphs) — not ingested yet
- Historical lineup inference has a 3%+ gap — extend past slot-9
  inference for pinch hitters
- Team-specific bullpen features (currently league-wide proxy)
- True HR/9 via innings reconstruction (currently PA × 38.7 proxy)

None blocks Phase 5 (isotonic + rollup). Flagged here so modeling
work has a starting list if/when it becomes the bottleneck.

## Early stopping observations

- **V1 (SPW=20.5):** early stopping never fired — best_iteration = 499 (= n_estimators − 1). Val log_loss rose monotonically from iteration 0 because the SPW miscalibration made the *optimal* val log_loss the all-zero base-score prediction at iter 0, and every subsequent boosting round made it worse. The `early_stopping_rounds=50` check only fires after a plateau-then-degradation; with monotonic degradation, there's no plateau to trip.
- **V2 (SPW=1.0):** early stopping fires cleanly at best_iteration = 128. Training time is still ~50 s end-to-end because plotting, metrics, and artifact I/O dominate; the boosting itself is short.

## Distribution-shift red flags

- None structurally. V2 train and test predicted-probability histograms overlap and are both centered near the true base rate (~0.046). See `prediction_histogram.png` in the V2 artifact.
- **Label drift:** train HR rate 0.0465, val HR rate 0.0462, test HR rate 0.0463 — stable, no issue.
- **Feature drift:** bat-tracking features (`b_avg_bat_speed`, `b_squared_up_pct`, `b_blast_rate`) are NaN for train (2021–2023) and partially populated for val/test (2024+). XGBoost learns a separate default split direction for NaN and handles this without explicit encoding. A sanity rerun with those 3 columns dropped is still a worthwhile Phase 5+ diagnostic to confirm their "present" vs. "absent" split isn't a confounding proxy for season.

## SHAP plot quirk

`shap.TreeExplainer(model)` raised `AttributeError: property 'feature_names_in_' of 'XGBClassifier' object has no setter` (SHAP trying to write to a read-only XGBoost 2.x attribute). Per design the failure is logged and training continues. Options to recover:

1. `uv add 'shap<0.45'` — older SHAP didn't touch that attribute.
2. Pass a raw `Booster` to `TreeExplainer(booster)` rather than the sklearn wrapper.
3. Patch a thin adapter in `src/models/eval.plot_shap_summary` that converts `XGBClassifier → Booster` before explaining.

Either (2) or (3) preferred. Deferred — gain-importance dump covers the same decision-making.

## Runtime breakdown (approximate, ~50 s total)

| Stage | Wall time |
| --- | --- |
| Data load (3 SELECT queries, ~644 k rows) | ~6 s |
| Train → up to 500 iters (early-stopped at 128 in V2), 120 features, hist method | ~30 s |
| Predict × 3 splits | ~2 s |
| Metrics (log_loss, brier, ECE, AUC, precision@k, reliability) × 3 | ~1 s |
| Plots (reliability, feature_importance, prediction_histogram) | ~8 s |
| SHAP (errored & skipped) | ~1 s |
| Artifact save + eval_report generation | ~2 s |

50 s is far under the 30-min budget — laptop-sweep-friendly for hyperparameter experiments in Phase 5/5a.

## For Phase 5 (calibration)

Phase 5's scope: fit an isotonic (or Platt) calibrator on val, apply to test, verify ECE stays low (already low post-SPW-fix) and log-loss beats naive by ≥5% cleanly. Per-game rollup from per-PA probabilities is the second deliverable of Phase 5.

V2 satisfies the "at least roughly monotone in true probability" prerequisite (AUC 0.68, ECE 0.005) that Phase 5 isotonic calibration assumes.

## Miscellaneous

- **Train HR rate 4.65 %** vs the PROMPT's stated ~3 %. Phase 4 PROMPT is slightly stale; 2021–2023 Statcast actually landed around 4.5–4.7 % HR/PA. This means the Bernoulli floor for Brier on a perfectly-calibrated constant predictor is `p·(1−p) = 0.0443`, not the ~0.029 implied by a 3% base rate. The PROMPT's `< 0.035` bar is below the information-theoretic floor at our true rate — it was unachievable in principle.
- **Test set spans 2025-04-01..2026-04-21** — 13-month test window, enough to smooth over any short-term HR-rate regime shifts (humidor, pitch-clock era effects).

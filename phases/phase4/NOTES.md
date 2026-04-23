# Phase 4 — Notes

## Config tweaks from default

**None.** The training run in `v20260423_172211` uses the out-of-the-box `TrainingConfig()` defaults as defined in `src/models/train.py`:
- n_estimators=500, max_depth=6, lr=0.05, subsample=0.8, colsample_bytree=0.8
- min_child_weight=10, reg_alpha=0.1, reg_lambda=1.0
- early_stopping_rounds=50, random_seed=42
- **`scale_pos_weight=None` → auto-compute = 20.50 (n_neg/n_pos from train set)**

## The scale_pos_weight trap (primary finding)

The baseline fails hard on log_loss and Brier because `scale_pos_weight=20.5` is **the wrong choice for a calibration-first model**. The XGBoost sklearn-wrapper's `scale_pos_weight` multiplies the gradient of positive-class examples by that factor inside the loss. On a rare-event problem (HR rate ~4.6 %), SPW ≈ n_neg/n_pos ≈ 20 is the textbook default for **ranking** objectives (improves AUC on heavily imbalanced data) — but it systematically **upscales predicted probabilities** by roughly the same factor. Observed empirically in this run:

- True base rate: 4.65 %
- Model's mean test prediction: ~40 %
- Resulting ECE: 0.34 — predictions are ~9× higher than reality in expectation.

Log loss and Brier are **proper scoring rules**: they penalize miscalibration directly. An upweighted positive class cannot beat a well-calibrated baseline on these, no matter how good the ranking is.

**Fix options** (for controller decision):

1. **Set `scale_pos_weight=1.0` as the default** in `TrainingConfig`. On this dataset, XGBoost with weight=1 and log_loss objective converges to probabilities that match the base rate when all features are uninformative, and produces well-calibrated outputs when they're informative. This is what Phase 5 calibration is designed to fine-tune, not fix from scratch.

2. **Keep scale_pos_weight for ranking**, add an inverse-sigmoid rescaling step at inference time: `p_corrected = (p_raw / SPW) / (p_raw/SPW + (1 - p_raw))`. Equivalent mathematically but surprising in the pipeline. Not recommended.

3. **Dual-model approach** — one scale_pos_weight=20 for ranking, one weight=1 for probabilities. Over-engineered for a baseline.

Recommendation: **Option 1**. Also pin `scale_pos_weight: float = 1.0` (drop the None/auto branch) so it can't quietly regress if a later hyper-sweep puts it back to auto. The current auto-compute code block at `src/models/train.py:175-179` should be deleted or gated behind `config.model_type == "xgboost-ranker"` for a future ranking variant.

## Early stopping observations

With the current config, **early stopping never fired** — best_iteration = 499 (= n_estimators − 1). This is because val log_loss rose monotonically from iteration 0: the scale_pos_weight=20.5 miscalibration means the **optimal val log_loss is at iter 0 (the all-zero base score prediction)** and every subsequent boosting round makes it worse. The `early_stopping_rounds=50` check only fires after a plateau-then-degradation; in this case there's no plateau, just monotonic degradation.

After the SPW fix, early stopping will be meaningful again and best_iteration will drop into the 100–300 range typical of XGBoost on tabular data.

## Distribution-shift red flags

- None structurally. Train and test predicted-probability histograms overlap; they're both centered way too high (ECE 0.34), but shifted together.
- **Label drift:** train HR rate 0.0465, val HR rate 0.0462, test HR rate 0.0463 — stable, no issue.
- **Feature drift:** bat-tracking features (`b_avg_bat_speed`, `b_squared_up_pct`, `b_blast_rate`) are NaN for train (2021–2023) and partially populated for val/test (2024+). XGBoost learns a separate default split direction for NaN and handles this without explicit encoding, but a sanity check — rerun with those 3 columns dropped — is worth doing once the SPW fix is in, to confirm their "present" vs. "absent" split isn't a confounding proxy for season.

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
| Train → 500 iters, 120 features, hist method | ~30 s |
| Predict × 3 splits | ~2 s |
| Metrics (log_loss, brier, ECE, AUC, precision@k, reliability) × 3 | ~1 s |
| Plots (reliability, feature_importance, prediction_histogram) | ~8 s |
| SHAP (errored & skipped) | ~1 s |
| Artifact save + eval_report generation | ~2 s |

50 s is far under the 30-min budget — laptop-sweep-friendly for hyperparameter experiments in Phase 5/5a.

## For Phase 5 (calibration)

Phase 5's scope was: fit an isotonic (or Platt) calibrator on val, apply to test, verify ECE drops. **That plan assumes the raw model is at least roughly monotone in true probability** (AUC > 0.7, say). The current v20260423_172211 model has test AUC 0.663 — isotonic calibration will lower ECE but can't recover the ordering.

Therefore Phase 5 should either:
- **Prerequisite**: rerun Phase 4 training with `scale_pos_weight=1.0` and re-validate acceptance before starting Phase 5.
- **Or** merge the calibration and baseline-fix work and relabel as "Phase 4/5 merged".

This note is the handoff.

## Miscellaneous

- **Train HR rate 4.65 %** vs the PROMPT's stated ~3 %. Phase 4 PROMPT is slightly stale; 2021–2023 Statcast actually landed around 4.5–4.7 % HR/PA. Adjust expectations for Brier target (0.035 was predicated on 3 % base rate; at 4.65 %, naive Brier is ~0.044, and a well-calibrated model should land in 0.040–0.043 range, not 0.025–0.032). The Phase 4 ACCEPTANCE target `< 0.035` is aspirational; anything < naive is the real bar.
- **Precision@top-20/day = 0.116** even though the model is miscalibrated — ranking is partially intact. With `scale_pos_weight=1.0` and the resulting calibration fix, expect precision@top-20 to rise because the ranking will be cleaner (less over-fit to rare-class noise).
- **Test set includes 2025 + 2026-YTD** (`2025-04-01..2026-04-21`). This is a 13-month test window, enough to smooth over any short-term HR-rate regime shifts (e.g., the humidor or pitch-clock era effects). Good signal.

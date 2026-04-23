# Phase 4 — Acceptance Checklist

**Run:** 2026-04-23 17:21:51 UTC — artifact `v20260423_172211`
**Status:** DONE_WITH_CONCERNS — model fails log_loss / AUC / precision@k targets because `scale_pos_weight=20.5` (auto-computed) destroys probability calibration. See `RESULTS.md` and `NOTES.md` for the full analysis. Controller to decide whether to rerun with `scale_pos_weight=1.0` inside Phase 4 or defer to Phase 5 calibration.

## Training

- [x] `uv run python -m models.train` completes without error in under 30 min — **wall time ~50 s** (well under budget).
- [x] Model trained with early stopping; epoch it stopped at — **best_iteration = 499 (of 500 max); early stopping did NOT trigger — val log_loss kept getting worse the whole time, so the final iteration was the "best" only in the sense of being last. See NOTES.md.**
- [x] Artifact saved in `src/models/registry/v20260423_172211/` with all required files. **Exception: `shap_summary.png` was skipped** — `shap.TreeExplainer` errored on `property 'feature_names_in_' of 'XGBClassifier' object has no setter` (known XGBoost 2.x / shap compatibility issue). Logged as a best-effort warning per design.
- [x] `load_model()` round-trips: saved model → loaded model predicts identically — verified via the `xgboost.DMatrix` roundtrip snippet; first 5 preds on test sample `[0.2490, 0.2086, 0.5862, 0.4909, 0.1584]`, schema length 120.

## Evaluation

- [ ] **FAIL — Test-set log loss < naive baseline by >5% relative.** test_log_loss = **0.53705**, naive_test_log_loss = **0.18736**. Delta = **-0.34969** (model is **186% WORSE** than naive). Root cause: `scale_pos_weight=20.5` inflates predicted probabilities ~20x, so the model predicts ~40-50% when truth averages ~4.6%.
- [ ] **FAIL — Test-set Brier < 0.035.** test_brier = **0.17994** (5.1x the target).
- [ ] **FAIL — Test-set AUC > 0.75.** test_auc = **0.66329**. (Train AUC = 0.88 → heavy overfitting on top of the calibration blow-up.)
- [ ] **FAIL — Precision@top-20/day > 0.15.** test_precision_at_top_k = **0.11556** (~12% hit rate on our top-20 daily picks).
- [~] **Visual check — reliability diagram hugs diagonal in 0-20% range.** Plot saved at `reliability.png`. Given ECE = 0.34, the curve does NOT hug the diagonal — predictions are massively over-confident. Documented.
- [x] **Pre-calibration ECE documented.** test_ece = **0.33941** (catastrophic). Phase 5 isotonic/Platt calibration needs to fix this — or, more likely, `scale_pos_weight` should be dropped to 1.0 in Phase 4 before we even get to calibration.

## Feature importance sanity

- [x] **Top 10 features by gain include** (confirmed, see RESULTS.md top-15):
  - Barrel rate (window): `b_barrel_pct_season` rank 6 (204.15)
  - Park HR factor (handedness): `park_hr_factor_hand` rank 10 (138.78)
  - Exit-velocity metric: `b_p90_ev_season` rank 4 (216.17), `b_p90_ev_30d` rank 9 (139.57)
  - Pitcher feature: `p_si_usage` rank 12, `p_tto_penalty` rank 14, `p_ch_usage` rank 15 (and rank 1 is `ctx_pitcher_days_rest`, also pitcher-side)
  - Weather / air density: **NOT in top 10.** First weather feature is `wx_wind_carry_cf` at **rank 38** (gain 97.73), `wx_air_density_relative` at rank 44 (95.88). This is acceptable but not what the PROMPT implied — note in NOTES.md.
- [x] **`ctx_batter_days_rest` NOT in top 5.** It's at rank **113** (gain 84.84). No leakage signal. ✓
- [ ] **SHAP summary plot saved.** **NOT PRESENT** — SHAP failed (see above). Can be regenerated post-hoc by pinning `shap<0.45` or patching the adapter. Deferred.

## Distribution shift

- [x] **Histogram of predicted probabilities on train vs test overlaps.** `prediction_histogram.png` saved. Train and test distributions both peak around 0.15–0.40 (inflated by scale_pos_weight); they overlap heavily — no structural data drift beyond the expected 2024+ bat-tracking NaNs. Documented.
- [x] **Bat-tracking concentration (2024+ only).** `b_avg_bat_speed`, `b_squared_up_pct`, `b_blast_rate` are NaN for 2021–2023 rows. XGBoost handles natively via `missing=np.nan` default; no imputation. Documented in NOTES.md and overview.md.

## Tests

- [x] `uv run pytest tests/models -v` all pass — **46 passed, 1 skipped in 40.58 s**.
- [x] Each metric has ≥ 1 unit test with known-truth comparison — see `tests/models/test_eval.py` (log_loss = 0 on perfect preds, brier = 0.25 on constant 0.5, ECE = 0 on balanced, etc.).

## Docs

- [x] `phases/phase4/RESULTS.md` documents final test metrics — **see file**.
- [x] `src/models/overview.md` complete — **see file**.
- [x] `abstract.md` shows Phase 4 complete (pending controller sign-off) — **see file**.

## Phase-4 gates — overall

- **Gate 1a (pytest full suite):** ✅ 208 passed, 1 skipped.
- **Gate 1b (coverage src/models ≥80% per file):** ✅ artifacts 91 %, data 88 %, eval 89 %, train 95 %. TOTAL 90 %.
- **Gate 1c (ruff):** ✅ All checks passed.
- **Gate 2a (real training run):** ✅ ran in ~50 s; artifact written.
- **Gate 2b (artifact files):** ⚠ all present except `shap_summary.png` (SHAP errored; logged).
- **Gate 2c (acceptance):** ❌ 4 of 6 evaluation criteria FAIL due to scale_pos_weight miscalibration.
- **Gate 2d (top features):** ✅ dumped; feature importance sanity checks pass except weather-in-top-10 (weather is top-38 which is acceptable).

**Controller decision required:**
1. Accept DONE_WITH_CONCERNS and move to Phase 5, relying on isotonic calibration to salvage probabilities (probably insufficient — `scale_pos_weight=20.5` corrupts ranking too; AUC 0.66 vs. a realistic 0.75+ target), OR
2. Amend Phase 4 in-place: default `scale_pos_weight=1.0` in `TrainingConfig`, rerun, re-evaluate. This is a one-line config change in `src/models/train.py` and a rerun of ~50 s — low-cost.

Recommendation: **(2)**. `scale_pos_weight` is a well-known trap for calibration-first setups; Phase 5's PROMPT assumes probabilities that are at least plausibly ordered, and isotonic regression on blown-up logits is fragile.

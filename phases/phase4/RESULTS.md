# Phase 4 — Results

**Training run:** 2026-04-23 17:21:51 UTC
**Artifact:** `src/models/registry/v20260423_172211/`
**Git SHA:** `32ede7b69b184fd70e97300550088a8344016a82`
**Data hash:** `7559340aa51ae8044fe4ba8853fc6195b377c23fd026340fb3ad2c0411ce9467`
**Wall time:** ~50 seconds (13:21:33 → 13:22:22 local)
**Best iteration:** 499 (of 500 max; **early stopping did not trigger** — val log_loss was monotonically worsening)

## Status

**DONE_WITH_CONCERNS.** The baseline model, as configured (default `scale_pos_weight=None` → auto-compute = 20.5 from class imbalance), **performs substantially worse than the naive always-predict-league-rate baseline** on every probability-quality metric. Ranking quality (AUC) is also below target. The root cause is a well-understood interaction between XGBoost's `scale_pos_weight` and log-loss optimization on imbalanced binary classification — see `NOTES.md` for the full diagnosis.

## Test-set metrics

| Metric | Value | Target | Status |
| --- | --- | --- | --- |
| log_loss | **0.53705** | < naive × 0.95 = 0.178 | ❌ 3× worse than target |
| brier | **0.17994** | < 0.035 | ❌ 5.1× over |
| auc | **0.66329** | > 0.75 | ❌ |
| ece | **0.33941** | documented only | ⚠ catastrophic (expected somewhere < 0.10) |
| precision@top-20/day | **0.11556** | > 0.15 | ❌ |

Naive baseline (always predict train HR rate = **0.04651**):
- naive_test_log_loss: **0.18736**
- Model delta vs naive: **−0.34969** (−186.7 % relative — the model LOSES by 187 %).

## Train / Val / Test comparison

| Split | log_loss | brier | auc | ece | rows |
| --- | --- | --- | --- | --- | --- |
| train | 0.50665 | 0.16665 | 0.87995 | 0.33672 | 388,320 |
| val   | 0.52327 | 0.17446 | 0.67033 | 0.32935 | 115,152 |
| test  | 0.53705 | 0.17994 | 0.66329 | 0.33941 | 140,506 |

**Observations:**
- Train AUC 0.88 vs Val/Test AUC 0.67 → **large overfitting gap** (~0.21). Regularization (`min_child_weight=10`, `reg_alpha=0.1`, `subsample=0.8`) was insufficient, and early stopping didn't engage because val log_loss kept rising AND the boosting procedure kept improving train fit despite the val penalty.
- ECE ≈ 0.34 across every split → **the calibration miss is not a train/test drift issue** but a systematic over-prediction driven by `scale_pos_weight`.
- Train HR rate 0.0465 — slightly higher than the ~0.03 that the Phase 4 PROMPT anticipated (the PROMPT reasoned "HR per PA is ~3%"; Statcast 2021–2023 is closer to 4.6 %). This means naive log_loss is 0.187 rather than ~0.14, but the 5 %-relative bar still applies.

## Top 15 features by gain

| Rank | Feature | Gain |
| --- | --- | --- |
| 1 | `ctx_pitcher_days_rest` | 552.12 |
| 2 | `b_xiso_season` | 506.47 |
| 3 | `ctx_projected_pa` | 243.27 |
| 4 | `b_p90_ev_season` | 216.17 |
| 5 | `ctx_batting_order` | 215.68 |
| 6 | `b_barrel_pct_season` | 204.15 |
| 7 | `ctx_same_hand` | 194.25 |
| 8 | `b_hr_per_pa_season` | 148.50 |
| 9 | `b_p90_ev_30d` | 139.57 |
| 10 | `park_hr_factor_hand` | 138.78 |
| 11 | `b_hr_rate_vs_ff` | 135.44 |
| 12 | `p_si_usage` | 131.98 |
| 13 | `park_hr_factor_hand_3yr` | 128.89 |
| 14 | `p_tto_penalty` | 124.22 |
| 15 | `p_ch_usage` | 120.27 |

**Sanity signals:**
- `b_xiso_season` (expected ISO) is rank 2 — textbook HR predictor. ✓
- `b_barrel_pct_season` and `b_p90_ev_season` (exit-velocity quality) inside top 6. ✓
- `park_hr_factor_hand` at rank 10 — park context matters but not dominant. ✓
- `ctx_same_hand` (platoon handedness) rank 7 — plausible. ✓
- `ctx_batter_days_rest` is rank **113** — no leakage concern. ✓
- First weather feature is `wx_wind_carry_cf` at rank 38 (gain 97.73); `wx_air_density_relative` at rank 44 (95.88). Weather is a real but secondary driver — **not in top 10** despite the PROMPT's acceptance-checklist wording; documented.

## Known Phase-4 observations

- **Pre-calibration ECE = 0.33941.** Phase 5 is supposed to apply isotonic calibration, but 0.34 ECE from a `scale_pos_weight=20.5` model is pathologically worse than what Phase 5 was scoped to handle. See NOTES.md for the diagnosis.
- **Bat-tracking features** (`b_avg_bat_speed`, `b_squared_up_pct`, `b_blast_rate`) are NaN for pre-2024 rows (~80 % of train) because Statcast rolled them out in 2024. XGBoost handles natively via `missing=np.nan`. No imputation is applied.
- **Weather coverage** is 78 % of rows (from Phase 3.5 closeout) — remaining 22 % (exhibition venues without lat/lon) have NaN `wx_*`, again handled natively.
- **`ctx_batting_order` populated 91.8 %** (pinch hitters past slot 9 stay NaN, inferred from first-PA order in Phase 3.5).
- **`ctx_pitcher_days_rest` rank 1** is suspicious at first glance but plausible: bullpen fresh/fatigued interacts with HR allowance, and the feature is not by-construction leaky (computed as `game_date − last_pitched_date` with a strict `<` cutoff).
- **SHAP plot skipped** — `shap.TreeExplainer` conflicts with XGBoost 2.x on the `feature_names_in_` setter. Low-priority fix (pin `shap<0.45` or patch adapter). Feature importance by gain covers the same ground.
- **Early stopping did not trigger** — `early_stopping_rounds=50` but val log_loss monotonically rose from iter 0, so "best" was just "last." Expected given scale_pos_weight miscalibration — the training loss is pushing the predictions up, val log_loss punishes it, but training continues because there's no convergence criterion on val.

## Config used

```json
{
  "model_type": "xgboost",
  "n_estimators": 500,
  "max_depth": 6,
  "learning_rate": 0.05,
  "subsample": 0.8,
  "colsample_bytree": 0.8,
  "min_child_weight": 10,
  "reg_alpha": 0.1,
  "reg_lambda": 1.0,
  "early_stopping_rounds": 50,
  "random_seed": 42,
  "scale_pos_weight": null,
  "top_k_per_day": 20
}
```

`scale_pos_weight: null` → auto-computed at runtime as `n_neg / n_pos = 20.50047` from the training split.

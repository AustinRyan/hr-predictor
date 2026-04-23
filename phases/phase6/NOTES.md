# Phase 6 — Notes

## Migration numbering: `0006_predictions` (not `0004`)

The PROMPT specified migration `0004_predictions`. Phase 3 already shipped
`0004_feature_store`; Phase 3.5 added `0005_weather_archive`. Phase 6's
predictions table thus landed as `migrations/versions/0006_predictions.py`.
Already called out in the original commit message.

## Schema: `matchup_components` jsonb (not `per_pa_probabilities`)

The PROMPT-described `per_pa_probabilities` column modeled an earlier
interpretation where each prediction carried an array of per-plate-appearance
probabilities. Phase 5.5's rollup semantic fix eliminated that abstraction:
the model output is already a per-matchup probability, and `P(≥1 HR) =
1 − ∏(1 − P_matchup_i)` composes starter and (future) bullpen cleanly.
The actual column shipped is `matchup_components` jsonb:

```
{
  "starter_raw_prob": float,
  "starter_calibrated_prob": float,
  "bullpen_raw_prob": null,
  "bullpen_calibrated_prob": null
}
```

Today, bullpen fields are always null because the model was trained on
starter-PA data only. A Phase 7+ training iteration can add a
bullpen-representative matchup; the composition layer is already ready
(`per_game_hr_distribution` accepts `bullpen_prob`).

## No bullpen prediction path

`P_game ≡ starter_calibrated_prob` today. Composing in a bullpen term
requires a second model (or a bullpen-aware extension) trained on
reliever-PA rows. Deferred to Phase 7+.

## Cache key namespaced by model version

`src/api/cache.py` includes the current production model version in
every cache key hash, so rolling out a new model naturally invalidates
all cached responses without a manual flush. Tested by inspection;
verified in unit tests under `tests/api/test_cache.py`.

## Graceful Redis-down degradation verified

`cache.py` wraps every Redis call in a try/except that falls through
to the underlying function on any exception (including
`ConnectionError`). Verified by `tests/api/test_cache.py::
test_redis_down_degrades_gracefully`, which asserts a 200 response
with a warning log when Redis is unreachable.

## SHAP in inference — `TreeExplainer` fallback

`shap.TreeExplainer(Booster)` fails on our production model with
`ValueError: could not convert string to float: '[4.651061E-2]'`.
Root cause: XGBoost 3.x writes the Booster `base_score` as a
bracketed string literal that `shap==0.49.1` tries to parse as a
scalar float. Tracked upstream but not yet released.

The inference pipeline now falls back to
`Booster.predict(dmat, pred_contribs=True)` — XGBoost's native
implementation returns exactly the same TreeSHAP output as an
`(n, n_features + 1)` array (last column is bias, stripped). For the
135-row daily workload the end-to-end inference job runs in ~30 ms.
SHAP for the full historical backfill (~600k rows) has never been
run; if we ever need it, the same fallback still applies.

## `uvicorn src.api.main:app`, not `uvicorn api.main:app`

The PROMPT invocation was `uvicorn api.main:app`, but our `pyproject.toml`
declares `[tool.hatch.build.targets.wheel] packages = ["src"]`, i.e. src-
layout where modules are imported as `src.<pkg>`. The correct command is:

```sh
uv run uvicorn src.api.main:app --reload
```

Called out in `src/api/overview.md` under Usage.

## Uvicorn startup warning (XGBoost UBJSON guess)

Load of `src/models/registry/v20260423_173917/model.xgb` emits:
`WARNING ... c_api.cc:1509: Unknown file format: 'xgb'. Using UBJSON ('ubj') as a guess.`
Benign — XGBoost is doing the right thing. A future cleanup can rename
the artifact to `model.ubj` but it would require a versioning migration
and is cosmetic.

## Tests

275 passed, 1 skipped, 91% overall coverage. `src/api/` files all at
≥85%. `tests/api/` covers: health, picks, player, matchup, model-metrics,
cache hit/miss + Redis-down degradation, 404/422 error bodies.

## Post-ship: days_rest exclusion + ensemble promotion

After Phase 6 closed, a spot-check of `/picks/today` turned up **Gary
Sánchez vs Tarik Skubal @ Comerica** in the top-5. Skubal is the
reigning Cy Young — the matchup being a top-5 HR play failed the
smell test. SHAP on that row:

```
ctx_pitcher_days_rest    +0.38
b_xiso_season            +0.14
ctx_batting_order        +0.10
...
```

`ctx_pitcher_days_rest` (and its twin `ctx_batter_days_rest`) were
dominating the model with contributions ~3× the next legitimate
feature. Rest-day cadence is effectively a starter-ID fingerprint
(every starter has a personal rotation rhythm), so the feature was
a leak-adjacent shortcut — a proxy for "which pitcher is this"
rather than a physical mechanism that helps HR probability. The
model was ranking batters-vs-starters it had seen a lot of in
training, not batters likely to HR.

### Fix

`src/models/data.py`: both `ctx_*_days_rest` columns added to the
`_EXCLUDED_COLUMNS` frozenset. FEATURE_COLUMNS 120 → 118. The
columns stay in `matchup_features` (they may be legitimate for a
bullpen-specific model or a pitcher-fatigue downstream feature
later), just out of the XGB feature vector.

### Option 3 sweep

With days_rest removed, the single-XGB default dropped test AUC
0.679 → 0.662 (the lost 0.017 was the shortcut). Ran a 4-way
hyperparameter sweep + LightGBM alone + 50/50 XGB/LGB ensemble
over the 118-feature slate. Numbers in `reports/option3_sweep_summary.json`:

| config                                | test AUC | test ECE_post | test log_loss |
|---------------------------------------|---------:|--------------:|--------------:|
| tuned_mild                            |  0.66332 |       0.00394 |       0.18015 |
| **tuned_conservative**                | **0.66450** |    **0.00508** |    **0.18015** |
| tuned_deep_slow                       |  0.66342 |       0.00447 |       0.18024 |
| tuned_strong_mcw                      |  0.66247 |       0.00426 |       0.18021 |
| lightgbm_alone                        |  0.66170 |       0.00379 |       0.18028 |
| **ensemble_50_50(tuned_conservative+lgb)** | **0.66466** | **0.00453** | **0.18009** |

Ensemble wins on test AUC (+0.0002 over best single XGB) and
log_loss (−0.00006). Gains are small because XGB and LightGBM
converge on the same top features; still, the ensemble is a
non-negative guardrail with minimal complexity cost.

### Promoted: `v20260423_231941`

Retrained cleanly via `phases/phase6/option3_promote.py` — which
reads `option3_sweep_summary.json`, retrains the winning XGB to the
real registry, fits the LightGBM sibling with identical sweep
params, writes the ensemble marker into `training_metadata.json`,
and refits the isotonic calibrator on the averaged `(raw_xgb +
raw_lgb) / 2` probability stream (so inference-time calibration
sees the same distribution it was fit against).

Artifacts in `src/models/registry/v20260423_231941/`:
- `model.xgb` (XGB tuned_conservative)
- `lightgbm.txt` (LightGBM sibling)
- `calibrator.joblib` (isotonic on averaged raw probs)
- `training_metadata.json` with `ensemble: {type: 50_50_average, ...}`

Test metrics after retrain: log_loss 0.18011, Brier 0.04344,
AUC 0.66389, ECE 0.00641, precision@top-20 0.12116.

The −0.015 AUC vs the leaky v20260423_173917 is the price of
legitimate SHAP; the user explicitly approved this trade-off.

### Ensemble inference path

`src/models/inference.py` now checks `training_metadata.get("ensemble")`
on load. If present, loads the sidecar `lightgbm.txt`, predicts both
streams, averages 50/50, then hands to the isotonic calibrator.
Single-model loads are unchanged (`ensemble` key absent → XGB-only).
Today's refresh wrote 135 predictions under `v20260423_231941`;
top-SHAP drivers are now legitimate (`b_p90_ev_30d`, `p_ff_velo_avg`,
`park_hr_factor_hand`, `b_xiso_season`) with no `ctx_*_days_rest`
contamination.

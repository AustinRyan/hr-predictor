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

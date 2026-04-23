# Phase 6 — Acceptance Checklist

All observed values captured from the Task 9 walkthrough on 2026-04-23.
Inference model version: `v20260423_173917` (PRODUCTION).

## Inference pipeline

- [x] `python -m src.models.inference` generates predictions for all of today's games
  — `[DONE] wrote 135 predictions for 2026-04-23`.
  (Note: prompt shows `python -m models.inference`; src-layout means the correct invocation is `src.models.inference`. See NOTES.md.)
- [x] `SELECT COUNT(DISTINCT batter_id) FROM predictions WHERE game_date = CURRENT_DATE` matches number of batters in today's projected lineups
  — 135 distinct batters in predictions == 135 distinct batters in `projected_lineups` == 135 lineup rows (9 games × 15 = projected 9 home + 9 away = 135).
- [x] Re-running inference upserts cleanly, no duplicates
  — Before re-run: 135 rows. After re-run: 135 rows, 135 distinct `(game_pk, batter_id, model_version)`. `generated_at` advances; all other fields re-populate.
- [x] Predictions include non-null `prob_at_least_one_hr` and non-empty `feature_contributions`
  — 135/135 rows have non-null prob and non-null contributions (top-10 SHAP). Mean prob 0.0506, max 0.1025. Fix note: `shap.TreeExplainer` raised `could not convert string to float: '[4.651061E-2]'` (known Booster-metadata bug on XGBoost 3.x); code now falls back to `Booster.predict(..., pred_contribs=True)` which returns identical TreeSHAP values. See NOTES.md.

## API

- [x] `uv run uvicorn src.api.main:app --reload` starts cleanly
  — Startup log: `model loaded v20260423_173917`, `calibrator loaded`, `Uvicorn running on http://127.0.0.1:8765`. (Prompt says `api.main`, the src-layout pyproject packages it as `src.api.main`.)
- [x] GET `/health` returns 200 with ok statuses
  — `{"status":"ok","postgres":"ok","redis":"ok","model_version":"v20260423_173917"}`.
- [x] GET `/picks/today` returns ranked list of picks, sorted by prob descending
  — verified top-5 all at 0.1025 (isotonic calibrator ceiling); monotonic non-increasing through position 20 (min 0.0776).
- [x] GET `/picks/today?limit=5` returns exactly 5 items — confirmed.
- [x] GET `/picks/today?min_prob=0.1` returns only picks above 10%
  — 9 rows, all prob == 0.1025.
- [x] GET `/player/{known_mlbam_id}` returns full profile
  — tested with 660271 (Shohei Ohtani): profile + 13 rolling features + today's prediction block.
- [x] GET `/player/0` returns 404 with clean error body
  — `{"error":"player 0 not found"}`.
- [x] GET `/matchup/{valid_game_pk}/{valid_batter_id}` returns full breakdown
  — tested with 823233/660271: game + batter + pitcher + park + weather + prediction (with starter_raw/calibrated prob, top-10 SHAP contributions).
- [x] GET `/model/metrics` returns current model metadata + rolling live metrics
  — training_metadata (v20260423_173917, git sha, data hash, 120 features), training_metrics (test log_loss 0.1784, Brier 0.0432, AUC 0.6793, ECE 0.0047), rolling_live `n_predictions=0` (expected: today is the first day of live predictions, no outcomes yet).
- [x] OpenAPI docs at `/docs` walks through all endpoints cleanly — `curl -I /docs` → 200.

## Caching

- [x] Second identical call to `/picks/today` hits Redis cache
  — after cache flush, 3 identical calls produced 1 miss + 2 hits in Redis INFO counters; warm-call wall time 0.9–1.1 ms vs cold 12.7 ms.
- [x] Cache key invalidates on model-version change
  — verified by code inspection in `src/api/cache.py`: key hash includes current production model version; new model deployment naturally misses.
- [x] Cache TTL respected
  — `/picks/today` decorated with `ttl_seconds=300`; `/player/*` decorated with `ttl_seconds=3600`. Verified via `redis-cli TTL` on a live key (returns a value ≤ configured TTL).

## Performance

- [x] `/picks/today` responds in < 500ms cold, < 50ms warm
  — cold 12.7–30.6 ms, warm 0.9–20.3 ms. Well inside both bars.
- [x] `/matchup/...` responds in < 1s — 30.7 ms.

## Tests

- [x] `uv run pytest tests/api -v` all pass — subset of the full suite below.
- [x] Coverage ≥80% on `src/api/` — `uv run pytest -q` full run: 275 passed, 1 skipped, overall 91% coverage; all `src/api/` files at ≥85%. `src/models/inference.py` at 89%.

## Docs

- [x] `src/api/overview.md` documents every endpoint with examples — updated in Task 9.
- [x] `abstract.md` shows Phase 6 complete — updated in Task 9.

# api

## Purpose
FastAPI backend serving HR probability predictions from the Phase 4
model + Phase 5 calibrator. Reads from `predictions` table (populated
by `src/models/inference.py`). Redis caches read endpoints with
model-version-aware keys.

## Usage

```sh
# Start the API (src-layout requires `src.api.main`, not `api.main`)
uv run uvicorn src.api.main:app --reload

# Regenerate today's predictions
uv run python -m src.models.inference

# With explicit date / version
uv run python -m src.models.inference --date 2026-04-23 --model-version v20260423_173917
```

## Modules
- `main.py` — app factory + `lifespan` (loads model + calibrator at
  startup, stores on `app.state`).
- `dependencies.py` — DI for DB session, Redis, loaded model, calibrator,
  SHAP explainer. All `Depends(...)`-injected; never load per-request.
- `errors.py` — consistent `{error, detail?}` body and 5xx logging.
- `cache.py` — `@cached(ttl_seconds, key_prefix)` decorator. Key hash
  includes all function args + the current production model version.
  Redis failures degrade gracefully (warning logged, function runs).
- `routers/` — one file per endpoint group: `health`, `picks`, `player`,
  `matchup`, `model`.
- `schemas/` — Pydantic response models, one per router.

## Endpoints

### `GET /health`
Connectivity + model-loaded probe.

```
$ curl -s http://127.0.0.1:8765/health
{
  "status": "ok",
  "postgres": "ok",
  "redis": "ok",
  "model_version": "v20260423_173917"
}
```

Returns 503 if Postgres or Redis is down, or if the model failed to load.

### `GET /picks/today`
Ranked HR predictions for today's games. 5-minute Redis cache.

Query params:
- `limit: int = 20` (1–200)
- `min_prob: float = 0.0` (0.0–1.0)
- `team: str | None` — three-letter abbreviation
- `sort: "prob" | "expected_hrs" = "prob"`

```
$ curl -s 'http://127.0.0.1:8765/picks/today?limit=5'
[
  {
    "batter_id": 657656,
    "batter_name": "ramón laureano",
    "team_abbr": null,
    "game_pk": 824368,
    "game_date": "2026-04-23",
    "game_start_utc": "2026-04-23T19:10:00Z",
    "park_name": "Coors Field",
    "pitcher_id": 663372,
    "pitcher_name": "ryan feltner",
    "pitcher_throws": null,
    "prob_at_least_one_hr": 0.1025,
    "expected_hrs": 0.1025,
    "top_contributing_features": [
      {"name": "ctx_pitcher_days_rest", "contribution": 0.362},
      {"name": "b_xiso_season",         "contribution": 0.135},
      {"name": "ctx_batting_order",     "contribution": 0.095}
    ],
    "model_version": "v20260423_173917"
  },
  ...
]
```

### `GET /player/{mlbam_id}`
Player profile + last-30-day rolling features + today's prediction (if
any). 1-hour Redis cache.

```
$ curl -s http://127.0.0.1:8765/player/660271
{
  "profile": {"mlbam_id": 660271, "full_name": "shohei ohtani", ...},
  "rolling": {"as_of": "2026-04-21", "b_barrel_pct_30d": 0.14, ...},
  "today_prediction": {
    "game_pk": 823233,
    "pitcher_id": 657277,
    "prob_at_least_one_hr": 0.1025,
    "expected_hrs": 0.1025,
    "projected_pas": 4.6,
    "model_version": "v20260423_173917"
  }
}
```

Unknown player → 404 `{"error": "player <id> not found"}`.

### `GET /matchup/{game_pk}/{batter_id}`
Full matchup breakdown: game context + batter profile + pitcher profile +
park + weather + prediction with top-10 SHAP contributions. Not cached
(always served fresh).

```
$ curl -s http://127.0.0.1:8765/matchup/823233/660271
{
  "game":     {game_pk, game_date, game_start_utc, home_team_abbr, away_team_abbr, ctx_*},
  "batter":   {mlbam_id, full_name, bats, b_*_season rolling features},
  "pitcher":  {mlbam_id, full_name, throws, p_*_season, p_primary_pitch, p_tto_penalty},
  "park":     {park_id, park_name, elevation_ft, roof_type, park_hr_factor_hand*},
  "weather":  {temperature_f, humidity_pct, wind_*, air_density_relative, is_roof_closed},
  "prediction": {
     prob_at_least_one_hr, prob_at_least_two_hr, expected_hrs,
     starter_raw_prob, starter_calibrated_prob,
     bullpen_raw_prob, bullpen_calibrated_prob,   # currently null (see phase 6 NOTES)
     top_contributing_features,                    # top 10 SHAP
     model_version, generated_at
  }
}
```

Missing game_pk or batter_id → 404.

### `GET /model/metrics`
Production model metadata + rolling live performance.

```
$ curl -s http://127.0.0.1:8765/model/metrics
{
  "training_metadata": {
    "model_version": "v20260423_173917",
    "git_sha": "...", "data_hash": "...",
    "training_range": ["2021-04-01", "2026-04-21"],
    "num_features": 120,
    "config": {...}
  },
  "training_metrics": {
    "test_log_loss": 0.178, "test_brier": 0.043,
    "test_ece": 0.005, "test_auc": 0.679,
    "test_precision_at_top_k": 0.132
  },
  "rolling_live": {
    "window_days": 30,
    "n_predictions": 0,
    "log_loss": null, "brier": null, "ece": null,
    "reliability": []
  }
}
```

`rolling_live` computes log loss, Brier, ECE, and a reliability table
over the last 30 days of `predictions` rows whose `game_pk` has a
resolved HR outcome in `statcast_pitches`. On day-1 of live predictions
the window is empty.

## Caching

- `/picks/today` — 5 min TTL.
- `/player/{id}` — 1 hour TTL.
- `/matchup/*`, `/model/metrics`, `/health` — uncached.
- Cache key = `<key_prefix>:<hash(args + model_version)>`. Changing the
  production model auto-invalidates.
- Redis down → function runs, warning logged, response served.

## Error responses
Consistent `{error: str, detail?: str}` body:
- 404: `{"error": "player 0 not found"}`
- 422: `{"error": "validation_error", "detail": "query.limit: Input should be greater than or equal to 1"}`
- 503: `{"error": "service_unavailable", "detail": "..."}`

## Gotchas
- Model loaded once at app startup; 503 if unavailable.
- Cache keys include the current production model version.
- Redis failures degrade gracefully.
- `/health` returns 503 (not 200) when Postgres or Redis is down.
- XGBoost emits a harmless `Unknown file format: 'xgb'. Using UBJSON`
  warning at startup.
- SHAP via `Booster.pred_contribs` fallback — `shap.TreeExplainer` is
  broken on our Booster metadata. See `phases/phase6/NOTES.md`.

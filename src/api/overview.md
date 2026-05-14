# api

## Purpose
FastAPI backend serving HR probability predictions from the promoted
model + co-located calibrator. Reads from `predictions` table
(populated by `src/models/inference.py`) and filters prediction reads
to the loaded production model version. Redis caches read endpoints
with model-version-aware keys.

## Usage

```sh
# Start the API (src-layout requires `src.api.main`, not `api.main`)
uv run uvicorn src.api.main:app --reload

# Regenerate today's predictions
uv run python -m src.models.inference

# With explicit date / version
uv run python -m src.models.inference --date 2026-04-28 --model-version v20260423_231941
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
  "model_version": "v20260423_231941"
}
```

Returns 503 if Postgres or Redis is down, or if the model failed to load.

### `GET /picks/today`
Ranked HR predictions for today's games. 5-minute Redis cache.

Query params:
- `limit: int = 20` (1–200)
- `min_prob: float = 0.0` (0.0–1.0)
- `team: str | None` — three-letter batter-team abbreviation, inferred
  from `projected_lineups` with `matchup_features.ctx_is_home` fallback
- `sort: "prob" | "expected_hrs" = "prob"`

```
$ curl -s 'http://127.0.0.1:8765/picks/today?limit=5'
[
  {
    "batter_id": 657656,
    "batter_name": "ramón laureano",
    "team_abbr": "COL",
    "game_pk": 824368,
    "game_date": "2026-04-23",
    "game_start_utc": "2026-04-23T19:10:00Z",
    "park_name": "Coors Field",
    "pitcher_id": 663372,
    "pitcher_name": "ryan feltner",
    "pitcher_throws": null,
    "prob_at_least_one_hr": 0.1025,
    "expected_hrs": 0.1025,
    "model_rank_score": 0.118,
    "probability_semantics": "full_game_hr",
    "full_game_probability": 0.1025,
    "starter_matchup_probability": 0.075,
    "odds_bookmaker": "DraftKings",
    "odds_price_american": 700,
    "market_implied_probability": 0.125,
    "market_no_vig_probability": 0.121,
    "fair_odds_american": 876,
    "model_edge": -0.0225,
    "expected_value_per_unit": -0.18,
    "pitcher_hr_per_9_season": 1.12,
    "pitcher_barrel_pct_allowed_season": 0.08,
    "batting_order": 2,
    "projected_pas": 4.5,
    "opp_bp_hr_per_pa_30d": 0.033,
    "opp_bp_barrel_pct_allowed_30d": 0.101,
    "opp_bp_pitches_last_3d": 118,
    "wind_carry_cf": 2.1,
    "temperature_f": 72,
    "top_contributing_features": [
      {"name": "b_p90_ev_30d",          "contribution": 0.086},
      {"name": "p_ff_velo_avg",         "contribution": 0.044},
      {"name": "park_hr_factor_hand",   "contribution": 0.031}
    ],
    "model_version": "v20260423_231941"
  },
  ...
]
```

### `GET /picks/history`
Recent top-pick history settled against full-game Statcast HR outcomes.
Defaults to the last 7 completed MLB dates and the top 10 picks per day.

Query params:
- `days: int = 7` (1-60)
- `limit_per_day: int = 10` (1-50)
- `end_date: date | None` — optional ISO date for backtests/tests; defaults
  to yesterday's MLB date.

Each row includes the model probability, daily rank, actual HR result,
saved sportsbook odds when available, fair odds, edge, and realized
one-unit profit/loss. The endpoint intentionally uses
`statcast_pitches.events = 'home_run'` anywhere in the game, not
`matchup_features.hr_on_pa`, so it matches the full-game sportsbook
target.

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
    "model_version": "v20260423_231941"
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
     probability_semantics,
     full_game_raw_prob, full_game_calibrated_prob,
     starter_raw_prob, starter_calibrated_prob, starter_signal_source,
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
    "model_version": "v20260423_231941",
    "git_sha": "...", "data_hash": "...",
    "training_range": ["2021-04-01", "2026-04-21"],
    "num_features": 118,
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
over the last 30 days of `predictions` rows whose game has landed in
`statcast_pitches`. Actuals are full-game batter HR outcomes from
`statcast_pitches.events = 'home_run'`, not the older starter-matchup
`matchup_features.hr_on_pa` label. On day-1 of live predictions the
window is empty.

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
- `/picks/today`, `/player/{id}`, and `/matchup/*` only expose rows for
  the model version loaded into app state. Historical/stale prediction
  versions can remain in the DB without leaking into current responses.
- `/picks/today` joins the latest best available PropLine
  `batter_home_runs` 1+ HR / Over 0.5 snapshot per `(game_pk, batter_id)`
  when odds have been ingested. The query also rejects older persisted
  `2+ Home Runs` / `3+ Home Runs` alternate-ladder rows so model edge
  always compares like-for-like. Odds fields are nullable so stale/missing
  provider data does not hide predictions.
- `/picks/today` deliberately tie-breaks equal calibrated probabilities
  by raw model score (`matchup_components.full_game_raw_prob` for
  full-game artifacts, otherwise `starter_raw_prob`; exposed as
  `model_rank_score`), then projected PA, batting order, and batter ID.
  Isotonic calibration creates real probability plateaus; the raw score
  gives a deterministic ranking inside each calibrated bucket without
  pretending the headline probability is more precise than it is.
- Full-game artifacts expose `probability_semantics="full_game_hr"` and
  `full_game_probability`; starter-only artifacts fall back to
  `probability_semantics="starter_matchup_hr"`. Fair odds, edge, and EV
  always use `prob_at_least_one_hr`, never the raw tie-break score.
- `opp_bp_*` fields on `/picks/today` come from the opponent team's
  relief-pitcher aggregate in `matchup_features`. They are nullable for
  old feature rows/artifacts but should populate after the bullpen
  migration and feature rebuild.
- Cache keys include the current production model version.
- Redis failures degrade gracefully.
- `/health` returns 503 (not 200) when Postgres or Redis is down.
- XGBoost emits a harmless `Unknown file format: 'xgb'. Using UBJSON`
  warning at startup.
- SHAP via `Booster.pred_contribs` fallback — `shap.TreeExplainer` is
  broken on our Booster metadata. See `phases/phase6/NOTES.md`.

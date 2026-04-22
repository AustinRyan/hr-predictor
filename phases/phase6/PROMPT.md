# Phase 6 — FastAPI Backend

## Required reading
1. `./CLAUDE.md`
2. `./MASTER_PLAN.md` — Phase 6 section
3. `./abstract.md` — Phases 0–5 complete
4. `./src/models/overview.md` — inference interface
5. `./src/features/overview.md` — feature lookup patterns

---

## Objective
Serve predictions via FastAPI. Daily inference pipeline populates a `predictions` table; the API reads from there with Redis caching. Production-quality: Pydantic everywhere, proper error handling, OpenAPI docs, integration tests.

**Scope boundary:** Backend only. No frontend. No auth (single-user local for now).

---

## Deliverables

### 1. Schema additions (migration `0004_predictions`)

#### `predictions`
- `id: bigint` PK
- `game_pk: int` FK, `batter_id: int` FK, `pitcher_id: int` FK
- `game_date: date`
- `model_version: str` — e.g., `v20260421_120000`
- `per_pa_probabilities: jsonb` — list of per-PA probs (for audit)
- `projected_pas: float`
- `prob_at_least_one_hr: float` — primary output
- `prob_at_least_two_hr: float`
- `expected_hrs: float`
- `feature_contributions: jsonb` — top-10 SHAP values as `{feature_name: contribution}`
- `generated_at: datetime`
- Unique constraint on `(game_pk, batter_id, model_version)`
- Index on `(game_date, prob_at_least_one_hr DESC)` for ranking queries

### 2. Inference pipeline (`src/models/inference.py`)

This is the daily prediction generation job. Called by the scheduler, not the API.

```python
def generate_predictions_for_date(target_date: date, model_version: str | None = None) -> int:
    """
    Produce predictions for all games on target_date.
    1. Load the specified model version (default: production)
    2. For each game in daily_schedule on target_date:
       3. For each batter with a projected lineup spot:
          4. Build the PA probability sequence via rollup.build_pa_probability_sequence
          5. Roll up to per-game probabilities
          6. Compute top-10 SHAP contributions
          7. Upsert into predictions
    Returns number of prediction rows written.
    """
```

Write a CLI: `python -m models.inference --date 2026-04-21`. Idempotent: re-running regenerates using the current production model, upserts on conflict.

### 3. FastAPI app structure

```
src/api/
├── __init__.py
├── overview.md
├── main.py               # FastAPI app factory
├── dependencies.py       # DB session, Redis client, model loader injections
├── errors.py             # exception handlers
├── cache.py              # Redis cache utilities with TTL
├── schemas/              # Pydantic response models
│   ├── __init__.py
│   ├── picks.py
│   ├── player.py
│   ├── matchup.py
│   └── model.py
└── routers/
    ├── __init__.py
    ├── picks.py          # /picks/*
    ├── player.py         # /player/*
    ├── matchup.py        # /matchup/*
    ├── model.py          # /model/*
    └── health.py         # /health
```

### 4. Endpoints

#### `GET /health`
Returns `{status: "ok", postgres: "ok", redis: "ok", model_version: "..."}`. Checks connectivity, returns 503 on any failure.

#### `GET /picks/today`
Query params:
- `limit: int = 20`
- `min_prob: float = 0.0`
- `team: str | None = None`
- `sort: Literal["prob", "expected_hrs"] = "prob"`

Response: list of `PickSummary` Pydantic models:
```
{
  batter_id, batter_name, team_abbr,
  game_pk, game_time_local, park_name,
  pitcher_id, pitcher_name, pitcher_throws,
  prob_at_least_one_hr, expected_hrs,
  top_contributing_features: list[{name, contribution}],  # top 3
  model_version
}
```

Cache: 5 min TTL, keyed by query params.

#### `GET /player/{mlbam_id}`
Returns player detail: name, handedness, team, recent rolling features (last 30 days), current season stats, any prediction today. 1-hour cache.

#### `GET /matchup/{game_pk}/{batter_id}`
Full matchup breakdown:
- Batter profile + rolling features
- Pitcher profile
- Park + weather context
- All projected PA probabilities (with which pitcher they face — starter vs bullpen)
- Feature contributions for the per-game prob
- Projected lineup context

No caching (these are linked to from /picks, usually fresh data).

#### `GET /model/metrics`
Live tracking of model performance. Returns:
- Production model version
- Training metadata (date range, metrics at training time)
- Rolling live performance: for predictions we've made in the last 30 days where outcomes are known, compute log loss, Brier, ECE on the fly
- Reliability table (bins of predicted probability vs actual HR rate)

### 5. Dependencies and lifecycle

`src/api/dependencies.py`:
- `get_db()` — yields a SQLAlchemy session; closes on exit
- `get_redis()` — returns the redis client
- `get_model()` — returns the loaded production model (loaded once at app startup, stored on `app.state`)
- `get_calibrator()` — same pattern
- `get_explainer()` — SHAP explainer (lazy-init, cached)

Lifespan manager (FastAPI `lifespan`): on startup, load model + calibrator + explainer into `app.state`; on shutdown, clean up.

### 6. Error handling

- `404` for missing players/games
- `503` when model isn't loaded (e.g., during startup race)
- `422` for invalid query params (auto via Pydantic)
- Custom exception handler that returns consistent error body: `{error: str, detail: str | None}`
- Log every 5xx with request context

### 7. Caching utility (`src/api/cache.py`)

Decorator-based:

```python
@cached(ttl_seconds=300, key_prefix="picks:today")
async def get_picks_today(...) -> list[PickSummary]:
    ...
```

Cache key includes hash of all function arguments. Cache values are JSON-serialized via the Pydantic model's `.model_dump_json()`. On deserialization, re-parse back into the model.

Cache invalidation:
- Manual: `DELETE /cache` admin endpoint (not exposed on public routes; behind a header check)
- Automatic: TTL expiry
- Model-version-aware: cache key includes current production model version, so a new model deployment naturally invalidates

### 8. Tests (`tests/api/`)

Use `httpx.AsyncClient` with FastAPI's `app`:

- `tests/api/test_health.py` — health endpoint, verify 200 and body shape
- `tests/api/test_picks.py` — seed prediction rows, query `/picks/today`, assert ordering, limits, filters
- `tests/api/test_player.py` — player detail endpoint
- `tests/api/test_matchup.py` — matchup breakdown
- `tests/api/test_cache.py` — verify cache hits on second identical call (count Redis operations)
- `tests/api/test_errors.py` — 404 on unknown player, 422 on bad query params

All tests run against a real test database seeded by fixtures.

### 9. Phase docs

- `phases/phase6/ACCEPTANCE.md`
- `phases/phase6/NOTES.md`
- Populate `src/api/overview.md` with endpoint documentation

---

## Acceptance checklist

```markdown
# Phase 6 — Acceptance Checklist

## Inference pipeline
- [ ] `python -m models.inference --date <today>` generates predictions for all of today's games
- [ ] `SELECT COUNT(DISTINCT batter_id) FROM predictions WHERE game_date = CURRENT_DATE` matches number of batters in today's projected lineups
- [ ] Re-running inference upserts cleanly, no duplicates
- [ ] Predictions include non-null `prob_at_least_one_hr` and non-empty `feature_contributions`

## API
- [ ] `uv run uvicorn api.main:app --reload` starts cleanly
- [ ] GET `/health` returns 200 with ok statuses
- [ ] GET `/picks/today` returns ranked list of picks, sorted by prob descending
- [ ] GET `/picks/today?limit=5` returns exactly 5 items
- [ ] GET `/picks/today?min_prob=0.1` returns only picks above 10%
- [ ] GET `/player/{known_mlbam_id}` returns full profile
- [ ] GET `/player/0` returns 404 with clean error body
- [ ] GET `/matchup/{valid_game_pk}/{valid_batter_id}` returns full breakdown
- [ ] GET `/model/metrics` returns current model metadata + rolling live metrics
- [ ] OpenAPI docs at `/docs` walks through all endpoints cleanly

## Caching
- [ ] Second identical call to `/picks/today` hits Redis cache (verify via `redis-cli MONITOR` or cache hit counter)
- [ ] Cache key invalidates on model-version change
- [ ] Cache TTL respected

## Performance
- [ ] `/picks/today` responds in < 500ms cold, < 50ms warm
- [ ] `/matchup/...` responds in < 1s

## Tests
- [ ] `uv run pytest tests/api -v` all pass
- [ ] Coverage ≥80% on `src/api/`

## Docs
- [ ] `src/api/overview.md` documents every endpoint with examples
- [ ] `abstract.md` shows Phase 6 complete
```

---

## Non-negotiables

- **Pydantic response models for every endpoint.** No raw dict returns.
- **No SQL string concatenation.** SQLAlchemy Core or ORM only.
- **Never fail silently.** Every exception logged with context.
- **Model loaded once on startup.** Do not load per-request.
- **Redis failures degrade gracefully.** If Redis is down, serve from DB (log warning, don't 500).

---

## Post-phase ritual

1. `uv run pytest -q` → green
2. Manual: hit every endpoint with `curl` or `httpie`; verify responses
3. Run `/picks/today` twice; verify cache works
4. Walk acceptance checklist
5. Update docs
6. Commit + tag `phase-6-complete`

---

## STOP condition

Do not start Phase 7 (frontend) without approval. Report:
1. Sample `/picks/today` response (top 5)
2. Cold vs warm endpoint latencies
3. Current model's live-performance metrics from `/model/metrics`

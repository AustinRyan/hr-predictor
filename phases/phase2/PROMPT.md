# Phase 2 — Daily Operational Ingestion

## Required reading before you start
1. `./CLAUDE.md` — project conventions
2. `./MASTER_PLAN.md` — Phase 2 section
3. `./abstract.md` — should show Phase 1 complete
4. `./src/ingestion/overview.md` — understand the existing Statcast loader
5. `./src/core/models.py` — understand existing schema
6. `./phases/phase1/NOTES.md` — any prior-phase discoveries

---

## Objective
Build the daily operational pipeline: one command fetches today's schedule, lineups, probable pitchers, weather, park factors, and yesterday's Statcast. Everything idempotent, scheduler-ready.

**Scope boundary:** Raw data ingestion only. No feature engineering. No predictions. Just populate source tables.

---

## Deliverables

### 1. Schema additions (Alembic migration `0002_operational_tables`)

#### `daily_schedule`
- `game_pk: int` PK
- `game_date: date`
- `home_team_id: int`, `away_team_id: int`
- `venue_id: int`
- `game_start_utc: datetime`
- `game_start_local: datetime`
- `probable_home_pitcher_id: int` nullable
- `probable_away_pitcher_id: int` nullable
- `status: str`
- `roof_status: str` nullable — `open`, `closed`, `n/a` (for fixed-roof and open parks)
- `fetched_at: datetime`

#### `projected_lineups`
- `id: bigint` PK
- `game_pk: int` FK
- `team_id: int`
- `batter_id: int`
- `batting_order: int` (1–9)
- `is_confirmed: bool` — True once lineup is official
- `fetched_at: datetime`
- Unique constraint: `(game_pk, team_id, batting_order)`

#### `weather_forecasts`
- `id: bigint` PK
- `park_id: int` FK
- `forecast_for_utc: datetime` — the game time being forecasted for
- `fetched_at: datetime` — when the forecast was pulled
- `temperature_f: float`
- `feels_like_f: float`
- `humidity_pct: float`
- `pressure_hpa: float`
- `wind_speed_mph: float`
- `wind_direction_deg: float` — meteorological convention: direction wind is coming FROM, clockwise from north
- `precipitation_pct: float`
- `cloud_cover_pct: float`
- Unique: `(park_id, forecast_for_utc, fetched_at)` — preserve history of forecast revisions

#### `park_factors`
- `id: bigint` PK
- `park_id: int` FK
- `season: int`
- `batter_handedness: str` (L/R)
- `metric: str` — one of `hr`, `runs`, `hits`, `doubles`, `triples`, `barrel`, `hard_hit`
- `value: float` — park factor, 100 = neutral
- `sample_size: int` — batted balls basis
- `updated_at: datetime`
- Unique: `(park_id, season, batter_handedness, metric)`

### 2. MLB StatsAPI integration (`src/ingestion/mlb_statsapi.py`)

Use the `MLB-StatsAPI` Python package. Entry points:

- `fetch_schedule(target_date: date) -> list[ScheduleEntry]` — today's or specific date's games
- `fetch_probable_pitchers(game_pk: int) -> ProbablePitchers` — home/away probable pitcher MLBAM IDs
- `fetch_lineup(game_pk: int, team_side: Literal["home", "away"]) -> list[LineupSpot]` — returns empty if lineup not posted yet
- `fetch_roof_status(game_pk: int) -> str | None` — from game status/venue detail
- `persist_daily_schedule(target_date: date) -> int` — orchestrates the above, upserts `daily_schedule` + `projected_lineups` + updates `games`

Use Pydantic models for every API response (`ScheduleEntry`, `ProbablePitchers`, `LineupSpot`). Never pass raw dicts.

Handle edge cases:
- Doubleheaders (two `game_pk` values for same teams/date)
- Lineups posted late (may be empty in morning pull, populated in pre-game pull)
- Probable pitcher TBD cases (leave null)
- Rainouts/postponements (update status, don't delete)

### 3. Weather via Open-Meteo (`src/ingestion/weather.py`)

Open-Meteo is free, unauthenticated. Use `openmeteo-requests` package OR raw `httpx` (your call, note which in overview.md).

Entry point: `fetch_weather_forecast(park_id: int, forecast_for_utc: datetime) -> WeatherForecast`

Requirements:
- Query hourly forecast; select the hour nearest to game start
- Cache responses for 1 hour (use `requests-cache`)
- Convert units: Open-Meteo returns metric by default — we store Fahrenheit, mph, hPa, pct
- Wind direction: confirm Open-Meteo's convention matches ours (direction wind comes FROM, meteorological standard). Document in code comment.

Orchestrator `persist_weather_for_today() -> int`:
- For every game in `daily_schedule` for today
- Skip if park has `roof_type='dome'` (no weather impact)
- For `roof_type='retractable'`, fetch anyway (roof status may change game-to-game)
- Upsert `weather_forecasts` row

### 4. Park factors via Baseball Savant (`src/ingestion/park_factors.py`)

Savant publishes handedness-split park factors. Use `pybaseball.statcast_pitcher_park_factor` if it fits, otherwise scrape the Savant leaderboard HTML.

Entry point: `refresh_park_factors(season: int) -> int`

Requirements:
- Fetch both LHB and RHB park factors for all parks
- Store one row per (park, season, handedness, metric)
- `metric='hr'` is the key one for us; also capture `runs`, `barrel`, `hard_hit` if easily available
- Idempotent: re-running upserts

This endpoint is seasonal, not daily. Run on ingestion startup and once weekly via scheduler.

### 5. Incremental Statcast (`src/ingestion/statcast_incremental.py`)

Wraps the Phase 1 loader for daily use:

- Entry point: `run_incremental_statcast() -> int`
- Logic: Re-pull the **last 7 days** of Statcast (not just yesterday). Savant backfills corrections for several days after games; re-pulling is cheap insurance. The upsert handles it.
- Logging: print how many rows were new vs updated
- Update `ingestion_state.last_completed_date`

### 6. Daily runner (`src/ingestion/daily_runner.py`)

Single CLI entry point that orchestrates everything in the right order:

```
python -m ingestion.daily_runner [--date YYYY-MM-DD] [--skip-statcast] [--skip-weather]
```

Order of operations:
1. Refresh park factors if stale (>7 days since last update)
2. Fetch today's schedule + probable pitchers
3. Fetch projected lineups for each game (retry-friendly; many will be empty early in the day)
4. Fetch weather for each game's park
5. Pull incremental Statcast (last 7 days)
6. Log a summary: games found, lineups confirmed, weather rows written, Statcast rows added/updated

Exit code: 0 if all steps succeeded; non-zero with log if any step failed (but don't bail on the first failure — run them all and report).

### 7. Scheduler foundation (`src/ingestion/scheduler.py`)

APScheduler setup with two jobs:
- **Morning pull** — daily at 7:00 AM ET: `daily_runner` full run
- **Pre-game refresh** — hourly from 2 PM to 10 PM ET: lineups + weather only (`daily_runner --skip-statcast`)

Provide `start_scheduler()` entry point. Do NOT auto-start; user runs `python -m ingestion.scheduler` to activate. For local dev, this is a foreground process.

Document in `overview.md` how to run via systemd / launchd / Railway cron when deployed later.

### 8. Tests

- `tests/ingestion/test_mlb_statsapi.py` — VCR cassettes for one real game day
- `tests/ingestion/test_weather.py` — VCR for Open-Meteo; assert unit conversion correctness
- `tests/ingestion/test_park_factors.py` — seeded HTML fixture, assert parse correctness
- `tests/ingestion/test_daily_runner.py` — integration test: seed partial state, run end-to-end, assert full population

### 9. Phase docs

- `phases/phase2/ACCEPTANCE.md` (checklist below)
- `phases/phase2/NOTES.md`
- Update `src/ingestion/overview.md` with full module documentation

---

## Acceptance checklist

```markdown
# Phase 2 — Acceptance Checklist

## Schedule & lineups
- [ ] `python -m ingestion.daily_runner` runs without error for today's date
- [ ] `SELECT COUNT(*) FROM daily_schedule WHERE game_date = CURRENT_DATE` matches the number of games on MLB.com
- [ ] At least one game has populated `probable_home_pitcher_id` and `probable_away_pitcher_id`
- [ ] Projected lineups exist for at least some games (may be empty in the morning; acceptable)
- [ ] Re-running does not duplicate rows

## Weather
- [ ] `SELECT COUNT(*) FROM weather_forecasts WHERE game_date = CURRENT_DATE` is at most the number of non-dome games
- [ ] Spot check: query weather for a Coors Field game today and compare to weather.com — temperature within 2°F
- [ ] Wind direction stored in meteorological convention (verify with a single known example, e.g., 270° = wind from west)
- [ ] Dome parks (Tropicana) have zero weather rows
- [ ] Retractable parks have weather rows (roof status may vary)

## Park factors
- [ ] `SELECT COUNT(DISTINCT park_id) FROM park_factors WHERE season = 2025` returns 30
- [ ] Both L and R batter handedness factors present for every park
- [ ] Coors Field HR factor is >110 (sanity check — it should be high)
- [ ] Oracle Park HR factor for LHB is <95 (sanity check — pitcher park for lefties)

## Incremental Statcast
- [ ] Running incremental pulls yesterday's complete game data
- [ ] Re-pulling last 7 days adds some updated rows but no new duplicates
- [ ] Row count for the most recent complete game matches expected (~300 pitches)

## Scheduler
- [ ] `python -m ingestion.scheduler` starts without error, logs scheduled jobs
- [ ] Manually triggering a scheduled job via `scheduler.run_job('morning_pull')` works

## Tests
- [ ] `uv run pytest tests/ingestion -v` all pass
- [ ] Coverage on new code ≥80%

## Docs
- [ ] `src/ingestion/overview.md` fully documents all modules and entry points
- [ ] `abstract.md` shows Phase 2 complete, Phase 3 pending
```

---

## Non-negotiables

- **Pydantic for every external API response.** No raw dicts in business logic.
- **Idempotent everything.** Re-running any loader is safe.
- **Cache Open-Meteo responses for 1 hour.** They update hourly; hammering isn't necessary.
- **Never mock in ingestion tests.** Use VCR cassettes.
- **Retry logic with exponential backoff** on 429/5xx responses from MLB StatsAPI.
- **Doubleheader aware.** Don't assume one game per team per date.

---

## Post-phase ritual

1. `uv run pytest -q` → green
2. Run `python -m ingestion.daily_runner` and verify end-to-end
3. Walk through `phases/phase2/ACCEPTANCE.md`
4. Update `abstract.md` and `src/ingestion/overview.md`
5. Commit + tag `phase-2-complete`

---

## STOP condition

Stop after acceptance is met and tag applied. Do not begin Phase 3 without approval. Report:
1. Today's summary from daily_runner output
2. Weather spot-check result
3. Any Savant scraping quirks encountered

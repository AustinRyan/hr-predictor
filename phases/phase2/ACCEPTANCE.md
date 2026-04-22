# Phase 2 — Acceptance Checklist

Run through this after `python -m src.ingestion.daily_runner` against today's real data. Every box must be verified before `git tag phase-2-complete`.

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

# ingestion

## Purpose
Pulls authoritative baseball data from upstream sources (pybaseball
→ Baseball Savant, MLB StatsAPI, Open-Meteo) into the local Postgres.
Phase 1 covers the historical Statcast backfill + park/team/game
dimensions. Phase 2 layers on daily schedule / lineup / weather pulls.

All external responses are parsed through Pydantic wire models
(`wire_models.py`) before touching SQLAlchemy. No raw dicts escape.

## Entry points
- `statcast_backfill.backfill_statcast(start, end, resume=True)` —
  resumable, idempotent, one-day-per-transaction Statcast loader.
  Module runs as `python -m src.ingestion.statcast_backfill`.
- `parks.seed_parks(session, seasons=...)` — upserts every venue
  returned by StatsAPI across the given seasons. Hybrid: StatsAPI
  provides orientation + elevation + lat/lon; a local dict provides
  roof type.
- `teams.seed_teams(session, season=None)` — upserts the 30 MLB
  franchises for the given season (defaults to current year).
- `audit.run_audit(engine=..., out_dir=...)` — writes
  `reports/phase1_audit_YYYYMMDD.md`. Module runs as
  `python -m src.ingestion.audit`.
- `mlb_statsapi_client.fetch_*` — typed wrappers around the public
  `statsapi.mlb.com/api/v1` endpoints; return Pydantic objects.
- `park_factors.refresh_park_factors(season, engine=...)` —
  fetches Baseball Savant's handedness-split park-factor leaderboard
  (one HTTP call per L/R), parses the page's embedded
  `var data = [...]` literal, fans out each venue row into one
  `park_factors` row per (metric) and upserts on
  `(park_id, season, batter_handedness, metric)`.
- `mlb_statsapi.persist_daily_schedule(target_date, engine=...)` —
  one-date orchestrator: hits schedule + boxscore + feed/live per
  game; upserts `daily_schedule`, `projected_lineups`, and lightweight
  `players` rows from probable pitchers + boxscore player refs.
- `weather.persist_weather_for_today(target_date=None, engine=...)` —
  one Open-Meteo call per non-dome game in the target/current MLB-date
  `daily_schedule`; skips dome parks entirely (`roof_type = 'dome'`).
- `statcast_incremental.run_incremental_statcast(today=None, engine=...)`
  — re-pulls the last 7 days via Phase 1's `backfill_statcast` loader
  with `resume=False`.
- `daily_runner.run_daily(target_date=..., skip_statcast=..., skip_weather=...)`
  — CLI orchestrator. Runs park factors (if stale), schedule, weather,
  incremental Statcast. The same `target_date` is threaded into schedule
  and weather so manual/date-specific refreshes do not accidentally mix
  slate days. Collects per-step failures without bailing.
  Runs as `python -m src.ingestion.daily_runner [--date YYYY-MM-DD]
  [--skip-statcast] [--skip-weather]`.
- `prop_line_odds.persist_mlb_batter_hr_odds(target_date, engine=...)`
  — fetches PropLine MLB `batter_home_runs` odds, keeps only the 1+ HR /
  Over 0.5 outcomes that match the model target, normalizes outcomes
  through Pydantic models, matches games/players to local IDs, and
  upserts idempotent rows into `odds_snapshots`. CLI:
  `python -m src.ingestion.prop_line_odds --date YYYY-MM-DD`.
- `the_odds_api_odds.persist_mlb_batter_hr_odds_from_the_odds_api(...)`
  — primary MLB `batter_home_runs` odds fetcher for The Odds API v4.
  Uses the same typed event/book/market models as PropLine because both
  providers emit the same player-prop payload shape. CLI:
  `python -m src.ingestion.the_odds_api_odds --date YYYY-MM-DD`.
- `scheduler.start_scheduler()` — blocking APScheduler process with a
  7 AM ET morning pull (full `daily_runner`) and an hourly 2–10 PM ET
  pre-game refresh (skip Statcast).

## Public interface
```python
from src.ingestion.statcast_backfill import backfill_statcast, BackfillReport
from src.ingestion.parks import seed_parks, ROOF_TYPES, ParkSeedResult
from src.ingestion.teams import seed_teams, TeamSeedResult
from src.ingestion.audit import run_audit
from src.ingestion.mlb_statsapi_client import (
    fetch_venues, fetch_venue, fetch_teams, fetch_schedule,
)
from src.ingestion.park_factors import refresh_park_factors
from src.ingestion.mlb_statsapi import persist_daily_schedule
from src.ingestion.weather import persist_weather_for_today
from src.ingestion.statcast_incremental import run_incremental_statcast
from src.ingestion.daily_runner import run_daily, DailyRunReport
from src.ingestion.prop_line_odds import persist_mlb_batter_hr_odds
from src.ingestion.the_odds_api_odds import persist_mlb_batter_hr_odds_from_the_odds_api
from src.ingestion.scheduler import build_scheduler, start_scheduler
```

## Internal dependencies
- `src.core.db` — engine + session
- `src.core.models` — SQLAlchemy tables
- `src.core.logging_config` — JSON-line logger
- External: `pybaseball`, `requests`, `requests-cache`, `pandas`,
  `apscheduler`, `vcrpy` (tests only)

## Gotchas
- **Parks + teams must be seeded before the backfill** — `games`
  references `parks.park_id` via FK. The backfill CLI does not
  self-seed; Phase 2's `daily_runner` will wrap this prerequisite.
- **`games.home_team_id` / `away_team_id` carry no FK** to `teams` —
  All-Star / exhibition games use IDs 159 / 160 which are not in the
  30-team dimension. See migration `0002_drop_games_team_fks`.
- **pybaseball's `statcast()` has a 30k-row/query cap.** The backfill
  chunks by day (always under the cap) and enables pybaseball's cache.
- **Savant occasionally emits duplicate rows** for reviewed plays.
  `_frame_to_rows` dedups on the composite PK before upsert (last
  write wins, matching the `ON CONFLICT` upsert behavior).
- **Resume is date-based, not row-based.** The loader stores only
  `last_completed_date`; mid-day crashes replay the whole day (safe
  due to idempotent upsert).
- **pybaseball's first `playerid_reverse_lookup` call downloads the
  full Chadwick register** (~3s warmup, ~15MB). Subsequent calls are
  local.
- **MLB StatsAPI publishes `azimuthAngle` (orientation) and `elevation`
  per venue** when hitting `/api/v1/venues?hydrate=location`. This
  contradicts the Phase 1 prompt but was verified on 72 venues. Only
  `roof_type` is not published and thus lives in a local dict.
- **Savant park factors have no CSV endpoint** for handedness splits.
  `park_factors.py` parses HTML and the embedded `var data = [...]`
  literal. The querystring parameter is `batSide` (camelCase);
  `bat_side` is silently ignored. `rolling=1` selects single-season
  data; omitting it yields the 3-year rolling view. See
  `phases/phase2/NOTES.md` for the locked-in parameter contract.
- **Boxscore batting order is empty pre-posting.** Morning `daily_runner`
  runs may yield zero `projected_lineups` rows; the hourly pre-game
  refresh fills them in. Upsert handles both passes via
  `(game_pk, team_id, batting_order)` uniqueness.
- **Daily StatsAPI is also the player-name safety net.** Rookies/recent
  call-ups can appear in lineups before historical Statcast has seeded
  `players`. `persist_daily_schedule` therefore upserts names, handedness,
  and position from the boxscore `players` map and probable-pitcher refs;
  do not remove this as "duplicate" of the Statcast backfill.
- **Weather `fetched_at` advances each run** — the
  `(park_id, forecast_for_utc, fetched_at)` unique key means each
  `persist_weather_for_today` call writes a new row per game (by design:
  preserves forecast-revision history). Downstream features should
  read the latest `fetched_at` per `(park_id, forecast_for_utc)`.
- **"Today" means MLB Eastern date.** `daily_runner` and weather default
  through `src.core.time.current_mlb_date()` to avoid UTC rollovers
  creating a different schedule/weather date near midnight.
- **Retractable parks are queried for weather.** `daily_schedule.roof_status`
  disambiguates at feature-compute time.
- **Park factors refresh is NOT daily.** `daily_runner` only calls
  `refresh_park_factors` when `ParkFactor.updated_at` is older than
  7 days. Savant updates this leaderboard seasonally.
- **`fetch_game_content` lives on StatsAPI v1.1, not v1.** See
  `phases/phase2/NOTES.md` → "StatsAPI client — feed/live is v1.1".
- **Sportsbook odds are persisted snapshots, not live reads from picks.**
  This protects page latency, preserves line movement history, and keeps
  provider outages from breaking already-generated predictions. The
  refresh script uses The Odds API first when `THE_ODDS_API_KEY` is set,
  and falls back to PropLine when the primary provider returns zero rows
  or is unavailable. Both clients retry transient 429/5xx/connect/read
  failures; if the event list is unavailable, ingestion returns a
  failure report with zero rows instead of aborting the daily picks
  refresh.
- **`scripts/refresh-picks.sh` is date-specific end to end.** Schedule,
  weather, proxy lineups, feature building, inference, and odds ingestion
  all receive the same explicit target date. Use that script for live
  slate updates; use `python -m src.features.builder --start ... --end ...`
  only for controlled historical feature backfills.
- **PropLine `batter_home_runs` may include alternate ladders** such as
  `2+ Home Runs`, `3+ Home Runs`, or Over 1.5. Those are different
  bets from the model target (`P(at least one HR)`) and must be filtered
  out before persistence.

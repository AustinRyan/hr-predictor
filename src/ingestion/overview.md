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
```

## Internal dependencies
- `src.core.db` — engine + session
- `src.core.models` — SQLAlchemy tables
- `src.core.logging_config` — JSON-line logger
- External: `pybaseball`, `requests`, `pandas`, `vcrpy` (tests only)

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

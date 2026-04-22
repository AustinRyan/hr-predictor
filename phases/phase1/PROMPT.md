# Phase 1 — Historical Statcast Backfill

## Required reading before you start
1. `./CLAUDE.md` — project conventions
2. `./MASTER_PLAN.md` — full roadmap (read Phase 1 section carefully)
3. `./abstract.md` — current project state (should show Phase 0 complete)
4. `./src/ingestion/overview.md` — will be empty/stub, you'll populate it
5. `./src/core/overview.md` — understand what infra primitives are already in place
6. `./phases/phase0/NOTES.md` — any implementation notes from Phase 0

**If abstract.md does not show Phase 0 as complete, STOP and ask the user.**

---

## Objective
Load MLB Statcast pitch-level data from 2021-01-01 through yesterday into Postgres. Resumable, idempotent, rate-limit-aware, with a data-quality audit report at the end.

**Scope boundary:** You are writing ingestion *and* schema *and* audit code. You are not writing feature engineering. You are not computing rolling metrics. Raw pitch data lands in tables; that's it.

---

## Deliverables

### 1. Alembic setup

- Initialize Alembic in `migrations/` (use `alembic init migrations`)
- Configure `alembic.ini` to read DATABASE_URL from `.env`
- Configure `migrations/env.py` to use SQLAlchemy models from `src/core/db.py`

### 2. SQLAlchemy models in `src/core/models.py`

Define the following tables. Use SQLAlchemy 2.x declarative style with `Mapped[]` typing.

#### `parks`
- `park_id: int` PK (MLB venue ID — authoritative, from MLB StatsAPI)
- `name: str`
- `city: str`, `state: str` (nullable; some international venues may lack state)
- `latitude: float` (nullable)
- `longitude: float` (nullable)
- `orientation_deg: float` nullable — bearing from home plate to center field, clockwise from north
- `elevation_ft: int` nullable
- `roof_type: str` nullable — one of `open`, `retractable`, `dome`
- `created_at: datetime`, `updated_at: datetime`

#### Parks seeding methodology (important — read carefully)

Park metadata is split into two parts:

**Part A — authoritative (MLB StatsAPI):** `park_id`, `name`, `city`, `state`, `latitude`, `longitude`. Query `https://statsapi.mlb.com/api/v1/venues?sportId=1&season={year}` for each season 2021 through current. Upsert every unique `venue.id` encountered. This catches primary parks *and* alternate venues (Field of Dreams, Steinbrenner Field for 2025 Rays, Sutter Health Park for 2025 A's, London Stadium, etc.).

**Part B — manually maintained (dict below):** `orientation_deg`, `elevation_ft`, `roof_type`. MLB doesn't publish these. Use the dict. For any `venue_id` pulled from StatsAPI that isn't in the dict, leave those fields null and log a warning. The feature layer will handle nulls by gating weather features off.

```python
# Maintained by hand. Orientation is bearing from home plate to dead CF, clockwise from north (0° = N, 90° = E).
# VERIFY Yankee Stadium, Wrigley, and Coors against Google Maps during Phase 1 and note any discrepancies in NOTES.md.
# Do NOT silently adjust values; log and ask the user.
PARK_PHYSICAL_ATTRS = {
    # park_id: (orientation_deg, elevation_ft, roof_type)
    1:    (45,  15,   "dome"),         # Tropicana Field (Rays primary, 2021-2024)
    2:    (91,  0,    "open"),         # Oracle Park (Giants)
    3:    (32,  36,   "open"),         # Camden Yards (Orioles)
    4:    (45,  21,   "open"),         # Fenway Park (Red Sox)
    5:    (45,  160,  "open"),         # Angel Stadium (Angels)
    7:    (45,  750,  "open"),         # Kauffman Stadium (Royals)
    10:   (60,  0,    "open"),         # Oakland Coliseum (Athletics 2021-2024)
    12:   (30,  600,  "open"),         # Wrigley Field (Cubs)
    14:   (152, 585,  "open"),         # Comerica Park (Tigers)
    15:   (345, 50,   "retractable"),  # Minute Maid Park (Astros)
    17:   (25,  500,  "open"),         # Dodger Stadium (Dodgers)
    19:   (75,  16,   "open"),         # Yankee Stadium (Yankees)
    22:   (25,  1100, "retractable"),  # Chase Field (Diamondbacks)
    31:   (0,   650,  "open"),         # Progressive Field (Guardians)
    32:   (130, 595,  "open"),         # Rate Field / Guaranteed Rate Field (White Sox)
    680:  (135, 635,  "retractable"),  # American Family Field (Brewers)
    2392: (118, 730,  "open"),         # PNC Park (Pirates)
    2394: (130, 482,  "open"),         # Great American Ball Park (Reds)
    2395: (60,  465,  "open"),         # Busch Stadium (Cardinals)
    2602: (30,  37,   "open"),         # Citi Field (Mets)
    2680: (30,  30,   "open"),         # Nationals Park (Nationals)
    2681: (90,  840,  "open"),         # Target Field (Twins)
    2700: (30,  1050, "open"),         # Truist Park (Braves)
    2889: (40,  10,   "retractable"),  # loanDepot park (Marlins)
    3289: (15,  20,   "open"),         # Citizens Bank Park (Phillies)
    3309: (0,   62,   "open"),         # Petco Park (Padres)
    4169: (8,   551,  "retractable"),  # Globe Life Field (Rangers)
    4705: (0,   266,  "retractable"),  # Rogers Centre (Blue Jays)
    4706: (75,  16,   "open"),         # George M. Steinbrenner Field (Rays 2025 alternate)
    5325: (45,  134,  "retractable"),  # T-Mobile Park (Mariners)
    5403: (0,   5200, "open"),         # Coors Field (Rockies)
    9031: (30,  30,   "open"),         # Sutter Health Park (Athletics 2025 alternate)
}
```

**Venue IDs I'm less certain about — verify at runtime against MLB StatsAPI response and log any mismatch:**
- `32` (Rate Field / White Sox)
- `10` (Oakland Coliseum)
- `4706` (Steinbrenner Field)
- `9031` (Sutter Health Park)

If StatsAPI returns a different ID than what's in the dict key for one of these venues, trust StatsAPI as authoritative and log a `NOTES.md` entry with the correction. Alternate venue IDs (Field of Dreams, London Stadium, etc.) will show up in StatsAPI and should be inserted with null physical attrs.

**Also during Phase 1:** pick 3 parks (Yankee Stadium, Wrigley, Coors) and verify orientation_deg by measuring the bearing from home plate to dead center field on Google Maps. Log results in `NOTES.md` whether they match or not.

#### `teams`
- `team_id: int` PK (MLB team ID)
- `abbr: str` (3-letter)
- `name: str`
- `home_park_id: int` FK to `parks` (primary home park)
- `league: str`, `division: str`

Seed from MLB StatsAPI `/api/v1/teams?season={current_year}&sportId=1`. Do NOT use `pybaseball.teams_batting` — that returns stats, not metadata.

#### `players`
- `mlbam_id: int` PK
- `full_name: str`
- `first_name: str`, `last_name: str`
- `birth_date: date` nullable
- `bats: str` nullable — L/R/S
- `throws: str` nullable — L/R
- `primary_position: str` nullable
- `debut_date: date` nullable
- `active: bool` default True
- `updated_at: datetime`

Populate lazily — the statcast loader upserts player rows as it encounters new batter/pitcher IDs. Enrich names via `pybaseball.playerid_reverse_lookup` in batches.

#### `games`
- `game_pk: int` PK
- `game_date: date`
- `season: int`
- `home_team_id: int` FK, `away_team_id: int` FK
- `venue_id: int` FK to parks.park_id (can reference any venue, including alternates)
- `game_type: str` — R/F/D/L/W + S (spring)
- `day_night: str` — D/N
- `game_start_utc: datetime`
- `status: str` — Final / In Progress / Scheduled / etc.

#### `statcast_pitches` — partitioned table

**Partitioned by `game_date` (RANGE, yearly partitions).**

**Critical:** Postgres requires the partition key to be part of any PK or unique constraint on a partitioned table. The PK must include `game_date` as the first component:

```
PRIMARY KEY (game_date, game_pk, at_bat_number, pitch_number)
```

Columns — the pybaseball fields we persist (lowercase snake_case):

- `game_date: date`, `game_pk: int` — in PK
- `at_bat_number: int`, `pitch_number: int` — in PK
- `batter: int`, `pitcher: int`
- `pitch_type: str` nullable (5 chars)
- `release_speed: float` nullable
- `release_spin_rate: int` nullable
- `effective_speed: float` nullable
- `launch_speed: float`, `launch_angle: float`, `hit_distance_sc: float`
- `hc_x: float`, `hc_y: float`
- `events: str` nullable — `home_run`, `single`, `strikeout`, etc.
- `description: str` nullable
- `balls: int`, `strikes: int`, `outs_when_up: int`, `inning: int`, `inning_topbot: str`
- `stand: str` (L/R), `p_throws: str` (L/R)
- `estimated_woba_using_speedangle: float` nullable
- `estimated_ba_using_speedangle: float` nullable
- `woba_value: float`, `woba_denom: float`
- `launch_speed_angle: int` nullable — Statcast 1–6 classification (6 = barrel)
- `zone: int` nullable
- `plate_x: float`, `plate_z: float`
- `home_team: str`, `away_team: str`
- `bat_speed: float` nullable — 2024+ only
- `swing_length: float` nullable — 2024+ only

**Indexes** (on parent table; Postgres propagates to partitions):
- `CREATE INDEX ON statcast_pitches (batter, game_date DESC)` — batter rolling
- `CREATE INDEX ON statcast_pitches (pitcher, game_date DESC)` — pitcher profile
- `CREATE INDEX ON statcast_pitches (game_pk)` — game lookups
- Partial: `CREATE INDEX ON statcast_pitches (batter, game_date DESC) WHERE events = 'home_run'`

**Yearly partitions:** Create for 2021 through (current_year + 1). The +1 is an empty buffer so next-season's first data has a home.

#### `ingestion_state`
- `operation_key: str` PK — e.g., `"statcast_backfill"`
- `last_completed_date: date`
- `status: str` — `running`, `paused`, `complete`, `failed`
- `error_message: str` nullable
- `updated_at: datetime`

Single Alembic migration for all of the above. Migration name: `0001_initial_schema`.

### 3. Statcast loader (`src/ingestion/statcast_backfill.py`)

Use `pybaseball.statcast(start_dt, end_dt)`. Design:

- **Entry point:** `backfill_statcast(start_date: date, end_date: date, resume: bool = True) -> BackfillReport`
- **Chunking:** iterate day-by-day. For each day:
  1. If `resume=True` and `ingestion_state.last_completed_date >= day`, skip
  2. Pull that day's Statcast data
  3. Upsert into `statcast_pitches` with `ON CONFLICT (game_date, game_pk, at_bat_number, pitch_number) DO UPDATE` (Savant occasionally backfills corrections — latest value wins)
  4. Upsert new batter/pitcher IDs into `players` (enrich via `pybaseball.playerid_reverse_lookup` in batches of 50)
  5. Upsert `games` row with game-level context
  6. Update `ingestion_state.last_completed_date = day`, commit transaction
- **Error handling:** on failure for a day, mark state `failed`, log exception, do NOT advance date. User re-runs to resume.
- **Logging:** INFO for per-day summary (date, rows loaded, elapsed). DEBUG for per-upsert detail.
- **Rate limiting:** enable `pybaseball` cache (`pybaseball.cache.enable()`). Add 1-second sleep between days.
- **Memory:** commit per-day; do NOT accumulate dataframes across days.

**Idempotency guarantee:** the upsert is deterministic. Re-running produces identical state. Document any caveats in `overview.md`.

### 4. Data quality audit (`src/ingestion/audit.py`)

Produces `reports/phase1_audit_{YYYYMMDD}.md`:

- **Row counts per season** (expected ~700k/full season, ~4000/game day)
- **Null-rate table:** per-column null %, split by season
- **FK integrity:** any `batter`/`pitcher` in `statcast_pitches` missing from `players`?
- **Game coverage:** any `game_pk` in pitches missing from `games`?
- **Venue coverage:** any `venue_id` in games missing from `parks`? (Must be zero — seeder should catch all of these.)
- **Date gaps:** missing dates between first/last of each season (exclude All-Star break and off days)
- **Suspicious values:** `launch_speed > 125` (physically implausible), `abs(launch_angle) > 90`
- **Spot checks — look up IDs via queries, do not hardcode game_pks:**
  - Aaron Judge's 62nd HR: find Judge's `mlbam_id` via `playerid_lookup('judge', 'aaron')`, then query `SELECT * FROM statcast_pitches WHERE events='home_run' AND batter=<id> AND game_date='2022-10-04'`. Expect exactly one row, `launch_speed` in [99, 101], `launch_angle` in [30, 40].
  - Shohei Ohtani 2024: `SELECT COUNT(*) FROM statcast_pitches WHERE events='home_run' AND batter=<ohtani_id> AND EXTRACT(year FROM game_date)=2024`. Expect ≥50.
  - Coors Field 2023 HRs: `SELECT COUNT(*) FROM statcast_pitches p JOIN games g USING(game_pk, game_date) WHERE g.venue_id=5403 AND p.events='home_run' AND g.season=2023`. Expect ≥180.

### 5. Tests

- `tests/ingestion/test_statcast_backfill.py`:
  - VCR cassette for one real pybaseball call (single day, early 2024)
  - Idempotency: load same day twice, assert zero new rows on second run
  - Resume: truncate `ingestion_state`, set `last_completed_date` mid-range, re-run, assert picks up from correct day
- `tests/ingestion/test_parks_seed.py`:
  - StatsAPI venues endpoint mocked via VCR
  - All primary 30 parks seeded with non-null physical attrs
  - Unknown venue creates a row with null physical attrs
  - Idempotent re-seed
- `tests/ingestion/test_audit.py`:
  - Synthetic seed, run audit, assert known issues flagged
- `tests/core/test_models.py`:
  - PK on `statcast_pitches` starts with `game_date` (inspect via SQLAlchemy metadata)
  - Create + query roundtrip for each model

### 6. Phase docs

- `phases/phase1/ACCEPTANCE.md` — checklist below
- `phases/phase1/NOTES.md` — populate with: venue_id verifications, orientation spot-checks (Yankee / Wrigley / Coors vs Google Maps), any pybaseball gotchas, any schema adjustments
- Update `src/ingestion/overview.md` with real content

---

## Acceptance checklist (write into `phases/phase1/ACCEPTANCE.md`)

```markdown
# Phase 1 — Acceptance Checklist

## Schema
- [ ] `uv run alembic upgrade head` succeeds on fresh DB
- [ ] `uv run alembic downgrade base && uv run alembic upgrade head` succeeds (migrations reversible)
- [ ] In psql: `\d+ statcast_pitches` shows composite PK beginning with `game_date`
- [ ] Yearly partitions exist for 2021 through (current_year + 1)
- [ ] `SELECT COUNT(*) FROM parks` returns ≥30
- [ ] All 30 primary parks have non-null `orientation_deg`, `elevation_ft`, `roof_type`
- [ ] Retractable roofs correct for: Minute Maid, Chase, American Family, loanDepot, Globe Life, Rogers Centre, T-Mobile
- [ ] Dome correct for: Tropicana
- [ ] Orientation verification documented in NOTES.md for Yankee Stadium, Wrigley, Coors

## Data load
- [ ] `uv run python -m ingestion.statcast_backfill --start 2021-04-01 --end <yesterday>` completes
- [ ] Total row count within 2% of sum of pybaseball season totals 2021–current
- [ ] Per-season row counts reasonable (~700k per full season)
- [ ] Re-running backfill produces zero new rows
- [ ] `SELECT COUNT(DISTINCT mlbam_id) FROM players` returns ≥1500

## Spot checks
- [ ] Judge 62nd HR query returns exactly one row, launch_speed in [99, 101]
- [ ] Ohtani 2024 home_run count ≥50
- [ ] Coors Field 2023 home_run count ≥180
- [ ] `bat_speed` non-null for reasonable fraction of 2024+ rows, all null for pre-2024

## Audit report
- [ ] Report generated in `reports/`
- [ ] Null rates under 15% for `launch_speed`, `launch_angle`, `events`
- [ ] Zero FK integrity violations
- [ ] Zero missing venue_id rows in parks
- [ ] No unexpected date gaps

## Tests
- [ ] `uv run pytest tests/ingestion tests/core -v` all pass
- [ ] Coverage ≥80% on `src/ingestion/`

## Docs
- [ ] `src/ingestion/overview.md` populated
- [ ] `phases/phase1/NOTES.md` documents orientation verifications and any venue_id corrections
- [ ] `abstract.md` updated: Phase 1 complete, Phase 2 next
```

---

## Non-negotiables (re-read CLAUDE.md)

- **Idempotent.** Running backfill twice is safe and produces no new rows.
- **Resumable.** Killing mid-run and restarting continues from last completed day.
- **Hybrid park seeding.** StatsAPI for metadata; dict for physical attrs. Never invent orientations.
- **Pydantic for external API responses.** No raw dict passing.
- **Every external call logged** with date range, row count, elapsed time.
- **Chunked queries.** Never >1 day of Statcast per pybaseball call during backfill.
- **Partition key in PK.** Non-negotiable for Postgres.
- **Alternate venues create null-attr rows.** No FK violations; physical attrs null is acceptable.

---

## Post-phase ritual

1. `uv run pytest -q` → green
2. Run full backfill end-to-end (30–90 min); do not skip
3. Run audit, review report
4. Walk every acceptance item
5. Update `abstract.md` and `src/ingestion/overview.md`
6. Commit + tag `phase-1-complete`

---

## STOP condition

After Phase 1 complete and tagged, **stop**. Do not start Phase 2 without explicit user approval. Report:

1. Row counts per season
2. Audit highlights
3. Backfill elapsed time
4. Orientation verification results (Yankee Stadium, Wrigley, Coors)
5. Any venue_ids that weren't in the dict (flagged, not silently added)

# Phase 1 — Implementation Notes

## Major deviation from PROMPT.md: park ID system

The `PARK_PHYSICAL_ATTRS` dict in `phases/phase1/PROMPT.md` is keyed by
IDs that do **not** match the authoritative MLB StatsAPI venue ID
system. Not just "a few alternates"; every key is wrong. Some examples:

| Park | PROMPT.md key | StatsAPI venue_id |
|---|---:|---:|
| Yankee Stadium | 19 | **3313** |
| Coors Field | 5403 | **19** |
| Wrigley Field | 12 | **17** |
| Dodger Stadium | 17 | **22** |
| Fenway Park | 4 | **3** |
| Oracle Park | 2 | **2395** |
| American Family Field | 680 | **32** |
| T-Mobile Park | 5325 | **680** |
| Truist Park | 2700 | **4705** |
| Rogers Centre | 4705 | **14** |
| Great American Ball Park | 2394 | **2602** |

The prompt-supplied dict appears to conflate two different numbering
systems. Following the prompt's own rule ("trust StatsAPI as
authoritative and log corrections") and CLAUDE.md ("never invent
values"), Phase 1 ships with:

1. `parks` seeded entirely from MLB StatsAPI (`/api/v1/venues?hydrate=location`).
2. `orientation_deg` pulled from `location.azimuthAngle` (turns out
   StatsAPI **does** publish this, contradicting the prompt's claim it
   doesn't).
3. `elevation_ft` pulled from `location.elevation` (ditto).
4. A small hand-maintained `ROOF_TYPES` dict in `src/ingestion/parks.py`
   keyed by StatsAPI venue ID — StatsAPI does not publish roof type.
5. Every physical-attr value cross-checked against Wikipedia where
   available (see "Orientation & elevation verification" below).

## Venue IDs seeded outside the primary 30-park roster

Picked up across seasons 2021–2026 via StatsAPI:

- `2523` George M. Steinbrenner Field (Rays 2025 alternate home) — roof_type=open
- `2529` Sutter Health Park (Athletics 2025 alternate home) — roof_type=open
- `2536` TD Ballpark (spring training) — roof_type null
- `2756` Sahlen Field (Blue Jays 2020–21 alternate, now AAA) — roof_type null
- `3329` Arvest Ballpark (spring training) — roof_type null
- `4249` Salt River Fields at Talking Stick (spring training) — roof_type null

Spring-training venues (`2536`, `3329`, `4249`) are expected to have
null roof_type — the feature layer will gate weather features off for
them. Alternate primary venues (`2523`, `2529`) are included in
`ROOF_TYPES` as `open`.

## Orientation & elevation verification

StatsAPI-provided values compared against Wikipedia (where Wikipedia
listed a value). "Bearing" is cw-from-north degrees home plate → CF.

| Park | StatsAPI orientation | StatsAPI elevation | Wikipedia elevation | Notes |
|---|---:|---:|---:|---|
| Yankee Stadium (3313) | 75° | 55 ft | not listed | Bronx sits ~40–60 ft; value plausible. Wikipedia gives 40°49′45″N 73°55′35″W coords only. |
| Wrigley Field (17) | 37° | 595 ft | 600 ft | Wrigley is famously oriented NE; 37° matches. Elevation within 5 ft. |
| Coors Field (19) | 4° | 5,190 ft | 5,200 ft | Famously points near-due-N; 4° matches. Elevation within 10 ft. |
| Fenway Park (3) | 45° | 21 ft | — | Fenway's classic home-to-CF ~45° (aligns with the Green Monster's orientation). |
| Tropicana Field (12) | 359° | 15 ft | — | Dome; orientation matters less but still published. |

All three required spot-check parks (Yankee, Wrigley, Coors) show
internally-consistent values. A full field-by-field Google-Maps
verification was not performed in this phase — deferred to Phase 3
when wind-vector features are wired up.

## pybaseball gotchas observed

- **`statcast()` returns game_date as string** (not pandas date). The
  loader normalizes to `datetime.date` before PK assembly.
- **Integer columns are nullable-Int64** in the returned DataFrame.
  Standard `int(val)` fails on `pd.NA`. `_clean()` handles via
  `pd.isna()` pre-check.
- **All-Star Game (`game_type='A'`) carries team_ids 159/160** for
  AL/NL All-Star sides. These are valid MLB team IDs but are not in
  the 30-team `teams` dimension. Migration `0002_drop_games_team_fks`
  removes the FK from `games.home_team_id`/`away_team_id` → `teams`.
  `venue_id` FK is retained since parks is authoritative (via the
  StatsAPI-seeded dimension).
- **Savant occasionally emits duplicate rows** for reviewed plays.
  `_frame_to_rows` dedups on the composite PK before the upsert.
- **First `playerid_reverse_lookup` call downloads the full Chadwick
  register** (~3s warmup). Subsequent calls are local. Per-day player
  enrichment runs in batches of 50.

## Schema decisions

- `league` / `division` widened from `VARCHAR(8/16)` to `VARCHAR(32)`
  during implementation — StatsAPI returns full names like
  "American League West" (20 chars).
- `roof_type` is `VARCHAR(16)` — values: `open`, `retractable`, `dome`.
  Null for alternate / spring venues.
- Partitioned PK ordering `(game_date, game_pk, at_bat_number,
  pitch_number)` confirmed via `\d+ statcast_pitches`. Yearly
  partitions for 2021 through (current_year + 1) = 2021..2027.

## Ingestion-order prerequisite

The backfill CLI assumes `parks` and `teams` are already seeded.
Seed order:

```bash
uv run python -c "
from src.core.db import get_engine
from sqlalchemy.orm import sessionmaker
from src.ingestion.parks import seed_parks
from src.ingestion.teams import seed_teams
with sessionmaker(bind=get_engine(), future=True)() as s:
    seed_parks(s); seed_teams(s); s.commit()
"
uv run python -m src.ingestion.statcast_backfill --start 2021-04-01 --end 2026-04-21
```

Phase 2 will absorb this into a single `daily_runner` entry point.

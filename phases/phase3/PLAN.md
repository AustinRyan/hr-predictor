# Phase 3 — Feature Engineering — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`. Unlike Phase 2's plan, this one is **lean by design** — `phases/phase3/PROMPT.md` already specifies the schema, physics formulas, and acceptance bars exhaustively. Tasks reference PROMPT sections rather than duplicating them.

**Goal:** Materialize a wide `matchup_features` table keyed by `(game_pk, batter_id, pitcher_id)` with every feature in MASTER_PLAN.md's Phase 3 table populated. No modeling, no predictions — feature computation only.

**Architecture:** One Alembic migration (`0004_feature_store`) + SQLAlchemy model for `matchup_features`. Ten focused feature modules under `src/features/` (one per feature category). One `builder.py` orchestrator that assembles rows per game. Historical backfill via day-at-a-time iteration. All computation SQL-first where possible (rolling windows, pitcher aggregates) with Python orchestration on top. No external API hits — Phase 3 reads only from Postgres tables populated in Phases 1–2.

**Tech Stack:** SQLAlchemy 2.x + Alembic, Postgres window functions, NumPy (physics), pytest. No new deps.

---

## Locked design decisions (controller-approved 2026-04-22)

1. **Migration filename:** `0004_feature_store` (PROMPT.md says `0003`; Phase 2 used `0003_operational_tables`).
2. **`matchup_features` is a TABLE, not a materialized view.** Rationale: streaming-friendly upserts for operational daily adds, PK-indexed lookups are fast, simpler lifecycle. MV is a Phase 4 perf refinement option if builds exceed the 30-min acceptance bar.
3. **Rolling windows computed ON-THE-FLY in `builder.py` via SQL CTEs**, not pre-materialized. Same reasoning — simplicity over premature perf tuning.
4. **Historical backfill spans 2021 → current date** (not just 2021–2024). Covers train/val/test AND gives operational the latest state.
5. **Reuse Phase 2 conventions** — `session_factory` local name, `pg_insert(...).on_conflict_do_update(...)` upsert pattern, Pydantic for any non-pg-native data (none expected in Phase 3). No new patterns.
6. **Table partitioning** — partition `matchup_features` by `game_date` RANGE yearly, same as `statcast_pitches`. Covers 2021..current_year+1. Composite PK `(game_date, game_pk, batter_id, pitcher_id)` since Postgres requires the partition key in the PK.
7. **Leakage test is explicit** — one test seeds a synthetic "clobber on date D" and asserts rolling features for a PA on date D do NOT include that row.

---

## File structure

**Create:**
- `migrations/versions/0004_feature_store.py`
- `src/core/models.py` → append `MatchupFeature` ORM class (model mirrors the table; append `BigInteger` already imported)
- `src/features/weather_physics.py` — pure-Python: `air_density_relative()`, `wind_carry_components()`, `apply_roof_gating()`
- `src/features/park_factors_features.py` — joins `park_factors` + `parks` for env columns
- `src/features/context.py` — PA projection map, day/night, home/away, days-rest, same-hand
- `src/features/batter_rolling.py` — 7d/14d/30d/season window SQL for batter metrics
- `src/features/batter_splits.py` — platoon + pitch-type matrices + regression helper
- `src/features/batter_tracking.py` — 2024+ bat-tracking (avg bat speed, squared-up, blast)
- `src/features/pitcher_profile.py` — rolling + handedness splits + hr/9 + ball-in-play rates
- `src/features/pitcher_pitch_mix.py` — pitch usage% + velocity
- `src/features/bullpen.py` — team-level opposing bullpen aggregates
- `src/features/builder.py` — orchestrator: `build_features_for_game`, `build_features_for_historical`, `build_features_for_today`
- `tests/features/__init__.py`
- `tests/features/test_weather_physics.py`
- `tests/features/test_leakage.py`
- `tests/features/test_rolling.py`
- `tests/features/test_platoon_regression.py`
- `tests/features/test_context.py`
- `tests/features/test_builder_smoke.py`
- `phases/phase3/ACCEPTANCE.md`
- `phases/phase3/NOTES.md`

**Modify:**
- `src/core/models.py` — add `MatchupFeature`
- `src/features/overview.md` — replace stub with full module docs
- `abstract.md` — at phase-end

**No modification:** any Phase 1 or Phase 2 code. Phase 3 reads existing tables, writes new ones.

---

## Task order + dispatch strategy

Tasks are ordered to allow **parallel subagent dispatch within each group**; groups run sequentially because later groups depend on earlier ones. Controller waits for all tasks in a group before starting the next.

**Group A (sequential — schema foundation)**
- Task 1: Migration `0004_feature_store` + `MatchupFeature` ORM + partition setup

**Group B (parallel — self-contained modules)**
- Task 2: `weather_physics.py` (pure Python, no DB)
- Task 3: `context.py` (PA map, day/night, rest)

**Group C (sequential — data-dependent)**
- Task 4: `park_factors_features.py` (joins `park_factors` + `parks`)
- Task 5: `batter_rolling.py` (SQL-heavy; core of the phase)
- Task 6: `batter_splits.py` (platoon regression, pitch-type matrix)
- Task 7: `batter_tracking.py` (2024+ only)
- Task 8: `pitcher_profile.py`
- Task 9: `pitcher_pitch_mix.py`
- Task 10: `bullpen.py`

**Group D (sequential — integration)**
- Task 11: `builder.py` + leakage test + builder smoke test
- Task 12: Historical backfill + acceptance walk-through + phase docs + tag

**Controller note:** Groups B and C aren't hard-parallel-safe because they all write the same `matchup_features` columns eventually — but each subagent only writes its OWN module + its OWN tests, so no file collisions. Dispatch them serially for simplicity; parallelize only if the schedule demands it.

---

# Task 1 — Migration 0004_feature_store + ORM

**Files:**
- Create: `migrations/versions/0004_feature_store.py`
- Modify: `src/core/models.py` (append `MatchupFeature`)
- Create: `tests/features/__init__.py` (empty)
- Create: `tests/features/test_migration.py`

**Spec source:** `phases/phase3/PROMPT.md` § "Schema additions" — enumerate every column listed there. All numeric columns `Float` unless explicitly `int`/`bool`/`str`. Nullable unless called out as a key.

**Partitioning:** yearly RANGE on `game_date`, 2021..current_year+1, using the exact pattern from `migrations/versions/0001_initial_schema.py` (see `_create_statcast_partitioned_table` / `_create_yearly_partitions`).

**PK:** composite `(game_date, game_pk, batter_id, pitcher_id)` — game_date must appear in PK since Postgres partition-key rule.

**Indexes:**
- `CREATE INDEX idx_matchup_features_batter_date ON matchup_features (batter_id, game_date DESC)`
- `CREATE INDEX idx_matchup_features_pitcher_date ON matchup_features (pitcher_id, game_date DESC)`
- `CREATE INDEX idx_matchup_features_game_pk ON matchup_features (game_pk)`
- `CREATE INDEX idx_matchup_features_historical ON matchup_features (game_date) WHERE is_historical = true` (for training-set queries)

**Steps:**

1. Write `tests/features/test_migration.py`:
   - `test_matchup_features_table_exists`
   - `test_matchup_features_pk_includes_game_date`
   - `test_matchup_features_yearly_partitions_exist` (check for `matchup_features_2021` through `matchup_features_{current_year+1}`)
   - `test_matchup_features_indexes_present`
2. Run → TDD red (table doesn't exist).
3. Write the migration following `0001_initial_schema.py`'s partition pattern (hand-rolled DDL via `op.execute` since Alembic's `create_table` can't emit `PARTITION BY RANGE`).
4. Write the `MatchupFeature` ORM class in `src/core/models.py`. Use SQLAlchemy 2.x `Mapped[T]` annotations. Include `__table_args__ = {"postgresql_partition_by": "RANGE (game_date)"}`. The ORM is descriptive-only; the migration owns actual DDL.
5. Update `tests/ingestion/conftest.py` `clean_tables` fixture to include `matchup_features` in the TRUNCATE.
6. Run `uv run alembic upgrade head` against `hrp` and confirm `0004_feature_store` is head.
7. Full regression test suite green.
8. Commit: `feat(features): add matchup_features partitioned table (0004)`.

**Not in this task:** any feature computation. Only the empty container.

---

# Task 2 — `src/features/weather_physics.py`

Pure Python, no DB. Standalone unit tests.

**Spec source:** `phases/phase3/PROMPT.md` § 3 "The physics" — air density formula + wind carry component function verbatim.

**API (public):**
```python
def air_density_relative(temperature_f: float, humidity_pct: float, pressure_hpa: float) -> float: ...

def wind_carry_components(
    wind_direction_deg: float,  # meteorological: direction FROM
    wind_speed_mph: float,
    park_orientation_deg: float,  # bearing from home plate to CF
) -> tuple[float, float, float]:
    """Returns (lf, cf, rf) signed mph — positive aids carry, negative suppresses."""
    ...

def apply_roof_gating(raw_features: dict, is_roof_closed: bool) -> dict:
    """If roof closed, overwrite wx_* with climate-controlled baselines per PROMPT § 3."""
    ...
```

**Test expectations (from PROMPT § "Acceptance checklist — Physics sanity checks"):**
- Wind 270° (west) at 15 mph, park 0°: `lf ≈ -10.6`, `cf ≈ 0`, `rf ≈ +10.6` (±0.5)
- Wind direction 180° (from south, blowing north) at 10 mph, park 0°: `cf ≈ +10`, `lf ≈ +7.07`, `rf ≈ +7.07` (both cos 45° components)
- Wind speed 0 → all three are exactly 0.0
- `air_density_relative(95, 60, 1013)` ≈ 0.96 (±0.01)
- `air_density_relative(40, 40, 1013)` ≈ 1.07 (±0.01)
- `apply_roof_gating({...real values...}, True)` returns the baseline dict from PROMPT § 3 (temp=72, hum=50, press=1013.25, density=1.0, wind=0, carries=0, is_roof_closed=True)
- `apply_roof_gating({...}, False)` returns input unchanged except `wx_is_roof_closed=False`

**Steps:** standard TDD — test first, implement, verify. Single file, single commit: `feat(features): add weather physics (air density, wind carry, roof gating)`.

---

# Task 3 — `src/features/context.py`

Pure Python. No DB.

**Spec source:** PROMPT § 6 "Projected PA by batting order" + the "Context" column group.

**Module contents:**

```python
PA_BY_BATTING_ORDER: dict[int, float] = {
    1: 4.60, 2: 4.50, 3: 4.40, 4: 4.29, 5: 4.19,
    6: 4.08, 7: 3.97, 8: 3.86, 9: 3.75,
}
# TODO(phase4+): recompute annually from statcast_pitches.

def projected_pa_for_slot(slot: int) -> float: ...
def same_hand(batter_stand: str, pitcher_throws: str) -> bool: ...
def day_night_letter(dt: datetime) -> str: ...  # UTC → D/N based on local hour in park tz; default to scheduled-start hour heuristic
def days_since_last_game(player_id: int, game_date: date, session) -> int: ...
```

`day_night_letter` — simplest reliable approach: the `games.day_night` column (Phase 1) already has D/N populated for historical games. For future games, read from `daily_schedule` if extended; otherwise derive from `game_start_utc` hour (< 21 UTC → D, else N, as a coarse fallback). Just re-emit the `games.day_night` value; no derivation logic.

`days_since_last_game(player_id, game_date, session)` queries `statcast_pitches` for the max `game_date` where that player (batter or pitcher) appeared strictly before `game_date`, returns the delta in days. None if no prior game.

**Tests:**
- `test_pa_map_covers_slots_1_to_9`
- `test_projected_pa_for_slot_9_is_3_75`
- `test_projected_pa_for_slot_out_of_range_raises`
- `test_same_hand_pairs` — (L,L)→True, (L,R)→False, (R,L)→False, (R,R)→True, (S,*)→False (switch-hitter treated as never same-handed; document)
- `test_day_night_letter_from_game_start_utc` — 19:00 UTC (= 3pm ET) → D; 01:00 UTC (= 9pm ET) → N
- `test_days_since_last_game_returns_delta` — integration test with seeded pitches

Commit: `feat(features): add context features (PA slot, day/night, rest, same-hand)`.

---

# Task 4 — `src/features/park_factors_features.py`

Reads Phase 2's `park_factors` + `parks` tables; emits env columns.

**API:**

```python
def park_hr_factor_for(batter_hand: str, park_id: int, season: int, session) -> float | None:
    """park_factors.value where metric='hr', batter_handedness matches."""
    ...

def park_hr_factor_3yr_weighted(batter_hand: str, park_id: int, ref_season: int, session) -> float | None:
    """3-season weighted: season, season-1, season-2 with weights 3/2/1 (or equal — document choice).
    Falls back to single-season when older data missing."""
    ...

def park_elevation_ft(park_id: int, session) -> int | None:
    """Read from parks.elevation_ft."""
    ...
```

**Weighting choice:** use weights `[0.5, 0.3, 0.2]` for seasons `[ref, ref-1, ref-2]`. Document in code + NOTES.md.

Tests: `test_park_hr_factor_for_known_park` (Coors L vs R differ), `test_3yr_weighted_falls_back` (if only 2 seasons, weights [0.625, 0.375] normalized from [0.5, 0.3]).

Commit: `feat(features): add park-factor env joiners`.

---

# Task 5 — `src/features/batter_rolling.py`

**This is the core SQL task.** Computes rolling-window metrics with strict leakage prevention.

**API:**

```python
def rolling_features_sql(reference_date: str = "game_date") -> str:
    """Return a SQL string (SELECT ... as CTE) that, for each row of an input
    (batter_id, game_date) tuple, emits all b_*_{7d,14d,30d,season} columns.
    Uses `statcast_pitches` and computes strictly prior to the input game_date."""
    ...
```

The function returns a parameterized SQL CTE that the `builder.py` orchestrator composes into the final `INSERT INTO matchup_features SELECT ...` pipeline.

**Metric definitions** (all computed over prior PAs):
- `barrel_pct`: `COUNT(*) FILTER (WHERE launch_speed_angle = 6) / COUNT(*) FILTER (WHERE launch_speed IS NOT NULL)` — barrels / ball-in-play events
- `hardhit_pct`: `COUNT(*) FILTER (WHERE launch_speed >= 95) / COUNT(*) FILTER (WHERE launch_speed IS NOT NULL)`
- `avg_ev`: `AVG(launch_speed)` ball-in-play only
- `p90_ev`: `percentile_cont(0.9) WITHIN GROUP (ORDER BY launch_speed)` ball-in-play only
- `avg_la`: `AVG(launch_angle)` ball-in-play only
- `sweet_spot_pct`: `AVG(CASE WHEN launch_angle BETWEEN 8 AND 32 THEN 1.0 ELSE 0 END)` ball-in-play only
- `pulled_fb_pct`: pulled fly ball — need hit direction + launch angle >25. Use `hc_x, hc_y` with batter-handedness-aware pull zone: for RHB, pulled = hit_x < 125.42 (Statcast center); for LHB, hit_x > 125.42. Document simplified approach in NOTES.md.
- `xwobacon`: `AVG(estimated_woba_using_speedangle)` ball-in-play only
- `xiso`: proxy via xwobacon scaled — actually Statcast publishes `estimated_ba_using_speedangle`; xISO = `xwobacon - estimated_ba_using_speedangle` when both exist. Or: define as `AVG(launch_speed >= 95 AND launch_angle BETWEEN 20 AND 35) * (avg_ev/100)` — scrap this; just use the xwobacon-xba delta.
- `hr_per_pa`: `COUNT(*) FILTER (WHERE events = 'home_run') / COUNT(DISTINCT (game_pk, at_bat_number))`
- `pa_count`: `COUNT(DISTINCT (game_pk, at_bat_number))`

**Windows:** 7 / 14 / 30 / season (current + prior completed seasons through reference_date).

**Leakage contract:** all COUNT/AVG/PERCENTILE are over pitches where `game_date < <reference_date>`. Strict inequality. The test (Task 11) will assert this.

**Implementation approach:** PL/pgSQL is overkill; use a single CTE with `LATERAL` joins or window functions. Ideal structure:

```sql
WITH prior_stats AS (
    SELECT
        input.batter_id,
        input.reference_date,
        -- 7d window
        AVG(sp.launch_speed) FILTER (
            WHERE sp.game_date >= input.reference_date - INTERVAL '7 days'
              AND sp.game_date < input.reference_date
              AND sp.launch_speed IS NOT NULL
        ) AS b_avg_ev_7d,
        -- (repeat for 14d, 30d, season)
        ...
    FROM input
    LEFT JOIN statcast_pitches sp ON sp.batter = input.batter_id
    GROUP BY input.batter_id, input.reference_date
)
SELECT * FROM prior_stats;
```

**Tests (in `tests/features/test_rolling.py`):**
- `test_rolling_avg_ev_from_synthetic_batter` — seed 3 pitches with known launch_speeds across 3 days, call rolling on day 4, verify avg is mean of all 3; on day 3, verify avg is mean of first 2 (leakage guard).
- `test_rolling_zero_pa_returns_null` — batter with no prior PAs → all windows NULL (not 0).
- `test_barrel_pct_uses_launch_speed_angle_6` — seed a barrel + non-barrel ball, verify 50%.

Commit: `feat(features): add batter rolling-window SQL builder`.

---

# Task 6 — `src/features/batter_splits.py`

**API:**

```python
def regress_rate(observed_rate: float, pa_count: int, league_avg: float, regression_weight: int = 100) -> float:
    """Regression toward league average. PROMPT § 5 formula."""
    return (observed_rate * pa_count + league_avg * regression_weight) / (pa_count + regression_weight)


def platoon_features_sql(...) -> str:
    """CTE emitting b_vs_lhp_* and b_vs_rhp_* columns.
    Raw rate + regressed rate for each handedness."""
    ...


def pitch_type_matrix_sql(...) -> str:
    """CTE emitting b_xwoba_vs_{ff,si,fc,sl,cu,ch,fs} and b_hr_rate_vs_*
    over the 2-season window ending at reference_date."""
    ...
```

**League averages** — compute once per season from `statcast_pitches` and hardcode in the module as a dict (ok because features are recomputed on backfill). Document in NOTES.md that the 2024 league-avg HR/PA is ~0.028 and sanity-bound between 0.020 and 0.035.

Tests:
- `test_regress_rate_small_sample_moves_to_mean` — 20 PAs with 30% HR rate and league_avg 3% regresses toward ~7-8% (heavily regressed because PA << weight).
- `test_regress_rate_large_sample_stays_close` — 500 PAs with 10% rate regresses only slightly toward 3% (to ~8.8%).
- `test_pitch_type_matrix_covers_all_7_types` — seed 1 PA per type, assert columns populated.

Commit: `feat(features): add batter platoon splits + pitch-type matrix`.

---

# Task 7 — `src/features/batter_tracking.py`

2024+ bat-tracking metrics. Null for earlier seasons.

**API:**
```python
def bat_tracking_sql(...) -> str:
    """CTE emitting b_avg_bat_speed, b_squared_up_pct, b_blast_rate.
    Returns NULL for all three when bat_speed data not yet available (pre-2024)."""
    ...
```

Definitions:
- `b_avg_bat_speed`: `AVG(bat_speed)` where `bat_speed IS NOT NULL`
- `b_squared_up_pct`: `AVG(CASE WHEN launch_speed / NULLIF(bat_speed, 0) > 0.92 THEN 1.0 ELSE 0 END) WHERE bat_speed IS NOT NULL` (squared-up is Statcast's term for solid contact; their threshold is EV/bat_speed ratio ≥ ~0.92).
- `b_blast_rate`: `AVG(CASE WHEN bat_speed >= 75 AND squared_up THEN 1.0 ELSE 0 END)` — blasts require both high bat speed AND squared-up. Use the same EV/bat_speed ratio for squared-up.

Window: 30d rolling.

Tests:
- `test_bat_tracking_null_for_pre_2024_batter` — synthetic batter with only 2023 data → all three NULL.
- `test_bat_tracking_computed_for_2024_batter` — seed 3 swings in 2024 with known bat_speeds, verify averages.

Commit: `feat(features): add batter bat-tracking features`.

---

# Task 8 — `src/features/pitcher_profile.py`

**API:**
```python
def pitcher_profile_sql(...) -> str:
    """CTE emitting p_hr_per_9_{season,career}, p_barrel_pct_allowed_season,
    p_hardhit_pct_allowed_season, p_fb_pct, p_gb_pct, p_k_pct, p_bb_pct,
    p_vs_lhb_{xwoba,hr_rate}_allowed, p_vs_rhb_{xwoba,hr_rate}_allowed."""
    ...


def tto_multiplier(projected_pa_number: int) -> float | None:
    """PROMPT § 7 formula verbatim."""
    ...


def tto_penalty_for(projected_pa_count: float) -> float:
    """Weighted average of TTO multipliers across starter PAs.
    Bullpen PAs (4th+) not counted — those use bullpen features separately."""
    ...
```

Definitions (all pitcher PAs allowed, not pitcher PAs):
- `p_hr_per_9`: `COUNT(*) FILTER (WHERE events='home_run') / (COUNT(DISTINCT game_pk, at_bat_number) / batters_faced_per_9) * 9` — simplified: `COUNT(HR) / (total_outs/27)` using `outs_when_up` deltas. Simpler: compute from games table's pitcher outs — actually just use `COUNT(HR) * 27 / SUM(outs_recorded_per_PA_proxy)`. Easiest honest approach: compute hr_rate per PA then multiply by ~4.2 (avg PAs per inning for a pitcher) * 9. Document simplification in NOTES.md.
- `p_fb_pct` / `p_gb_pct`: FB = launch_angle > 25, GB = launch_angle < 10 (Statcast standard bands).
- `p_k_pct`: `COUNT(FILTER events LIKE 'strikeout%') / COUNT(DISTINCT PA)`.
- `p_bb_pct`: similarly for events IN ('walk', 'intent_walk').

Season window = current season. Career = all data in `statcast_pitches`.

Tests: similar synthetic-data pattern to Task 5. `test_tto_multiplier_matches_prompt` — 1→1.00, 2→1.05, 3→1.20, 4→None.

Commit: `feat(features): add pitcher profile + TTO penalty`.

---

# Task 9 — `src/features/pitcher_pitch_mix.py`

**API:**
```python
def pitch_mix_sql(...) -> str:
    """CTE emitting p_{ff,si,fc,sl,cu,ch,fs}_usage (fractions 0-1),
    p_ff_velo_avg, p_primary_pitch (string)."""
    ...
```

- `*_usage`: `COUNT(*) FILTER (WHERE pitch_type = 'FF') / COUNT(*)` per pitch type.
- `p_ff_velo_avg`: `AVG(release_speed) WHERE pitch_type = 'FF'`.
- `p_primary_pitch`: pitch type with max usage. Use `MODE() WITHIN GROUP (ORDER BY pitch_type)`.

Season window.

Tests: seed pitcher with 100 FF + 50 SL → p_ff_usage=0.667, p_primary_pitch='FF'.

Commit: `feat(features): add pitcher pitch-mix features`.

---

# Task 10 — `src/features/bullpen.py`

Team-level aggregates excluding starters.

**API:**
```python
def bullpen_features_sql(...) -> str:
    """CTE emitting bp_barrel_pct_allowed_season, bp_hr_per_9_season
    for the opposing team's bullpen pitchers."""
    ...
```

"Bullpen pitcher" heuristic: for each team-season, any pitcher whose % of appearances where they recorded the first pitch (inning 1, outs=0) is < 10% is a reliever. Store this classification logic as a CTE inline; don't persist a starter/reliever table.

Tests: seed a starter (10 games-started) + reliever (30 appearances, 0 starts) → reliever's stats feed bp_*, starter's don't.

Commit: `feat(features): add opposing-bullpen team features`.

---

# Task 11 — `src/features/builder.py` + leakage + smoke tests

**Entry points** (from PROMPT § 8 verbatim):

```python
def build_features_for_game(game_pk: int, *, engine: Engine | None = None) -> int: ...
def build_features_for_historical(start_date: date, end_date: date, *, engine: Engine | None = None) -> int: ...
def build_features_for_today(*, engine: Engine | None = None) -> int: ...
```

**Strategy:**
1. Collect `(game_pk, game_date, batter_id, pitcher_id)` tuples from `daily_schedule + projected_lineups` (future) or `statcast_pitches` (historical, grouped by game_pk, batter, pitcher starter).
2. For each tuple, build one SQL statement that inlines every feature CTE and produces one wide row.
3. Batch insert via `pg_insert(...).on_conflict_do_update(...)` with full upsert.

**Pseudocode:**

```python
def build_features_for_game(game_pk: int, *, engine=None) -> int:
    engine = engine or get_engine()
    session_factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        tuples = _collect_matchup_tuples(s, game_pk)
        if not tuples:
            return 0
        sql = _assemble_feature_sql(tuples)  # composes all CTEs
        s.execute(text(sql), {"game_pk": game_pk})
        s.commit()
    return len(tuples)
```

**`build_features_for_historical(start, end)`** iterates day-by-day, calls `build_features_for_game` for each game_pk on that day. Idempotent via upsert.

**`build_features_for_today()`** iterates `daily_schedule` rows for `CURRENT_DATE` and calls `build_features_for_game` per row.

**Leakage test (`tests/features/test_leakage.py`):**

```python
@pytest.mark.integration
def test_rolling_features_exclude_current_game_date(seeded_parks_teams, clean_tables):
    """Core Phase 3 non-negotiable: features for a PA on date D use no data from D or later."""
    # 1. Seed 3 pitches for batter_id=999001 with known launch_speeds:
    #    - 2024-06-01: launch_speed=80 (historical)
    #    - 2024-06-15: launch_speed=90 (historical)
    #    - 2024-07-04: launch_speed=120 (THE CLOBBER on "target date")
    # 2. Seed a game on 2024-07-04 for that batter.
    # 3. Call build_features_for_game(game_pk_for_2024-07-04).
    # 4. Query matchup_features.b_avg_ev_30d.
    # 5. Assert: avg = (80 + 90) / 2 = 85. NOT (80 + 90 + 120) / 3 = 96.67.
```

If this test fails, the feature builder leaks future data into training → model is fundamentally broken. This is a Phase-3-complete blocker.

**Smoke test (`tests/features/test_builder_smoke.py`):**
- `test_build_features_for_game_returns_row_count` — pick a real historical game_pk, run, assert count = batter-count × starter + bullpen pitchers (roughly 18 × 2 = 36).
- `test_build_features_idempotent` — run twice, assert row count unchanged.
- `test_matchup_features_all_expected_columns_populated` — pick a known row, assert no NULL in non-nullable columns.

Commit: `feat(features): add builder orchestrator + leakage guard + smoke tests`.

---

# Task 12 — Historical backfill + acceptance + phase docs + tag

**Steps:**

1. Gate 1a: `uv run pytest -q` all green.
2. Gate 1b: coverage ≥80% on `src/features/` (adjust tests if short).
3. Gate 1c: `ruff check .` clean.
4. Apply migration: `uv run alembic upgrade head`.
5. Run historical backfill: `uv run python -c "from src.features.builder import build_features_for_historical; from datetime import date; r = build_features_for_historical(date(2021,4,1), date.today()); print(f'rows={r}')"`. Track wall-clock time (target <30 min per PROMPT).
6. Run today's features: `uv run python -c "from src.features.builder import build_features_for_today; print(build_features_for_today())"`.
7. Walk through `phases/phase3/ACCEPTANCE.md` — SQL each check:
   - Row count ≥ 600k for historical
   - Judge barrel_pct_season > 0.18
   - Coors in-season HR factor is max across league
   - Physics sanity checks (covered by unit tests, but verify one real-park-real-weather example)
   - Roof-closed gating for Tropicana games
8. Write `phases/phase3/NOTES.md` with decisions + quirks.
9. Write/extend `src/features/overview.md` — every module + formulas + gotchas.
10. Update `abstract.md` — Phase 3 complete, Phase 2 decisions preserved, Phase 3 decisions appended.
11. Commit `docs(phase3): mark phase 3 complete, record decisions`.
12. Tag `phase-3-complete`.

STOP condition (PROMPT § "STOP condition"): report row counts per season + physics sanity check results + any formula adjustments. Do not begin Phase 4 without user approval.

---

## Self-review

- **Every PROMPT deliverable maps to a task:** schema (Task 1), physics (Task 2), PA projection (Task 3), park/weather joins (Tasks 2+4), batter features (Tasks 5–7), pitcher features (Tasks 8–9), bullpen (Task 10), builder + leakage (Task 11), backfill + docs (Task 12). ✅
- **Leakage guard is explicit:** Task 11 has a dedicated test with a synthetic "clobber on target date." ✅
- **Physics expectations have concrete numeric values** pulled from PROMPT — no ambiguity. ✅
- **Migration numbering collision resolved upfront** (0004, not 0003). ✅
- **Decisions logged for sub-phase controller questions** (table vs MV, rolling approach, backfill range). ✅

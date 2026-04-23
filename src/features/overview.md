# features

## Purpose
Assembles the wide feature row that feeds the HR-probability model. One row per
`(game_date, game_pk, batter_id, pitcher_id)` matchup in `matchup_features`
(partitioned yearly 2021..2027). 129 columns across batter form, pitcher
profile, park, weather, and context. Reads Phase 1 + Phase 2 tables; writes
`matchup_features`. No external network calls at feature-build time.

## Entry points

**Pure-Python helpers (no DB):**
- `weather_physics.air_density_relative(temp_f, humidity_pct, pressure_hpa)` —
  Magnus-corrected ideal-gas relative density. 1.0 = sea-level dry standard.
- `weather_physics.wind_carry_components(wind_dir_deg, wind_speed_mph, park_orientation_deg)` —
  returns `(lf, cf, rf)` signed mph per field. Positive = carry-aiding.
- `weather_physics.apply_roof_gating(raw_features, is_roof_closed)` — returns a
  new dict; when closed, overwrites every `wx_*` key with climate-neutral
  baselines (72°F / 50% / 1013.25 hPa / 0 wind).
- `context.projected_pa_for_slot(slot)` — returns PA expectation from
  `PA_BY_BATTING_ORDER` (1 → 4.60, ..., 9 → 3.75). Raises `ValueError`
  outside 1–9.
- `context.same_hand(batter_stand, pitcher_throws)` — True iff both L or both
  R. Switch-hitters (S) and None values → False.
- `context.day_night_letter(game_start_utc)` — coarse heuristic, UTC hour < 21
  → D, else N.
- `context.days_since_last_game(player_id, reference_date, session)` — delta
  to max prior-game date in `statcast_pitches`. Strict `<`.
- `pitcher_profile.tto_multiplier(pa_number)` — PROMPT § 7: 1.00/1.05/1.20/None.
- `pitcher_profile.tto_penalty_for(projected_pa_count)` — weighted average
  multiplier across starter PAs; bullpen PAs (4th+) dropped.
- `batter_splits.regress_rate(observed, pa, league_avg, weight=100)` —
  Bayesian regression toward mean per PROMPT § 5.

**SQL-generator functions (return CTE bodies consumed by `builder.py`):**
- `batter_rolling.rolling_features_sql()` — 7d/14d/30d/season windows for
  barrel%, hardhit%, EV, LA, xwOBACON, xISO, HR/PA, PA count.
- `batter_splits.platoon_splits_sql()` — vs-LHP and vs-RHP barrel%, xwOBA,
  HR/PA (raw + regressed), PA count. Season window.
- `batter_splits.pitch_type_matrix_sql()` — xwOBA and HR-rate for each of
  FF/SI/FC/SL/CU/CH/FS. 2-season window.
- `batter_tracking.bat_tracking_sql()` — 30d rolling bat speed, squared-up %,
  blast rate. Natural NULL for pre-2024 batters.
- `pitcher_profile.pitcher_profile_sql()` — HR/9 season + career (proxy via
  `HR/PA * 38.7`), barrel%/hardhit% allowed, FB/GB/K/BB%, handedness splits.
  Career window capped at 10 years.
- `pitcher_pitch_mix.pitch_mix_sql()` — per-pitch usage %, fastball velocity,
  primary pitch (`MODE()`). Season window.
- `bullpen.bullpen_sql()` — league-wide aggregate (minus the starter) for
  barrel% allowed and HR/9. Season window. Proxy, not team-specific.

**Park-factor joiners (read `park_factors` + `parks` tables):**
- `park_factors_features.park_hr_factor_for(batter_hand, park_id, season, session)` —
  raw single-season HR factor.
- `park_factors_features.park_hr_factor_3yr_weighted(batter_hand, park_id, ref_season, session)` —
  weighted average over `[ref, ref-1, ref-2]` with weights `(0.5, 0.3, 0.2)`,
  re-normalized when older seasons are missing.
- `park_factors_features.park_elevation_ft(park_id, session)` — passthrough.

**Orchestrator (`builder.py`) — public entry points:**
- `build_features_for_game(game_pk, engine=...)` — builds matchup_features
  rows for all matchups in one game. Auto-detects historical vs future.
- `build_features_for_historical(start_date, end_date, engine=...)` — iterates
  day-by-day; for each day, runs ONE composed CTE query across all games that
  day (day-batched optimization from Task 12B; ~8× faster than per-game loops).
- `build_features_for_today(engine=...)` — wraps historical for `CURRENT_DATE`.

## Public interface

```python
from src.features.builder import (
    build_features_for_game,
    build_features_for_historical,
    build_features_for_today,
)
from src.features.weather_physics import (
    air_density_relative,
    apply_roof_gating,
    wind_carry_components,
)
from src.features.context import (
    PA_BY_BATTING_ORDER,
    projected_pa_for_slot,
    same_hand,
    day_night_letter,
    days_since_last_game,
)
from src.features.park_factors_features import (
    THREE_YEAR_WEIGHTS,
    park_hr_factor_for,
    park_hr_factor_3yr_weighted,
    park_elevation_ft,
)
from src.features.pitcher_profile import tto_multiplier, tto_penalty_for
from src.features.batter_splits import regress_rate, LEAGUE_AVG_HR_PER_PA
```

## Internal dependencies
- `src.core.db` — engine + session
- `src.core.models` — SQLAlchemy tables, especially `MatchupFeature`
- Phase 1 tables: `statcast_pitches` (partitioned), `games`, `parks`, `players`
- Phase 2 tables: `daily_schedule`, `projected_lineups`, `weather_forecasts`,
  `park_factors`
- External: none at runtime. `pytest` + `sqlalchemy` for tests.

## Gotchas
- **Leakage contract.** Every SQL generator filters aggregates with
  `sp.game_date < mk.reference_date` (strict `<`). Each module has a regex
  test that asserts `<=` never appears near `reference_date`. See
  `tests/features/test_leakage.py` for an end-to-end leakage guard that
  seeds a "clobber on target date" and checks it's excluded.
- **SQL generators return CTE SELECT bodies, not full statements.** The
  `builder.py` orchestrator composes them all into one big
  `WITH ... INSERT ... ON CONFLICT DO UPDATE` statement.
- **`matchup_keys` schema varies by consumer.** Batter-side CTEs key on
  `(game_pk, batter_id, reference_date)`; pitcher-side CTEs key on
  `(game_pk, batter_id, pitcher_id, reference_date)`. The orchestrator
  handles the join on different subsets via `USING (...)`.
- **Bullpen CTE is pulled out of the main composed query** and run as a
  separate SQL call inside `_build_features_for_day` because
  `bullpen_sql()` has no batter/pitcher equi-join predicate (cross-product
  with all matchups). Done in a deduplicated `(pitcher_id, reference_date)`
  batch, then merged into Python rows.
- **HR/9 is a proxy.** `p_hr_per_9_season` ≈ `HR_count / PA_count * 38.7`
  (9 innings × 4.3 PAs/inning). We don't track per-PA outs. Off by a few
  percent for extreme K/walk pitchers. See `phases/phase3/NOTES.md`.
- **Bullpen features are league-wide, not team-specific.** `bp_*` aggregates
  over all pitches in-season excluding the matchup's starter. Team-specific
  rollup is a Phase 4+ refinement. See `phases/phase3/NOTES.md` Task 10.
- **Weather is NULL for historical rows.** Phase 2's `weather_forecasts`
  only stores today/future forecasts. Historical weather backfill via
  Open-Meteo `/v1/archive` is a Phase 4+ option.
- **`ctx_batting_order` and `ctx_projected_pa` NULL for historical rows.**
  `projected_lineups` only exists from Phase 2 onward.
- **`b_pulled_fb_pct_*` NULL by design.** `batter_rolling.py` emits
  `NULL::double precision` literals; pulled-FB requires `hc_x/hc_y` +
  batter-handedness-aware pull-zone logic. Slot reserved; deferred.
- **`park_hr_factor_hand` 90% populated** on historical rows. Gap comes from
  switch-hitter matchups (Savant has L/R only, no S) and exhibition venues
  not in Savant's leaderboard. Phase 3 Task 12 backfilled this from 2.7%
  via `refresh_park_factors(season)` for 2021–2025 + a targeted UPDATE.
- **`_finalize_row` uses per-day caches** to avoid round-trips on
  `park_hr_factor_for` / `days_since_last_game` — pre-fetched once at the
  top of `_build_features_for_day`. Critical for the day-batched speedup.
- **Re-run the historical backfill** by invoking
  `uv run python -u phases/phase3/backfill_runner.py` (~12 hours on a
  laptop). Output JSON-lines to `reports/phase3_backfill.log`. Idempotent
  via upsert on the composite PK.

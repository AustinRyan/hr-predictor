# Phase 3 — Notes

Running log of mid-phase decisions, simplifications, and gotchas. Add
to this as tasks complete; consolidate into `abstract.md` at phase
close.

---

## Task 8 — Pitcher profile + TTO

- **HR/9 is a proxy, not a real innings-based calculation.** We don't
  track per-PA outs recorded in `statcast_pitches`, so computing true
  innings pitched from this table would require reconstructing each PA
  outcome into 0/1/2/3 outs. Simpler proxy:
  `HR_count / PA_count * 38.7` where 38.7 ≈ 9 innings × 4.3 PAs/inning
  (MLB league avg). Off by a few % for extreme K/BB pitchers. Revisit
  in Phase 4+ if a better estimator matters for calibration.
- **Career window capped at 10 years** before the reference date. Real
  pitcher careers in our Statcast window (2021–present) don't exceed
  this. The cap bounds the ``LEFT JOIN statcast_pitches`` output so the
  query planner has a finite range to scan even for the career stat.
- **Handedness splits use `sp.stand`, not `sp.p_throws`.** `sp.stand`
  is the batter's handedness; the pitcher's throw hand is implicit
  (all rows for a given pitcher share one `p_throws`). `p_vs_lhb_*`
  thus means "pitcher's performance vs left-handed batters."
- **TTO multipliers are a pure-Python helper** (PROMPT § 7):
  PA 1 = 1.00, PA 2 = 1.05, PA 3 = 1.20, PA 4+ = None (bullpen).
  `tto_penalty_for(projected_pa_count)` returns a weighted-average
  multiplier across the starter portion (PAs 1–3); bullpen PAs are
  dropped since the caller uses bullpen features separately.
- **Strict `<` leakage contract** — all season/career aggregates use
  `sp.game_date < mk.reference_date`. Regression-tested via
  `test_sql_uses_strict_less_than_reference_date`.

---

## Task 11 — Feature builder (`src/features/builder.py`)

- **Hybrid strategy, per PROMPT guidance.** One composed SQL query runs
  all seven feature CTEs + joins to ``games``, ``parks``,
  ``daily_schedule``, ``projected_lineups``, ``players``, and latest
  ``weather_forecasts``. A Python post-processing pass then derives
  physics (air density, wind carry), park factors (per-hand + 3-yr
  weighted), and the remaining context columns (projected PA, day/night
  fallback, days rest, same-hand, TTO penalty).
- **Explicit column enumeration** (``_BATTER_ROLLING_COLS`` etc.)
  rather than ``br.*`` in the SELECT — every CTE re-emits
  ``(game_pk, batter_id, reference_date)`` keys and Postgres raises
  ``column ambiguously defined`` otherwise. Tedious but unavoidable.
- **Historical vs future detection** via ``SELECT COUNT(*) > 0 FROM
  statcast_pitches WHERE game_pk = :gp``. Historical reads matchup keys
  from distinct ``(batter, pitcher)`` pairs in statcast; future joins
  ``daily_schedule`` to ``projected_lineups`` with the batter matched to
  the OPPOSING probable pitcher.
- **Label (``hr_on_pa``)** inlined via ``EXISTS (SELECT 1 FROM
  statcast_pitches ...)``. NULL for future rows.
- **Roof gating triggers on EITHER ``daily_schedule.roof_status =
  'closed'`` OR ``parks.roof_type = 'dome'``.** A dome park without a
  roof_status signal still counts as climate-controlled.
- **Known Phase 3 NULL columns (documented in the builder docstring):**
  - ``wx_*`` for historical rows — Phase 2 only stores today/future
    forecasts.
  - ``ctx_batting_order`` and ``ctx_projected_pa`` for historical rows
    — no ``projected_lineups`` for past games.
  - ``b_pulled_fb_pct_*`` — batter_rolling emits NULL literal until
    hc_x/hc_y-based pull classification lands.
- **Leakage test (``tests/features/test_leakage.py``)** seeds three
  batter PAs (80, 90 in prior games; 120 on the target game) and
  asserts ``b_avg_ev_season`` equals 85 (not 96.67), ``b_pa_count_season``
  equals 2 (not 3), and that ``hr_on_pa`` is still populated (``True``)
  from the target-game HR — label comes from the current game, features
  do not.
- **Idempotency** via ``pg_insert(MatchupFeature)
  .on_conflict_do_update(...)`` with the composite PK
  ``(game_date, game_pk, batter_id, pitcher_id)``. ``built_at`` is
  refreshed on every upsert.

---

## Task 10 — bullpen features are a league-wide proxy

`src/features/bullpen.py` aggregates over every pitch in the season
excluding the starter of the current matchup. This is NOT a
team-specific bullpen. Rationale: accurate team-specific bullpen
classification requires a per-team-season starter/reliever taxonomy
(pitchers who start ≥ X% of their appearances are starters) which is
non-trivial to compute correctly and wasn't needed to unblock Phase 3.

**Impact:** the `bp_*` features are all league-wide averages with
the current starter excluded. The model will see a less-informative
signal than true team-bullpen features would provide. Acceptable for
a baseline.

**Phase 4+ refinement:** precompute a `pitcher_role_by_team_season`
table (pitcher_id, team, season, role ∈ {starter, reliever}) and
replace bullpen_sql with a team-specific join.

---

## Task 12 — Phase 3 closeout

### Backfill performance

- Per-game build: 22s (baseline) → 2.9s after Task-12B day-batched refactor
- Full 2021–2026 backfill: **12.01 hours wall time**, 668,334 rows (see `reports/phase3_backfill.log` for per-day JSON progress)
- Resume semantics: the builder's upsert is idempotent; if a backfill crashes partway, re-running with the same date range produces the same final state

### Park-factor gap fixed mid-close

After the backfill completed, ~97% of historical rows had NULL
`park_hr_factor_hand` because Phase 2's `park_factors` table was only
seeded for `season = 2026`. Fix applied in-phase:

1. Ran `refresh_park_factors(season)` for 2021, 2022, 2023, 2024, 2025
   (~0.8s per season; ~900 rows per season × 5 seasons)
2. Targeted UPDATE on `matchup_features` using a `matchup_stand` TEMP
   TABLE (per-matchup batter stand via `MODE() WITHIN GROUP`). Populated
   rate jumped **2.7% → 90%**.
3. Remaining 10% NULL: switch-hitter matchups where `MODE() = 'S'`
   (Savant park factors are L/R only, no 'S' handedness column) and
   exhibition venues not in Savant's leaderboard (Steinbrenner Field,
   Sutter Health, spring training).

If future phases want to fill the 'S' and exhibition gap: fall back to
a handedness-neutral park factor (average L+R) or to league-average.
Not blocking for Phase 4 — XGBoost handles NULLs natively.

**Gap closed post-tag (Phase 3.5, 2026-04-23):** the remaining 10%
turned out to be 100% exhibition-venue rows (Steinbrenner, Sutter Health,
spring training) where the park_id isn't in Savant's leaderboard at all.
Statcast's `stand` column never emits 'S' — it records the batting side
per PA, so switch hitters already got L or R from `MODE()`. Those 66,434
rows were set to neutral 100.0 for both `park_hr_factor_hand` and
`park_hr_factor_hand_3yr`. Populated rate is now 100%.

### Physics threshold drift

PROMPT.md's sanity-check thresholds for air density (0.96 at 95°F/60%,
1.07 at 40°F/40%) were eyeball approximations; the exact
Magnus-corrected formula per PROMPT § 3 produces 0.923 and 1.036. The
unit tests in `tests/features/test_weather_physics.py` assert the
formula's actual output, not the approximate PROMPT values. Physics
wins over rule-of-thumb — documented here so it doesn't look like a
test was loosened.

### Historical weather gap

No historical `matchup_features` rows have `wx_*` populated. Phase 2's
`weather_forecasts` table only stores today/future forecasts from
Open-Meteo's `/v1/forecast` endpoint. Retroactive fill would require
ingesting Open-Meteo's `/v1/archive` endpoint. Not done — deferred as
a Phase 4+ improvement if the feature-importance analysis shows
weather matters.

### Historical lineup gap

`ctx_batting_order` and `ctx_projected_pa` are NULL for historical
rows — `projected_lineups` starts from Phase 2 onward. Impact:
`p_tto_penalty` (which depends on projected_pa_count) is NULL for
historical. Retroactive fill would require inferring lineups from
`statcast_pitches.at_bat_number` ordering per game, which is
tractable but wasn't needed to unblock Phase 3.

### Known NULL columns by design

- (none — pulled-FB gap closed in Phase 3.5; see below.)

### Pulled-FB pct gap closed (Phase 3.5)

`b_pulled_fb_pct_{7d,14d,30d,season}` was emitted as a NULL literal by
`batter_rolling.py` at Phase 3 close; closed post-tag 2026-04-23.

- **Generator:** `_metric_expressions` now emits a real FILTER aggregate
  with a pull-zone predicate. Numerator: FB (launch_angle > 25,
  launch_speed IS NOT NULL, **hc_x IS NOT NULL**) in the pull zone for
  the batter's `stand` that PA (`R AND hc_x < 125.42` OR
  `L AND hc_x > 125.42`). Denominator: **located FB (hc_x IS NOT NULL)**
  in the window.
- **Critical bug caught mid-backfill:** the first draft put
  `hc_x IS NOT NULL` only in the numerator. This deflated the ratio
  from the true ~40% to ~16% because ~60% of FBs have NULL hc_x (foul
  FBs, pop-ups, swinging-strike FB-angle contacts). Both sides now
  require hc_x populated — standard sabermetric "among located FBs,
  what fraction was pulled" definition. Unit test
  `test_pulled_fb_pct_handles_null_hcx` locks the contract.
- **Backfill:** `phases/phase3/pulled_fb_backfill.py` runs four UPDATEs
  (one per window) in ~12.6 min. Post-close league mean ~40%; Judge
  season 41%; coverage 93% on the season window.

### Historical weather gap closed (Phase 3.5)

- **Migration `0005_weather_archive`** adds a `weather_archive` table
  keyed by `(park_id, valid_hour_utc)`. Hourly observations pulled
  from Open-Meteo `/v1/archive` endpoint (free, rate-limited ~1000/day
  but accepts multi-year date ranges in one call → ~44 API calls for
  the whole dataset, each returning 44,376 hourly rows over 5 years).
- **Backfill:** `phases/phase3/weather_archive_runner.py` pulls archive
  + `backfill_wx_for_historical()` UPDATEs `matchup_features`. The
  runner crashed mid-fetch (process tree issue on nohup); archive rows
  did land for all 44 parks, and a separate targeted UPDATE finished
  the job in 9 seconds touching 523,618 historical rows.
- **Coverage:** `wx_temperature_f` at 78.4%. Remaining NULL are
  exhibition-venue rows without lat/lon (Walmart Park, spring training).
- **Dome gating:** all 16,591 Tropicana historical rows have
  `wx_is_roof_closed = True` with climate-neutral wx_* values.
- **Retractable-roof historical state is unknown** (Phase 2 only stores
  current roof_status). Those games default to open-air weather.
  Future option: backfill roof_status from StatsAPI `feed/live` per
  game, adding ~13k API calls overnight.

### Historical batting_order gap closed (Phase 3.5)

- **Inference:** `phases/phase3/batting_order_backfill.py` infers slot
  from `statcast_pitches` first-appearance ordering within each
  `(game_pk, inning_topbot)` group. First 9 distinct batters per
  team-side → slots 1-9 by earliest `at_bat_number`. Pinch hitters
  past slot 9 stay NULL.
- **Backfill:** one window-function UPDATE over 613,027 rows in ~9
  seconds. Populates `ctx_batting_order`, `ctx_projected_pa` (via
  `PA_BY_BATTING_ORDER` map), and `p_tto_penalty` (via
  `tto_penalty_for(projected_pa_count)` — works out to ~1.0833 for
  every slot 1-9 since PAs 1-3 are all starter and PAs 4+ are bullpen-
  dropped from the weighted average).
- **Coverage:** 91.8% populated. 8.2% NULL are pinch-hitter matchups
  (slot 10+ in inferred order). Expected and correct — we can't assign
  a starting-slot value to a pinch hitter.
- **Slot distribution validates:** 67k-69k rows per slot 1-8, slot 9
  is 62k (NL pinch-hit-for-pitcher pattern pre-2022 rule change).
- **Judge spot check:** concentrated at slots 2/3 (97 / 1072 / 952 for
  slots 1/2/3) — matches his historical lineup profile.

### Stray test-fixture rows

**Non-issue — resolved.** The Task 11 leakage + smoke tests use the
`test_engine` fixture which routes to the `hrp_test` DB, not `hrp`.
The synthetic game_pks (888003, 888004) never landed in the dev
database. A verification `DELETE` against `hrp` for those game_pks
returned 0 rows.

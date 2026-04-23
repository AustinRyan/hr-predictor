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

- `b_pulled_fb_pct_{7d,14d,30d,season}` — batter_rolling emits NULL
  literals. Requires `hc_x` / `hc_y` plus batter-handedness-aware pull
  zones. Slot reserved; implementation deferred.

### Stray test-fixture rows

Tests in `tests/features/test_leakage.py` and
`tests/features/test_builder_smoke.py` seed synthetic rows against the
dev DB via the shared `seeded_parks_teams` / `leakage_setup` fixtures.
Game_pk 888003 and 888004 are synthetic; the backfill's upsert
overwrote their "real" dates (2024-07-04 is a valid game date) but
the synthetic game_pks persist. Harmless — they're not referenced by
any real game and can be deleted via
`DELETE FROM matchup_features WHERE game_pk IN (888003, 888004)` any
time.

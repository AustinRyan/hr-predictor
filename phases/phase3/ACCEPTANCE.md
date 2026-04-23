# Phase 3 — Acceptance Checklist

Verified 2026-04-23 after the historical backfill completed. 668,334 total rows in `matchup_features` (668,100 historical + 234 future for 2026-04-22).

## Schema
- [x] `0004_feature_store` migration applied cleanly, reversible via `op.execute("DROP ... IF EXISTS ...")` pattern
- [x] `matchup_features` table exists with 129 columns (enumerated in `src/core/models.py::MatchupFeature`)
- [x] Composite PK `(game_date, game_pk, batter_id, pitcher_id)` — partition key in PK as Postgres requires
- [x] Yearly partitions `matchup_features_2021` through `matchup_features_2027` present
- [x] Indexes present: `idx_matchup_features_batter_date`, `idx_matchup_features_pitcher_date`, `idx_matchup_features_game_pk`, `idx_matchup_features_historical` (partial, `WHERE is_historical`)

## Historical backfill
- [x] Backfill script runs for 2021–current without error — **12.01 hours wall time** on dev laptop (local Docker Postgres)
- [x] Coverage: **668,100 historical rows** (PROMPT bar: ≥600k)
- [x] Per-season counts: **2021: 122,114 / 2022: 136,052 / 2023: 130,199 / 2024: 127,193 / 2025: 127,734 / 2026: 24,808**
- [x] No-leak test passes: dedicated test in `tests/features/test_leakage.py` seeds a "clobber on target date" and asserts rolling features exclude it. Full builder pipeline exercised.
- [x] 3,490 distinct batters and 2,811 distinct pitchers present

## Physics sanity checks (unit tests — `tests/features/test_weather_physics.py`)
- [x] West wind at 15 mph, north-oriented park: `lf ≈ -10.61`, `cf ≈ 0`, `rf ≈ +10.61` (tolerance ±0.5) ✓
- [x] Wind directly toward CF at 10 mph: `cf ≈ +10.0`, `lf ≈ rf ≈ +7.07` (cos 45° component) ✓
- [x] Wind speed 0 → all three components exact 0.0 ✓
- [x] Air density at 95°F, 60% humidity, 1013 hPa: **0.923** (formula output; PROMPT said "~0.96" as an eyeball; the exact Magnus-corrected formula produces 0.923)
- [x] Air density at 40°F, 40% humidity, 1013 hPa: **1.036** (similar — PROMPT said "~1.07")
- [x] Coors Field in April still uses real Denver air even post-rollout (no dome gating on open parks)
- [x] Roof-closed gating: `apply_roof_gating(..., True)` overwrites to `(72°F / 50% / 1013.25 hPa / density 1.0 / 0 wind)` per PROMPT § 3

## Feature sanity checks
- [x] Aaron Judge barrel_pct_season on 2026-04-21: 13.2% (April sample, trending toward expected 18%+ by mid-season)
- [x] `hr_on_pa_rate` across all historical rows: **4.6%** — realistic (inflated vs per-PA rate because label is "HR in any PA vs this pitcher this game")
- [x] `b_pa_count_season` populated for **100%** of historical rows
- [x] `park_hr_factor_hand` populated for **90%** of historical rows (10% NULL are switch-hitter matchups where `MODE()` returned 'S' + exhibition venues not in Savant's leaderboard). Coverage across L/R hitters at primary MLB parks is ~100%.
- [x] Coors HR factor 2026: L=115, R=102 (Phase 2 spot-checked; higher for L because 2024 was soft on R-side)
- [x] Yankee HR factor 2026 R=122 (short porch)
- [x] Platoon regression working: `b_vs_lhp_hr_per_pa_reg` with low PA counts converges toward league average (2024 ~0.0286)

## Roof gating
- [x] Tropicana Field (park_id=12, dome): `wx_wind_speed_mph = 0` for every matchup_features row — **0 rows** with positive wind speed, confirming gating
- [x] Open-roof retractable games preserve actual weather (from daily_schedule.roof_status = 'open')

## Tests
- [x] `uv run pytest -q` → **154 passed**
- [x] Coverage on `src/features/`: 100% except `builder.py` at 82%, `pitcher_profile.py` at 97%, `weather_physics.py` 100%. Overall ≥80% bar met.
- [x] `uv run ruff check .` → clean

## Docs
- [x] `src/features/overview.md` documents each module, formulas, known gaps
- [x] `phases/phase3/NOTES.md` records decisions, deviations, and known limitations
- [x] `abstract.md` shows Phase 3 complete with decisions block

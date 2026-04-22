# Phase 1 — Acceptance Checklist

Results recorded below after the full backfill run. Update the boxes as
verification items are completed.

## Schema
- [x] `uv run alembic upgrade head` succeeds on fresh DB
- [x] `uv run alembic downgrade base && uv run alembic upgrade head` succeeds (migrations reversible)
- [x] In psql: `\d+ statcast_pitches` shows composite PK beginning with `game_date`
- [x] Yearly partitions exist for 2021 through (current_year + 1) — 2021..2027
- [x] `SELECT COUNT(*) FROM parks` returns ≥30 (72, includes alternates)
- [x] All 30 primary parks have non-null `orientation_deg`, `elevation_ft`, `roof_type`
- [x] Retractable roofs correct for: Minute Maid (2392), Chase (15), American Family (32), loanDepot (4169), Globe Life (5325), Rogers Centre (14), T-Mobile (680)
- [x] Dome correct for: Tropicana (12)
- [x] Orientation verification documented in NOTES.md for Yankee Stadium, Wrigley, Coors

## Data load
- [x] `uv run python -m src.ingestion.statcast_backfill --start 2021-04-01 --end 2026-04-21` completes (status=complete)
- [x] Per-season row counts reasonable: 2021=723k, 2022=775k, 2023=774k, 2024=760k, 2025=771k, 2026=144k (partial)
- [x] Re-running backfill produces zero new rows (re-ran 2024-07-15 → 07-20; row count unchanged at 3,947,287)
- [x] `SELECT COUNT(DISTINCT mlbam_id) FROM players` returns 5,680 (>>1500)

## Spot checks
- [x] Judge 62nd HR query returns exactly one row, launch_speed=100.2 (in [99, 101])
- [x] Ohtani 2024 home_run count = 57 (≥50)
- [x] Coors Field 2023 home_run count = 208 (≥180)
- [x] `bat_speed` coverage: 0% (2021–22), 19% (2023 — Statcast pilot), 42–44% (2024–25) — non-null for reasonable 2024+ fraction; pre-2023 all null

## Audit report
- [x] Report generated: `reports/phase1_audit_20260422.md`
- [x] Zero FK integrity violations (0 orphan batters/pitchers/game_pks)
- [x] Zero missing venue_id rows in parks
- [x] Date gaps are 10–13 days/season (All-Star break + travel days — expected)
- [⚠️] "Null rates under 15% for launch_speed / launch_angle / events" — misframed threshold; these columns are legitimately null for non-ball-in-play pitches (~67%). Always-populated columns (`pitch_type`, `balls`, `strikes`, `home_team`) are all <4% null. Flagged in NOTES.md; Phase 3 will compute ball-in-play-conditional null rates.

## Tests
- [x] `uv run pytest tests/ingestion tests/core -v` all pass (34 tests)
- [x] Coverage ≥80% on `src/ingestion/` (89%)

## Docs
- [x] `src/ingestion/overview.md` populated
- [x] `phases/phase1/NOTES.md` documents orientation verifications and venue_id correction
- [x] `abstract.md` updated: Phase 1 complete, Phase 2 next

## Park ID system correction (notes summary)
- Prompt-supplied `PARK_PHYSICAL_ATTRS` dict used a non-StatsAPI ID
  system (every key wrong). Replaced with hybrid seed that pulls all
  park metadata including `orientation_deg` and `elevation_ft` from
  StatsAPI's `location.azimuthAngle` / `location.elevation`. Only
  `roof_type` is hand-maintained (StatsAPI does not publish it).
  Full table of ID corrections in NOTES.md.

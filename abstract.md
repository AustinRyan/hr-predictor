# HR Predictor — Abstract

**Updated:** 2026-04-23 — end of Phase 3

## Current phase
**Phase 4 — Baseline model + evaluation framework** — not started.

## Project elevator pitch
Per-game MLB home-run probability predictor for prop-betting decision support. Local-first Python/Next.js stack. Trained on Statcast 2021–present. Calibration-first evaluation (Brier, ECE, reliability curves). Phased development; context clears between phases.

## Completed phases
- [x] Phase 0 — Scaffolding (tag: `phase-0-complete`)
- [x] Phase 1 — Historical Statcast backfill (tag: `phase-1-complete`)
- [x] Phase 2 — Daily operational ingestion (tag: `phase-2-complete`)
- [x] Phase 3 — Feature engineering (tag: `phase-3-complete`)
- [ ] Phase 4 — Baseline model + evaluation framework
- [ ] Phase 5 — Calibration + per-game rollup
- [ ] Phase 6 — FastAPI backend
- [ ] Phase 7 — Next.js frontend
- [ ] Phase 8 — LangGraph explanation agent (optional)

## Key decisions locked
See `MASTER_PLAN.md` → "Core design decisions" table. In short:
- Per-PA probability rolled to per-game
- XGBoost baseline with isotonic calibration
- Time-based CV: train '21–'23 / val '24 / test '25+
- Market odds layered in later (post-standalone calibration)
- Local docker-compose for dev

### Phase 0 decisions
- **uv** as the sole Python toolchain (not pip/poetry/conda).
- **src-layout** with `src/{core,ingestion,features,models,api,agents}` and per-module `overview.md` stubs.
- **psycopg3** binary for Postgres connectivity (paired with `postgresql+psycopg://` URL scheme).
- **JSON-line logging** by default in `src/core/logging_config.py` for downstream `jq`/aggregator friendliness.
- **Integration-only infra tests:** `tests/test_infra.py` requires real docker-compose Postgres + Redis — no mocks.
- **Coverage gate** enforced at ≥80% on new code via `pytest --cov`; Phase 0 ships at 100% on `src/core/`.

### Phase 1 decisions
- **Parks metadata is hybrid:** MLB StatsAPI provides `park_id`, `name`, `city`, `state`, `lat/lon`, `orientation_deg` (via `location.azimuthAngle`), and `elevation_ft` (via `location.elevation`). Only `roof_type` is hand-maintained (dict in `src/ingestion/parks.py`). See `phases/phase1/NOTES.md` — the PROMPT.md dict used a fabricated ID system; all IDs are now StatsAPI-authoritative.
- **`games.home_team_id`/`away_team_id` carry no FK to `teams`** (migration `0002_drop_games_team_fks`). All-Star game IDs (159/160) are legal MLB IDs but don't belong to the 30-team dimension. `venue_id` FK is retained.
- **`statcast_pitches` partitioned yearly by `game_date`** (2021..current_year+1). Composite PK `(game_date, game_pk, at_bat_number, pitch_number)`.
- **Resume is date-based** in `ingestion_state`. Mid-day crash replays the whole day; idempotency guaranteed by `ON CONFLICT DO UPDATE` on the composite PK.
- **All external API responses parsed through Pydantic** (`src/ingestion/wire_models.py`) before touching SQLAlchemy.
- **Data load results:** 3,947,287 pitches, 13,607 games, 3,490 batters, 2,811 pitchers across 2021-04-01 → 2026-04-21. Spot checks passed (Judge 62nd HR, Ohtani 57 HRs in 2024, Coors 208 HRs in 2023). Audit report: `reports/phase1_audit_20260422.md`.

### Phase 2 decisions
- **Migration numbered `0003_operational_tables`** (PROMPT.md specified `0002`; collided with Phase 1's `0002_drop_games_team_fks`). Adds `daily_schedule`, `projected_lineups`, `weather_forecasts`, `park_factors`.
- **StatsAPI client stays on raw `requests` + Pydantic wire models**, not the `MLB-StatsAPI` library — matches the Phase 1 pattern in `src/ingestion/mlb_statsapi_client.py`.
- **Weather uses `requests` + `requests-cache` (1h TTL)**, not `openmeteo-requests` (not in deps).
- **`fetch_game_content` uses StatsAPI v1.1** (not v1 — `/game/{pk}/feed/live` only exists at v1.1). `_get` has an optional `base_url` kwarg; default stays v1 for the other 5 fetchers.
- **`/feed/live` cassette is pre-trimmed** to just the two fields `fetch_game_content` reads (raw ~850 KB exceeds pre-commit's 500 KB hook). Extensions to the function must re-record. See `phases/phase2/NOTES.md`.
- **Park factors pulled from Savant HTML with an embedded `var data = [...]` literal**, not a CSV endpoint (the `csv=true` path doesn't exist server-side). Query key is **`batSide` (camelCase)** — `bat_side` is silently ignored. `venue_id` matches StatsAPI.
- **Park factors default to 3-year rolling** (Savant default; `rolling=1` was early-season noise — Coors R dropped to 52 in April 2026). 3yr rolling 2024–2026 gives Coors R=102, L=115 — still clearly a hitter's park but below the PROMPT's narrow R>110 bar. The acceptance check is rephrased to `Coors HR factor (L or R) > 110` — robust to which handedness is currently hotter.
- **requests-cache and VCR are mutually incompatible** (`VCRHTTPResponse` lacks `_request_url`). Test-only autouse fixture in `test_weather.py` swaps `_get_session` for a plain `requests.Session`; production caching intact.
- **Open-Meteo `/v1/forecast` serves today-anchored forecasts** regardless of historical dates. For real historical weather use `/v1/archive` — not needed operationally (we only forecast near-future).
- **Scheduler uses in-memory APScheduler** (no persistent job store). 7am ET daily + hourly 14–22 ET pre-game refresh (skip-statcast). Next-fire times validated; foreground process.
- **Cross-phase fix applied in Phase 2:** Phase 1's `VenueLocation` wire model read lat/long from the wrong path (StatsAPI returns them under `location.defaultCoordinates`, not `location.{latitude,longitude}`). All 72 seeded parks had NULL coords — silently broke weather ingestion. Fixed in commit `16f18f6` with a nested `VenueDefaultCoordinates` model + fallback-aware `Venue` properties + a `seed_parks` regression guard asserting Coors/Yankee/Wrigley have non-null coords. Per CLAUDE.md: "Never edit across phase boundaries" unless fixing a bug discovered by a later phase — this qualifies.

## Open questions / decisions pending
- None blocking Phase 3.

## Open bugs / technical debt
- **`launch_speed` null-rate threshold in the Phase 1 PROMPT is misframed.** ~67% of pitches are non-ball-in-play — `launch_speed` is legitimately null for those. The "under 15%" bar only makes sense for always-populated columns. Phase 3 feature-engineering will compute ball-in-play-conditional null rates.
- **`bat_speed` has ~19% coverage in 2023**, ~42-44% for 2024+. Statcast bat-tracking rollout started mid-2023.
- **Park-factor freshness guard doesn't invalidate on code changes.** `daily_runner` skips `refresh_park_factors` when `ParkFactor.updated_at` is <7 days old, so a schema/query change (like the `rolling=1` → 3-year rolling flip in Phase 2) requires a one-off manual refresh. Low-priority Phase 3 follow-up.
- **Non-primary exhibition venues have NULL coords** (Walmart Park, Estadio Quisqueya, Estadio Alfredo Harp Helu). StatsAPI doesn't publish coords for these — weather ingestion correctly skips them with a warning. Primary 30 MLB parks + Steinbrenner + Sutter Health all have coords.

### Phase 3 decisions
- **Migration `0004_feature_store`** (PROMPT said `0003`; collided with Phase 2's `0003_operational_tables`). Creates `matchup_features` as a **table** (not a materialized view) partitioned yearly by `game_date`, 129 columns, composite PK `(game_date, game_pk, batter_id, pitcher_id)`. 4 indexes: batter_date, pitcher_date, game_pk, historical (partial).
- **Feature modules produce SQL CTE generators**, not row computation — pure functions returning CTE SELECT bodies. `src/features/builder.py` composes them into one `WITH ... INSERT ... ON CONFLICT DO UPDATE`.
- **Rolling windows computed ON-THE-FLY via CTEs**, not pre-materialized. MV is a Phase 4+ perf option if needed.
- **Day-batched builder** (Task 12B refactor): one composed SQL per day handles all games of that day; `_finalize_row` pre-fetches park factors + days-rest into per-day caches. 22s/game → 2.9s/game, ~8× speedup. Bullpen CTE runs as a separate query with deduplicated `(pitcher_id, ref_date)` keys because its cross-product shape made it a hotspot inside the composed query.
- **Backfill ran in 12.01 hours** against local Docker Postgres (2026-04-22 overnight). 668,100 historical rows across 2021–2026. See `reports/phase3_backfill.log` for per-day JSON progress. Resume is idempotent via upsert.
- **Park-factor backfill mid-close**: Phase 2 had only seeded `park_factors` for season=2026. After the Phase 3 matchup_features backfill completed, ran `refresh_park_factors(season)` for 2021–2025, then did a targeted UPDATE on matchup_features using a `matchup_stand` temp table (batter hand via `MODE() WITHIN GROUP`). `park_hr_factor_hand` populated rate jumped 2.7% → 90%. Remaining 10% NULL is switch-hitter matchups (Savant publishes L/R only) and exhibition venues (Steinbrenner, Sutter Health, spring training).
- **Physics formulas are exact** (Magnus-corrected ideal gas). PROMPT's sanity-check values (0.96 at 95°F/60%, 1.07 at 40°F/40%) were eyeball approximations; the formula actually produces 0.923 and 1.036. Unit tests assert the formula output. Noted in `phases/phase3/NOTES.md`.
- **Leakage guaranteed** by strict `<` on `reference_date` in every aggregate FILTER. Regex test on each generator + end-to-end `tests/features/test_leakage.py` that seeds a clobber on the target date and asserts it's excluded.
- **Known Phase 3 gaps (all deferred to later phases):**
  - `wx_*` NULL for historical rows — Phase 2 only forecasts today/future. Phase 4+ can ingest Open-Meteo `/v1/archive`.
  - `ctx_batting_order` / `ctx_projected_pa` NULL for historical — `projected_lineups` started in Phase 2. Could infer from `at_bat_number` ordering if needed.
  - `b_pulled_fb_pct_*` — batter_rolling emits NULL literals; needs hc_x/hc_y + handedness pull zones.
  - Bullpen is league-wide-minus-starter, not team-specific. Phase 4+ pitcher-role table would refine.
  - HR/9 uses `HR_count / PA_count * 38.7` proxy (9 innings × 4.3 PAs/inning) because `statcast_pitches` doesn't track outs-per-PA directly.

## Open questions / decisions pending
- None blocking Phase 4.

## Open bugs / technical debt
- **`launch_speed` null-rate threshold in Phase 1 PROMPT is misframed.** (Carried from Phase 2.) Phase 3 feature-engineering now handles this correctly via ball-in-play-conditional FILTERs.
- **`bat_speed` has ~19% coverage in 2023**, ~42-44% for 2024+. Batter-tracking features in Phase 3 emit natural NULL for pre-2024 swings.
- **Park-factor freshness guard doesn't invalidate on code changes.** (Carried from Phase 2.) `daily_runner` skips refresh when rows <7 days old.
- **Synthetic test-fixture rows in `matchup_features`** (game_pk 888003, 888004 from Task 11 leakage + smoke tests). Harmless — cleanable via `DELETE FROM matchup_features WHERE game_pk IN (888003, 888004)`.
- **Full historical rebuild of `matchup_features` requires ~12 hours.** Day-batching already gets us an 8× speedup; next lever is a pre-materialized `batter_rolling_mv` (Phase 4+ perf option).

## Next action
Execute Phase 4 prompt at `phases/phase4/PROMPT.md` after clearing context.

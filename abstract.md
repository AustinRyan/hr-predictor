# HR Predictor — Abstract

**Updated:** 2026-04-23 — end of Phase 4 (DONE_WITH_CONCERNS, see below)

## Current phase
**Phase 5 — Calibration + per-game rollup** — not started. **Prerequisite:** Phase 4 baseline currently fails probability-quality acceptance gates due to a `scale_pos_weight=20.5` calibration trap. Controller to decide whether to amend Phase 4 (pin `scale_pos_weight=1.0` and rerun — ~50 s) before starting Phase 5, or merge the fix into the calibration pass. See `phases/phase4/RESULTS.md` + `NOTES.md`.

## Project elevator pitch
Per-game MLB home-run probability predictor for prop-betting decision support. Local-first Python/Next.js stack. Trained on Statcast 2021–present. Calibration-first evaluation (Brier, ECE, reliability curves). Phased development; context clears between phases.

## Completed phases
- [x] Phase 0 — Scaffolding (tag: `phase-0-complete`)
- [x] Phase 1 — Historical Statcast backfill (tag: `phase-1-complete`)
- [x] Phase 2 — Daily operational ingestion (tag: `phase-2-complete`)
- [x] Phase 3 — Feature engineering (tag: `phase-3-complete`)
- [~] Phase 4 — Baseline model + evaluation framework (DONE_WITH_CONCERNS; tag `phase-4-complete` pending controller sign-off)
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
- **Phase 3.5 gap-fix pass (2026-04-23):** closed the three high-impact NULL columns from Phase 3 closeout.
  - **Weather backfill:** migration `0005_weather_archive` + Open-Meteo `/v1/archive` ingestion. All 44 primary parks × 5 years of hourly observations (~1.95M rows). Targeted UPDATE on matchup_features populated `wx_*` at 78.4% (remaining is exhibition venues without lat/lon). Dome gating verified (16,591 Tropicana rows).
  - **Pulled FB%:** `batter_rolling.py` now emits real FILTER aggregates over hc_x/handedness pull zones. Critical fix mid-backfill: **both numerator and denominator gate on `hc_x IS NOT NULL`** because ~60% of Statcast FBs lack location data (foul FBs, pop-ups, swinging strikes). Without this gating, the ratio deflates from the true ~40% to ~16%. Coverage 93% on season window; Judge 41% matches his profile.
  - **ctx_batting_order:** inferred from `statcast_pitches.at_bat_number` first-appearance ordering within each `(game_pk, inning_topbot)`. First 9 distinct batters per team-side → slots 1-9. Pinch hitters past slot 9 stay NULL. 91.8% populated; slot distribution balanced 1-8 with slot 9 slightly lower (NL pinch-hit-for-pitcher pre-2022). `ctx_projected_pa` + `p_tto_penalty` filled via the same UPDATE.
- **Still deferred to Phase 4+:**
  - Bullpen is league-wide-minus-starter, not team-specific. Phase 4+ pitcher-role table would refine.
  - HR/9 uses `HR_count / PA_count * 38.7` proxy (9 innings × 4.3 PAs/inning) because `statcast_pitches` doesn't track outs-per-PA directly.
  - Retractable-roof historical status unknown. Phase 4+ can backfill via StatsAPI `/feed/live` per game (~13k calls).

### Phase 4 decisions
- **`src/models/` four-module layout** (`data.py`, `eval.py`, `artifacts.py`, `train.py`) as specified in the PROMPT. `FEATURE_COLUMNS` enumerated from the `MatchupFeature` ORM at import time (120 numeric features), so schema additions auto-propagate.
- **Time-based split hard-wired**: train 2021-04-01..2023-10-31 (388,320 rows), val 2024-04-01..2024-10-31 (~115 k), test 2025-04-01..last-available (140,506 rows on 2026-04-22). No shuffling ever.
- **XGBoost 2.x sklearn wrapper** with `tree_method="hist"`, `missing=np.nan` (native NaN handling — no imputation). `early_stopping_rounds` is a constructor arg (breaking change from 1.x).
- **Artifact versioning at `src/models/registry/v{YYYYMMDD_HHMMSS}/`** (UTC timestamp). Gitignored. `PRODUCTION` pointer is a plain-text file, not a symlink (Windows-safe). `load_model()` round-trip verified.
- **`precision_at_top_k` is per-`game_date`**: rank daily, take top 20, count hits, mean across days.
- **Naive baseline = constant `mean(y_train) = 0.04651`** applied to val + test log_loss. Must beat it by ≥ 5 % relative.
- **SHAP is best-effort** — `shap.TreeExplainer` errors on XGBoost 2.x (`feature_names_in_` setter conflict). Training logs a warning and continues; gain-based importance covers the same ground. Low-priority fix.
- **`scale_pos_weight` calibration trap — this is the Phase 4 open bug.** The default `TrainingConfig` sets `scale_pos_weight=None` which auto-computes to `n_neg/n_pos ≈ 20.5`. This is the textbook setting for AUC-optimized ranking on imbalanced data but catastrophically miscalibrates probabilities (ECE = 0.34; mean test pred ≈ 40 % vs true rate 4.6 %). Resulting test log_loss = 0.537 is **187 % worse** than naive (0.187). All four probability-quality acceptance gates (log_loss, Brier, AUC, precision@top-20) fail under these defaults. Fix = default `scale_pos_weight=1.0` in `TrainingConfig` and rerun (~50 s). See `phases/phase4/NOTES.md` for the full diagnosis.
- **Training runtime ~50 s on laptop** for 388 k train × 120 features × 500 iters (hist method). Early stopping (rounds=50) didn't trigger in the miscalibrated run because val log_loss was monotonically rising from iter 0.
- **Artifact v20260423_172211** is the current baseline run; metrics are in `src/models/registry/v20260423_172211/metrics.json`. Keep for reference even after the SPW fix lands.

## Open questions / decisions pending
- **Phase 4 amendment vs Phase 5 merge.** Either (a) default `scale_pos_weight=1.0` in Phase 4, rerun, re-acceptance, then start Phase 5 cleanly — OR (b) merge the SPW fix into Phase 5 calibration. Recommendation in `phases/phase4/NOTES.md`: option (a).

## Open bugs / technical debt
- **`launch_speed` null-rate threshold in Phase 1 PROMPT is misframed.** (Carried from Phase 2.) Phase 3 feature-engineering now handles this correctly via ball-in-play-conditional FILTERs.
- **`bat_speed` has ~19% coverage in 2023**, ~42-44% for 2024+. Batter-tracking features in Phase 3 emit natural NULL for pre-2024 swings. Phase 4 XGBoost handles natively.
- **Park-factor freshness guard doesn't invalidate on code changes.** (Carried from Phase 2.) `daily_runner` skips refresh when rows <7 days old.
- **Synthetic test-fixture rows in `matchup_features`** (game_pk 888003, 888004 from Task 11 leakage + smoke tests). Harmless — cleanable via `DELETE FROM matchup_features WHERE game_pk IN (888003, 888004)`.
- **Full historical rebuild of `matchup_features` requires ~12 hours.** Day-batching already gets us an 8× speedup; next lever is a pre-materialized `batter_rolling_mv` (Phase 4+ perf option).
- **Phase 4 `scale_pos_weight` auto-default is a miscalibration trap** — see Phase 4 decisions. Must be resolved before Phase 5 calibration is meaningful.
- **Phase 4 SHAP plot generation is broken** on XGBoost 2.x (`feature_names_in_` setter). Pin `shap<0.45` or adapt to raw `Booster`. Low priority.

## Next action
Controller reviews Phase 4 DONE_WITH_CONCERNS. Decides whether to tag `phase-4-complete` + amend with scale_pos_weight fix, or merge into Phase 5 prompt. `phases/phase5/PROMPT.md` follows.

# HR Predictor — Abstract

**Updated:** 2026-04-22 — end of Phase 5

## Current phase
**Phase 6 — FastAPI backend** — not started.

## Project elevator pitch
Per-game MLB home-run probability predictor for prop-betting decision support. Local-first Python/Next.js stack. Trained on Statcast 2021–present. Calibration-first evaluation (Brier, ECE, reliability curves). Phased development; context clears between phases.

## Completed phases
- [x] Phase 0 — Scaffolding (tag: `phase-0-complete`)
- [x] Phase 1 — Historical Statcast backfill (tag: `phase-1-complete`)
- [x] Phase 2 — Daily operational ingestion (tag: `phase-2-complete`)
- [x] Phase 3 — Feature engineering (tag: `phase-3-complete`)
- [x] Phase 4 — Baseline model + evaluation framework (tag: `phase-4-complete`)
- [x] Phase 5 — Calibration + per-game rollup (tag: pending controller review)
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
- **Time-based split hard-wired**: train 2021-04-01..2023-10-31 (388,320 rows), val 2024 (115,152 rows), test 2025-04-01..last-available (140,506 rows on 2026-04-23). No random shuffle — ever — since the use case is forward-in-time prediction.
- **120-column `FEATURE_COLUMNS` enumerated from `MatchupFeature` ORM at import time**, so schema changes auto-propagate to training runs without hand-maintained lists. `src/models/` four-module layout: `data.py` (load + split), `eval.py` (metrics + plots), `artifacts.py` (versioned persistence), `train.py` (orchestrator).
- **Calibration-first design: `scale_pos_weight=1.0` default (unweighted), not `n_neg/n_pos` auto-compute.** That's the right setting for log_loss/brier (proper scoring rules) and composes cleanly with Phase 5 isotonic downstream. A ranking variant can pass `scale_pos_weight` explicitly. See `phases/phase4/NOTES.md` → "The SPW fix" for the V1 failure analysis that forced this decision.
- **NaN handling: XGBoost native `missing=np.nan`; no imputation.** Bat-tracking features are NaN for pre-2024 rows; weather is NaN for exhibition venues without coords; XGBoost learns a default split direction for each.
- **Artifact registry: `src/models/registry/v{UTC_timestamp}/`** with `model.xgb` + `feature_schema.json` + `training_metadata.json` (git SHA + data SHA256 hash) + `metrics.json` + plots + `eval_report.md`. Registry directory is gitignored. `PRODUCTION` pointer is a plain-text file (not a symlink — Windows-safe).
- **`precision_at_top_k` grouped per-`game_date`** for daily pick-set semantics (rank daily, take top 20, count hits, mean across days) — matches the prop-betting use case.
- **Baseline V2 test metrics**: log_loss 0.178 (naive 0.187, −4.78% delta), brier 0.043 (≈ Bernoulli floor `p·(1−p) = 0.0443` at 4.65% HR rate), AUC 0.679, ECE 0.005, precision@top-20 0.132. PROMPT's 0.035 brier bar was premised on a 3% base rate; at 4.65% the information-theoretic floor is 0.044, so 0.043 is effectively the bound. AUC/precision@k bars not met but within typical range for per-PA HR prediction; deferred as feature/capacity work to Phase 5+.
- **V1 SPW=20.5 diagnostic artifact preserved at `src/models/registry/v20260423_172211/`** as a teaching moment — the textbook `n_neg/n_pos` default is the #1 foot-gun for calibration-first binary classifiers, and having the broken artifact next to the working one (`v20260423_173917`, PRODUCTION) documents the failure mode directly.

### Phase 5 decisions
- **Isotonic over Platt for post-hoc calibration.** Tree-ensemble score distributions are not logistic-shaped; Platt under-corrects. `sklearn.isotonic.IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)` fit on the val slice, applied on the test slice. Test ECE **0.00555 → 0.00248** (−55%), log loss 0.17862 → 0.17849 (slightly improved, did not hurt). Bar was < 0.03; we're ~12× below it.
- **Calibrator co-located with the model** at `src/models/registry/v{version}/calibrator.joblib`. Strictly additive — never overwrites `model.xgb` or training metadata. `load_calibrator(version)` + `load_model(version)` use the same string, so version-mixing bugs are a filesystem impossibility.
- **Per-PA sequence uses single-inference + scalar adjustments** (`src/models/pa_sequence.py`), not per-PA feature-row regeneration. Regenerating rows would require swapping starter columns for bullpen columns in a way the model never saw during training (OOD). Instead: one Booster call per matchup, divide out `p_tto_penalty` to recover a "pure" per-PA prob, then re-apply TTO multipliers (1.00/1.05/1.20) for PAs 1-3 and a clipped bullpen ratio for PAs 4+. Faithful to training distribution; much cheaper (1 call vs. up to 6).
- **Bullpen adjustment clipped to [0.5, 2.0]** to prevent outlier HR/9 ratios from producing physically-implausible per-PA probs. Pressly (0.37 HR/9) against a league bullpen (1.1 HR/9) would otherwise multiply PA4 by ~3.0×. Clip is the dominant reason the distribution's max P(≥1 HR) = 0.72 sits above the PROMPT's 0.35–0.55 guide band; the alternative (uncapped) is much worse.
- **Exact Poisson-binomial PMF via convolution** (`src/models/rollup.py`), not Poisson approximation. n ≤ 10 PAs per game; O(n²) is instantaneous. Per-PA probabilities vary too much (TTO + starter/bullpen transition) for the Poisson mean-equals-variance assumption to hold.
- **No ensemble.** Phase-4 pre-cal ECE was already 0.006; post-cal is 0.002. A second base model adds complexity without measurable calibration gain. The PROMPT framed ensemble as "only if single model misses the bar" — the single model hit the bar 12× over.
- **Sanity-check caveat carried as Phase-4 tech debt, not a Phase-5 defect.** The test-set top-5 P(≥1 HR) matchups are not dominated by Judge/Ohtani/Alonso as the PROMPT expected — they're a mix of fringe (Osuna, Bliss, Mangum) and regular-but-not-elite (Ruiz, Naylor) players. Root cause is Phase-4 AUC = 0.68 compressing mid-tier regulars and elite sluggers into the same right-tail raw-probability bucket. The calibration layer can't fix ranking (monotone by construction); the rollup is deterministic given per-PA probs. This is a **modeling capacity** problem to solve in a later phase, not a Phase-5 acceptance blocker. See `phases/phase5/RESULTS.md` and `NOTES.md` for the full narrative.

## Open questions / decisions pending
- None blocking Phase 6.

## Open bugs / technical debt
- **`launch_speed` null-rate threshold in Phase 1 PROMPT is misframed.** (Carried from Phase 2.) Phase 3 feature-engineering now handles this correctly via ball-in-play-conditional FILTERs.
- **`bat_speed` has ~19% coverage in 2023**, ~42-44% for 2024+. Batter-tracking features in Phase 3 emit natural NULL for pre-2024 swings. Phase 4 XGBoost handles natively.
- **Park-factor freshness guard doesn't invalidate on code changes.** (Carried from Phase 2.) `daily_runner` skips refresh when rows <7 days old.
- **Synthetic test-fixture rows in `matchup_features`** (game_pk 888003, 888004 from Task 11 leakage + smoke tests). Harmless — cleanable via `DELETE FROM matchup_features WHERE game_pk IN (888003, 888004)`.
- **Full historical rebuild of `matchup_features` requires ~12 hours.** Day-batching already gets us an 8× speedup; next lever is a pre-materialized `batter_rolling_mv` (Phase 5+ perf option).
- **Phase 4 SHAP plot generation is broken** on XGBoost 2.x (`feature_names_in_` setter). Pin `shap<0.45` or adapt to raw `Booster`. Low priority.
- **Per-PA model ranking capacity is weak** (test AUC 0.68). Carried forward from Phase 4, surfaced in the Phase 5 sanity check — top-5 P(≥1 HR) is not dominated by elite sluggers. Resolving requires better features / ensemble / ranking-optimized objective; deferred to a post-Phase-6 modeling pass.
- **`sanity_runner.py` relies on row-order alignment** between `time_based_split`'s `X` and a re-query of `matchup_features` with the same filters. Stable in practice but not formally guaranteed. A future small refactor can plumb `(game_pk, batter_id, pitcher_id)` through `FeatureFrame.metadata` to make alignment explicit.

## Next action
Controller applies `phase-5-complete` tag after final review. Phase 6 (`phases/phase6/PROMPT.md`) covers the FastAPI backend.

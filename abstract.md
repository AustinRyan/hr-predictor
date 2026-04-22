# HR Predictor — Abstract

**Updated:** 2026-04-22 — end of Phase 1

## Current phase
**Phase 2 — Daily operational ingestion** — not started.

## Project elevator pitch
Per-game MLB home-run probability predictor for prop-betting decision support. Local-first Python/Next.js stack. Trained on Statcast 2021–present. Calibration-first evaluation (Brier, ECE, reliability curves). Phased development; context clears between phases.

## Completed phases
- [x] Phase 0 — Scaffolding (tag: `phase-0-complete`)
- [x] Phase 1 — Historical Statcast backfill (tag: `phase-1-complete`)
- [ ] Phase 2 — Daily operational ingestion
- [ ] Phase 3 — Feature engineering
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

## Open questions / decisions pending
- None blocking Phase 2.

## Open bugs / technical debt
- **`launch_speed` null-rate threshold in the Phase 1 PROMPT is misframed.** ~67% of pitches are non-ball-in-play (balls, strikes, fouls) — so `launch_speed` is legitimately null for most rows. The "under 15%" acceptance threshold in PROMPT.md only makes sense for always-populated columns like `pitch_type`. Flagged in `phases/phase1/NOTES.md`; Phase 3 feature-engineering layer will compute ball-in-play-conditional null rates.
- **`bat_speed` has ~19% coverage in 2023** (not "all null for pre-2024" as PROMPT.md expected). Statcast's bat-tracking rollout started mid-2023. 2024+ coverage is ~42-44%, aligned with the prompt's spirit.
- **Pre-commit hooks pin ruff 0.5.0 / black 24.4.2** while the `uv` env ships newer versions, causing an occasional stash-rollback loop during commits. Workaround: `uv run pre-commit run --all-files` before staging. Cheap fix is bumping the hook pins in an early Phase 2 chore commit.

## Migration numbering for Phase 2
The Phase 2 PROMPT.md references migration `0002_operational_tables`, but Phase 1 already used `0002_drop_games_team_fks`. Phase 2 should start at `0003_operational_tables`.

## Next action
Execute Phase 2 prompt at `phases/phase2/PROMPT.md` after clearing context.

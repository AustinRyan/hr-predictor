# HR Predictor — Abstract

**Updated:** 2026-04-22 — end of Phase 0

## Current phase
**Phase 1 — Historical Statcast backfill** — not started.

## Project elevator pitch
Per-game MLB home-run probability predictor for prop-betting decision support. Local-first Python/Next.js stack. Trained on Statcast 2021–present. Calibration-first evaluation (Brier, ECE, reliability curves). Phased development; context clears between phases.

## Completed phases
- [x] Phase 0 — Scaffolding (tag: `phase-0-complete`)
- [ ] Phase 1 — Historical Statcast backfill
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

## Open questions / decisions pending
- None yet. Add as they arise.

## Open bugs / technical debt
- None yet.

## Next action
Execute Phase 1 prompt at `phases/phase1/PROMPT.md` after clearing context.

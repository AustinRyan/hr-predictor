# HR Predictor

A per-game MLB home-run probability predictor for prop-betting decision support. Local-first stack: Python ML backend (XGBoost on Statcast 2021–present), Postgres + Redis, FastAPI, Next.js. Calibration-first evaluation (Brier, ECE, reliability curves).

## Quickstart

Prerequisites: Docker + Docker Compose, [`uv`](https://docs.astral.sh/uv/), Python 3.12 (uv will fetch it).

```bash
# 1. Bring up Postgres + Redis
docker-compose up -d

# 2. Install Python deps (creates .venv automatically)
uv sync

# 3. Copy env template
cp .env.example .env

# 4. Run tests (requires docker services up)
uv run pytest -q
```

## Project layout

```
src/
  core/        # config, DB session, Redis client, logging
  ingestion/   # data pulls (Statcast, MLB StatsAPI, weather, parks)
  features/    # feature engineering
  models/      # training, calibration, evaluation
  api/         # FastAPI service
  agents/      # optional LangGraph explainer
phases/        # one folder per phase: PROMPT, ACCEPTANCE, NOTES
tests/
```

## Development workflow

This project follows a phase-driven workflow. See:

- [`MASTER_PLAN.md`](./MASTER_PLAN.md) — full 8-phase roadmap
- [`abstract.md`](./abstract.md) — current phase + key decisions
- [`CLAUDE.md`](./CLAUDE.md) — project conventions and non-negotiables
- [`phases/phaseN/`](./phases/) — per-phase prompt, acceptance checklist, notes

Every phase ends with two gates: automated (`pytest`, `ruff`) and manual (per-phase `ACCEPTANCE.md`). Tag with `phase-N-complete` after both pass.

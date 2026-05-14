# HR Predictor

HR Predictor is a local-first MLB home-run probability system for prop-betting
research and decision support. It ingests public baseball data, builds
matchup-level features, trains calibrated machine-learning models, writes daily
predictions to Postgres, and serves a Next.js leaderboard focused on probability,
market edge, and explainability.

This is not betting advice. The project is a research tool for evaluating model
probabilities against sportsbook prices.

## What It Does

- Ingests MLB schedule, probable starters, projected lineups, weather, park
  factors, Statcast pitch data, and optional sportsbook odds.
- Builds leakage-safe batter, pitcher, context, weather, park, and opponent
  bullpen features.
- Trains XGBoost/LightGBM models with time-based splits and calibration-focused
  evaluation.
- Generates per-game `P(at least one HR)` predictions for each batter on a slate.
- Stores predictions, SHAP-style feature contributions, model metadata, and
  sportsbook edge context in Postgres.
- Serves a Next.js app with a ranked leaderboard, matchup pages, player pages,
  model metrics, odds edge, and shareable visuals.

## How It Works

```text
Public data sources
  -> ingestion loaders
  -> Postgres operational tables
  -> matchup feature builder
  -> calibrated model inference
  -> predictions table
  -> Next.js leaderboard and detail pages
```

The current modeling direction is full-game home-run probability. The latest
local model adds opponent bullpen quality features such as relief HR rate,
barrel rate allowed, hard-hit rate allowed, handedness splits, and recent bullpen
usage. Model artifacts are intentionally not committed to git.

## Stack

- Python 3.12 managed by `uv`
- Postgres 16 and Redis 7 through Docker Compose
- SQLAlchemy 2.x, Alembic, Pydantic v2, FastAPI
- pybaseball, MLB StatsAPI, Open-Meteo, requests-cache
- XGBoost, LightGBM, scikit-learn, SHAP
- Next.js 16, React 19, Tailwind CSS 4
- pytest, pytest-cov, pytest-asyncio, vcrpy, ruff

## Repository Layout

```text
src/
  core/        config, database sessions, Redis, logging
  ingestion/   Statcast, MLB StatsAPI, weather, park factors, sportsbook odds
  features/    matchup feature engineering and historical backfills
  models/      training, calibration, evaluation, inference, artifacts
  api/         FastAPI service and response schemas
  agents/      reserved for the optional analyst/explanation layer
ui/
  app/         Next.js routes
  components/  leaderboard, landing, model, ticket, and matchup UI
  lib/         direct Postgres queries and API adapters
scripts/       daily refresh and operational helpers
migrations/    Alembic migrations
phases/        phase plans, acceptance notes, and project history
tests/         backend and data-pipeline tests
```

## Prerequisites

- Docker and Docker Compose
- Python 3.12, installed automatically by `uv` if needed
- `uv`
- Node.js 20+
- npm

## Backend Setup

```bash
# 1. Start Postgres and Redis
docker-compose up -d

# 2. Install Python dependencies
uv sync

# 3. Create local environment config
cp .env.example .env

# 4. Apply database migrations
uv run alembic upgrade head

# 5. Run backend tests
uv run pytest -q
```

The default `.env.example` points at the local Docker database. For a hosted
database, replace `DATABASE_URL` with your own connection string. Do not commit
real database URLs or API keys.

## Frontend Setup

```bash
cd ui
npm install
npm run dev
```

The frontend reads from Postgres through `DATABASE_URL`. For local development,
use the same database as the backend. For Vercel, set `DATABASE_URL` as an
environment variable in the Vercel dashboard and set the project root to `ui`.

## Daily Prediction Refresh

After the database is configured and a local model artifact exists:

```bash
./scripts/refresh-picks.sh
```

That script runs the daily pipeline:

1. Ingest schedule, lineups, weather, and Statcast.
2. Fill proxy lineups when official lineups are missing.
3. Build matchup features for the target slate.
4. Run model inference and write predictions.
5. Fetch sportsbook odds. The Odds API is primary when
   `THE_ODDS_API_KEY` is configured; PropLine remains a fallback when
   `PROP_LINE_API_KEY` is configured and the primary source returns zero rows.

If neither sportsbook key is set, the odds step is skipped and predictions
still run.

## Model Artifacts

Model artifacts live under `src/models/registry/` and are ignored by git:

```text
src/models/registry/
  vYYYYMMDD_HHMMSS/
    model.xgb
    calibrator.joblib
    feature_schema.json
    metrics.json
    training_metadata.json
  PRODUCTION
```

To run inference on a fresh clone, train or copy a model artifact locally and
point `src/models/registry/PRODUCTION` at the chosen version. The production
pointer and artifact directories should stay out of git because they can be
large and environment-specific.

## Useful Commands

```bash
# Backend quality checks
uv run pytest -q
uv run ruff check .

# Frontend checks
cd ui
npm run test:ranking-sort
npm run lint
npm run build

# Run FastAPI locally
uv run uvicorn src.api.main:app --reload --port 8765

# Run Next.js locally
cd ui && npm run dev
```

## Environment Variables

Root `.env`:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
THE_ODDS_API_KEY=
THE_ODDS_API_BASE_URL=https://api.the-odds-api.com/v4
THE_ODDS_API_REGIONS=us
PROP_LINE_API_KEY=
PROP_LINE_BASE_URL=https://api.prop-line.com/v1
```

Frontend/Vercel:

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DB?sslmode=require
NEXT_PUBLIC_ALLOW_REFRESH=false
```

Sportsbook API keys are optional and should only be stored in local or
deployment environment variables.

## Security Notes

- Real `.env` files are ignored.
- Model registry artifacts are ignored.
- Local cache, report, and backfill output directories are ignored.
- Do not commit sportsbook keys, database URLs, generated model artifacts, or
  exported data dumps.
- If a secret is ever committed, rotate the credential and rewrite history
  before making the repository public.

## Project Docs

- `abstract.md` tracks current project state and key decisions.
- `MASTER_PLAN.md` contains the original phased roadmap.
- `AGENTS.md` defines project conventions for future coding agents.
- `phases/` contains implementation plans, acceptance criteria, and notes.

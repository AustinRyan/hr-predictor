# PropLine Odds Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist MLB batter home-run sportsbook odds snapshots, compute real model-vs-market edge, and expose that edge in picks.

**Architecture:** Add a focused PropLine ingestion layer under `src/ingestion`, a normalized `odds_snapshots` table, and reusable odds math helpers. API and Next picks queries left-join the latest snapshot per `(game_date, player, market)` so the UI can display real edge while staying fast and resilient when odds are missing.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy 2.x, Alembic, FastAPI, Next.js TypeScript.

---

### Task 1: Odds Math

**Files:**
- Create: `src/models/odds.py`
- Test: `tests/models/test_odds.py`

- [ ] Write tests for American-odds implied probability and expected value.
- [ ] Verify tests fail because `src.models.odds` does not exist.
- [ ] Implement `american_to_implied_probability`, `probability_to_fair_american`, `edge_probability`, and `expected_value_per_unit`.
- [ ] Run `uv run pytest -q tests/models/test_odds.py`.

### Task 2: Persistence Schema

**Files:**
- Create: `migrations/versions/0007_odds_snapshots.py`
- Modify: `src/core/models.py`
- Test: `tests/core/test_odds_schema.py`

- [ ] Write schema tests asserting `odds_snapshots` columns, unique snapshot key, and indexes.
- [ ] Verify tests fail before migration/model exists.
- [ ] Add the Alembic migration and `OddsSnapshot` ORM model.
- [ ] Run `uv run pytest -q tests/core/test_odds_schema.py`.

### Task 3: PropLine Client And Ingestion

**Files:**
- Modify: `src/core/config.py`
- Modify: `.env.example`
- Create: `src/ingestion/prop_line_client.py`
- Create: `src/ingestion/prop_line_odds.py`
- Test: `tests/ingestion/test_prop_line_client.py`
- Test: `tests/ingestion/test_prop_line_odds.py`

- [ ] Write client parsing tests using representative PropLine/The-Odds-API-style JSON.
- [ ] Write ingestion tests proving idempotent upsert and player-name matching to `players.full_name`.
- [ ] Verify tests fail before client/ingestion code exists.
- [ ] Implement settings, typed client models, odds normalization, and snapshot upsert.
- [ ] Run `uv run pytest -q tests/ingestion/test_prop_line_client.py tests/ingestion/test_prop_line_odds.py`.

### Task 4: API And Frontend Edge Fields

**Files:**
- Modify: `src/api/schemas/picks.py`
- Modify: `src/api/routers/picks.py`
- Modify: `ui/lib/types.ts`
- Modify: `ui/lib/queries/picks.ts`
- Modify: `ui/lib/adapters.ts`
- Test: `tests/api/test_picks.py`

- [ ] Extend pick tests so a seeded odds snapshot returns sportsbook, odds, implied probability, edge, and EV.
- [ ] Verify tests fail before API fields exist.
- [ ] Add latest-odds left join and response fields to FastAPI and Next SQL.
- [ ] Switch UI adapter from cosmetic lift to real edge when present.
- [ ] Run `uv run pytest -q tests/api/test_picks.py`.

### Task 5: Refresh Flow And Verification

**Files:**
- Modify: `src/api/routers/admin.py`
- Modify: `src/ingestion/overview.md`
- Modify: `src/api/overview.md`
- Modify: `src/models/overview.md`
- Modify: `ui/overview.md`
- Modify: `abstract.md`

- [ ] Call odds ingestion after prediction generation in the admin refresh path when an API key is configured.
- [ ] Update touched overviews and abstract with the odds-layer decision.
- [ ] Run targeted Python tests for odds, ingestion, API, and migrations.
- [ ] Run `npm run lint` and `npm run build` in `ui/`.

# Phase 0 — Project Scaffolding

## Required reading before you start
1. `./CLAUDE.md` — project conventions and non-negotiables
2. `./MASTER_PLAN.md` — complete 8-phase roadmap
3. `./abstract.md` — current project state

**Read all three in full before writing any code.** If any conflict with instructions in this prompt, flag the conflict and stop; do not resolve it silently.

---

## Objective
Take the repo from "three markdown files at root" to "working local dev environment where `docker-compose up -d && pytest` succeeds, all infrastructure is healthy, and the directory skeleton is in place for Phases 1–8."

**You are implementing Phase 0 only.** Do not write ingestion code, feature code, model code, or anything beyond scaffolding. When Phase 0 is complete, stop and report — do not start Phase 1.

---

## Stack requirements (pinned)
- Python **3.12**
- Dependency manager: **uv** (not pip, not poetry, not conda)
- **Postgres 16** via docker-compose
- **Redis 7** via docker-compose
- Layout: **src-layout** (code under `src/`, not flat)
- Linting: **ruff** + **black** via pre-commit
- Testing: **pytest** + **pytest-cov** + **pytest-asyncio**

---

## Deliverables

### 1. Root-level files

- `pyproject.toml` — Python project config with the following dependency groups:
  - **Runtime deps:** `sqlalchemy>=2.0,<3`, `alembic>=1.13`, `psycopg[binary]>=3.2`, `redis>=5.0`, `pydantic>=2.5,<3`, `pydantic-settings>=2.0`, `fastapi>=0.110`, `uvicorn[standard]>=0.29`, `httpx>=0.27`, `requests-cache>=1.2`, `pybaseball>=2.2`, `MLB-StatsAPI>=1.7`, `pandas>=2.2`, `numpy>=1.26,<2`, `xgboost>=2.0`, `lightgbm>=4.0`, `scikit-learn>=1.4`, `shap>=0.44`, `apscheduler>=3.10`, `python-dotenv>=1.0`
  - **Dev deps:** `pytest>=8.0`, `pytest-cov>=4.1`, `pytest-asyncio>=0.23`, `vcrpy>=6.0`, `ruff>=0.4`, `black>=24.0`, `pre-commit>=3.6`, `ipython>=8.0`
  - Configure `[tool.ruff]` with sensible defaults (line length 100, common rule sets E/F/I/N/UP)
  - Configure `[tool.black]` with line length 100
  - Configure `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`, `testpaths = ["tests"]`, coverage on `src/`

- `docker-compose.yml` — two services:
  - `postgres` (image: `postgres:16-alpine`, env: `POSTGRES_USER=hrp`, `POSTGRES_PASSWORD=hrp`, `POSTGRES_DB=hrp`, port `5432:5432`, named volume `pg_data`, healthcheck using `pg_isready`)
  - `redis` (image: `redis:7-alpine`, port `6379:6379`, named volume `redis_data`, healthcheck using `redis-cli ping`)

- `.env.example` with:
  ```
  DATABASE_URL=postgresql+psycopg://hrp:hrp@localhost:5432/hrp
  REDIS_URL=redis://localhost:6379/0
  LOG_LEVEL=INFO
  ```

- `.gitignore` — Python, IDE (.vscode, .idea), env files, `.venv/`, `*.db`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`, `htmlcov/`, `models/artifacts/`, `data/cache/`, OS junk (`.DS_Store`, `Thumbs.db`), Node (`node_modules/`, `.next/`) for the future UI

- `.pre-commit-config.yaml` — ruff (with `--fix`) and black hooks, plus standard `check-yaml`, `end-of-file-fixer`, `trailing-whitespace`

- `README.md` — short: project purpose (1 paragraph), quickstart (`docker-compose up -d`, `uv sync`, `pytest`), link to MASTER_PLAN.md for details

### 2. Directory skeleton under `src/`

Create these directories, each with an `__init__.py` and an `overview.md` stub:
- `src/core/` — config, DB session, Redis client, logging setup
- `src/ingestion/` — Phase 1+2 territory
- `src/features/` — Phase 3 territory
- `src/models/` — Phase 4+5 territory
- `src/api/` — Phase 6 territory
- `src/agents/` — Phase 8 territory (optional phase)

Each `overview.md` stub should follow this template:
```markdown
# <module name>

## Purpose
TBD — populated during Phase N.

## Entry points
TBD.

## Public interface
TBD.

## Internal dependencies
TBD.

## Gotchas
None yet.
```

### 3. Working Phase 0 code in `src/core/`

- `src/core/config.py` — Pydantic Settings class reading from `.env`. Fields: `database_url: str`, `redis_url: str`, `log_level: str = "INFO"`. Use `pydantic_settings.BaseSettings`.
- `src/core/db.py` — SQLAlchemy engine + sessionmaker factory. Export `get_engine()` and `get_session()` (context manager).
- `src/core/redis_client.py` — Redis client factory. Export `get_redis()`.
- `src/core/logging_config.py` — one-function logger setup (JSON-friendly formatter, level from settings).

### 4. Tests in `tests/`

- `tests/conftest.py` — fixtures for DB engine and Redis client
- `tests/test_infra.py` — **integration tests, not mocks**. Must:
  - Connect to Postgres via `get_engine()`, execute `SELECT 1`, assert result
  - Connect to Redis via `get_redis()`, `SET`/`GET` a test key, assert roundtrip
  - Verify `Settings` loads from `.env`

These tests require `docker-compose up -d` to be running. That's intentional and correct for this project per CLAUDE.md ("Never mock data sources in ingestion tests").

### 5. Phase 0 docs

- `phases/phase0/PROMPT.md` — copy of this file (so it's preserved in git history)
- `phases/phase0/ACCEPTANCE.md` — the manual test checklist (template below, you'll fill in any phase-specific items you discover)
- `phases/phase0/NOTES.md` — empty scaffold: `# Phase 0 Notes\n\n(Add implementation discoveries here.)\n`

### 6. Git initialization

- `git init` if not already initialized
- Commit all of the above in logical chunks using Conventional Commits:
  - `chore: initial project scaffolding`
  - `chore(infra): docker-compose for postgres and redis`
  - `chore(deps): pin dependencies via pyproject.toml`
  - `feat(core): config, db session, redis client, logging`
  - `test(core): infra connectivity integration tests`
  - `docs: phase 0 scaffolding complete`
- After final commit: `git tag phase-0-complete`

---

## Acceptance checklist (write this into `phases/phase0/ACCEPTANCE.md` as part of this phase)

```markdown
# Phase 0 — Acceptance Checklist

Run each command and check the box when the expected result is observed.

## Infrastructure
- [ ] `docker-compose up -d` brings up both services without error
- [ ] `docker-compose ps` shows both services as `healthy`
- [ ] `psql postgresql://hrp:hrp@localhost:5432/hrp -c 'SELECT 1'` returns `1`
- [ ] `redis-cli -u redis://localhost:6379/0 PING` returns `PONG`

## Python environment
- [ ] `uv sync` installs all dependencies with no errors
- [ ] `uv run python -c "import xgboost, pybaseball, fastapi, sqlalchemy"` runs with no errors
- [ ] Python version is 3.12.x (`uv run python --version`)

## Code quality
- [ ] `uv run ruff check .` passes clean
- [ ] `uv run black --check .` passes clean
- [ ] `uv run pre-commit run --all-files` passes clean

## Tests
- [ ] `uv run pytest -q` passes all tests
- [ ] Coverage report shows ≥80% on `src/core/`

## Project structure
- [ ] `CLAUDE.md`, `MASTER_PLAN.md`, `abstract.md` exist at project root
- [ ] `src/` contains subdirectories: `core`, `ingestion`, `features`, `models`, `api`, `agents`
- [ ] Each subdirectory has an `overview.md` stub and `__init__.py`
- [ ] `phases/phase0/` contains `PROMPT.md`, `ACCEPTANCE.md`, `NOTES.md`

## Git
- [ ] `git log --oneline` shows Conventional Commits for Phase 0
- [ ] `git tag` shows `phase-0-complete`
- [ ] `abstract.md` has been updated to mark Phase 0 complete and point to Phase 1
```

---

## Non-negotiables (from CLAUDE.md — re-read if unsure)

- **No hallucinated dependencies.** If you're unsure whether a package exists at the pinned version, check PyPI or ask. Do not guess.
- **Idempotent git init.** Check for existing `.git/` before running `git init`.
- **Do not start writing code for Phase 1.** Phase 0 is scaffolding only. The `ingestion/` directory gets `__init__.py` and `overview.md` stub — nothing else.
- **Type everything.** Every function signature in `src/core/` has full type hints.
- **Tests must hit real infrastructure.** Do not mock Postgres or Redis in `tests/test_infra.py`. If the docker services aren't up, the tests should fail with a clear error message telling the user to run `docker-compose up -d`.
- **Read files in full before editing.** Partial reads produce broken edits.

---

## Post-phase ritual (execute before reporting done)

1. Run `uv run pytest -q` → green
2. Run `uv run ruff check .` → clean
3. Walk through every item in `phases/phase0/ACCEPTANCE.md` → all boxes checked
4. Update `abstract.md`: mark Phase 0 complete, set current phase to "Phase 1 — Historical Statcast backfill — not started"
5. Update `src/core/overview.md` with real content (remove TBDs for this module only)
6. Final commit: `docs: phase 0 complete`
7. `git tag phase-0-complete`

---

## STOP condition

Once the post-phase ritual is complete, **stop**. Do not read the Phase 1 prompt, do not start Phase 1 work, do not speculatively create ingestion files. Report back with:

1. Confirmation that all acceptance-checklist items passed
2. The exact test output from `pytest -q`
3. Any deviations from this prompt, with one-line rationale each
4. Any `NOTES.md` entries you'd recommend for future phases (e.g., "Postgres 16 psycopg3 requires binary extra on macOS; documented in `phases/phase0/NOTES.md`")

**Do not proceed to Phase 1 without explicit user approval.**

# Phase 0 — Acceptance Checklist

Run each command and check the box when the expected result is observed.

## Infrastructure
- [x] `docker-compose up -d` brings up both services without error
- [x] `docker-compose ps` shows both services as `healthy`
- [x] `psql postgresql://hrp:hrp@localhost:5432/hrp -c 'SELECT 1'` returns `1` (verified via `docker exec hrp-postgres psql -U hrp -d hrp -c 'SELECT 1'`; equivalent host-side command also works if `psql` is installed)
- [x] `redis-cli -u redis://localhost:6379/0 PING` returns `PONG` (verified via `docker exec hrp-redis redis-cli PING`)

## Python environment
- [x] `uv sync` installs all dependencies with no errors
- [x] `uv run python -c "import xgboost, pybaseball, fastapi, sqlalchemy"` runs with no errors
- [x] Python version is 3.12.x (`uv run python --version` → `Python 3.12.12`)

## Code quality
- [x] `uv run ruff check .` passes clean
- [x] `uv run black --check .` passes clean
- [x] `uv run pre-commit run --all-files` passes clean

## Tests
- [x] `uv run pytest -q` passes all tests (8 passed)
- [x] Coverage report shows ≥80% on `src/core/` (100% achieved)

## Project structure
- [x] `CLAUDE.md`, `MASTER_PLAN.md`, `abstract.md` exist at project root
- [x] `src/` contains subdirectories: `core`, `ingestion`, `features`, `models`, `api`, `agents`
- [x] Each subdirectory has an `overview.md` stub and `__init__.py`
- [x] `phases/phase0/` contains `PROMPT.md`, `ACCEPTANCE.md`, `NOTES.md`

## Git
- [x] `git log --oneline` shows Conventional Commits for Phase 0
- [x] `git tag` shows `phase-0-complete`
- [x] `abstract.md` has been updated to mark Phase 0 complete and point to Phase 1

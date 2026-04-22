# HR Predictor — Project Conventions

**Read this file at the start of every Claude Code session.** It is the difference between a project that stays clean across many phases and one that becomes unmaintainable.

---

## Project purpose
A per-game MLB home-run probability predictor for prop-betting decision support. Local-first dev. Python ML backend, Next.js frontend, Postgres + Redis.

## Stack (pinned — do not substitute without updating this file)
- **Python 3.12** with `uv` for dependency management
- **Postgres 16** (docker-compose)
- **Redis 7** (docker-compose)
- **FastAPI** + **Pydantic v2**
- **SQLAlchemy 2.x** + **Alembic** migrations
- **XGBoost**, **LightGBM**, **scikit-learn**
- **pybaseball**, **MLB-StatsAPI**, **requests-cache**
- **Next.js 15** (App Router) + **Tailwind** + **shadcn/ui**
- **pytest** + **pytest-cov** + **pytest-asyncio** + **vcrpy** (for ingestion tests)

---

## Required reading order for every new session

1. `./abstract.md` at project root — current state, active phase, key decisions
2. `overview.md` of every directory you will touch (if one exists)
3. This file (`CLAUDE.md`)
4. Skim existing similar code in the target module before writing new code

**If any of 1–3 is missing for a directory you're working in, creating it is part of your current task.**

---

## Context management: `abstract.md` and `overview.md`

### `abstract.md` (project root, one file)
The living state-of-the-project doc. Updated at every phase boundary. Contains:
- Current phase and what's in progress
- Completed phases (checklist)
- Key technical decisions with one-line rationale
- Open questions or blockers
- Links to phase-specific docs under `phases/`

Do not bloat this beyond one page. Terse is better.

### `overview.md` (one per major directory)
What lives in this directory and why. Contains:
- One-paragraph purpose
- Entry points (which file does what)
- Public interface (what other modules import from here)
- Internal dependencies (what this module needs)
- Gotchas / non-obvious behavior

Update whenever non-trivial changes land in the directory.

**Do not duplicate `abstract.md` content.** `abstract.md` = project state; `overview.md` = module structure.

---

## Non-negotiable rules

- **Never skip a test to make CI green.** Fix the code or fix the test. Skipping hides regressions.
- **Never mock data sources in ingestion tests.** Use VCR cassettes or a seeded local Postgres fixture.
- **Idempotency is mandatory for all ingestion.** Running any loader twice must produce identical DB state.
- **No raw dicts from external APIs.** Every API response goes through a Pydantic model before touching anything else.
- **No SQL string concatenation.** Use SQLAlchemy constructs or `.sql` files loaded at import time.
- **Type everything.** All function signatures and class attributes. Not for mypy strictness — for the next Claude who reads this.
- **Do not invent APIs.** Before calling a `pybaseball` function, grep the installed source or check the docs. Hallucinated function calls are the #1 failure mode.
- **Before adding a dependency, read `pyproject.toml`.** If a lib already handles the need, use it.
- **Before writing a new pattern, grep for 3+ uses of a similar pattern.** If found, follow it rather than invent.
- **Never commit secrets.** `.env.example` only; real `.env` is gitignored.
- **Never edit across phase boundaries.** If you're in Phase 3, do not touch Phase 2 code unless fixing a bug discovered by Phase 3 tests — and log that in `abstract.md`.

---

## Per-phase quality gates

Every phase ends with two gates before context-clear:

### Gate 1 — Automated
- `pytest -q` passes with **≥80% coverage on new code**.
- Integration tests run against a real docker-compose Postgres (not a mock).
- Any linting (`ruff check`) is clean.

### Gate 2 — Manual
- Walk through `phases/phaseN/ACCEPTANCE.md` checklist item by item.
- Each item is a concrete, verifiable command or spot-check (e.g., "Query `SELECT COUNT(*) FROM statcast_pitches WHERE game_date = '2024-10-30';` returns 300 ± 10 rows").
- Every item passes, or the phase is not done.

**Failing either gate means the phase is not done. Do not start the next phase prompt.**

---

## Commit discipline

- **Conventional Commits:** `feat:`, `fix:`, `chore:`, `test:`, `docs:`, `refactor:`
- **Scope by directory when possible:** `feat(ingestion): add idempotent Statcast loader`
- **One logical change per commit.** No "misc fixes" dumps.
- **At phase completion:** `git tag phase-N-complete` after the final commit.

---

## Post-phase ritual (do this every time before clearing context)

1. `pytest -q` → green
2. `ruff check .` → clean
3. Manual acceptance checklist in `phases/phaseN/ACCEPTANCE.md` → all green
4. Update `abstract.md` at project root: mark phase complete, point to next phase, log any mid-phase decisions
5. Update `overview.md` in every directory touched
6. Commit with Conventional format, then `git tag phase-N-complete`
7. Safe to clear context now

---

## Claude Code working tips (what actually helps in practice)

- **Read files in full before editing them.** Partial reads produce edits that break surrounding code.
- **Plan before executing** for anything non-trivial. Drop a 3–5 bullet plan in a comment or scratch file before writing the diff. Makes reviews faster and catches wrong assumptions early.
- **Log liberally in ingestion scripts.** `logger.info` with row counts, date ranges, error objects. Data pipelines fail silently otherwise.
- **Run tests after every logical change**, not just at the end. Catches breakage while context is fresh.
- **When stuck, instrument rather than guess.** Print shapes, dtypes, first 3 rows. Guessing wastes more tokens than inspecting.
- **Prefer the simpler of two equally-good approaches.** You can always refactor later; you can't un-overengineer.
- **If you find yourself writing the same code twice, stop and extract a helper.** Third occurrence is too late.
- **Never leave silent TODOs.** If it's worth noting, it's worth an entry in `abstract.md` under "open items."

---

## Data-source-specific notes

- **pybaseball** hits Baseball Savant with a 30,000-row-per-query limit. Always chunk by day or smaller. Large requests parallelize automatically but can hit rate limits; use `requests-cache` to avoid re-fetching during development.
- **MLB-StatsAPI** has no auth but rate-limits aggressively. Use exponential backoff on 429s. Cache schedule/lineup calls for 5 minutes minimum.
- **Open-Meteo** is free and unauthenticated. Cache responses for 1 hour. Free tier has no hard rate limit but be polite.
- **Baseball Savant leaderboards** (park factors, xStats, bat tracking) sometimes require HTML scraping. Prefer `pybaseball` wrappers when available; do not roll your own scraper unless documented otherwise.
- **Statcast data is mutable**: Baseball Savant occasionally backfills/corrects prior games. Re-pulling the last 7 days during incremental updates is cheap insurance.

---

## When in doubt
Ask the user. A 30-second clarification beats a 30-minute wrong build.

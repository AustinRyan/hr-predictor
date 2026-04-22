# HR Predictor — Master Plan

The complete 8-phase roadmap. Kept in the project root so future Claude Code sessions can always re-orient.

**Per-phase detail docs live under `phases/phaseN/`** and include:
- `PROMPT.md` — the Claude Code prompt used to execute the phase
- `ACCEPTANCE.md` — manual test checklist
- `NOTES.md` — anything discovered during implementation worth preserving

---

## Core design decisions (locked unless `abstract.md` says otherwise)

| Decision | Choice | Rationale |
|---|---|---|
| Prediction target | Per-PA HR probability, rolled up to per-game | Prop-bet markets are per-game; per-PA is the natural modeling unit |
| Training window | Statcast 2021–present | Post-juiced-ball, post-sticky-stuff-enforcement; modern-relevant |
| Primary model | XGBoost binary classifier | Calibratable, interpretable, dominant in literature |
| Calibration | Isotonic regression on time-based holdout | Better than Platt for tree models |
| Evaluation split | Train 2021–2023, validate 2024, test 2025+ | Time-based only; no random splits |
| Primary metrics | Log loss, Brier score, ECE, reliability curves | Calibration-first because bets pay on probability |
| Market odds integration | Phase 8+ (later) | Get standalone model calibrated first |
| Deployment | Local dev (docker-compose) for now | Fastest iteration path |
| Language | Python for all data/ML; TS for UI | Pybaseball ecosystem is Python-native |

---

## Phase 0 — Project scaffolding

**Goal:** Empty repo → working dev environment where `docker-compose up && pytest` succeeds.

**Deliverables:**
- `CLAUDE.md` (already written — drop in)
- `MASTER_PLAN.md` (this file)
- `abstract.md` seeded with Phase 0 in progress
- `pyproject.toml` with pinned deps (Python 3.12, uv)
- `docker-compose.yml` (Postgres 16, Redis 7, named volumes, healthchecks)
- `.env.example` + `.gitignore`
- `src/` directory structure with `overview.md` placeholders
- `tests/` with a single passing placeholder test
- Pre-commit hooks (ruff, black)
- GitHub repo init + first commit

**Acceptance checklist (`phases/phase0/ACCEPTANCE.md`):**
- [ ] `docker-compose up -d` brings up Postgres + Redis without errors
- [ ] `psql postgresql://hrp:hrp@localhost:5432/hrp -c 'SELECT 1'` succeeds
- [ ] `redis-cli ping` returns PONG
- [ ] `uv sync` installs all dependencies without error
- [ ] `pytest -q` passes (placeholder test)
- [ ] `ruff check .` passes clean
- [ ] CLAUDE.md, MASTER_PLAN.md, abstract.md exist at project root
- [ ] Every top-level `src/` subdirectory has an `overview.md` stub

---

## Phase 1 — Historical Statcast backfill

**Goal:** Statcast 2021–present loaded into Postgres, resumable, idempotent, with data-quality audits.

**Deliverables:**
- DB schema via Alembic migrations:
  - `statcast_pitches` (partitioned by year)
  - `games`, `players`, `parks`, `teams`
- `src/ingestion/statcast_backfill.py` — resumable loader using `pybaseball.statcast()`, chunked by day, with `requests-cache`
- Data-quality audit script: row counts per day, null-rate report, foreign-key integrity, compare to Savant totals
- `src/ingestion/overview.md`
- Tests: VCR cassettes for pybaseball calls; integration test against seeded Postgres

**Acceptance checklist:**
- [ ] Total row count matches pybaseball's per-season totals within 1%
- [ ] Spot check: `SELECT launch_speed, launch_angle, events FROM statcast_pitches WHERE game_pk = <Judge's 62nd HR game>` returns correct known values
- [ ] Re-running the backfill produces zero new rows (idempotency proven)
- [ ] Audit report generated showing null rates, row counts, and anomalies
- [ ] All integration tests pass against docker-compose Postgres

---

## Phase 2 — Daily operational ingestion

**Goal:** One command fetches today's data end-to-end: schedule, lineups, probables, weather, yesterday's Statcast.

**Deliverables:**
- `src/ingestion/mlb_statsapi.py` — schedule, probable pitchers, projected + confirmed lineups
- `src/ingestion/weather.py` — Open-Meteo per park (lat/lon lookup table)
- `src/ingestion/park_factors.py` — Baseball Savant scraper for handedness-split component park factors
- `src/ingestion/roof_status.py` — detect closed/open for retractable parks (MLB StatsAPI exposes this in game status)
- `src/ingestion/daily_runner.py` — orchestrates all of the above
- APScheduler config (or cron script) for daily 7 AM ET pull + pre-game 1-hour-before refresh

**Acceptance checklist:**
- [ ] `python -m ingestion.daily_runner` populates: `daily_schedule`, `projected_lineups`, `weather_forecasts`, `park_factors`, and appends yesterday's pitches to `statcast_pitches`
- [ ] Today's lineups match MLB.com (spot check 3 games)
- [ ] Weather for Coors Field today matches a manual check on weather.com within 2°F
- [ ] Park factors table has handedness-split values for all 30 parks
- [ ] Running twice in an hour doesn't duplicate rows

---

## Phase 3 — Feature engineering

**Goal:** Every historical PA and every upcoming PA has a fully populated feature row in the feature store.

**Feature categories (all into a single wide materialized view `matchup_features`):**

Batter:
- Rolling Statcast: 7/14/30-day and season — barrel%, xwOBACON, xISO, HardHit%, avg EV, 90th-pct EV, avg LA, sweet-spot%, pulled-FB%, bat speed, squared-up%, blast rate
- Platoon splits: each metric above, split vs LHP / vs RHP (prior-season weighted for stability)
- Pitch-type matrix: xwOBA vs FF/SI/FC/SL/CU/CH/FS (season + career)
- Expected PA count today (batting-order-driven)

Pitcher:
- Rolling: HR/9, Barrel% allowed, HardHit% allowed, FB%, GB%, K%, BB%
- Handedness splits: same metrics vs LHB / vs RHB
- Pitch mix + velocity averages
- Stuff+ / Location+ / Pitching+ (from FanGraphs)
- Times-through-order HR-rate penalty

Environment:
- Park handedness × direction component factor
- Weather: temp, humidity, pressure → air-density composite
- Wind vector × park orientation → carry-direction-relative wind component
- Roof status (if retractable, gate weather features to zero when closed)

Context:
- Batting order position
- Day/night flag
- Home/away
- Rest (batter, pitcher days' rest)
- Bullpen team-level Barrel% allowed (for later innings)

**Deliverables:**
- `src/features/` with one module per category
- `src/features/matchup_view.py` that joins all of the above
- Feature-freshness tracker (which rows are stale, which need refresh)
- Unit tests per feature module + integration test asserting feature-row completeness

**Acceptance checklist:**
- [ ] Every historical PA 2021–present has a non-null row in `matchup_features` for all Tier 1 features (missingness in Tier 2 is acceptable for early-season rows)
- [ ] Feature row for today's Aaron Judge vs an average RHP at Yankee Stadium passes the smell test (barrel% ~20%+, 90th-pct EV ~112+, park factor LHB-neutral/RHB-slight-help)
- [ ] Wind-vector-vs-park-orientation correctly produces +carry when wind blows toward OF, -carry when toward IF
- [ ] Roof-closed state nulls out weather features

---

## Phase 4 — Baseline model + evaluation framework

**Goal:** A calibratable XGBoost model trained on Phase 3 features, with evaluation infrastructure that will survive every future model swap.

**Deliverables:**
- `src/models/train.py` — XGBoost binary classifier, per-PA HR target
- `src/models/eval.py` — log loss, Brier, ECE, reliability-diagram generator, SHAP summary
- Time-based CV: train 2021–2023, validate 2024, test 2025+
- Model artifact versioning: `models/artifacts/v{timestamp}/` with model binary, feature schema, training metadata, eval metrics JSON
- `src/models/overview.md`

**Acceptance checklist:**
- [ ] Training completes on full dataset without OOM
- [ ] Test-set log loss and Brier documented in `phases/phase4/RESULTS.md`
- [ ] Reliability diagram generated and saved as PNG
- [ ] Top-20 features printed — barrel rate, pulled-FB rate, and park-factor variables should be near the top (sanity check)
- [ ] SHAP summary plot generated
- [ ] Model predicts >20% HR prob on some known clobber-days and <2% on Coors games where nobody homered

---

## Phase 5 — Calibration + per-game rollup

**Goal:** Per-PA probabilities that are well-calibrated, plus a per-game probability via proper aggregation.

**Deliverables:**
- `src/models/calibrate.py` — isotonic regression fit on validation fold, applied at inference
- `src/models/rollup.py` — combine per-PA probability with projected PA count using Poisson binomial (gives P(≥1 HR in game))
- Optional: LightGBM + logistic stack via `src/models/ensemble.py`
- Updated eval framework showing pre/post-calibration reliability

**Acceptance checklist:**
- [ ] Post-calibration ECE < 0.03 on test set
- [ ] Reliability curve hugs the diagonal in the 5%–40% probability range (where prop bets live)
- [ ] Per-game probability for an elite slugger on a homer-friendly day (e.g., Judge at Coors in August, 15 mph tailwind) is sensibly high (≥35%)
- [ ] Per-game probability for a weak hitter vs an ace on a pitcher's park is sensibly low (≤3%)

---

## Phase 6 — FastAPI backend

**Goal:** Serve predictions via a clean API.

**Deliverables:**
- `src/api/main.py` — FastAPI app
- Endpoints:
  - `GET /picks/today?limit=N&min_prob=X` — ranked predictions
  - `GET /player/{mlbam_id}` — profile + rolling features
  - `GET /matchup/{game_pk}/{batter_id}` — full feature contributions
  - `GET /model/metrics` — live calibration, rolling log loss
  - `GET /health` — DB + Redis connectivity
- Redis caching on `/picks/today` (5-min TTL) and `/player/*` (1-hour TTL)
- Pydantic response models for every endpoint
- OpenAPI docs auto-generated
- Integration tests via `httpx.AsyncClient` against a test DB

**Acceptance checklist:**
- [ ] `uvicorn api.main:app --reload` starts cleanly
- [ ] `/docs` Swagger UI walks through all endpoints
- [ ] All endpoints return 200 with valid responses on today's data
- [ ] Cache hit on second identical `/picks/today` request (verify via Redis `MONITOR`)
- [ ] Integration test suite green

---

## Phase 7 — Next.js frontend

**Goal:** A polished prop-bet-focused UI.

**Deliverables:**
- Next.js 15 App Router project in `ui/`
- Pages:
  - `/` — Today's ranked picks (sortable by probability, filterable by team/park/probability threshold)
  - `/player/[id]` — Player detail with rolling metrics, recent form charts
  - `/matchup/[gamePk]/[batterId]` — Matchup breakdown with feature contributions (waterfall chart)
  - `/model` — Model performance: reliability curve, rolling log loss, predictions-vs-outcomes table
- Tailwind + shadcn/ui components, dark mode default
- Real-time data via server components + revalidation
- `ui/overview.md` covering routing, data-fetching patterns, component conventions

**Acceptance checklist:**
- [ ] `npm run dev` launches without errors
- [ ] Rankings page loads in under 2s with today's data
- [ ] Clicking a row navigates to player detail and back without full page reload
- [ ] Matchup breakdown shows top-5 feature contributions visually
- [ ] Mobile-responsive (spot-check at 375px width)
- [ ] Lighthouse perf score ≥ 85

---

## Phase 8 (optional) — LangGraph explanation agent

**Goal:** Natural-language "why this pick" narratives.

**Deliverables:**
- `src/agents/explainer.py` — LangGraph graph that takes a prediction + SHAP + matchup context and produces a 3-sentence explanation
- Streamed to UI via SSE
- Cached per prediction in Redis

**Acceptance checklist:**
- [ ] Explanation for a known elite pick mentions the key drivers (barrel rate, park, weather)
- [ ] Explanation latency < 3s
- [ ] No hallucinations of feature values (agent cites real numbers from the feature row)

---

## What's explicitly out of scope for v1

- Automated bet placement (decision support only)
- Live in-game updating
- Historical bet tracking / ROI dashboards (will follow when odds are integrated in a future phase)
- Pitcher HR prop predictions (different problem)
- Mobile app
- User accounts / auth (local single-user for now)

---

## Open questions (track in `abstract.md` as they arise)

None yet. Add as they come up mid-phase.

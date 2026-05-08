# Team Bullpen Full-Game Probability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace sportsbook-facing HR fair odds with a calibrated full-game home-run probability that includes opponent team bullpen strength, while preserving the current starter-matchup model as a diagnostic signal.

**Architecture:** Add team-specific bullpen features keyed by opponent team and reference date, train a new batter-game model whose label is “batter hit at least one HR anywhere in this game,” and route odds/fair-value calculations to that full-game probability. The existing starter-matchup probability remains in `matchup_components` for explainability and regression comparison, but `predictions.prob_at_least_one_hr` becomes the full-game probability once the new model is promoted.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x, Alembic, Postgres, XGBoost/LightGBM, scikit-learn isotonic calibration, pytest, FastAPI, Next.js TypeScript.

---

## Why This Is Needed

The current production probability behaves closer to a starter-matchup probability than a sportsbook-compatible “1+ HR in the game” probability. Recent completed slates showed model averages around 5.5%-6.1%, actual full-game HR rates around 9.3%-12.0%, and actual starter-only HR rates around 6.7%-8.8%. Sportsbooks price the full game: starter, bullpen, lineup slot, projected plate appearances, park/weather, and pinch-hit/late-game exposure.

Do not solve this with a flat multiplier. A flat multiplier would push weak hitters too high and still miss matchups where a strong starter is backed by a vulnerable bullpen or vice versa. The model should learn the bullpen effect from historical games.

## File Structure

- Modify `migrations/versions/0008_team_bullpen_features.py`
  - Add team-bullpen feature columns to `matchup_features`.
- Modify `src/core/models.py`
  - Add ORM columns for the new feature fields.
- Create `src/features/team_bullpen.py`
  - SQL generator for opponent team bullpen aggregates.
- Modify `src/features/builder.py`
  - Compute opponent team identity and merge team bullpen features into each future/historical matchup row.
- Modify `src/features/overview.md`
  - Document team-specific bullpen features, leakage rules, and limitations.
- Create `tests/features/test_team_bullpen.py`
  - Unit tests for bullpen aggregation, starter exclusion, handedness splits, and leakage.
- Modify `tests/features/test_builder_smoke.py`
  - Assert new bullpen columns populate on representative rows.
- Create `src/models/full_game_data.py`
  - Builds one training row per batter-game by selecting the starter-matchup row and labeling full-game HR.
- Create `tests/models/test_full_game_data.py`
  - Regression tests for one-row-per-batter-game selection and full-game labels.
- Create `src/models/train_full_game.py`
  - Train/evaluate/save full-game model artifact using the new dataset.
- Create `tests/models/test_train_full_game_smoke.py`
  - Small seeded-data smoke test for train/eval orchestration.
- Modify `src/models/inference.py`
  - Load full-game artifacts, write full-game probability, and preserve starter model signal in `matchup_components`.
- Modify `src/models/per_game_hr.py`
  - Clarify helper semantics or add a new helper so full-game model output is not treated as starter-only.
- Modify `tests/models/test_inference.py`
  - Assert full-game probability is used for `predictions.prob_at_least_one_hr`.
- Modify `src/api/schemas/picks.py`
  - Add optional `starter_matchup_probability`, `full_game_probability`, and bullpen display fields.
- Modify `src/api/routers/picks.py`
  - Expose the new fields and keep fair odds tied to the full-game probability.
- Modify `ui/lib/types.ts`
  - Mirror new API fields.
- Modify `ui/lib/queries/picks.ts`
  - Mirror FastAPI picks query for direct Neon reads.
- Modify `ui/lib/adapters.ts`
  - Display bullpen factor chips and distinguish full-game P(HR) from starter signal.
- Modify `tests/api/test_picks.py`
  - Verify fair odds and model edge use the full-game probability.
- Modify `ui/scripts/verify-ranking-sort.mjs`
  - Add a fixture row with starter probability separate from full-game probability if sorting/display assumptions change.
- Modify `src/models/overview.md`, `src/api/overview.md`, `ui/overview.md`, and `abstract.md`
  - Document the target change and rollout decision.
- Create `reports/full_game_bullpen_model_YYYYMMDD.md`
  - Evaluation report comparing current starter-matchup model, new full-game model, and available sportsbook odds snapshots.

---

### Task 1: Add Team Bullpen Schema Columns

**Files:**
- Create: `migrations/versions/0008_team_bullpen_features.py`
- Modify: `src/core/models.py`
- Create: `tests/core/test_team_bullpen_schema.py`

- [ ] **Step 1: Write failing schema test**

Add a schema test that inspects `MatchupFeature.__table__.columns` and asserts these columns exist:

```python
EXPECTED_TEAM_BULLPEN_COLUMNS = {
    "opp_team_id",
    "opp_bp_hr_per_pa_30d",
    "opp_bp_hr_per_pa_season",
    "opp_bp_barrel_pct_allowed_30d",
    "opp_bp_barrel_pct_allowed_season",
    "opp_bp_hardhit_pct_allowed_30d",
    "opp_bp_hardhit_pct_allowed_season",
    "opp_bp_lhb_hr_per_pa_season",
    "opp_bp_rhb_hr_per_pa_season",
    "opp_bp_pitches_last_3d",
}
```

Expected failure: missing columns.

- [ ] **Step 2: Run the failing test**

Run:

```bash
uv run pytest -q tests/core/test_team_bullpen_schema.py
```

Expected: FAIL because the ORM does not expose the new columns.

- [ ] **Step 3: Add migration**

Create Alembic migration `0008_team_bullpen_features.py` that adds nullable columns to `matchup_features`. Use nullable columns because old rows and exhibition games may not have team context.

Columns:
- `opp_team_id INTEGER`
- `opp_bp_hr_per_pa_30d FLOAT`
- `opp_bp_hr_per_pa_season FLOAT`
- `opp_bp_barrel_pct_allowed_30d FLOAT`
- `opp_bp_barrel_pct_allowed_season FLOAT`
- `opp_bp_hardhit_pct_allowed_30d FLOAT`
- `opp_bp_hardhit_pct_allowed_season FLOAT`
- `opp_bp_lhb_hr_per_pa_season FLOAT`
- `opp_bp_rhb_hr_per_pa_season FLOAT`
- `opp_bp_pitches_last_3d FLOAT`

Add an index on `(game_date, opp_team_id)` for audits/backfills.

- [ ] **Step 4: Add ORM fields**

Add typed mapped columns to `MatchupFeature` in `src/core/models.py` with `Mapped[float | None]` for rates and `Mapped[int | None]` for `opp_team_id`.

- [ ] **Step 5: Verify schema test passes**

Run:

```bash
uv run pytest -q tests/core/test_team_bullpen_schema.py
```

Expected: PASS.

- [ ] **Step 6: Commit schema task**

```bash
git add migrations/versions/0008_team_bullpen_features.py src/core/models.py tests/core/test_team_bullpen_schema.py
git commit -m "feat(features): add team bullpen feature columns"
```

---

### Task 2: Build Opponent Team Bullpen Feature SQL

**Files:**
- Create: `src/features/team_bullpen.py`
- Create: `tests/features/test_team_bullpen.py`
- Modify: `src/features/overview.md`

- [ ] **Step 1: Write failing SQL contract tests**

Create tests that assert:
- The SQL references `reference_date` with strict `<` filters.
- It excludes the team’s starter from relief aggregates.
- It emits every column from Task 1.
- It derives pitcher team from inning context:
  - `inning_topbot = 'Top'` means the home team is pitching.
  - `inning_topbot = 'Bot'` means the away team is pitching.

Seed a tiny game:
- Home team `100`
- Away team `200`
- Home starter `9001`
- Home reliever `9002`
- Away starter `9011`
- Away reliever `9012`

The home bullpen aggregate must include `9002` and exclude `9001`.

- [ ] **Step 2: Run the failing tests**

Run:

```bash
uv run pytest -q tests/features/test_team_bullpen.py
```

Expected: FAIL because `src.features.team_bullpen` does not exist.

- [ ] **Step 3: Implement `team_bullpen_sql()`**

Create a SQL generator with signature:

```python
def team_bullpen_sql() -> str:
    """Return SELECT body for opponent team bullpen rolling features.

    Required input CTE: matchup_keys with columns
    (game_pk, reference_date, batter_id, pitcher_id, is_historical, opp_team_id).
    """
```

The SQL should:
- Build a historical pitch table with `pitcher_team_id`.
- Identify each team’s starter per game from inning 1 first pitcher.
- Keep relief pitchers as all pitcher-team-game rows where `pitcher_id != starter_id`.
- Aggregate by `mk.opp_team_id` and strict `sp.game_date < mk.reference_date`.
- Use 30-day and season windows.
- Compute HR per PA using distinct PA keys.
- Compute barrel/hard-hit rates only on batted balls with `launch_speed IS NOT NULL`.
- Compute handedness splits using batter stand on pitches faced by the bullpen.
- Compute workload as relief pitches in the last 3 days.

- [ ] **Step 4: Verify tests pass**

Run:

```bash
uv run pytest -q tests/features/test_team_bullpen.py
```

Expected: PASS.

- [ ] **Step 5: Document gotchas**

Update `src/features/overview.md`:
- Team bullpen features are opponent-team-specific.
- Historical rows use only games before `reference_date`.
- Starters are excluded per team-game.
- This is still team-level, not projected-reliever-level.

- [ ] **Step 6: Commit feature SQL task**

```bash
git add src/features/team_bullpen.py tests/features/test_team_bullpen.py src/features/overview.md
git commit -m "feat(features): add opponent team bullpen aggregates"
```

---

### Task 3: Merge Team Bullpen Features Into Matchup Builder

**Files:**
- Modify: `src/features/builder.py`
- Modify: `tests/features/test_builder_smoke.py`
- Modify: `tests/features/test_leakage.py`

- [ ] **Step 1: Write failing builder test**

Extend the builder smoke test to seed:
- `daily_schedule.home_team_id`
- `daily_schedule.away_team_id`
- projected lineups for both teams
- historical relief appearances before the target date

Assert future rows for a home batter use away-team bullpen as `opp_team_id`, and future rows for an away batter use home-team bullpen.

- [ ] **Step 2: Run the failing builder test**

Run:

```bash
uv run pytest -q tests/features/test_builder_smoke.py::test_builder_populates_team_bullpen_features
```

Expected: FAIL because `opp_team_id` and team bullpen columns are not populated.

- [ ] **Step 3: Add `opp_team_id` to matchup keys**

Modify `_matchup_keys_cte()` so both historical and future branches emit `opp_team_id`.

Historical derivation:
- Join `games` or `daily_schedule` for home/away team IDs.
- For the batter side, infer whether the batter is home from the first pitch:
  - `Bot` means home batter, opponent is away team.
  - `Top` means away batter, opponent is home team.

Future derivation:
- If lineup team is home team, opponent is away team.
- If lineup team is away team, opponent is home team.

- [ ] **Step 4: Run team bullpen CTE alongside existing bullpen query**

Follow the current `_run_bullpen_query()` pattern. Add `_run_team_bullpen_query()` that deduplicates `(opp_team_id, reference_date)` keys so the expensive aggregate runs once per opponent team/date, not once per batter.

- [ ] **Step 5: Merge fields into final rows**

In `build_matchup_features_for_date()`, when materializing `final_rows`, merge team-bullpen values by `(opp_team_id, game_date)`. Keep all new columns `None` if no historical team bullpen data exists.

- [ ] **Step 6: Verify leakage tests**

Add a leakage test where a reliever allows a HR on the target date. Assert target-date HR does not change `opp_bp_hr_per_pa_30d` for that same date.

Run:

```bash
uv run pytest -q tests/features/test_builder_smoke.py tests/features/test_leakage.py tests/features/test_team_bullpen.py
```

Expected: PASS.

- [ ] **Step 7: Commit builder task**

```bash
git add src/features/builder.py tests/features/test_builder_smoke.py tests/features/test_leakage.py
git commit -m "feat(features): attach opponent bullpen context to matchups"
```

---

### Task 4: Create Full-Game Training Dataset

**Files:**
- Create: `src/models/full_game_data.py`
- Create: `tests/models/test_full_game_data.py`
- Modify: `src/models/overview.md`

- [ ] **Step 1: Write failing dataset tests**

Seed a historical game where one batter faces the starter and two relievers. Insert `matchup_features` rows for each pitcher. Insert Statcast pitches where the batter homers off a reliever.

Assert:
- `load_full_game_training_data()` returns one row for that batter-game.
- The chosen feature row is the starter-matchup row.
- The label is `1` because the batter homered anywhere in the game.
- A batter with no HR anywhere in the game has label `0`.

- [ ] **Step 2: Run the failing dataset test**

Run:

```bash
uv run pytest -q tests/models/test_full_game_data.py
```

Expected: FAIL because `src.models.full_game_data` does not exist.

- [ ] **Step 3: Implement dataset loader**

Create:

```python
@dataclass(slots=True, frozen=True)
class FullGameFeatureFrame:
    X: pd.DataFrame
    y: pd.Series
    dates: pd.Series
    metadata: pd.DataFrame
```

Create:

```python
def load_full_game_training_data(
    start_date: date,
    end_date: date,
    *,
    engine: Engine | None = None,
) -> FullGameFeatureFrame:
    ...
```

Query strategy:
- Use only historical `matchup_features`.
- Identify each batter-game’s starter row by matching the opponent starter from first inning.
- Compute label with `EXISTS` over `statcast_pitches` for any `events = 'home_run'` for `(game_pk, batter_id)`, regardless of pitcher.
- Keep feature order from the current artifact-style numeric schema plus new `opp_bp_*` fields.
- Exclude identifiers, labels, strings, `is_historical`, `built_at`, and leakage diagnostics.

- [ ] **Step 4: Add time split helper**

Create:

```python
def full_game_time_based_split(engine: Engine | None = None) -> TrainValTest:
    ...
```

Use the same date ranges as the existing model:
- train: 2021-04-01 through 2023-10-31 when available
- validation: 2024 season when available
- test: 2025+ when available

For the current Neon/local reduced dataset, tests should seed explicit dates and avoid relying on full historical availability.

- [ ] **Step 5: Verify dataset tests pass**

Run:

```bash
uv run pytest -q tests/models/test_full_game_data.py
```

Expected: PASS.

- [ ] **Step 6: Commit dataset task**

```bash
git add src/models/full_game_data.py tests/models/test_full_game_data.py src/models/overview.md
git commit -m "feat(models): add full-game HR training dataset"
```

---

### Task 5: Train And Evaluate Full-Game Model

**Files:**
- Create: `src/models/train_full_game.py`
- Create: `tests/models/test_train_full_game_smoke.py`
- Modify: `src/models/artifacts.py` if artifact metadata needs a target marker
- Create: `reports/full_game_bullpen_model_YYYYMMDD.md`

- [ ] **Step 1: Write smoke test**

Write a seeded-data smoke test that runs a tiny training configuration and asserts the saved artifact metadata contains:

```json
{
  "target": "full_game_hr",
  "uses_team_bullpen_features": true,
  "probability_semantics": "batter hits at least one HR in the full game"
}
```

- [ ] **Step 2: Run the failing smoke test**

Run:

```bash
uv run pytest -q tests/models/test_train_full_game_smoke.py
```

Expected: FAIL because trainer does not exist.

- [ ] **Step 3: Implement trainer**

Build `train_full_game_model(config: FullGameTrainingConfig | None = None)`.

Minimum config:
- `learning_rate`
- `max_depth`
- `n_estimators`
- `subsample`
- `colsample_bytree`
- `random_seed`
- `top_k_per_day`
- `scale_pos_weight=1.0` by default to preserve calibration

Use the existing model training/eval patterns:
- XGBoost baseline.
- Optional LightGBM ensemble only if it improves validation log loss without harming ECE.
- Isotonic calibration fit on validation probabilities.
- Save `model.xgb`, `calibrator.joblib`, `feature_schema.json`, `training_metadata.json`, `metrics.json`, and eval report.

- [ ] **Step 4: Add model comparison metrics**

The generated report must include:
- Full-game model Brier/log loss/ECE/AUC.
- Existing starter-matchup model evaluated against full-game labels on the same rows.
- Reliability curve for full-game target.
- Top-20 precision per day.
- Average predicted probability vs actual full-game HR rate by bucket.
- Available sportsbook odds comparison for dates where `odds_snapshots` exist.

- [ ] **Step 5: Train on available local data**

Run:

```bash
uv run python -m src.models.train_full_game
```

Expected:
- Writes a new artifact under `src/models/registry/v...`.
- Report shows whether the full-game model is better calibrated than current production for full-game labels.

- [ ] **Step 6: Promotion gate**

Do not promote the new model unless:
- Test-set ECE is not worse than current production by more than 0.005.
- Full-game label Brier/log loss improve over the current starter-matchup model evaluated as full-game.
- Reliability curve is not systematically under the diagonal.
- Top daily picks still pass a sanity spot-check: mostly real power hitters or clearly favorable park/weather/bullpen spots.

- [ ] **Step 7: Commit trainer task**

```bash
git add src/models/train_full_game.py tests/models/test_train_full_game_smoke.py reports/full_game_bullpen_model_*.md
git commit -m "feat(models): train full-game HR model with bullpen context"
```

---

### Task 6: Route Inference To Full-Game Probability

**Files:**
- Modify: `src/models/inference.py`
- Modify: `src/models/per_game_hr.py`
- Modify: `tests/models/test_inference.py`
- Modify: `tests/models/test_per_game_hr.py`

- [ ] **Step 1: Write failing inference test**

Seed a loaded model metadata fixture with `target = "full_game_hr"`. Assert generated prediction row has:

```python
row["prob_at_least_one_hr"] == row["matchup_components"]["full_game_calibrated_prob"]
row["matchup_components"]["probability_semantics"] == "full_game_hr"
row["matchup_components"]["starter_calibrated_prob"] is not None
```

If preserving starter signal requires loading the old starter model during inference, assert it is optional and failures do not block full-game predictions.

- [ ] **Step 2: Run failing inference test**

Run:

```bash
uv run pytest -q tests/models/test_inference.py::test_full_game_model_probability_drives_prediction
```

Expected: FAIL because inference only writes starter/bullpen placeholders today.

- [ ] **Step 3: Update inference semantics**

When loaded artifact metadata says `target = "full_game_hr"`:
- Treat calibrated model output as full-game probability.
- Write `prob_at_least_one_hr = full_game_calibrated_prob`.
- Write `expected_hrs = full_game_calibrated_prob` as the conservative Bernoulli expectation for at least one HR.
- Set `prob_at_least_two_hr = null` unless/until a separate multi-HR model exists.
- Store:

```json
{
  "probability_semantics": "full_game_hr",
  "full_game_raw_prob": 0.0,
  "full_game_calibrated_prob": 0.0,
  "starter_raw_prob": 0.0,
  "starter_calibrated_prob": 0.0,
  "team_bullpen_features_version": 1
}
```

If starter-model sidecar is not implemented in this task, keep `starter_*` as the old raw/calibrated values only when available; otherwise set them to `null` and document that the model drivers now explain the full-game model.

- [ ] **Step 4: Avoid misusing `per_game_hr_distribution`**

Do not pass full-game model output into a helper named as if it were starter probability. Either:
- Add `full_game_hr_distribution(probability: float)`, or
- Bypass distribution composition for full-game artifacts.

- [ ] **Step 5: Verify inference tests pass**

Run:

```bash
uv run pytest -q tests/models/test_inference.py tests/models/test_per_game_hr.py
```

Expected: PASS.

- [ ] **Step 6: Commit inference task**

```bash
git add src/models/inference.py src/models/per_game_hr.py tests/models/test_inference.py tests/models/test_per_game_hr.py
git commit -m "feat(models): use full-game probability in inference"
```

---

### Task 7: Make Odds/Fair Value Explicitly Full-Game

**Files:**
- Modify: `src/api/schemas/picks.py`
- Modify: `src/api/routers/picks.py`
- Modify: `tests/api/test_picks.py`
- Modify: `ui/lib/types.ts`
- Modify: `ui/lib/queries/picks.ts`
- Modify: `ui/lib/adapters.ts`
- Modify: `ui/scripts/verify-ranking-sort.mjs`

- [ ] **Step 1: Write failing API odds test**

Seed a prediction with:
- `prob_at_least_one_hr = 0.12`
- `matchup_components.starter_calibrated_prob = 0.07`
- sportsbook `+700`

Assert:
- `fair_odds_american == 733`
- `model_edge == 0.12 - 0.125`
- `starter_matchup_probability == 0.07`
- `full_game_probability == 0.12`

This proves fair odds use the full-game probability, not starter probability.

- [ ] **Step 2: Run failing API test**

Run:

```bash
uv run pytest -q tests/api/test_picks.py::test_picks_today_fair_odds_use_full_game_probability
```

Expected: FAIL until schema/query expose the new fields.

- [ ] **Step 3: Update FastAPI picks**

In `src/api/routers/picks.py`:
- Parse `full_game_calibrated_prob` and `starter_calibrated_prob` from `matchup_components`.
- Keep fair odds based on `prob_at_least_one_hr`.
- Add response fields for starter/full-game probabilities and opponent bullpen features.

- [ ] **Step 4: Mirror Next direct query**

In `ui/lib/queries/picks.ts`:
- Select the same `matchup_components` fields.
- Select `opp_bp_*` fields.
- Keep SQL behavior aligned with FastAPI.

- [ ] **Step 5: Update UI adapter labels**

In `ui/lib/adapters.ts`:
- Keep headline `P(HR)` as full-game probability.
- Add factor chips:
  - `STARTER P`
  - `BP HR/PA`
  - `BP BRL`
  - `BP LOAD`
- Keep Model Lift/Edge filtering logic unchanged.

- [ ] **Step 6: Verify API and UI helper tests**

Run:

```bash
uv run pytest -q tests/api/test_picks.py
cd ui && npm run test:ranking-sort
```

Expected: PASS.

- [ ] **Step 7: Commit odds/UI task**

```bash
git add src/api/schemas/picks.py src/api/routers/picks.py tests/api/test_picks.py ui/lib/types.ts ui/lib/queries/picks.ts ui/lib/adapters.ts ui/scripts/verify-ranking-sort.mjs
git commit -m "feat(api): expose full-game bullpen-adjusted odds edge"
```

---

### Task 8: Backfill, Refresh, And Promotion Workflow

**Files:**
- Modify: `scripts/refresh-picks.sh`
- Modify: `.agents/skills/refresh-picks/SKILL.md`
- Modify: `src/ingestion/overview.md`
- Modify: `src/models/overview.md`
- Modify: `src/api/overview.md`
- Modify: `ui/overview.md`
- Modify: `abstract.md`

- [ ] **Step 1: Apply migration locally**

Run:

```bash
uv run alembic upgrade head
```

Expected: migration `0008_team_bullpen_features` applied.

- [ ] **Step 2: Backfill team bullpen features**

Run a controlled backfill over the needed model-training range. Use yearly chunks so progress is observable and failures resume cleanly:

```bash
uv run python -m src.features.builder --start 2021-04-01 --end 2021-10-31
uv run python -m src.features.builder --start 2022-04-01 --end 2022-10-31
uv run python -m src.features.builder --start 2023-04-01 --end 2023-10-31
uv run python -m src.features.builder --start 2024-04-01 --end 2024-10-31
uv run python -m src.features.builder --start 2025-04-01 --end 2025-10-31
uv run python -m src.features.builder --start 2026-03-15 --end 2026-05-08
```

If the current builder CLI does not support date ranges, add a small CLI wrapper rather than running ad hoc SQL from the terminal.

- [ ] **Step 3: Train full-game artifact**

Run:

```bash
uv run python -m src.models.train_full_game
```

Expected: new model artifact with `target = "full_game_hr"`.

- [ ] **Step 4: Promote only after gates pass**

Promote:

```bash
uv run python - <<'PY'
from src.models.artifacts import promote_to_production
promote_to_production("vYYYYMMDD_HHMMSS")
PY
```

Only do this after Task 5 promotion gates pass.

- [ ] **Step 5: Refresh picks**

Run:

```bash
./scripts/refresh-picks.sh
```

Expected:
- `matchup_features rows` equals active projected hitters.
- `predictions written` equals active projected hitters.
- odds ingestion succeeds or reports odds-only failures without aborting predictions.
- Top picks show full-game probabilities closer to plausible sportsbook ranges.

- [ ] **Step 6: Update docs**

Document:
- The sportsbook-facing probability is now full-game.
- Team bullpen features are opponent-team-level, not projected reliever-level.
- Starter probability is diagnostic, not the fair-odds basis.
- Fair odds and model edge use full-game probability.

- [ ] **Step 7: Commit rollout docs**

```bash
git add scripts/refresh-picks.sh .agents/skills/refresh-picks/SKILL.md src/ingestion/overview.md src/models/overview.md src/api/overview.md ui/overview.md abstract.md
git commit -m "docs: document full-game bullpen probability rollout"
```

---

### Task 9: Final Verification Before Merge

**Files:** no new code unless failures require fixes.

- [ ] **Step 1: Run targeted Python tests**

```bash
uv run pytest -q \
  tests/core/test_team_bullpen_schema.py \
  tests/features/test_team_bullpen.py \
  tests/features/test_builder_smoke.py \
  tests/features/test_leakage.py \
  tests/models/test_full_game_data.py \
  tests/models/test_inference.py \
  tests/models/test_per_game_hr.py \
  tests/api/test_picks.py
```

Expected: PASS.

- [ ] **Step 2: Run broader Python checks**

```bash
uv run pytest -q
uv run ruff check .
```

Expected: PASS. Do not skip tests to make this green.

- [ ] **Step 3: Run frontend checks**

```bash
cd ui
npm run test:ranking-sort
npm run lint
npm run build
```

Expected: PASS.

- [ ] **Step 4: Run odds sanity query**

Run a query comparing model probability, fair odds, selected sportsbook odds, market implied probability, and actual full-game labels for the latest completed slates.

Expected:
- Full-game model average is materially closer to actual full-game HR rate than the old starter-matchup model.
- Fair odds are mathematically consistent with displayed probability.
- Positive edges are rare and explainable, not an artifact of comparing starter-only probability to full-game odds.

- [ ] **Step 5: Secret scan**

```bash
git diff --cached | rg -n "(apiKey|PROP_LINE|DATABASE_URL|SECRET|TOKEN|gho_|neondb_owner|postgresql\\+psycopg|password|PRIVATE|BEGIN RSA|BEGIN OPENSSH)"
```

Expected: no output.

- [ ] **Step 6: Final commit if needed**

If verification fixes were needed, inspect the exact files first:

```bash
git status --short
git diff --stat
git add src/core/models.py src/features/team_bullpen.py src/features/builder.py src/models/full_game_data.py src/models/train_full_game.py src/models/inference.py src/models/per_game_hr.py src/api/schemas/picks.py src/api/routers/picks.py ui/lib/types.ts ui/lib/queries/picks.ts ui/lib/adapters.ts tests/core/test_team_bullpen_schema.py tests/features/test_team_bullpen.py tests/features/test_builder_smoke.py tests/features/test_leakage.py tests/models/test_full_game_data.py tests/models/test_train_full_game_smoke.py tests/models/test_inference.py tests/models/test_per_game_hr.py tests/api/test_picks.py
git commit -m "fix: harden full-game bullpen probability rollout"
```

---

## Rollout Recommendation

Do not replace production immediately after adding the features. The safest sequence is:

1. Add schema/features and backfill.
2. Train full-game model.
3. Compare old starter model vs new full-game model on full-game labels.
4. Refresh one current slate without promoting, using a local artifact override.
5. Inspect top picks, fair odds, and sportsbook edge.
6. Promote only if calibration and sanity checks pass.

The first production version should expose both:
- `P(HR)` = full-game sportsbook-facing probability.
- `STARTER P` = diagnostic starter-matchup signal.

That keeps the betting edge honest while preserving the information we already trust.

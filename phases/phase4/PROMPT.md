# Phase 4 — Baseline Model + Evaluation Framework

## Required reading
1. `./CLAUDE.md`
2. `./MASTER_PLAN.md` — Phase 4 section
3. `./abstract.md` — should show Phases 0–3 complete
4. `./src/features/overview.md` — know what features are available
5. All previous `phases/phaseN/NOTES.md`

---

## Objective
Build an XGBoost binary classifier that predicts `hr_on_pa` for each plate appearance, plus the evaluation framework that will survive every future model swap. **Evaluation infrastructure matters more than model accuracy right now** — we'll improve the model in Phase 5; we will not re-architect evaluation.

**Scope boundary:** Train model, evaluate, version artifacts. No calibration layer (Phase 5). No per-game rollup (Phase 5). No API (Phase 6).

---

## Deliverables

### 1. Directory + module structure

```
src/models/
├── __init__.py
├── overview.md
├── train.py              # training entrypoint
├── eval.py               # evaluation metrics and plots
├── data.py               # feature loading + train/val/test splitter
├── artifacts.py          # model versioning and persistence
└── registry/             # local model registry (gitignored)
    └── .gitkeep
```

### 2. Feature loader (`src/models/data.py`)

- `load_training_data(start_date, end_date) -> FeatureFrame`:
  - Pulls from `matchup_features` WHERE `is_historical=True`
  - Returns a dataclass with: `X: pd.DataFrame`, `y: pd.Series` (binary, `hr_on_pa`), `dates: pd.Series`, `metadata: dict`
  - Drops any rows with null in the label

- `time_based_split(frame: FeatureFrame) -> TrainValTest`:
  - **Train:** 2021-04-01 through 2023-10-31
  - **Validation:** 2024-04-01 through 2024-10-31
  - **Test:** 2025-04-01 through last available
  - Absolutely NO random shuffling
  - Return three `FeatureFrame` objects

- `FEATURE_COLUMNS: list[str]` — central list of feature column names to use. Defined in this file so every consumer imports from one place.

### 3. Training script (`src/models/train.py`)

```python
def train_baseline(config: TrainingConfig) -> TrainingResult:
    """Fit an XGBoost binary classifier. Returns metrics + model artifact path."""
```

`TrainingConfig` (Pydantic):
- `model_type: Literal["xgboost"]`  (extensible later)
- `n_estimators: int = 500`
- `max_depth: int = 6`
- `learning_rate: float = 0.05`
- `subsample: float = 0.8`
- `colsample_bytree: float = 0.8`
- `min_child_weight: int = 10`
- `reg_alpha: float = 0.1`, `reg_lambda: float = 1.0`
- `early_stopping_rounds: int = 50`
- `random_seed: int = 42`
- `scale_pos_weight: float | None = None`  # None = auto-compute from class imbalance

Steps:
1. Load data, split time-based
2. Train XGBoost with `eval_set=[(X_val, y_val)]` and early stopping
3. Compute all metrics (see next section) on train, val, and test
4. Generate plots (reliability, feature importance, SHAP summary) saved as PNGs
5. Persist artifact via `artifacts.save_model(...)`
6. Return `TrainingResult` with paths and metrics

CLI: `python -m models.train [--config path/to/config.yaml]`. If no config, use defaults.

### 4. Evaluation (`src/models/eval.py`)

Primary metrics (implement each as a pure function):

- `log_loss(y_true, y_prob) -> float`
- `brier_score(y_true, y_prob) -> float`
- `expected_calibration_error(y_true, y_prob, n_bins: int = 10) -> float`
  - Bin predictions, compute |avg_pred - avg_actual| per bin, weight by bin size
- `reliability_curve(y_true, y_prob, n_bins: int = 10) -> tuple[list, list, list]`
  - Returns (mean_pred_per_bin, actual_rate_per_bin, count_per_bin)
- `precision_at_top_k(y_true, y_prob, k: int) -> float`
  - Useful for prop-bet ranking: "of our top 20 picks per day, what % hit?"
- `auc(y_true, y_prob) -> float` — secondary; rank quality check

Plotting (matplotlib only, no seaborn required):
- `plot_reliability(curves: dict[str, ReliabilityCurve], save_path: Path)` — overlay train/val/test
- `plot_feature_importance(model, feature_names, save_path, top_n=30)`
- `plot_shap_summary(model, X_sample, save_path, max_display=30)` — use `shap.TreeExplainer`

Generate a markdown eval report (`reports/phase4_eval_v{timestamp}.md`) with:
- All metrics on train, val, test
- Reliability table
- Top 30 features by gain + SHAP
- Prediction distribution histograms (training vs test — distribution shift check)
- Comparison to a **naive baseline:** always predict the league HR-per-PA rate. Our model must beat this on log loss or it's broken.

### 5. Artifact management (`src/models/artifacts.py`)

Save to `src/models/registry/v{YYYYMMDD_HHMMSS}/`:
- `model.xgb` — XGBoost model binary
- `feature_schema.json` — ordered list of feature columns + dtypes
- `training_metadata.json` — training date range, test date range, config, git commit SHA, data hash (SHA256 of first+last+middle rows of training set)
- `metrics.json` — all evaluation metrics
- `reliability_train.png`, `reliability_val.png`, `reliability_test.png`
- `feature_importance.png`
- `shap_summary.png`
- `eval_report.md`

Functions:
- `save_model(model, config, metrics, eval_artifacts) -> Path`
- `load_model(version: str | None = None) -> LoadedModel` — defaults to latest
- `list_versions() -> list[ModelVersion]`
- `promote_to_production(version: str)` — writes a `production` symlink/pointer (used later by inference)

The `registry/` directory is gitignored. Artifacts are local-only for now.

### 6. Tests

- `tests/models/test_data.py`:
  - Time-based split produces non-overlapping, correctly-dated splits
  - Shuffling assertion: split is deterministic, train max date < val min date < test min date
- `tests/models/test_eval.py`:
  - Unit tests for each metric with known inputs
    - Perfect predictions: log_loss = 0, brier = 0, ECE = 0
    - Random predictions on balanced data: log_loss ≈ 0.693
    - Constant prediction 0.5 on balanced data: brier = 0.25
  - Reliability curve: known dataset, expected bins
- `tests/models/test_train.py`:
  - Small integration test: train on tiny seed dataset, confirm model trains and artifact is saved
  - Config defaults produce a model that beats the naive baseline on held-out data

### 7. Phase docs

- `phases/phase4/ACCEPTANCE.md`
- `phases/phase4/NOTES.md` — include hyperparameter observations
- `phases/phase4/RESULTS.md` — final metrics on test set, ready for reference
- Populate `src/models/overview.md` with clear module docs

---

## Acceptance checklist

```markdown
# Phase 4 — Acceptance Checklist

## Training
- [ ] `uv run python -m models.train` completes without error in under 30 min on a laptop
- [ ] Model trained with early stopping; documented the epoch it stopped at
- [ ] Artifact saved in `src/models/registry/v*/` with all required files
- [ ] `load_model()` round-trips: saved model → loaded model predicts identically

## Evaluation
- [ ] Test-set log loss is less than the naive baseline (league-average predictor) log loss by a meaningful margin (>5% relative improvement)
- [ ] Test-set Brier score < 0.035 (the HR base rate is ~3%, so random guessing would hit 0.029; a decent model should be 0.025–0.032)
- [ ] Test-set AUC > 0.75
- [ ] Precision at top-20 predictions per day > 0.15 (i.e., 15%+ of our top-20 daily picks actually homer)
- [ ] Reliability diagram visually hugs the diagonal in the 0–20% probability range (most of our density)
- [ ] Pre-calibration ECE documented; it may be poor (that's fine, Phase 5 fixes it)

## Feature importance sanity
- [ ] Top 10 features by gain include: barrel rate (some window), park HR factor (handedness), exit velocity metric, pitcher barrel% allowed OR fly ball %, some weather or air density feature
- [ ] If batter_days_rest is in the top 5, something is wrong — investigate (might be a leakage signal)
- [ ] SHAP summary plot saved and reviewable

## Distribution shift
- [ ] Histogram of predicted probabilities on train vs test overlaps substantially; no wild divergence
- [ ] If a specific feature is concentrated in one season (e.g., bat_speed only 2024+), document how it's handled (imputed or forced null)

## Tests
- [ ] `uv run pytest tests/models -v` all pass
- [ ] Each metric has at least one unit test with a known-truth comparison

## Docs
- [ ] `phases/phase4/RESULTS.md` documents final test metrics
- [ ] `src/models/overview.md` complete
- [ ] `abstract.md` shows Phase 4 complete
```

---

## Non-negotiables

- **NO random shuffling.** Time-based splits only. Random splits on baseball data leak season context and inflate metrics.
- **Log git commit SHA** into training metadata. Every model is traceable to a code state.
- **Log data hash** into training metadata. If you retrain on different data, we can detect it.
- **Seed everything.** `random_seed` flows to XGBoost, numpy, python `random`. Two runs with the same config and data produce identical results.
- **Naive baseline is mandatory.** If the model doesn't beat "always predict league average," we have a bug, not a model.
- **All artifacts together.** A model binary without its feature schema is useless. Save them atomically.

---

## Post-phase ritual

1. `uv run pytest -q` → green
2. Full training run produces a versioned artifact
3. Walk through acceptance checklist
4. Update `abstract.md`, `phases/phase4/RESULTS.md`, `src/models/overview.md`
5. Commit + tag `phase-4-complete`

---

## STOP condition

Do not start Phase 5 calibration without approval. Report:
1. Train/val/test log loss and Brier
2. Top-10 features by SHAP
3. Naive baseline comparison
4. Any distribution shift concerns
5. Total training time

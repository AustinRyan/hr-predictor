# Phase 4 — Baseline Model + Evaluation Framework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`. Lean plan. Tasks reference `phases/phase4/PROMPT.md` sections rather than duplicating them.

**Goal:** Train an XGBoost binary classifier for `hr_on_pa` per PA, with an evaluation framework that survives future model swaps. Calibration is Phase 5; per-game rollup is Phase 5; API is Phase 6.

**Architecture:** Four focused modules under `src/models/` (`data.py`, `eval.py`, `artifacts.py`, `train.py`). Time-based train/val/test split reading from `matchup_features`. XGBoost with native NULL handling, early stopping on val. Per-PA metrics + plots + SHAP. Versioned artifacts in a gitignored local registry.

**Tech Stack:** XGBoost 2.x, scikit-learn (metrics baseline only), SHAP, matplotlib, pandas, pytest. All already in `pyproject.toml`.

---

## Locked design decisions (controller-approved 2026-04-23)

1. **FEATURE_COLUMNS strategy:** enumerate numeric feature columns from `src.core.models.MatchupFeature` programmatically — exclude key columns (`game_date`, `game_pk`, `batter_id`, `pitcher_id`), the label (`hr_on_pa`), the historical flag (`is_historical`), the audit timestamp (`built_at`), and the string columns (`p_primary_pitch`, `ctx_day_night`). One place to edit when the schema changes. Enumerated list produced at module-load time.

2. **NULL handling:** use XGBoost's native `missing=np.nan` support. Don't impute — the missingness itself is signal (pre-2024 bat_speed = NULL, historical retractable roof = NULL, etc.). Document in NOTES.md.

3. **`precision_at_top_k` semantics:** "per day" = per `game_date`. For each day in the evaluation set, rank predictions by probability, take top K, count how many had `hr_on_pa=True`. Return mean across days. K defaults to 20.

4. **Naive baseline:** single probability = training-set `mean(hr_on_pa)`. Applied uniformly to val and test sets. Log loss on that constant prediction is the floor to beat by ≥5% relative.

5. **Seeding:** `random_seed=42` flows to numpy (`np.random.seed`), python's `random.seed`, and XGBoost's `random_state`. Env var `PYTHONHASHSEED=0` NOT set (makes tests fragile); document that hash-dependent ops aren't used.

6. **Artifact version IDs:** `v{YYYYMMDD_HHMMSS}` (UTC) — human-readable and collision-free. Production pointer is a plain-text file `src/models/registry/PRODUCTION` containing the version string, NOT a symlink (symlinks don't play well on Windows / cross-platform).

7. **Plots:** matplotlib only. Each plot function takes a `save_path: Path` and returns None. No interactive displays.

8. **Data loading:** pull via SQLAlchemy `engine.execute(text(...))` → `pd.read_sql()`. One query per split (train/val/test) with explicit date bounds + `is_historical=True` + `hr_on_pa IS NOT NULL`.

---

## File structure

**Create:**
- `src/models/__init__.py`
- `src/models/overview.md` (full, not stub)
- `src/models/data.py`
- `src/models/eval.py`
- `src/models/artifacts.py`
- `src/models/train.py`
- `src/models/registry/.gitkeep`
- `tests/models/__init__.py`
- `tests/models/test_data.py`
- `tests/models/test_eval.py`
- `tests/models/test_artifacts.py`
- `tests/models/test_train.py`
- `phases/phase4/ACCEPTANCE.md`
- `phases/phase4/NOTES.md`
- `phases/phase4/RESULTS.md`

**Modify:**
- `.gitignore` — add `src/models/registry/v*/` (keep `.gitkeep` tracked; gitignore versioned artifacts and the PRODUCTION pointer)
- `abstract.md` — at phase close

**No modification:** any Phase 1/2/3/3.5 code. Phase 4 reads `matchup_features`; writes only to `src/models/registry/`.

---

## Task order + dispatch (serial; each depends on the previous)

- **Task 1:** `data.py` + `FEATURE_COLUMNS` + time-based split + tests
- **Task 2:** `eval.py` metrics (log_loss, brier, ECE, reliability, precision_at_top_k, auc) + unit tests with known-truth values
- **Task 3:** `eval.py` plots (reliability, feature_importance, shap_summary) — plotting-only, separate commit for clarity
- **Task 4:** `artifacts.py` save/load/list/promote + tests
- **Task 5:** `train.py` — `TrainingConfig` Pydantic model + `train_baseline` + CLI
- **Task 6:** Real training run (produces the first artifact), eval report generation, acceptance walk-through, phase docs, tag

---

# Task 1 — data loader + time-based split

**Files:**
- Create: `src/models/__init__.py` (empty)
- Create: `src/models/data.py`
- Create: `tests/models/__init__.py` (empty)
- Create: `tests/models/test_data.py`

**API:**

```python
@dataclass(slots=True)
class FeatureFrame:
    X: pd.DataFrame
    y: pd.Series
    dates: pd.Series
    metadata: dict[str, Any]


@dataclass(slots=True)
class TrainValTest:
    train: FeatureFrame
    val: FeatureFrame
    test: FeatureFrame


# Enumerated from MatchupFeature columns at import time; excludes:
#   - keys: game_date, game_pk, batter_id, pitcher_id
#   - label: hr_on_pa
#   - metadata: is_historical, built_at
#   - string columns: p_primary_pitch, ctx_day_night
# Keeps all numeric feature columns (~120 of them).
FEATURE_COLUMNS: list[str] = [...]


def load_training_data(
    start_date: date,
    end_date: date,
    *,
    engine: Engine | None = None,
) -> FeatureFrame:
    """Pull historical matchup_features in [start_date, end_date] with non-null labels."""


def time_based_split(
    frame: FeatureFrame | None = None,
    *,
    engine: Engine | None = None,
) -> TrainValTest:
    """Train: 2021-04-01..2023-10-31
    Val:   2024-04-01..2024-10-31
    Test:  2025-04-01..last-available

    If `frame` is None, load each split independently. If `frame` is given,
    slice from it via date ranges.
    """
```

**Tests:**
- `test_feature_columns_excludes_keys_and_label` — assert `game_pk`, `hr_on_pa`, `is_historical`, `built_at`, `p_primary_pitch` not in FEATURE_COLUMNS.
- `test_feature_columns_includes_expected_families` — at least one column from each family: `b_barrel_pct_*`, `p_hr_per_9_*`, `park_hr_factor_*`, `wx_*`, `ctx_*`.
- `test_feature_columns_count_reasonable` — `80 <= len(FEATURE_COLUMNS) <= 130` (sanity bound).
- `@pytest.mark.integration test_time_based_split_nonoverlapping_dates` — run against real dev DB, verify `train.dates.max() < val.dates.min() < val.dates.max() < test.dates.min()`.
- `@pytest.mark.integration test_time_based_split_row_counts_sane` — train has ≥ 300k rows, val ≥ 100k, test ≥ 100k.
- `@pytest.mark.integration test_load_training_data_excludes_null_labels` — `y.notna().all()`.

**Commit:** `feat(models): add feature loader + time-based train/val/test splitter`.

---

# Task 2 — evaluation metrics

**Files:**
- Create: `src/models/eval.py` (metrics half only; plots in Task 3)
- Create: `tests/models/test_eval.py`

**API (pure functions, no side effects):**

```python
def log_loss(y_true: np.ndarray, y_prob: np.ndarray, eps: float = 1e-15) -> float:
    """Binary cross-entropy. Clip probs to [eps, 1-eps]."""


def brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Mean squared error between prob and label."""


def expected_calibration_error(
    y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10
) -> float:
    """Equal-width bins, weighted by bin count. Empty bins contribute 0."""


@dataclass(slots=True)
class ReliabilityCurve:
    mean_pred: list[float]   # mean predicted prob per bin
    actual_rate: list[float] # empirical HR rate per bin
    counts: list[int]        # bin size


def reliability_curve(
    y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10
) -> ReliabilityCurve:
    """Equal-width bins over [0, 1]. Empty bins emit NaN for means."""


def precision_at_top_k(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    dates: np.ndarray,  # group key — per game_date
    k: int = 20,
) -> float:
    """Per-date precision@k averaged across dates. Skip dates with fewer than k predictions."""


def auc(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Wrap sklearn.metrics.roc_auc_score; separate here for consistency."""


def naive_baseline_log_loss(
    y_true: np.ndarray, train_rate: float, eps: float = 1e-15
) -> float:
    """Log loss of always predicting `train_rate`. Used to validate model beats naive."""
```

**Tests (known-truth):**
- `test_log_loss_perfect_prediction_is_zero` — `y_true=[1,0,1,0]`, `y_prob=[1,0,1,0]` → 0 (with eps clipping, ~1e-15).
- `test_log_loss_random_on_balanced_data` — `y_true` balanced, `y_prob=0.5` everywhere → `≈ 0.693` (= ln 2).
- `test_brier_constant_half_on_balanced_data` — `y_prob=0.5`, balanced labels → 0.25.
- `test_brier_perfect_is_zero`.
- `test_ece_perfect_calibration_is_zero` — `y_prob` matches actual bin rate exactly.
- `test_ece_known_miscalibration` — handcraft a simple 2-bin case, verify numeric output.
- `test_reliability_curve_emits_n_bins_values` — always 10 bins, NaN for empty.
- `test_precision_at_top_k_simple_case` — 2 days × 5 predictions each; verify fraction hit.
- `test_auc_perfect_predictions_is_one`.
- `test_auc_random_predictions_near_half` — seeded random → 0.45-0.55 tolerance.
- `test_naive_baseline_matches_log_loss_of_constant`.

**Commit:** `feat(models): add evaluation metrics (log_loss, brier, ECE, reliability, top_k, auc)`.

---

# Task 3 — evaluation plots

**Files:**
- Modify: `src/models/eval.py` (append plotting functions)
- Modify: `tests/models/test_eval.py` (append smoke tests)

**API:**

```python
def plot_reliability(
    curves: dict[str, ReliabilityCurve],
    save_path: Path,
    title: str = "Reliability",
) -> None:
    """Overlay train/val/test reliability curves. Diagonal reference line.
    Saves PNG to save_path; closes the figure."""


def plot_feature_importance(
    model: xgboost.Booster,
    feature_names: list[str],
    save_path: Path,
    top_n: int = 30,
    importance_type: Literal["gain", "weight", "cover"] = "gain",
) -> None:
    """Horizontal bar of top_n features."""


def plot_shap_summary(
    model: xgboost.Booster,
    X_sample: pd.DataFrame,
    save_path: Path,
    max_display: int = 30,
) -> None:
    """Uses shap.TreeExplainer; down-samples X to 5000 rows max to keep runtime
    under 60s."""


def plot_prediction_histogram(
    predictions: dict[str, np.ndarray],  # "train" / "test" mapping
    save_path: Path,
    bins: int = 50,
) -> None:
    """Overlay train vs test prediction distribution for shift check."""
```

**Tests (smoke-level; plots are hard to unit-test deeply):**
- `test_plot_reliability_writes_png_file` — fake minimal curves, save to tmp_path, assert file exists + nonzero.
- `test_plot_feature_importance_handles_fewer_features_than_top_n` — small fake model, don't crash.
- `test_plot_prediction_histogram_writes_file`.
- `plot_shap_summary` gets an integration test in Task 6 (needs a real trained model).

**Commit:** `feat(models): add evaluation plots (reliability, feature importance, SHAP, histograms)`.

---

# Task 4 — artifacts

**Files:**
- Create: `src/models/artifacts.py`
- Create: `src/models/registry/.gitkeep`
- Modify: `.gitignore` (add `src/models/registry/v*/` and `src/models/registry/PRODUCTION`)
- Create: `tests/models/test_artifacts.py`

**API:**

```python
@dataclass(slots=True)
class ModelVersion:
    version: str          # "v20260423_143022"
    path: Path            # src/models/registry/v20260423_143022/
    created_at: datetime
    metrics: dict         # loaded from metrics.json


@dataclass(slots=True)
class LoadedModel:
    model: xgboost.Booster
    feature_schema: list[str]  # ordered feature names
    training_metadata: dict
    metrics: dict
    version: str


def save_model(
    model: xgboost.Booster,
    config: TrainingConfig,
    metrics: dict,
    feature_columns: list[str],
    plot_paths: dict[str, Path] = ...,
    eval_report: str = ...,
    *,
    registry_root: Path | None = None,
) -> Path:
    """Create src/models/registry/v{ts}/ with:
      - model.xgb
      - feature_schema.json
      - training_metadata.json (git SHA, data hash, config, training range)
      - metrics.json
      - <all plot PNGs copied in>
      - eval_report.md
    Returns the version directory."""


def load_model(version: str | None = None, *, registry_root: Path | None = None) -> LoadedModel:
    """Load a version (or latest if None)."""


def list_versions(registry_root: Path | None = None) -> list[ModelVersion]:
    """All versions sorted newest-first."""


def promote_to_production(version: str, *, registry_root: Path | None = None) -> None:
    """Write src/models/registry/PRODUCTION containing version string."""


def current_production(registry_root: Path | None = None) -> str | None:
    """Read the PRODUCTION pointer, or None if unset."""
```

**Helper:**
```python
def _compute_data_hash(X: pd.DataFrame, y: pd.Series) -> str:
    """SHA256 of first+middle+last rows of (X, y) serialized. Fast + identity-sensitive."""
```

**Tests:**
- `test_save_and_load_roundtrip` — train a trivial XGBoost on 50 rows, save, load, verify predictions identical.
- `test_list_versions_sorted_newest_first`.
- `test_promote_to_production_roundtrips`.
- `test_current_production_returns_none_when_unset`.
- `test_data_hash_stable_for_same_data`.
- `test_data_hash_changes_when_data_changes`.

**Commit:** `feat(models): add artifact versioning + registry`.

---

# Task 5 — training orchestrator

**Files:**
- Create: `src/models/train.py`
- Create: `tests/models/test_train.py`

**API:**

```python
class TrainingConfig(BaseModel):
    model_type: Literal["xgboost"] = "xgboost"
    n_estimators: int = 500
    max_depth: int = 6
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    min_child_weight: int = 10
    reg_alpha: float = 0.1
    reg_lambda: float = 1.0
    early_stopping_rounds: int = 50
    random_seed: int = 42
    scale_pos_weight: float | None = None  # None = auto-compute from class imbalance


@dataclass(slots=True)
class TrainingResult:
    artifact_path: Path
    metrics: dict       # flat dict, keys like "train_log_loss", "val_brier", etc.
    best_iteration: int
    config: TrainingConfig


def train_baseline(
    config: TrainingConfig | None = None,
    *,
    engine: Engine | None = None,
) -> TrainingResult:
    """Full training pipeline:
    1. Load + split via data.py.
    2. Compute scale_pos_weight if unset: (#negatives / #positives) on train.
    3. Fit XGBClassifier with eval_set=[(X_val, y_val)], early stopping.
    4. Compute all metrics on train/val/test.
    5. Generate plots (reliability x3, feature_importance, SHAP, histogram).
    6. Build naive-baseline comparison.
    7. Write eval report markdown.
    8. Persist artifact via artifacts.save_model(...).
    """
```

**CLI:** `python -m src.models.train`. Uses defaults. `--config path/to/config.yaml` optional (pydantic YAML loader).

**Tests:**
- `test_training_config_defaults` — unchanged from PROMPT § 3.
- `@pytest.mark.integration test_train_tiny_dataset_produces_artifact` — seeded 200-row synthetic frame, skip network, train in <5s, assert artifact exists.
- `@pytest.mark.integration test_trained_model_beats_naive_on_tiny_set` — same fixture, verify `metrics["test_log_loss"] < metrics["naive_test_log_loss"]`.

**Commit:** `feat(models): add baseline XGBoost trainer + CLI`.

---

# Task 6 — real training run + acceptance + phase docs + tag

**Steps:**

1. Gate 1a: `uv run pytest -q` — expect ~180 tests passing (adds ~18 from Phases 4-4 tests).
2. Gate 1b: coverage on `src/models/` ≥80% (not counting untested plot code paths).
3. Gate 1c: `uv run ruff check .` clean.
4. **Real training run:**
   ```bash
   uv run python -u -m src.models.train 2>&1 | tee reports/phase4_training.log
   ```
   Expected wall time: 2-15 min on a laptop (500 estimators × ~500k rows × 100 features).
5. Inspect output:
   - Best iteration (should be <500 with early stopping)
   - `test_log_loss`, `test_brier`, `test_auc`, `test_precision_at_top_20`
   - `naive_test_log_loss` for comparison
6. Check artifact:
   - `ls src/models/registry/v*/` — all required files present
   - Review `eval_report.md` in the artifact dir
7. Walk through `phases/phase4/ACCEPTANCE.md` — tick boxes with actual numbers.
8. Write `phases/phase4/RESULTS.md` with:
   - Final test metrics
   - Best-iteration / training time
   - Top 10 features by SHAP + by gain
   - Naive baseline delta
   - Reliability curve summary (pre-calibration — expected to need Phase 5)
9. Write `phases/phase4/NOTES.md` with:
   - Any hyperparameter observations worth noting
   - Distribution shift findings (pre-/post-2024 bat_speed gap, weather-only-post-Phase-3.5, etc.)
   - Feature-importance surprises (expected vs observed)
10. Populate `src/models/overview.md`.
11. Update `abstract.md` — mark Phase 4 complete, add Phase 4 decisions block.
12. Commit: `docs(phase4): mark phase 4 complete, record results`.
13. **Do NOT tag `phase-4-complete` yourself** — controller reviews results first, then tags.

**STOP condition (PROMPT § "STOP condition"):** report train/val/test log loss + Brier, top-10 SHAP features, naive baseline comparison, any distribution shift concerns, total training time.

---

## Self-review

- **Every PROMPT deliverable maps to a task:** modules (1-5), tests (1-5), real training + artifacts + docs (6). ✅
- **Non-negotiables addressed:** no random shuffling (Task 1 + test), git SHA + data hash (Task 4), seeded everywhere (Task 5 config), naive baseline (Task 5), atomic artifacts (Task 4). ✅
- **Unknowns flagged:** FEATURE_COLUMNS selection strategy, NULL handling via XGBoost native, precision_at_top_k "per day" semantics, artifact version format. ✅

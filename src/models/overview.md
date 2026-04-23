# models

## Purpose
Baseline XGBoost binary classifier for per-plate-appearance home-run probability, plus the evaluation + artifact-versioning framework that every future model swap will reuse. Phase 5 adds isotonic post-hoc calibration (`calibrate.py`), the per-PA probability sequence builder (`pa_sequence.py`) that turns one matchup row into PA-by-PA probabilities (TTO for PAs 1–3, bullpen-adjusted for PAs 4+), and the Poisson-binomial per-game roll-up (`rollup.py`) that maps PA-level probabilities to P(≥1), P(≥2), P(≥3), and the full PMF. Runs offline against the Phase 3 `matchup_features` store; emits a versioned artifact bundle (model binary + calibrator + schema + metrics + plots + eval report) into `src/models/registry/v{YYYYMMDD_HHMMSS}/`.

Scope boundary: **no API** (Phase 6), **no daily inference pipeline** (Phase 6+).

## Entry points

- **`train.py`** — orchestrator. `train_baseline(config: TrainingConfig | None = None, ...) -> TrainingResult` runs the full pipeline: load → time-based split → fit XGBoost → predict → compute metrics → render plots → persist artifact. CLI wrapper `python -m src.models.train` uses defaults.
- **`data.py`** — feature loading + split. `load_training_data(start_date, end_date, *, engine=None) -> FeatureFrame` pulls `matchup_features` WHERE `is_historical=True AND hr_on_pa IS NOT NULL`. `time_based_split(engine=None) -> TrainValTest` materializes the three fixed-date frames. `FEATURE_COLUMNS: list[str]` is the single source of truth for column order.
- **`eval.py`** — pure-function metrics + matplotlib plotters. `log_loss`, `brier_score`, `expected_calibration_error`, `reliability_curve`, `precision_at_top_k` (per-day semantics), `auc`, `naive_baseline_log_loss`, plus `plot_reliability`, `plot_feature_importance`, `plot_shap_summary`, `plot_prediction_histogram`.
- **`artifacts.py`** — versioned persistence. `save_model(...) -> Path`, `load_model(version=None) -> LoadedModel`, `list_versions() -> list[ModelVersion]`, `promote_to_production(version)`, `compute_data_hash(X, y)`. Version IDs are `v{YYYYMMDD_HHMMSS}` (UTC). Production pointer is a plain-text file `registry/PRODUCTION` (not a symlink — Windows friendly).
- **`calibrate.py`** — isotonic post-hoc calibrator. `fit_calibrator(val_probs, val_labels) -> IsotonicRegression`, `apply_calibrator(cal, raw_probs) -> ndarray`, `save_calibrator(cal, version) -> Path`, `load_calibrator(version) -> IsotonicRegression`. Calibrator lives at `src/models/registry/v{version}/calibrator.joblib` — co-located with the model to prevent version-mixing bugs.
- **`pa_sequence.py`** — per-PA probability sequence for a matchup. `build_pa_probability_sequence(PaSequenceInputs) -> list[float]` takes a single calibrated per-PA base probability plus TTO / bullpen context columns and emits one probability per projected PA (TTO scaling for PAs 1–3 from `tto_multiplier`; clipped bullpen ratio for PAs 4+). Single-inference + scalar-adjustment design (see `phases/phase5/NOTES.md` for the rationale; per-PA feature-row regeneration would be out-of-distribution).
- **`rollup.py`** — exact Poisson-binomial PMF + per-game rollup. `poisson_binomial_pmf(probs) -> list[float]` via direct convolution (O(n²), n ≤ 10 in baseball); `per_game_probability(probs) -> GameHRDistribution` exposes `prob_at_least_one`, `prob_at_least_two`, `prob_at_least_three`, `expected_hrs`, and `pmf`. No Poisson approximation — per-PA probs vary enough across starter/bullpen that the Poisson assumption breaks.

## Public interface

Most-common imports for other modules (Phase 6 API, inference pipelines):

```python
from src.models.artifacts import load_model, LoadedModel, list_versions, promote_to_production
from src.models.data import FEATURE_COLUMNS, FeatureFrame, load_training_data, time_based_split
from src.models.eval import log_loss, brier_score, expected_calibration_error, precision_at_top_k
from src.models.train import TrainingConfig, TrainingResult, train_baseline
from src.models.calibrate import fit_calibrator, apply_calibrator, save_calibrator, load_calibrator
from src.models.pa_sequence import PaSequenceInputs, build_pa_probability_sequence
from src.models.rollup import per_game_probability, poisson_binomial_pmf, GameHRDistribution
```

`LoadedModel` exposes `.model` (XGBoost Booster), `.feature_schema` (ordered list of 120 feature names), `.metadata` (git_sha, data_hash, config, training_range), `.metrics`.

**Standard inference pipeline** (Phase 6 onward):

```python
loaded = load_model()                          # latest or version=...
cal = load_calibrator(loaded.version)          # co-located with model
dmat = xgboost.DMatrix(X.values, feature_names=loaded.feature_schema)
raw = loaded.model.predict(dmat)
calibrated = apply_calibrator(cal, raw)        # per-PA HR probability
# then for each matchup row: build_pa_probability_sequence(...) → per_game_probability(...)
```

## Internal dependencies

- `src.core.db.get_engine` — SQLAlchemy engine (defaults to docker-compose Postgres).
- `src.core.models.MatchupFeature` — ORM class. **`FEATURE_COLUMNS` is enumerated from this class at import time**, so schema changes to `matchup_features` propagate automatically (see Gotchas).
- External: `xgboost` 2.x (sklearn wrapper + Booster), `shap`, `matplotlib`, `pandas`, `numpy`, `pydantic` v2.

## Data layout

- **Train:** `game_date ∈ [2021-04-01, 2023-10-31]`, 388,320 rows.
- **Val:**   `game_date ∈ [2024-04-01, 2024-10-31]`, ~115 k rows.
- **Test:**  `game_date ∈ [2025-04-01, last-available]`, ~140 k rows on 2026-04-22.
- Splits are **strictly time-based, never shuffled**. `time_based_split` returns three `FeatureFrame`s with aligned `X`, `y`, `dates`, `metadata`.

## Artifact layout per version

```
src/models/registry/v{YYYYMMDD_HHMMSS}/
├── model.xgb                  # Booster in UBJSON (xgboost 2.x default)
├── calibrator.joblib          # isotonic post-hoc calibrator (Phase 5; added strictly-additive)
├── feature_schema.json        # ordered feature names + dtypes
├── training_metadata.json     # git_sha, data_hash, config, training_range, num_features
├── metrics.json               # flat dict: train/val/test × {log_loss, brier, auc, ece}, precision@k, naive_*
├── reliability.png            # train/val/test overlay
├── feature_importance.png     # top 30 by gain
├── shap_summary.png           # best-effort; may be absent if SHAP errored (logged)
├── prediction_histogram.png   # train/val/test density
└── eval_report.md             # human-readable summary
```

`registry/` is gitignored. A plain-text `registry/PRODUCTION` file (optional) points at the currently-promoted version.

## Gotchas

- **`FEATURE_COLUMNS` is enumerated at module-load time** from `MatchupFeature`. Excluded columns: `game_date`, `game_pk`, `batter_id`, `pitcher_id` (keys), `hr_on_pa` (label), `is_historical` (flag), `built_at` (audit), and two string columns (`p_primary_pitch`, `ctx_day_night`). Add a new numeric feature column to the ORM and it's automatically in `FEATURE_COLUMNS` — no manual update. Currently 120 features.
- **NaN handling is native XGBoost**, not imputed. Bat-tracking (`b_avg_bat_speed`, `b_squared_up_pct`, `b_blast_rate`) is NaN pre-2024; weather is NaN at exhibition venues; retractable-roof context can be NaN. Don't re-enter imputation logic — XGBoost learns a default split direction per feature.
- **`precision_at_top_k` is "per-day":** for each `game_date` in the eval set, rank preds, take top K (default 20), count hits. Average across days. K=20 ≈ "a slate of 20 prop bets" — tunable via `TrainingConfig.top_k_per_day`.
- **Naive baseline** is a constant equal to `mean(y_train)` (train-set HR rate, currently 0.0465). `log_loss(y_any, naive)` is the floor every model must beat by ≥ 5 % relative.
- **`scale_pos_weight=None`** in `TrainingConfig` **auto-computes** to `n_neg/n_pos` (~20 on this data). **This is a calibration trap** — it destroys probability quality even while modestly improving AUC. See `phases/phase4/NOTES.md` for the diagnosis. Phase 5 (or a Phase-4 amendment) should pin `scale_pos_weight=1.0`.
- **SHAP can fail** on new XGBoost releases (sklearn-wrapper `feature_names_in_` collision). `train_baseline` logs a warning and continues; the artifact may ship without `shap_summary.png`. Gain-based feature importance covers the same decisions.
- **Early stopping only fires on val-loss plateau-then-degradation.** If val loss is monotonically rising from iter 0 (as in the miscalibrated baseline), `best_iteration = n_estimators − 1` is not actually "best" — it's "last." Check the saved metrics and the reliability plot before trusting `best_iteration`.
- **Model file is named `model.xgb`** but XGBoost 2.x writes UBJSON by default. `load_model` uses the `Booster.load_model(path)` auto-detect; a warning `Unknown file format: 'xgb'. Using UBJSON (ubj) as a guess.` on load is expected and harmless.
- **Determinism:** `random_seed=42` flows to python `random`, `numpy`, XGBoost `random_state`. `PYTHONHASHSEED` is **not** set (makes tests fragile) — the models pipeline avoids hash-dependent ops.
- **`save_model` is atomic-ish**: plots are written into a `tempfile.TemporaryDirectory`, then copied into the version dir in one pass. Partial saves should not appear on disk.
- **Calibrator is strictly additive inside the version dir.** `save_calibrator` never overwrites `model.xgb` or `training_metadata.json`; it only writes `calibrator.joblib`. Safe to re-fit and re-save without invalidating the model artifact. The `IsotonicRegression` is fit with `out_of_bounds="clip"` so test-time raw probabilities outside the val-observed range clip to the nearest endpoint (no silent extrapolation).
- **Isotonic caps the calibrated range.** On this data the calibrated per-PA probability maxes out at ~0.222 (val's observed right tail). Downstream callers should expect clustering at that cap for the highest-raw matchups; it's isotonic's piecewise-constant behavior, not a bug.
- **`build_pa_probability_sequence` divides `base_prob` by `p_tto_penalty`** to recover a "pure" per-PA prob before re-applying per-PA multipliers. `base_prob` is assumed to be the model's prediction on the matchup feature row (which already has `p_tto_penalty` as a weighted-average starter multiplier baked in). The default TTO penalty (1.0833, the training-data constant) is used when the row's `p_tto_penalty` is missing.
- **Bullpen adjustment is clipped to [0.5, 2.0]** — see `_BULLPEN_ADJ_MIN` / `_BULLPEN_ADJ_MAX` in `pa_sequence.py` and the rationale in `phases/phase5/NOTES.md`. Without the clip, an extreme starter-vs-bullpen HR/9 ratio (e.g., Pressly) would yield physically-implausible 3×+ scaling on PA4 probs.
- **`poisson_binomial_pmf` is exact, not approximate.** O(n²) convolution on n ≤ 10 PAs is ~instant (<0.1ms per matchup in Python). The Poisson approximation is tempting but wrong here: per-PA probabilities vary enough (TTO multipliers, bullpen transition) that the Poisson mean-equals-variance assumption breaks.

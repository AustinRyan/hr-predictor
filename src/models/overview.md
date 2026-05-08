# models

## Purpose
Baseline XGBoost binary classifier for per-matchup (batter × pitcher × game) home-run probability, plus the evaluation + artifact-versioning framework that every future model swap will reuse. Phase 5 adds isotonic post-hoc calibration (`calibrate.py`), per-game composition of per-matchup probabilities (`per_game_hr.py`) via the independent-matchups formula `P(HR in game) = 1 - ∏(1 - P_matchup_i)`, and the Poisson-binomial machinery (`rollup.py`) that provides the exact PMF + `P(≥1)`, `P(≥2)`, `P(≥3)` breakdown used by the composition. Runs offline against the Phase 3 `matchup_features` store; emits a versioned artifact bundle (model binary + calibrator + schema + metrics + plots + eval report) into `src/models/registry/v{YYYYMMDD_HHMMSS}/`.

Scope boundary: **no API** (Phase 6), **no daily inference pipeline** (Phase 6+).

## Entry points

- **`train.py`** — orchestrator. `train_baseline(config: TrainingConfig | None = None, ...) -> TrainingResult` runs the full pipeline: load → time-based split → fit XGBoost → predict → compute metrics → render plots → persist artifact. CLI wrapper `python -m src.models.train` uses defaults.
- **`data.py`** — feature loading + split. `load_training_data(start_date, end_date, *, engine=None) -> FeatureFrame` pulls `matchup_features` WHERE `is_historical=True AND hr_on_pa IS NOT NULL`. `time_based_split(engine=None) -> TrainValTest` materializes the three fixed-date frames. `FEATURE_COLUMNS: list[str]` is the single source of truth for column order.
- **`full_game_data.py`** — full-game target loading + split.
  `load_full_game_training_data(start_date, end_date, *, engine=None) ->
  FullGameFeatureFrame` returns one row per batter-game, using the starter
  matchup row as the feature snapshot and labeling whether the batter homered
  anywhere in the game. `full_game_time_based_split(engine=None)` mirrors the
  project train/val/test date windows.
- **`eval.py`** — pure-function metrics + matplotlib plotters. `log_loss`, `brier_score`, `expected_calibration_error`, `reliability_curve`, `precision_at_top_k` (per-day semantics), `auc`, `naive_baseline_log_loss`, plus `plot_reliability`, `plot_feature_importance`, `plot_shap_summary`, `plot_prediction_histogram`.
- **`artifacts.py`** — versioned persistence. `save_model(...) -> Path`, `load_model(version=None) -> LoadedModel`, `list_versions() -> list[ModelVersion]`, `promote_to_production(version)`, `compute_data_hash(X, y)`. Version IDs are `v{YYYYMMDD_HHMMSS}` (UTC). `load_model()` honors the plain-text `registry/PRODUCTION` pointer first, falling back to newest directory only when no pointer exists.
- **`calibrate.py`** — isotonic post-hoc calibrator. `fit_calibrator(val_probs, val_labels) -> IsotonicRegression`, `apply_calibrator(cal, raw_probs) -> ndarray`, `save_calibrator(cal, version) -> Path`, `load_calibrator(version) -> IsotonicRegression`. Calibrator lives at `src/models/registry/v{version}/calibrator.joblib` — co-located with the model to prevent version-mixing bugs.
- **`per_game_hr.py`** — per-game composition of per-matchup probabilities. `per_game_hr_distribution(GameMatchupInputs) -> GameHRDistribution` composes the starter-matchup probability (and optionally a bullpen-matchup probability) into a game-level distribution via the independent-matchups formula. Phase 3's label `hr_on_pa` is per-(batter, pitcher, game), so the model's calibrated output is already a per-matchup game-level probability — no PA-level compounding is applied. Replaces the original `pa_sequence.py` (see `phases/phase5/NOTES.md` "Rollup semantic bug" for the fix narrative).
- **`rollup.py`** — exact Poisson-binomial PMF + per-game distribution. `poisson_binomial_pmf(probs) -> list[float]` via direct convolution (O(n²), near-instant for the small inputs we feed it); `per_game_probability(probs) -> GameHRDistribution` exposes `prob_at_least_one`, `prob_at_least_two`, `prob_at_least_three`, `expected_hrs`, and `pmf`. The math is unchanged from the original Phase 5 implementation — it's correct for combining any independent-event probabilities; `per_game_hr.py` now feeds it 1–2 per-matchup probabilities instead of the originally-incorrect 4 per-PA copies.
- **`odds.py`** — pure sportsbook math helpers: American odds to implied
  probability, fair American odds, model-vs-market edge, and one-unit EV.
  Used by `/picks/today` after PropLine snapshots are persisted.

## Public interface

Most-common imports for other modules (Phase 6 API, inference pipelines):

```python
from src.models.artifacts import load_model, LoadedModel, list_versions, promote_to_production
from src.models.data import FEATURE_COLUMNS, FeatureFrame, load_training_data, time_based_split
from src.models.full_game_data import (
    FULL_GAME_FEATURE_COLUMNS,
    FullGameFeatureFrame,
    full_game_time_based_split,
    load_full_game_training_data,
)
from src.models.eval import log_loss, brier_score, expected_calibration_error, precision_at_top_k
from src.models.train import TrainingConfig, TrainingResult, train_baseline
from src.models.calibrate import fit_calibrator, apply_calibrator, save_calibrator, load_calibrator
from src.models.per_game_hr import GameMatchupInputs, per_game_hr_distribution
from src.models.rollup import per_game_probability, poisson_binomial_pmf, GameHRDistribution
from src.models.odds import american_to_implied_probability, expected_value_per_unit
```

`LoadedModel` exposes `.model` (XGBoost Booster), `.feature_schema` (ordered list of 118 production feature names), `.training_metadata` (git_sha, data_hash, config, training_range), `.metrics`.

**Standard inference pipeline** (Phase 6 onward):

```python
loaded = load_model()                          # PRODUCTION or version=...
cal = load_calibrator(loaded.version)          # co-located with model
dmat = xgboost.DMatrix(X.values, feature_names=loaded.feature_schema)
raw = loaded.model.predict(dmat)
calibrated = apply_calibrator(cal, raw)        # per-matchup (per batter-pitcher-game) HR probability
# then for each matchup row: per_game_hr_distribution(GameMatchupInputs(starter_prob=calibrated[i]))
# when a bullpen prediction is available (Phase 6+): pass bullpen_prob=... to combine via 1 - (1-P_s)(1-P_b).
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

- **`FEATURE_COLUMNS` is enumerated at module-load time** from `MatchupFeature`. Excluded columns: `game_date`, `game_pk`, `batter_id`, `pitcher_id` (keys), `hr_on_pa` (label), `is_historical` (flag), `built_at` (audit), two string columns (`p_primary_pitch`, `ctx_day_night`), and the two leaky rest-day diagnostics. Add a new numeric feature column to the ORM and it's automatically in `FEATURE_COLUMNS` for future training runs — no manual update. Currently 118 features.
- **`FULL_GAME_FEATURE_COLUMNS` excludes `opp_team_id`.** The full-game model
  keeps the numeric bullpen-strength fields (`opp_bp_*`) but drops the raw team
  identifier to avoid treating MLBAM team IDs as ordered numeric signal.
- **Inference uses the artifact schema, not live `FEATURE_COLUMNS`.** `generate_predictions_for_date` validates every saved feature name exists on `matchup_features`, then selects/builds the frame in exactly that artifact order. This prevents a new ORM feature column from silently reshaping an older production model.
- **Inference defensively ranks future duplicates.** If stale future
  `matchup_features` rows exist for the same `(game_pk, batter_id)`, the
  query keeps the newest `built_at` row before prediction upsert. The feature
  builder should prune these first, but inference still guards the predictions
  table's unique `(game_pk, batter_id, model_version)` constraint.
- **Inference prunes stale current-slate predictions.** After lineup or
  probable-starter changes, players can disappear from the current feature
  set. `generate_predictions_for_date` deletes old rows for the same
  `(game_date, model_version)` before upserting the fresh slate so the UI does
  not show abandoned picks from an earlier refresh.
- **Production pointer is authoritative.** `load_model()` now loads `registry/PRODUCTION` when present; newest-directory fallback exists only for fresh local registries/tests.
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
- **Isotonic caps the calibrated range.** On this data the calibrated per-matchup probability maxes out at ~0.222 (val's observed right tail). Downstream callers should expect clustering at that cap for the highest-raw matchups; it's isotonic's piecewise-constant behavior, not a bug.
- **Use raw score only as a tie-breaker.** `matchup_components.starter_raw_prob`
  is the pre-calibration ensemble score. It is useful for deterministic
  ordering inside isotonic probability plateaus, but the headline
  probability and fair odds must use the calibrated `prob_at_least_one_hr`.
- **`per_game_hr_distribution` does not compound per-PA.** The model's calibrated output is already a per-matchup game-level probability (Phase 3 `hr_on_pa` is per-batter-pitcher-game, not per-PA). With only a starter prediction, `P(≥1 HR) == starter_prob`. With both starter and bullpen predictions, they combine via `1 - (1 - P_s)(1 - P_b)`. See `phases/phase5/NOTES.md` "Rollup semantic bug — fixed post-tag" for the history behind this correction.
- **`poisson_binomial_pmf` is exact, not approximate.** Reused by `per_game_hr_distribution` to produce the full PMF over 1–2 per-matchup probabilities (starter + optional bullpen). O(n²) convolution with small n is effectively free. The math works for any independent-Bernoulli composition; it's the same tool whether you feed it per-PA probabilities or per-matchup probabilities.

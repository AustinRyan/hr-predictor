# Phase 5 — Calibration + Per-Game Rollup

## Required reading
1. `./CLAUDE.md`
2. `./MASTER_PLAN.md` — Phase 5 section
3. `./abstract.md` — Phases 0–4 complete
4. `./src/models/overview.md`, `./phases/phase4/RESULTS.md`

---

## Objective
Two things:
1. **Calibrate** the Phase 4 XGBoost model so predicted probabilities match observed frequencies. Target: ECE < 0.03 on test set.
2. **Roll up per-PA probabilities to per-game probabilities** using the Poisson binomial formula. This is what the UI will actually display.

**Scope boundary:** Calibration + rollup + optional ensemble. No inference pipeline (Phase 6+). No API.

---

## Deliverables

### 1. Calibration module (`src/models/calibrate.py`)

Use `sklearn.isotonic.IsotonicRegression` (better than Platt for tree ensembles).

Functions:

```python
def fit_calibrator(val_probs: np.ndarray, val_labels: np.ndarray) -> IsotonicRegression:
    """Fit isotonic calibrator on validation set predictions."""

def apply_calibrator(calibrator: IsotonicRegression, raw_probs: np.ndarray) -> np.ndarray:
    """Transform raw model probabilities into calibrated ones."""

def save_calibrator(calibrator, model_version: str) -> Path:
    """Persist next to the model artifact."""

def load_calibrator(model_version: str) -> IsotonicRegression:
    """Load from artifact directory."""
```

Workflow:
1. Load Phase 4 model
2. Predict on validation set → raw probs
3. Fit isotonic on (raw_probs, true_labels)
4. Save calibrator to `src/models/registry/v{version}/calibrator.joblib`
5. Predict on test set, apply calibrator, measure post-calibration ECE
6. Generate pre/post reliability diagrams for comparison

### 2. Per-game rollup (`src/models/rollup.py`)

Given per-PA probabilities `p_1, p_2, ..., p_n` for a batter's expected PAs in a game, compute:

- **P(≥1 HR):** `1 - ∏(1 - p_i)`
- **P(exactly k HR):** Poisson binomial PMF
- **E[HR]:** `∑ p_i`

For prop bets, P(≥1) is the primary output. Also expose P(≥2), P(≥3) for "multi-HR" prop markets.

```python
def per_game_probability(per_pa_probs: list[float]) -> GameHRDistribution:
    """Returns named tuple/dataclass with:
        - prob_at_least_one: float
        - prob_at_least_two: float
        - prob_at_least_three: float
        - expected_hrs: float
        - pmf: list[float]  # P(HR=0), P(HR=1), ...
    """
```

Poisson binomial PMF implementation: use direct convolution for small n (≤ 10 PAs max in baseball), which is exact and fast. Do not approximate with Poisson distribution — the per-PA probabilities can vary enough that Poisson is a poor fit.

```python
def poisson_binomial_pmf(probs: list[float]) -> list[float]:
    """Exact PMF via convolution. O(n²) but n ≤ 10 so it's instant."""
    pmf = [1.0]
    for p in probs:
        new_pmf = [0.0] * (len(pmf) + 1)
        for i, v in enumerate(pmf):
            new_pmf[i] += v * (1 - p)
            new_pmf[i + 1] += v * p
        pmf = new_pmf
    return pmf
```

### 3. Projected PA count + pitcher transition modeling

A batter's per-PA probability changes across the game as the pitcher changes (starter → bullpen). Handle this:

```python
def build_pa_probability_sequence(matchup: MatchupFeatures, n_projected_pas: float) -> list[float]:
    """Given a matchup, return a list of per-PA HR probabilities reflecting:
    - Starter TTO adjustments for PAs 1-3
    - Transition to bullpen for PAs 4+
    Returns list of length round(n_projected_pas).
    """
```

For each projected PA slot (1st, 2nd, 3rd, 4th, ...), generate the feature row and run the model. PAs 1–3 use starter features with TTO multiplier; PAs 4+ use bullpen-adjusted features.

The model runs multiple times per matchup (once per PA slot). Cache projection features for efficiency.

### 4. Optional: Simple ensemble (`src/models/ensemble.py`)

Only if XGBoost baseline doesn't hit the acceptance criteria, add:
- LightGBM with same features, different hyperparameters
- Logistic regression with interaction terms (baseline for diversity)
- Simple average or stacked LR meta-learner

Controlled by a config flag. Default off. If enabled, train all base models, fit a stacking meta-model on validation fold, calibrate the stacked output.

Document in `phases/phase5/NOTES.md` whether ensemble was needed and what the delta was.

### 5. Integration: updated eval report

Extend the Phase 4 eval report to include:
- Pre-calibration vs post-calibration reliability diagrams (overlay)
- Pre-calibration vs post-calibration ECE and log loss
- Per-game probability distribution: histogram of P(≥1 HR) across all games in test set
- Sanity: identify the test-set game with the highest P(≥1 HR) prediction. It should be someone like Judge/Stanton/Alvarez in a homer park with good weather. If it's a random backup catcher, something's broken.

### 6. Tests

- `tests/models/test_calibrate.py`:
  - Isotonic fits monotonically increasing
  - Applied to validation set, achieves lower ECE than raw
  - Roundtrip save/load works
- `tests/models/test_rollup.py`:
  - `poisson_binomial_pmf([0.5, 0.5])` returns `[0.25, 0.5, 0.25]` (exact Pascal's triangle)
  - `poisson_binomial_pmf([0.1]*4)` returns expected values verified against scipy if available
  - Edge cases: empty list, single PA, all zeros, all ones
  - P(≥1) + P(0) = 1

### 7. Phase docs

- `phases/phase5/ACCEPTANCE.md`
- `phases/phase5/NOTES.md` — document whether ensemble was needed, any calibration surprises
- `phases/phase5/RESULTS.md` — final calibrated metrics
- Update `src/models/overview.md`

---

## Acceptance checklist

```markdown
# Phase 5 — Acceptance Checklist

## Calibration
- [ ] Isotonic calibrator fit on validation set
- [ ] Post-calibration test-set ECE < 0.03
- [ ] Post-calibration reliability curve visibly closer to diagonal than pre-calibration
- [ ] Post-calibration log loss on test set is ≤ pre-calibration log loss (calibration shouldn't hurt; if it does, something's wrong)
- [ ] Calibrator persists and loads correctly

## Per-game rollup
- [ ] `per_game_probability` returns values where P(≥1) + P(0) ≈ 1.0 (floating-point tolerance)
- [ ] `poisson_binomial_pmf` passes all test cases
- [ ] For a known test-set game with 4 projected PAs at 0.05 per-PA probability: P(≥1) ≈ 0.185 (1 - 0.95^4)
- [ ] `build_pa_probability_sequence` produces increasing p for PAs 1→3 (TTO penalty) when facing an average starter

## Sanity: the "it works" test
- [ ] Highest P(≥1 HR) in test-set predictions belongs to a known elite slugger in a homer-friendly context
- [ ] Lowest P(≥1 HR) belongs to a weak hitter facing an ace in a pitcher's park
- [ ] Per-game probability for a superstar on an ideal day (hot, wind-out, Coors-caliber park) is ≥ 0.35
- [ ] Per-game probability for a weak hitter facing an ace in a pitcher's park with cold/headwind weather is ≤ 0.03

## Optional ensemble
- [ ] If enabled: ensemble test-set log loss beats single-model log loss by ≥2%
- [ ] If disabled: documented in NOTES.md why it wasn't needed

## Tests
- [ ] `uv run pytest tests/models -v` all pass
- [ ] Coverage on new code ≥80%

## Docs
- [ ] `phases/phase5/RESULTS.md` shows pre/post calibration metrics
- [ ] `src/models/overview.md` updated with calibration and rollup module docs
- [ ] `abstract.md` shows Phase 5 complete
```

---

## Non-negotiables

- **Calibration fits on validation, evaluates on test.** Fitting on test is data leakage.
- **Post-calibration ECE < 0.03 is the hard bar.** If we can't hit that, the model isn't ready for betting decisions. Escalate to the user before proceeding.
- **Exact Poisson binomial PMF.** No Poisson approximation. N is small.
- **Per-game probability is the product of per-PA model calls.** Each PA slot gets its own model inference with correct features (TTO for starter, bullpen features for late innings).

---

## Post-phase ritual

1. `uv run pytest -q` → green
2. Full calibration pipeline runs end-to-end
3. Acceptance checklist walked
4. Update docs
5. Commit + tag `phase-5-complete`

---

## STOP condition

Do not start Phase 6 (API) without approval. Report:
1. Pre/post calibration ECE and log loss
2. The highest and lowest test-set predictions with player/context (sanity narrative)
3. Whether ensemble was used

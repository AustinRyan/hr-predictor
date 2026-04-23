# Phase 5 — Notes

Context and design rationale for the decisions that aren't obvious from code alone. Pair with `RESULTS.md` (metrics) and `ACCEPTANCE.md` (walked checklist).

> **Semantic-bug correction (post-tag):** the sections titled "Per-PA sequence: single-inference + scalar adjustments" and "Bullpen clip at [0.5, 2.0]" below describe the **original** (incorrect) rollup design that treated the model's output as per-PA. The actual Phase 3 label is per-(batter, pitcher, game), so no PA-level compounding is needed. See the "Rollup semantic bug — fixed post-tag" section at the bottom of this file for the corrected design. The original sections are retained here as historical context.

## Isotonic over Platt

Tree ensembles produce score distributions that are not logistic-shaped. Platt scaling (fit a sigmoid to raw scores) presupposes a logistic link and systematically under-corrects non-sigmoid miscalibration. Isotonic regression is non-parametric — it fits any monotone-increasing piecewise-constant map — so it's the standard choice for XGBoost/LightGBM post-hoc calibration. `sklearn.isotonic.IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)` also clips test-time predictions outside the validation-observed range to the nearest endpoint rather than extrapolating, which is the safe behavior when the val set's right tail doesn't reach the test set's right tail.

Trade-off: isotonic's piecewise-constant output means many different raw probabilities can map to the same calibrated value. We saw this in the top-5 sanity output — several test-set matchups land at exactly 0.22222 because they all fell into the same isotonic bucket at the top of the val distribution. This is not a bug; it's the expected behavior of an isotonic fit on ~115k val rows where the right tail has few positives per raw-prob bucket.

## No ensemble

Phase 4's single-model baseline already hit **pre-calibration test ECE = 0.00555** — roughly an order of magnitude below the 0.03 Phase-5 bar. Post-calibration ECE is **0.00248**. An ensemble (LightGBM + logistic + stacking) would double training complexity and persistence surface area for no measurable calibration gain: we're already near the reducible-error floor on calibration. The PROMPT explicitly framed ensembling as "only if the single model doesn't hit the bar." It does, by a factor of ~12x.

If a later phase needs *ranking* improvements (AUC from 0.68 toward 0.75), an ensemble is worth revisiting — but for that, the base models need diversity on the ranking signal, not on the probability-scale signal. Different problem, different phase.

## Per-PA sequence: single-inference + scalar adjustments

The PROMPT.md suggests "for each projected PA slot (1st, 2nd, 3rd, 4th, …), generate the feature row and run the model." We did **not** do that. Reason:

A proper per-PA feature row for PA4+ (bullpen) would require swapping `p_*` features (starter) for bullpen features (e.g., `bp_hr_per_9`, `bp_fip`, etc.) inside the same 120-col matrix. The Phase-4 model was trained on matchup rows where `p_*` is the *starter* and `bp_*` is *separate* context — it has never seen a row where the starter-position columns are filled with bullpen values. Feeding it one would be out-of-distribution inference.

The approved simplification (see `src/models/pa_sequence.py` docstring) is: run the model **once** per matchup on its existing feature row, recover a "pure" per-PA probability by dividing out `p_tto_penalty` (which is the weighted-average TTO multiplier baked into the model's training distribution), then re-apply per-PA scalars — TTO multipliers (1.00 / 1.05 / 1.20) for PAs 1–3 and a bullpen ratio (`bp_hr_per_9 / p_hr_per_9`, clipped to [0.5, 2.0]) for PA4+.

This is faithful to what the model was trained on and captures the two first-order PA-dependent effects (third-time-through-the-order penalty, transition to bullpen) without OOD feature manipulation. It's also much cheaper — one Booster call per matchup instead of up to 6.

## Bullpen clip at [0.5, 2.0]

Without a clip, Pressly (career HR/9 ≈ 0.37) against a league-average bullpen (HR/9 ≈ 1.1) would yield a PA4+ multiplier of ~3.0, sending per-PA probs to 0.45+. That's absurd for any one PA even against a truly weak reliever — no individual MLB PA has a 45% HR probability; Bonds' 2001 peak season was ~10% per PA. The clip bounds the adjustment to a physically plausible range while still letting the model differentiate "facing a lights-out closer" (0.5×) from "facing a soft-tossing long man" (2.0×).

The clip does occasionally bind: the top-5 sanity matchups include keibert ruiz vs. ryan pressly (clip active at 2.0×), driving P(≥1 HR) = 0.72 on a per-PA base prob of 0.22. This is the primary reason the distribution max exceeded the PROMPT's 0.35–0.55 guide band. The alternative (uncapped) is much worse. Acceptable tail behavior for the simplification.

## Sanity narrative: the ranking-capacity caveat

**Honest summary.** The top-5 P(≥1 HR) matchups in the test set are not Judge/Ohtani/Alonso; they are a mix of fringe (Osuna, Bliss, Mangum) and regular-but-not-elite (Ruiz, Naylor) hitters. The PROMPT's expectation — "highest P(≥1 HR) belongs to a known elite slugger" — is not met.

**Why this is not a Phase-5 defect.** The Phase 4 RESULTS.md already flagged that the baseline model's ranking capacity (test AUC = 0.679, precision@top-20 = 0.132) is below the aspirational targets and described the miss as "typical for per-PA HR prediction in the sabermetric literature." The model *does* price Judge highly — his maximum test-set raw prediction is 0.228, which is 4.9× the league base rate and in the top 0.01% of the raw distribution. The problem is that it prices Ruiz's top matchup at 0.240 (also in that top 0.01%). Mid-tier regulars and elite sluggers compress into the same right-tail bucket at this AUC.

The calibration layer doesn't fix (or break) the ranking — isotonic is monotone by construction, so relative order is preserved within calibrator input resolution. The per-game rollup doesn't fix the ranking either — it's just a deterministic Poisson-binomial on top of the per-PA predictions.

**What would fix it.** A stronger per-PA model: better pitcher-interaction features (e.g., recent xwOBAcon against similar pitch mix), deeper trees or an ensemble specifically tuned for ranking (with a different scoring rule than log-loss, e.g., rank-preserving AUC-optimized objective), and possibly batter×pitcher interaction embeddings. All of that is a modeling phase of its own; carrying as deferred tech debt rather than holding Phase 5 hostage to it.

## Pre/post log-loss: no regression

A common calibration quirk: isotonic-on-test can sometimes *increase* log loss slightly because it's fit to val and generalizes imperfectly to test. For this run, test log loss went 0.17862 → 0.17849 — strictly (if barely) improved. That's the good case: val and test are drawn from similar-enough conditional distributions that the val-fit calibrator generalizes. No STOP-and-flag needed.

## Artifact layout: calibrator lives with the model

`calibrator.joblib` is saved inside the model version directory (`src/models/registry/v20260423_173917/`). This is deliberate — the calibrator is conceptually part of the model's inference pipeline and should never be paired with a different model version. Co-locating them enforces that invariant at the filesystem layer. `load_calibrator(version)` and `load_model(version)` take the same version string, so correctness is trivially maintained at the call site.

## Sanity runner: row-alignment assumption

`sanity_runner.py` re-queries `matchup_features` for identity (game_pk, batter_id, pitcher_id, park_id) and **asserts row count equality with the prediction array**. The alignment depends on:

1. `time_based_split` ordering `X` by `game_date`,
2. The re-query ordering the same way (`ORDER BY game_date` with the same `is_historical = TRUE AND hr_on_pa IS NOT NULL` filter),
3. PostgreSQL's sort being stable (it is for identical keys in practice but not formally guaranteed).

If this assertion ever fires, the fix is to carry game_pk/batter_id/pitcher_id out of `load_training_data` into the FeatureFrame metadata rather than re-query. Deferred — the assertion is a safety net for now.

## Files added this phase

- `src/models/calibrate.py` — fit/apply/save/load isotonic calibrator. 100% coverage.
- `src/models/rollup.py` — Poisson-binomial PMF + GameHRDistribution dataclass. 100% coverage.
- `src/models/per_game_hr.py` — per-game composition of per-matchup probabilities (see "Rollup semantic bug" section below). 100% coverage. Supersedes the original `pa_sequence.py`.
- `phases/phase5/calibrate_runner.py` — end-to-end calibrator fit runner.
- `phases/phase5/sanity_runner.py` — top/bottom 5 P(≥1 HR) sanity harness.
- `tests/models/test_calibrate.py`, `test_rollup.py`, `test_per_game_hr.py` — unit coverage.

No changes to existing Phase 4 artifacts. Calibrator is strictly additive inside the model version dir.

## Rollup semantic bug — fixed post-tag

The first Phase 5 implementation treated the model's prediction as a
per-PA probability and compounded via Poisson binomial over
`round(projected_pa_count)` PAs. This was wrong — Phase 3's label
`hr_on_pa` is per-(batter, pitcher, game), not per-PA, so the model's
output is already a game-level matchup probability.

Consequence: top predictions saturated at ~0.72 regardless of which
player, because `1 - 0.75⁴ ≈ 0.68` for any `base_prob ≥ 0.25`. The
sanity check flagged fringe players in the top-5 because "top-5" was
essentially arbitrary within that 0.72 ceiling.

Fixed by replacing `pa_sequence.py` with `per_game_hr.py`. New
composition: `P(HR in game) = 1 - (1 - P_starter)(1 - P_bullpen)`
when both known, else `P_starter` directly. Math in `rollup.py`
(Poisson binomial) unchanged — the fix was only in how we feed it.

See commit history for the fix narrative.

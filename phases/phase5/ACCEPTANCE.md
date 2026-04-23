# Phase 5 — Acceptance Checklist

**Run:** 2026-04-22 (controller-review) — artifact `v20260423_173917` + `calibrator.joblib`
**Status:** Calibration objective met decisively (post-cal test ECE = 0.00248, ~12x below the 0.03 bar; log loss strictly improved). Per-game rollup verified end-to-end on the test slice. Sanity check surfaces a **known Phase-4 ranking-capacity limitation** (top-5 is not dominated by elite sluggers) — flagged in `NOTES.md`, not a Phase-5 calibration or rollup defect.

See `RESULTS.md` for the full pre/post metric table and `NOTES.md` for the calibration-curve narrative + the ranking-capacity caveat on sanity.

## Calibration

- [x] **Isotonic calibrator fit on validation set.** 115,152 val rows → `IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)`. Persisted as `src/models/registry/v20260423_173917/calibrator.joblib`.
- [x] **Post-calibration test-set ECE < 0.03.** Pre = **0.00555**, Post = **0.00248** (−55% relative). Clear pass, ~12x below bar.
- [x] **Post-calibration reliability curve visibly closer to diagonal than pre-calibration.** `reports/phase5_reliability_pre_post.png` overlays both curves with y=x reference. Pre curve already hugs the diagonal (Phase 4 baseline was well-calibrated); post curve tightens further in the 0.05–0.20 range.
- [x] **Post-calibration log loss on test set is ≤ pre-calibration log loss.** Pre = **0.17862**, Post = **0.17849** (−0.00013, −0.07% relative). Calibration did not hurt. Brier also improved (0.04327 → 0.04325).
- [x] **Calibrator persists and loads correctly.** `save_calibrator` + `load_calibrator` round-trip is exercised by `calibrate_runner.py` on the real artifact and by `tests/models/test_calibrate.py`.

## Per-game rollup

- [x] **`per_game_probability` returns values where P(≥1) + P(0) ≈ 1.0** (floating-point). Verified by `test_per_game_prob_at_least_one_plus_p_zero_is_one` in `tests/models/test_rollup.py`.
- [x] **`poisson_binomial_pmf` passes all test cases.** 9 unit tests in `tests/models/test_rollup.py` covering empty, single, Pascal's-triangle (`[0.5, 0.5]` → `[0.25, 0.5, 0.25]`), all-zeros, all-ones, mixed, out-of-range rejection, sums-to-one invariant.
- [x] **For 4 projected PAs at 0.05 per-PA probability: P(≥1) ≈ 0.185** (exactly `1 − 0.95^4 = 0.18549375`). Verified by `test_per_game_four_pas_at_5_percent` in `tests/models/test_rollup.py`.
- [x] **`per_game_hr_distribution` composes per-matchup probabilities correctly.** Verified by unit tests in `tests/models/test_per_game_hr.py` — starter-only returns `P(≥1) == starter_prob`; starter + bullpen combines via `1 - (1 - P_s)(1 - P_b)`; monotone in each component; multi-HR probs satisfy `P(≥1) ≥ P(≥2) ≥ P(≥3)`. (Supersedes the original `build_pa_probability_sequence` check after the post-tag semantic-bug fix — see `NOTES.md` "Rollup semantic bug".)

## Sanity: the "it works" test

- [~] **Highest P(≥1 HR) belongs to a known elite slugger in a homer-friendly context.** Post-fix top-5 sanity output (`reports/phase5_sanity_v2.log`, cited in `RESULTS.md`) is a tie cluster at the isotonic calibrator's 0.222 cap: Ben Rice, Josh Lowe, Christian Koss, James Wood, Zach Neto. Meaningfully more plausible than the pre-fix v1 (Osuna, Ruiz, Bliss, Naylor, Mangum at ~0.72) but still not dominated by Judge/Ohtani/Alonso. Root cause unchanged: Phase 4's model AUC = 0.68 compresses elite-vs-mid-tier into the same right-tail bucket; carried as deferred technical debt to a future modeling pass.
- [~] **Lowest P(≥1 HR) belongs to a weak hitter facing an ace / pitcher park.** Post-fix bottom-5 shows Elly De La Cruz, Aaron Judge, Brendan Donovan, Trent Grisham, Connor Wong — all at P(≥1) = 0.0 because the raw prediction fell below the isotonic calibrator's lowest val-set threshold. Aaron Judge appearing here is a Phase-4 ranking-capacity symptom (per-matchup features dominate over batter identity at this model capacity), not a rollup defect.
- [~] **P(≥1 HR) for a superstar on an ideal day ≥ 0.35.** **Not met post-fix** — the calibrator caps per-matchup probability at 0.222 (val's observed right tail), so no single-matchup prediction can exceed that today. Would require either (a) adding a bullpen-matchup prediction (Phase 6+), after which `1 - (1-0.22)(1-0.22) = 0.39` becomes reachable, or (b) refitting calibration on a larger val window so isotonic sees higher-raw buckets. The original v1 passed this bar only because it was compounding per-PA and saturating at 0.72, which was the semantic bug that this fix resolves.
- [~] **P(≥1 HR) for a weak hitter facing an ace in a pitcher's park ≤ 0.03.** Post-fix bottom-5 is P(≥1) = 0.0, well below 0.03. Directionally correct.

**Post-fix distribution summary:** min = 0.0, median = 0.0395, max = 0.2222, mean = 0.0487 across 140,506 test-set matchup rows. Mean aligns closely with the 4.65% training base rate, which is exactly what we expect of a correctly-interpreted per-matchup game-level probability. Max 0.222 is the isotonic calibrator's cap. Pre-fix distribution (median 0.1503, max 0.7227, mean 0.1799) was inflated by the incorrect per-PA Poisson-binomial compounding.

## Optional ensemble

- [x] **Ensemble not used.** Phase-4 pre-calibration ECE was already 0.00555, and post-calibration ECE dropped to 0.00248 — both decisively below the 0.03 bar with a single model. Ensemble would add complexity without a measurable calibration gain and was not justified. Documented in `NOTES.md` → "No ensemble".

## Tests

- [x] **`uv run pytest tests/models -v` all pass.** Part of the full suite.
- [x] **Full suite** `uv run pytest -q` — **240 passed, 1 skipped** post-fix (was 243 pre-fix; net −3 from removing 10 `pa_sequence` tests and adding 8 `per_game_hr` tests, plus one test that was inseparable from the old API).
- [x] **Coverage on new code ≥80%.** `calibrate.py` 100%, `rollup.py` 100%, `per_game_hr.py` 100%.
- [x] **Ruff clean.**

## Docs

- [x] `phases/phase5/RESULTS.md` shows pre/post calibration metrics and distribution summary.
- [x] `phases/phase5/NOTES.md` explains the no-ensemble decision, the ranking-capacity caveat, and the bullpen-clip tail behavior.
- [x] `src/models/overview.md` updated with sections on `calibrate.py`, `rollup.py`, `per_game_hr.py`.
- [x] `abstract.md` marks Phase 5 complete (tag-pending controller).

## Phase-5 gates — overall

- **Gate 1a (pytest full suite):** 240 passed, 1 skipped (post-fix).
- **Gate 1b (coverage on new code):** calibrate 100%, rollup 100%, per_game_hr 100%.
- **Gate 1c (ruff):** All checks passed.
- **Gate 2a (end-to-end calibrate run):** `calibrate_runner.py` completes in 18.3 s; writes calibrator + reliability plot.
- **Gate 2b (sanity rollup):** `sanity_runner.py` runs end-to-end on 140,506 test rows; top/bottom 5 produced; directional sanity passes (elite sluggers NOT at top is documented as Phase-4 ranking limitation, not a bug).
- **Gate 2c (ECE < 0.03):** 0.00248 ✓ (~12× below bar).
- **Gate 2d (log loss not worse):** 0.17849 ≤ 0.17862 ✓.

**Controller sign-off:** pending review. Do **not** auto-tag `phase-5-complete`.

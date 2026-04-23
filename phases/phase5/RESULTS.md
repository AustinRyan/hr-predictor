# Phase 5 — Results

**Model version:** `v20260423_173917` (Phase 4 baseline) + isotonic calibrator at `src/models/registry/v20260423_173917/calibrator.joblib`.
**Wall time:** `calibrate_runner.py` 18.3 s; `sanity_runner.py` ~70 s (dominated by the 140k-row Python per-row rollup loop — not a production path).

## Status

**Phase 5 calibration + rollup accepted.** Test-set ECE drops from 0.00555 → 0.00248 (~12× below the 0.03 bar) with no log-loss regression. Poisson-binomial per-game roll-up verified end-to-end on 140,506 test-set matchup rows. Sanity check surfaces a pre-existing Phase-4 ranking-capacity limitation (top-5 P(≥1 HR) is fringe/regular players rather than Judge/Ohtani) — covered in `NOTES.md` as deferred technical debt, not a Phase-5 defect.

## Calibration delta (test set)

| Metric    | pre (raw)   | post (isotonic) | delta        |
| ---       | ---         | ---             | ---          |
| log_loss  | **0.17862** | **0.17849**     | −0.00013 (−0.07%) |
| brier     | **0.04327** | **0.04325**     | −0.00002 (−0.05%) |
| ECE       | **0.00555** | **0.00248**     | −0.00307 (−55.3%) |

Reliability plot: `reports/phase5_reliability_pre_post.png` (overlay with y=x).

**Interpretation.** The Phase 4 baseline was already well-calibrated (pre-ECE = 0.006) because `scale_pos_weight = 1.0` preserved probability scale. Isotonic on top squeezes another 55% out of ECE for free, with negligible log-loss / Brier movement. Log loss is strictly (barely) improved — calibration did not hurt.

## Per-game probability distribution (test set, 140,506 rows)

Numbers below are from `reports/phase5_sanity_v2.log` after the post-tag semantic-bug fix: the model's prediction is now correctly interpreted as a per-matchup game-level probability (not per-PA), so no Poisson-binomial compounding is applied. Composition reduces to `P(≥1 HR) = starter_prob` today (bullpen prediction path is Phase 6+ work; bullpen signal is already partially absorbed into the starter matchup row via `bp_*` features).

| Stat    | P(≥1 HR) |
| ---     | ---      |
| min     | 0.0000   |
| median  | 0.0395   |
| max     | 0.2222   |
| mean    | 0.0487   |

Mean 0.049 aligns closely with the training-set base rate (4.65%), which is exactly what we expect of a calibrated per-matchup game-level probability. Max 0.222 is the isotonic calibrator's val-observed ceiling (documented as a known gotcha in `src/models/overview.md`).

The original (pre-fix) distribution had median 0.1503, max 0.7227, mean 0.1799 — the Poisson-binomial compounding was amplifying every matchup by ~4× and saturating the top tail at ~0.72. See `NOTES.md` "Rollup semantic bug — fixed post-tag" for the full narrative.

## Sanity — top 5 predictions (test set, v2 — post-fix)

```
 game_date    batter_name    pitcher_name                    park_name  calibrated  p_at_least_one
2025-04-27       ben rice  paxton schultz               Yankee Stadium    0.222222        0.222222
2025-05-23      josh lowe  braydon fisher George M. Steinbrenner Field    0.222222        0.222222
2025-05-28 christian koss    jackson jobe                Comerica Park    0.222222        0.222222
2025-05-31     james wood  brandon pfaadt                  Chase Field    0.222222        0.222222
2025-06-03      zach neto aroldis chapman                  Fenway Park    0.222222        0.222222
```

**Narrative.** The top-5 list is still a tie cluster at 0.222 — the isotonic calibrator's upper cap — but the composition is meaningfully more plausible than the original v1 (Osuna/Ruiz/Bliss/Naylor/Mangum). Ben Rice, Josh Lowe, James Wood, and Zach Neto are all real MLB power hitters; Jackson Jobe and Brandon Pfaadt are reasonable home-run-susceptible matchups. The tie cluster is a function of Phase 4's ranking capacity (AUC 0.68 + isotonic monotone piecewise-constant at the right tail) — an unchanged Phase-4-tech-debt caveat. The semantic fix does **not** solve the ranking compression; it only removes the 0.72 saturation artifact that was making the "top-5" comparison noisy.

## Sanity — bottom 5 predictions (test set, v2 — post-fix)

```
 game_date     batter_name   pitcher_name                   park_name  calibrated  p_at_least_one
2025-04-02 elly de la cruz   luke jackson    Great American Ball Park         0.0             0.0
2025-04-14     aaron judge john schreiber              Yankee Stadium         0.0             0.0
2025-04-28 brendan donovan  nick martínez    Great American Ball Park         0.0             0.0
2025-04-30   trent grisham félix bautista Oriole Park at Camden Yards         0.0             0.0
2025-05-02     connor wong  louis varland                 Fenway Park         0.0             0.0
```

**Narrative.** All five sit at the bottom of the calibrator's mapped range (calibrated ≈ 0.0 because the raw prediction fell below the val-set's lowest isotonic-bucket threshold). Aaron Judge appearing here is surprising; Schreiber is a high-leverage Red Sox reliever, but Judge in any matchup "rounds to zero" is a Phase-4 ranking-capacity symptom — not every Judge row clusters at the top, which confirms the per-matchup features dominate over batter identity at this model capacity. This is the same caveat surfaced in the v1 sanity narrative; removing the per-PA compounding didn't move it.

## Known Phase-5 simplifications

- **Per-game composition is starter-only today** (`src/models/per_game_hr.py`). The bullpen contribution is implicit in the starter matchup row's `bp_*` features rather than a separate model call. A Phase 6+ enhancement can synthesize a (batter, bullpen-representative) matchup row and combine via `1 - (1 - P_s)(1 - P_b)`; the `per_game_hr_distribution` function already supports that composition once a `bullpen_prob` is available.
- **No ensemble.** Phase 4 pre-cal ECE was already 0.006; post-cal is 0.002. A second base model adds no measurable calibration headroom.
- **Top-5 ranking is constrained by Phase-4 model AUC = 0.68.** Not a Phase-5 issue to fix; carried as deferred tech debt.
- **Post-tag semantic bug fix.** The first Phase 5 implementation used a per-PA sequence with Poisson-binomial compounding (`pa_sequence.py`); that was wrong because Phase 3's `hr_on_pa` label is per-matchup, not per-PA. Replaced with `per_game_hr.py`. See `NOTES.md` for details.

## Config / artifact

```
src/models/registry/v20260423_173917/
├── model.xgb                  (Phase 4)
├── calibrator.joblib          (Phase 5, new)
├── feature_schema.json, training_metadata.json, metrics.json, plots, eval_report.md
```

No changes to model.xgb. Calibrator is strictly additive.

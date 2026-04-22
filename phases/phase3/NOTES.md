# Phase 3 — Notes

Running log of mid-phase decisions, simplifications, and gotchas. Add
to this as tasks complete; consolidate into `abstract.md` at phase
close.

---

## Task 8 — Pitcher profile + TTO

- **HR/9 is a proxy, not a real innings-based calculation.** We don't
  track per-PA outs recorded in `statcast_pitches`, so computing true
  innings pitched from this table would require reconstructing each PA
  outcome into 0/1/2/3 outs. Simpler proxy:
  `HR_count / PA_count * 38.7` where 38.7 ≈ 9 innings × 4.3 PAs/inning
  (MLB league avg). Off by a few % for extreme K/BB pitchers. Revisit
  in Phase 4+ if a better estimator matters for calibration.
- **Career window capped at 10 years** before the reference date. Real
  pitcher careers in our Statcast window (2021–present) don't exceed
  this. The cap bounds the ``LEFT JOIN statcast_pitches`` output so the
  query planner has a finite range to scan even for the career stat.
- **Handedness splits use `sp.stand`, not `sp.p_throws`.** `sp.stand`
  is the batter's handedness; the pitcher's throw hand is implicit
  (all rows for a given pitcher share one `p_throws`). `p_vs_lhb_*`
  thus means "pitcher's performance vs left-handed batters."
- **TTO multipliers are a pure-Python helper** (PROMPT § 7):
  PA 1 = 1.00, PA 2 = 1.05, PA 3 = 1.20, PA 4+ = None (bullpen).
  `tto_penalty_for(projected_pa_count)` returns a weighted-average
  multiplier across the starter portion (PAs 1–3); bullpen PAs are
  dropped since the caller uses bullpen features separately.
- **Strict `<` leakage contract** — all season/career aggregates use
  `sp.game_date < mk.reference_date`. Regression-tested via
  `test_sql_uses_strict_less_than_reference_date`.

---

## Task 10 — bullpen features are a league-wide proxy

`src/features/bullpen.py` aggregates over every pitch in the season
excluding the starter of the current matchup. This is NOT a
team-specific bullpen. Rationale: accurate team-specific bullpen
classification requires a per-team-season starter/reliever taxonomy
(pitchers who start ≥ X% of their appearances are starters) which is
non-trivial to compute correctly and wasn't needed to unblock Phase 3.

**Impact:** the `bp_*` features are all league-wide averages with
the current starter excluded. The model will see a less-informative
signal than true team-bullpen features would provide. Acceptable for
a baseline.

**Phase 4+ refinement:** precompute a `pitcher_role_by_team_season`
table (pitcher_id, team, season, role ∈ {starter, reliever}) and
replace bullpen_sql with a team-specific join.

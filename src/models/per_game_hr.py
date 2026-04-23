"""Per-game HR probability composition.

Phase 3's label `hr_on_pa` is per-(batter, pitcher, game), not per-PA.
So the model's prediction IS a game-level probability for that matchup.
For games where the batter faces multiple pitchers (starter -> bullpen),
we compose via the independent-matchups formula.

This replaces the earlier `pa_sequence.py` which incorrectly treated the
model output as per-PA and compounded via Poisson binomial -- producing
a 0.72 saturation ceiling on top predictions. See commit history for the
semantic-bug fix narrative.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.models.rollup import GameHRDistribution, per_game_probability


@dataclass(slots=True, frozen=True)
class GameMatchupInputs:
    """Model predictions for the (batter, pitcher, game) matchups that make
    up a single game for one batter.

    `starter_prob` -- model prediction on the (batter, starter) matchup row.
    `bullpen_prob` -- optional; model prediction on a (batter, bullpen-
      representative) row. None when we only predicted vs the starter.
    """

    starter_prob: float
    bullpen_prob: float | None = None


def per_game_hr_distribution(inputs: GameMatchupInputs) -> GameHRDistribution:
    """Compose per-matchup probabilities into a game-level HR distribution.

    When only the starter prob is known, treat the bullpen contribution as
    implicit in the starter prediction (the Phase 4 model was trained on
    matchup rows that carry both `p_*` starter features and `bp_*` bullpen
    features, so the bullpen signal is partially absorbed into the starter
    prediction). Understates slightly versus true starter+bullpen composition
    but is a much better approximation than compounding the starter prob
    4x per PA.

    When bullpen_prob is also given, combine via 1 - (1-P_s)(1-P_b).
    """
    probs: list[float] = [float(inputs.starter_prob)]
    if inputs.bullpen_prob is not None:
        probs.append(float(inputs.bullpen_prob))
    return per_game_probability(probs)

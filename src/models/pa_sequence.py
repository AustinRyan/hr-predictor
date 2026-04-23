"""Per-PA HR probability sequence for a matchup, feeding the Poisson-
binomial per-game rollup.

Takes one matchup row (already-predicted), scales per-PA via:
  - TTO multiplier for PAs 1/2/3 (starter portion)
  - Bullpen adjustment (bp/p hr-per-9 ratio, clipped) for PAs 4+

See phases/phase5/PROMPT.md § 3 and the approved simplification note:
we run the model ONCE on the matchup row and then apply scalar
per-PA adjustments — we do NOT regenerate a full 120-column feature
row per PA slot. Per-PA feature-row regeneration would require swapping
starter features for bullpen features in a way the model wasn't trained
on, so the scalar approach is both faithful to training and simpler.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.features.pitcher_profile import tto_multiplier

_MIN_PROB = 1e-6
_MAX_PROB = 1.0 - 1e-6
_BULLPEN_ADJ_MIN = 0.5
_BULLPEN_ADJ_MAX = 2.0
_DEFAULT_TTO_PENALTY = 1.0833  # fallback when p_tto_penalty is NaN/None


@dataclass(slots=True)
class PaSequenceInputs:
    """Everything build_pa_probability_sequence needs per matchup.

    Callers typically fill this from a matchup_features row + a single
    base_prob (the model's calibrated prediction).
    """

    base_prob: float  # calibrated per-PA prob from model
    p_tto_penalty: float | None  # matchup row's p_tto_penalty
    p_hr_per_9_season: float | None  # starter's season HR/9
    bp_hr_per_9_season: float | None  # bullpen's season HR/9
    projected_pa_count: float  # from ctx_projected_pa, e.g., 4.29


def _bullpen_adjustment(
    p_hr_per_9: float | None,
    bp_hr_per_9: float | None,
) -> float:
    """Scalar for PAs 4+: how much to adjust from starter to bullpen.

    Returns bp/p clipped to [0.5, 2.0], or 1.0 when either is missing
    or the starter rate is zero (division-by-zero guard).
    """
    if p_hr_per_9 is None or bp_hr_per_9 is None or p_hr_per_9 <= 0:
        return 1.0
    adj = bp_hr_per_9 / p_hr_per_9
    if not (adj == adj):  # NaN
        return 1.0
    return max(_BULLPEN_ADJ_MIN, min(_BULLPEN_ADJ_MAX, adj))


def _clip(p: float) -> float:
    return max(_MIN_PROB, min(_MAX_PROB, p))


def build_pa_probability_sequence(inputs: PaSequenceInputs) -> list[float]:
    """Return per-PA HR probabilities for PAs 1..round(projected_pa_count).

    PAs 1/2/3 scale by TTO multiplier (1.00 / 1.05 / 1.20).
    PAs 4+ scale by a clipped bullpen adjustment.

    The input ``base_prob`` is assumed to already have ``p_tto_penalty``
    baked in (it's the model's prediction on the matchup feature row,
    which includes ``p_tto_penalty`` as a weighted-average starter
    multiplier). We divide it out to recover a "pure" per-PA prob, then
    re-apply per-PA multipliers.
    """
    n = max(1, round(inputs.projected_pa_count))

    tto = inputs.p_tto_penalty if inputs.p_tto_penalty else _DEFAULT_TTO_PENALTY
    pure = inputs.base_prob / tto

    bullpen_adj = _bullpen_adjustment(inputs.p_hr_per_9_season, inputs.bp_hr_per_9_season)

    seq: list[float] = []
    for pa_number in range(1, n + 1):
        mult = tto_multiplier(pa_number)
        if mult is None:
            mult = bullpen_adj
        seq.append(_clip(pure * mult))
    return seq

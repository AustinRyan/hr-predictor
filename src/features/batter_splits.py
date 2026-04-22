"""Batter platoon-split and pitch-type matrix feature SQL.

Pure Python helper ``regress_rate`` for unit testing the regression
formula from PROMPT section 5.

League average HR/PA per season is hardcoded as a dict (also used
inline in SQL via a CASE). TODO(phase4+): recompute annually from
``statcast_pitches``.

Windows:
  - Platoon: season YTD (Jan 1 of ref year -> ref_date, strict).
  - Pitch type: 2-season window (Jan 1 of prior year -> ref_date, strict).

Leakage contract: every aggregate uses ``sp.game_date < mk.reference_date``
(strict inequality). No ``<=`` anywhere.
"""

from __future__ import annotations

# League HR/PA averages. Update annually from statcast_pitches.
# TODO(phase4+): compute from DB rather than hardcoding.
LEAGUE_AVG_HR_PER_PA: dict[int, float] = {
    2021: 0.0309,
    2022: 0.0267,
    2023: 0.0272,
    2024: 0.0286,
    2025: 0.0285,  # preliminary; update annually
    2026: 0.0285,  # placeholder
}
DEFAULT_LEAGUE_AVG_HR_PER_PA: float = 0.028

# Pitch types tracked (matches PROMPT "Batter vs pitch-type" section).
_PITCH_TYPES: tuple[str, ...] = ("FF", "SI", "FC", "SL", "CU", "CH", "FS")


def regress_rate(
    observed_rate: float,
    pa_count: int,
    league_avg: float,
    regression_weight: int = 100,
) -> float:
    """Regress observed rate toward league average (PROMPT section 5).

    ``(observed_rate * pa_count + league_avg * regression_weight) /
       (pa_count + regression_weight)``

    At pa_count=0 the result equals ``league_avg``. Heavier samples pull
    the regressed estimate away from the mean.
    """
    denom = pa_count + regression_weight
    return (observed_rate * pa_count + league_avg * regression_weight) / denom


def _league_avg_case_sql(col: str = "mk.reference_date") -> str:
    """Inline CASE expression mapping EXTRACT(YEAR FROM {col}) -> league avg."""
    whens = " ".join(f"WHEN {year} THEN {avg}" for year, avg in LEAGUE_AVG_HR_PER_PA.items())
    return f"CASE EXTRACT(YEAR FROM {col})::int {whens} " f"ELSE {DEFAULT_LEAGUE_AVG_HR_PER_PA} END"


def platoon_splits_sql() -> str:
    """Return the SELECT body of the ``batter_platoon`` CTE.

    Expects an upstream CTE ``matchup_keys(game_pk, batter_id, reference_date)``.
    Emits 3 keys + 10 metric columns (5 per handedness).

    Leakage contract: aggregates use only pitches where
    ``sp.game_date < mk.reference_date`` (strict inequality).
    """
    season = (
        "sp.game_date >= DATE_TRUNC('year', mk.reference_date)::date "
        "AND sp.game_date < mk.reference_date"
    )
    league_case = _league_avg_case_sql()

    exprs: list[str] = ["mk.game_pk", "mk.batter_id", "mk.reference_date"]
    for hand, col_suffix in [("L", "lhp"), ("R", "rhp")]:
        base = f"({season} AND sp.p_throws = '{hand}')"
        bip = f"({season} AND sp.p_throws = '{hand}' AND sp.launch_speed IS NOT NULL)"
        xw = (
            f"({season} AND sp.p_throws = '{hand}' "
            f"AND sp.estimated_woba_using_speedangle IS NOT NULL)"
        )
        pa = (
            f"({season} AND sp.p_throws = '{hand}' "
            f"AND sp.events IS NOT NULL AND sp.events <> '')"
        )

        exprs.extend(
            [
                # Barrel pct = barrels / BIP vs this handedness.
                f"(COUNT(*) FILTER (WHERE {base} AND sp.launch_speed_angle = 6)::float"
                f" / NULLIF(COUNT(*) FILTER (WHERE {bip})::float, 0))"
                f" AS b_vs_{col_suffix}_barrel_pct",
                # Average xwOBA on balls with estimated_woba_using_speedangle populated.
                f"AVG(sp.estimated_woba_using_speedangle) FILTER (WHERE {xw})"
                f" AS b_vs_{col_suffix}_xwoba",
                # Raw HR/PA vs handedness.
                f"(COUNT(*) FILTER (WHERE {base} AND sp.events = 'home_run')::float"
                f" / NULLIF(COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
                f" FILTER (WHERE {pa})::float, 0))"
                f" AS b_vs_{col_suffix}_hr_per_pa",
                # Regressed HR/PA: PROMPT section 5 formula inlined.
                # (HR_count + league_avg * 100) / (PA + 100).
                f"((COUNT(*) FILTER (WHERE {base} AND sp.events = 'home_run')::float"
                f" + ({league_case}) * 100.0)"
                f" / NULLIF(COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
                f" FILTER (WHERE {pa})::float + 100.0, 0))"
                f" AS b_vs_{col_suffix}_hr_per_pa_reg",
                # PA count vs this handedness (distinct plate appearances).
                f"COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
                f" FILTER (WHERE {pa}) AS b_vs_{col_suffix}_pa_count",
            ]
        )

    select_list = ",\n        ".join(exprs)
    return f"""
    SELECT
        {select_list}
    FROM matchup_keys mk
    LEFT JOIN statcast_pitches sp
      ON sp.batter = mk.batter_id
     AND sp.game_date < mk.reference_date
     AND sp.game_date >= DATE_TRUNC('year', mk.reference_date)::date
    GROUP BY mk.game_pk, mk.batter_id, mk.reference_date
    """


def pitch_type_matrix_sql() -> str:
    """Return the SELECT body of the ``batter_pitch_type_matrix`` CTE.

    2-season window (Jan 1 of prior year -> ref_date, strict). Emits 3 keys
    plus xwOBA, HR-rate, and PA-count columns for each of the 7 tracked
    pitch types (21 metric columns total).

    Leakage contract: aggregates use only pitches where
    ``sp.game_date < mk.reference_date`` (strict inequality).
    """
    window = (
        "sp.game_date >= DATE_TRUNC('year', mk.reference_date - INTERVAL '1 year')::date "
        "AND sp.game_date < mk.reference_date"
    )

    exprs: list[str] = ["mk.game_pk", "mk.batter_id", "mk.reference_date"]
    for pt in _PITCH_TYPES:
        ptl = pt.lower()
        pt_filter = f"({window} AND sp.pitch_type = '{pt}')"
        xw = (
            f"({window} AND sp.pitch_type = '{pt}' "
            f"AND sp.estimated_woba_using_speedangle IS NOT NULL)"
        )
        pa = (
            f"({window} AND sp.pitch_type = '{pt}' "
            f"AND sp.events IS NOT NULL AND sp.events <> '')"
        )

        exprs.extend(
            [
                f"AVG(sp.estimated_woba_using_speedangle) FILTER (WHERE {xw})"
                f" AS b_xwoba_vs_{ptl}",
                f"(COUNT(*) FILTER (WHERE {pt_filter} AND sp.events = 'home_run')::float"
                f" / NULLIF(COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
                f" FILTER (WHERE {pa})::float, 0))"
                f" AS b_hr_rate_vs_{ptl}",
                f"COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
                f" FILTER (WHERE {pa}) AS b_pa_count_vs_{ptl}",
            ]
        )

    select_list = ",\n        ".join(exprs)
    return f"""
    SELECT
        {select_list}
    FROM matchup_keys mk
    LEFT JOIN statcast_pitches sp
      ON sp.batter = mk.batter_id
     AND sp.game_date < mk.reference_date
     AND sp.game_date >= DATE_TRUNC('year', mk.reference_date - INTERVAL '1 year')::date
    GROUP BY mk.game_pk, mk.batter_id, mk.reference_date
    """

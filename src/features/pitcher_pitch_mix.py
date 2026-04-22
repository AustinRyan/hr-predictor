"""Pitcher pitch-mix SQL generator.

Season window, leakage-safe. Usage fractions emit 0 (not NULL) when the
pitch type isn't thrown at all — makes downstream features easier.
(A pitcher who throws zero sliders should feed zero to the model.)
"""

from __future__ import annotations

_PITCH_TYPES = ("FF", "SI", "FC", "SL", "CU", "CH", "FS")
_SEASON = (
    "sp.game_date >= DATE_TRUNC('year', mk.reference_date)::date "
    "AND sp.game_date < mk.reference_date"
)


def pitch_mix_sql() -> str:
    """SELECT body for the pitcher_pitch_mix CTE.

    Keys: game_pk, batter_id, pitcher_id, reference_date.
    Features:
      p_ff_usage, p_si_usage, p_fc_usage, p_sl_usage, p_cu_usage, p_ch_usage, p_fs_usage
      p_ff_velo_avg (AVG release_speed where pitch_type='FF')
      p_primary_pitch (MODE of pitch_type)
    Season window, leakage-safe, joins on sp.pitcher = mk.pitcher_id.
    """
    exprs: list[str] = [
        "mk.game_pk",
        "mk.batter_id",
        "mk.pitcher_id",
        "mk.reference_date",
    ]
    for pt in _PITCH_TYPES:
        ptl = pt.lower()
        exprs.append(f"""
            COALESCE(
                COUNT(*) FILTER (WHERE {_SEASON} AND sp.pitch_type = '{pt}')::float
                / NULLIF(COUNT(*) FILTER (WHERE {_SEASON} AND sp.pitch_type IS NOT NULL)::float, 0),
                0
            ) AS p_{ptl}_usage""")
    exprs.append(
        f"AVG(sp.release_speed) FILTER (WHERE {_SEASON} AND sp.pitch_type = 'FF') "
        f"AS p_ff_velo_avg"
    )
    exprs.append(
        f"MODE() WITHIN GROUP (ORDER BY sp.pitch_type) "
        f"FILTER (WHERE {_SEASON} AND sp.pitch_type IS NOT NULL) "
        f"AS p_primary_pitch"
    )

    select_list = ",\n        ".join(exprs)
    return f"""
    SELECT
        {select_list}
    FROM matchup_keys mk
    LEFT JOIN statcast_pitches sp
      ON sp.pitcher = mk.pitcher_id
     AND sp.game_date < mk.reference_date
     AND sp.game_date >= DATE_TRUNC('year', mk.reference_date)::date
    GROUP BY mk.game_pk, mk.batter_id, mk.pitcher_id, mk.reference_date
    """

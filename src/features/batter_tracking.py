"""Batter bat-tracking SQL generator.

Emits b_avg_bat_speed, b_squared_up_pct, b_blast_rate over a 30-day
rolling window. Naturally returns NULL for batters with no bat_speed
data (pre-2024 or missing samples).

Squared-up threshold: launch_speed / bat_speed >= 0.8. This is a
simplified approximation of Statcast's official definition. The
official formula is proprietary; the 0.8 ratio captures most of the
signal.

Blast definition: squared-up + bat_speed >= 75 mph.

Leakage contract: strict `<` on reference_date. No `<=`.
"""

from __future__ import annotations

_WINDOW = (
    "sp.game_date >= mk.reference_date - INTERVAL '30 days' " "AND sp.game_date < mk.reference_date"
)


def bat_tracking_sql() -> str:
    """SELECT body for the batter_bat_tracking CTE.

    Expects an upstream CTE named ``matchup_keys`` with columns
    ``(game_pk INT, batter_id INT, reference_date DATE)``. Outputs one row
    per key with 6 columns: game_pk, batter_id, reference_date,
    b_avg_bat_speed, b_squared_up_pct, b_blast_rate.

    All three metrics use a 30-day rolling window with strict `<` on
    reference_date (no leakage).

    Returns NULL for any metric if there is no data to compute it
    (e.g., all bat_speed values are NULL, pre-2024 batter).
    """
    bat_only = f"({_WINDOW} AND sp.bat_speed IS NOT NULL)"
    swing = f"({_WINDOW} AND sp.bat_speed IS NOT NULL AND sp.launch_speed IS NOT NULL)"
    squared_up = (
        f"({_WINDOW} AND sp.bat_speed IS NOT NULL AND sp.launch_speed IS NOT NULL "
        f"AND sp.launch_speed >= 0.8 * sp.bat_speed)"
    )
    blast = (
        f"({_WINDOW} AND sp.bat_speed >= 75 AND sp.launch_speed IS NOT NULL "
        f"AND sp.launch_speed >= 0.8 * sp.bat_speed)"
    )

    return f"""
    SELECT
        mk.game_pk,
        mk.batter_id,
        mk.reference_date,
        AVG(sp.bat_speed) FILTER (WHERE {bat_only}) AS b_avg_bat_speed,
        (COUNT(*) FILTER (WHERE {squared_up})::float
         / NULLIF(COUNT(*) FILTER (WHERE {swing})::float, 0))
          AS b_squared_up_pct,
        (COUNT(*) FILTER (WHERE {blast})::float
         / NULLIF(COUNT(*) FILTER (WHERE {bat_only})::float, 0))
          AS b_blast_rate
    FROM matchup_keys mk
    LEFT JOIN statcast_pitches sp
      ON sp.batter = mk.batter_id
     AND sp.game_date < mk.reference_date
     AND sp.game_date >= mk.reference_date - INTERVAL '30 days'
    GROUP BY mk.game_pk, mk.batter_id, mk.reference_date
    """

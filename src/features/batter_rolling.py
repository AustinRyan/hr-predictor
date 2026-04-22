"""Batter rolling-window feature SQL generator.

Produces a SELECT body (not a full statement) that the feature builder
composes into an INSERT. Output schema documented in ``rolling_features_sql``.

Leakage contract: every aggregate filter uses ``sp.game_date < mk.reference_date``
(strict inequality). No ``<=`` anywhere.

Known gap: ``b_pulled_fb_pct_*`` is NOT computed here - it requires hc_x/hc_y
handedness-aware pull zones. Emitted as NULL; filled in a separate task.
"""

from __future__ import annotations

# Window spec -> SQL predicate against mk.reference_date + sp.game_date.
_WINDOWS: dict[str, str] = {
    "7d": (
        "sp.game_date >= mk.reference_date - INTERVAL '7 days' "
        "AND sp.game_date < mk.reference_date"
    ),
    "14d": (
        "sp.game_date >= mk.reference_date - INTERVAL '14 days' "
        "AND sp.game_date < mk.reference_date"
    ),
    "30d": (
        "sp.game_date >= mk.reference_date - INTERVAL '30 days' "
        "AND sp.game_date < mk.reference_date"
    ),
    "season": (
        "sp.game_date >= DATE_TRUNC('year', mk.reference_date)::date "
        "AND sp.game_date < mk.reference_date"
    ),
}


def _metric_expressions(window_label: str, window_predicate: str) -> list[str]:
    """Emit one SQL expression per metric for this window, using FILTER clauses."""
    bip = f"({window_predicate} AND sp.launch_speed IS NOT NULL)"
    la = f"({window_predicate} AND sp.launch_angle IS NOT NULL)"
    xw = f"({window_predicate} AND sp.estimated_woba_using_speedangle IS NOT NULL)"
    xwxba = (
        f"({window_predicate} AND sp.estimated_woba_using_speedangle IS NOT NULL "
        f"AND sp.estimated_ba_using_speedangle IS NOT NULL)"
    )
    pa = f"({window_predicate} AND sp.events IS NOT NULL AND sp.events <> '')"

    return [
        # barrel_pct = barrels / BIP
        f"(COUNT(*) FILTER (WHERE {window_predicate} AND sp.launch_speed_angle = 6)::float"
        f" / NULLIF(COUNT(*) FILTER (WHERE {bip})::float, 0))"
        f" AS b_barrel_pct_{window_label}",
        # hardhit_pct = hard_hit / BIP
        f"(COUNT(*) FILTER (WHERE {window_predicate} AND sp.launch_speed >= 95)::float"
        f" / NULLIF(COUNT(*) FILTER (WHERE {bip})::float, 0))"
        f" AS b_hardhit_pct_{window_label}",
        # avg_ev
        f"AVG(sp.launch_speed) FILTER (WHERE {bip}) AS b_avg_ev_{window_label}",
        # p90 ev
        f"percentile_cont(0.9) WITHIN GROUP (ORDER BY sp.launch_speed)"
        f" FILTER (WHERE {bip}) AS b_p90_ev_{window_label}",
        # avg_la
        f"AVG(sp.launch_angle) FILTER (WHERE {la}) AS b_avg_la_{window_label}",
        # sweet-spot pct
        f"(COUNT(*) FILTER (WHERE {window_predicate} AND sp.launch_angle BETWEEN 8 AND 32)::float"
        f" / NULLIF(COUNT(*) FILTER (WHERE {la})::float, 0))"
        f" AS b_sweet_spot_pct_{window_label}",
        # xwobacon
        f"AVG(sp.estimated_woba_using_speedangle) FILTER (WHERE {xw})"
        f" AS b_xwobacon_{window_label}",
        # xiso
        f"AVG(sp.estimated_woba_using_speedangle - sp.estimated_ba_using_speedangle)"
        f" FILTER (WHERE {xwxba}) AS b_xiso_{window_label}",
        # HR per PA
        f"(COUNT(*) FILTER (WHERE {window_predicate} AND sp.events = 'home_run')::float"
        f" / NULLIF(COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
        f" FILTER (WHERE {pa})::float, 0))"
        f" AS b_hr_per_pa_{window_label}",
        # PA count
        f"COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
        f" FILTER (WHERE {pa}) AS b_pa_count_{window_label}",
        # pulled FB pct - known gap; emit NULL literal for a later task.
        f"NULL::double precision AS b_pulled_fb_pct_{window_label}",
    ]


def rolling_features_sql() -> str:
    """Return the SELECT body of the ``batter_rolling`` CTE.

    Expects an upstream CTE named ``matchup_keys`` with columns
    ``(game_pk INT, batter_id INT, reference_date DATE)``. Outputs one row
    per key with 43 columns:

    - 3 keys (``game_pk``, ``batter_id``, ``reference_date``)
    - 10 metrics x 4 windows = 40 feature columns (includes ``b_pulled_fb_pct_*``
      emitted as NULL literals to be filled in a later task)

    Leakage contract: aggregates use only pitches where
    ``sp.game_date < mk.reference_date`` (strict inequality).
    """
    parts: list[str] = [
        "mk.game_pk",
        "mk.batter_id",
        "mk.reference_date",
    ]
    for label, predicate in _WINDOWS.items():
        parts.extend(_metric_expressions(label, predicate))

    select_list = ",\n        ".join(parts)
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

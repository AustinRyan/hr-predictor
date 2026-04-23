"""Batter rolling-window feature SQL generator.

Produces a SELECT body (not a full statement) that the feature builder
composes into an INSERT. Output schema documented in ``rolling_features_sql``.

Leakage contract: every aggregate filter uses ``sp.game_date < mk.reference_date``
(strict inequality). No ``<=`` anywhere.

Pulled-FB zones: ``hc_x`` is the Statcast screen coordinate of the batted
ball's landing location; the field's center-field line runs at
``hc_x = 125.42``. A ball is pulled if a right-handed batter hits it to
left field (``hc_x < 125.42``) or a left-handed batter hits it to right
field (``hc_x > 125.42``). Switch hitters use ``sp.stand``, which records
the side they actually batted from in that PA.
"""

from __future__ import annotations

# Statcast screen-coordinate boundary dividing LF from RF (center-field line).
_PULL_HCX_CENTER = 125.42

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
    # Fly-ball denominator for pulled-FB% requires hc_x IS NOT NULL on both
    # sides of the ratio — ~60% of FBs have NULL hc_x (foul FBs, pop-ups
    # caught close to home plate, etc.) and including them in the denominator
    # but not the numerator systematically deflates the ratio. Gating both
    # sides on hc_x presence gives the true "among known-location FBs, what
    # fraction was pulled." Matches standard sabermetric convention.
    fb_located = (
        f"({window_predicate} AND sp.launch_angle > 25 "
        f"AND sp.launch_speed IS NOT NULL AND sp.hc_x IS NOT NULL)"
    )
    # Pull zone: R hits to LF (hc_x < 125.42), L hits to RF (hc_x > 125.42).
    pull_zone = (
        f"((sp.stand = 'R' AND sp.hc_x < {_PULL_HCX_CENTER}) "
        f"OR (sp.stand = 'L' AND sp.hc_x > {_PULL_HCX_CENTER}))"
    )
    pulled_fb = f"({fb_located[1:-1]} AND {pull_zone})"

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
        # Pulled FB pct = pulled-FB / located-FB (both sides gated on hc_x
        # NOT NULL so NULL-location FBs don't bias the ratio down).
        f"(COUNT(*) FILTER (WHERE {pulled_fb})::float"
        f" / NULLIF(COUNT(*) FILTER (WHERE {fb_located})::float, 0))"
        f" AS b_pulled_fb_pct_{window_label}",
    ]


def rolling_features_sql() -> str:
    """Return the SELECT body of the ``batter_rolling`` CTE.

    Expects an upstream CTE named ``matchup_keys`` with columns
    ``(game_pk INT, batter_id INT, reference_date DATE)``. Outputs one row
    per key with 43 columns:

    - 3 keys (``game_pk``, ``batter_id``, ``reference_date``)
    - 11 metrics x 4 windows = 44 feature columns

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

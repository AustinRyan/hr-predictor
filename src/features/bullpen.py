"""Bullpen aggregate feature SQL (league-wide proxy).

Simplification: this is NOT a team-specific bullpen. It aggregates over
all statcast_pitches this season where the pitcher is NOT the starter
of the current matchup. Equivalent to "league-wide relief pool minus
this game's starter" — a first-pass proxy for the late-innings bullpen
effect. True team-specific bullpen classification (starter/reliever
per team-season) is a Phase 4+ refinement.

HR/9 proxy uses the same 38.7 PA-to-innings conversion as
pitcher_profile (9 innings × 4.3 PAs/inning league average).

Leakage contract: strict `<` on reference_date.
"""

from __future__ import annotations

_SEASON = (
    "sp.game_date >= DATE_TRUNC('year', mk.reference_date)::date "
    "AND sp.game_date < mk.reference_date"
)


def bullpen_sql() -> str:
    """Return the SELECT body of the ``bullpen`` CTE.

    Expects an upstream CTE named ``matchup_keys`` with columns
    ``(game_pk INT, batter_id INT, pitcher_id INT, reference_date DATE)``.
    Outputs one row per key with 4 keys + 2 metric columns:

    - ``bp_barrel_pct_allowed_season`` — barrels allowed / BIP, season,
      computed as league-wide (all pitchers except the starter)
    - ``bp_hr_per_9_season`` — HR allowed per 9 innings (proxy,
      HR/PA × 38.7), season, league-wide excluding starter

    Leakage contract: aggregates use only pitches where
    ``sp.game_date < mk.reference_date`` (strict inequality).
    The starter of the current matchup is excluded via
    ``sp.pitcher != mk.pitcher_id``.
    """
    # Filter predicates for the league-wide bullpen (all pitchers except starter).
    exclude = "sp.pitcher != mk.pitcher_id"
    base = f"({_SEASON} AND {exclude})"
    bip = f"({_SEASON} AND {exclude} AND sp.launch_speed IS NOT NULL)"
    pa = f"({_SEASON} AND {exclude} AND sp.events IS NOT NULL AND sp.events <> '')"

    # Barrel% allowed (season): barrels / BIP, league-wide excluding starter.
    barrel_pct_allowed = (
        f"(COUNT(*) FILTER (WHERE {base} AND sp.launch_speed_angle = 6)::float"
        f" / NULLIF(COUNT(*) FILTER (WHERE {bip})::float, 0))"
        " AS bp_barrel_pct_allowed_season"
    )

    # HR/9 proxy: COUNT(HR) / COUNT(PA) * 38.7, league-wide excluding starter.
    hr_per_9_season = (
        f"(COUNT(*) FILTER (WHERE {base} AND sp.events = 'home_run')::float"
        f" / NULLIF(COUNT(DISTINCT (sp.game_pk, sp.at_bat_number))"
        f" FILTER (WHERE {pa})::float, 0)) * 38.7"
        " AS bp_hr_per_9_season"
    )

    parts: list[str] = [
        "mk.game_pk",
        "mk.batter_id",
        "mk.pitcher_id",
        "mk.reference_date",
        barrel_pct_allowed,
        hr_per_9_season,
    ]
    select_list = ",\n        ".join(parts)

    # Outer join bounds to the season window so the join is finite even
    # when the season filter knocks all rows out.
    return f"""
    SELECT
        {select_list}
    FROM matchup_keys mk
    LEFT JOIN statcast_pitches sp
      ON sp.game_date < mk.reference_date
     AND sp.game_date >= DATE_TRUNC('year', mk.reference_date)::date
    GROUP BY mk.game_pk, mk.batter_id, mk.pitcher_id, mk.reference_date
    """

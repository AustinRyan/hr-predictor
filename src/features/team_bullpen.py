"""Opponent team bullpen aggregate feature SQL.

Team-bullpen features are keyed by ``opp_team_id`` and ``reference_date``.
They intentionally exclude each team's starter for every historical game
before aggregating relief-only pitches.

Leakage contract: strict ``<`` on ``reference_date``.
"""

from __future__ import annotations

TEAM_BULLPEN_COLS: tuple[str, ...] = (
    "opp_bp_hr_per_pa_30d",
    "opp_bp_hr_per_pa_season",
    "opp_bp_barrel_pct_allowed_30d",
    "opp_bp_barrel_pct_allowed_season",
    "opp_bp_hardhit_pct_allowed_30d",
    "opp_bp_hardhit_pct_allowed_season",
    "opp_bp_lhb_hr_per_pa_season",
    "opp_bp_rhb_hr_per_pa_season",
    "opp_bp_pitches_last_3d",
)

_PA_KEY = "(sp.game_pk, sp.at_bat_number, sp.batter)"
_PA = "sp.events IS NOT NULL AND sp.events <> ''"
_BIP = "sp.launch_speed IS NOT NULL"
_BARREL = "sp.launch_speed_angle = 6"
_HARD_HIT = "sp.launch_speed >= 95.0"
_SEASON = (
    "sp.game_date >= DATE_TRUNC('year', tk.reference_date)::date "
    "AND sp.game_date < tk.reference_date"
)
_LAST_30D = (
    "sp.game_date >= tk.reference_date - INTERVAL '30 days' AND sp.game_date < tk.reference_date"
)
_LAST_3D = (
    "sp.game_date >= tk.reference_date - INTERVAL '3 days' AND sp.game_date < tk.reference_date"
)


def _pa_count(where: str) -> str:
    return f"COUNT(DISTINCT {_PA_KEY}) FILTER (WHERE {where})"


def _rate(numerator_where: str, denominator_where: str) -> str:
    return (
        f"({_pa_count(numerator_where)}::float / NULLIF({_pa_count(denominator_where)}::float, 0))"
    )


def _bip_rate(numerator_where: str, denominator_where: str) -> str:
    return (
        f"(COUNT(*) FILTER (WHERE {numerator_where})::float "
        f"/ NULLIF(COUNT(*) FILTER (WHERE {denominator_where})::float, 0))"
    )


def team_bullpen_sql() -> str:
    """Return SELECT body for opponent team bullpen rolling features.

    Required input CTE: ``matchup_keys`` with columns
    ``(game_pk, reference_date, batter_id, pitcher_id, is_historical, opp_team_id)``.
    """
    hr_30d = _rate(f"{_LAST_30D} AND sp.events = 'home_run'", f"{_LAST_30D} AND {_PA}")
    hr_season = _rate(f"{_SEASON} AND sp.events = 'home_run'", f"{_SEASON} AND {_PA}")
    barrel_30d = _bip_rate(
        f"{_LAST_30D} AND {_BIP} AND {_BARREL}",
        f"{_LAST_30D} AND {_BIP}",
    )
    barrel_season = _bip_rate(
        f"{_SEASON} AND {_BIP} AND {_BARREL}",
        f"{_SEASON} AND {_BIP}",
    )
    hardhit_30d = _bip_rate(
        f"{_LAST_30D} AND {_BIP} AND {_HARD_HIT}",
        f"{_LAST_30D} AND {_BIP}",
    )
    hardhit_season = _bip_rate(
        f"{_SEASON} AND {_BIP} AND {_HARD_HIT}",
        f"{_SEASON} AND {_BIP}",
    )
    lhb_hr_season = _rate(
        f"{_SEASON} AND sp.stand = 'L' AND sp.events = 'home_run'",
        f"{_SEASON} AND sp.stand = 'L' AND {_PA}",
    )
    rhb_hr_season = _rate(
        f"{_SEASON} AND sp.stand = 'R' AND sp.events = 'home_run'",
        f"{_SEASON} AND sp.stand = 'R' AND {_PA}",
    )

    return f"""
    WITH team_date_keys AS (
        SELECT DISTINCT
            reference_date,
            opp_team_id
        FROM matchup_keys
        WHERE opp_team_id IS NOT NULL
    ),
    team_date_bounds AS (
        SELECT
            MIN(DATE_TRUNC('year', reference_date)::date) AS min_game_date,
            MAX(reference_date) AS max_reference_date
        FROM team_date_keys
    ),
    historical_pitches AS (
        SELECT
            sp.game_date,
            sp.game_pk,
            sp.at_bat_number,
            sp.pitch_number,
            sp.batter,
            sp.pitcher AS pitcher_id,
            sp.inning,
            sp.inning_topbot,
            sp.stand,
            sp.launch_speed,
            sp.launch_speed_angle,
            sp.events,
            CASE
                WHEN sp.inning_topbot = 'Top' THEN g.home_team_id
                WHEN sp.inning_topbot = 'Bot' THEN g.away_team_id
                ELSE NULL
            END AS pitcher_team_id
        FROM statcast_pitches sp
        JOIN games g ON g.game_pk = sp.game_pk
        CROSS JOIN team_date_bounds tdb
        WHERE sp.inning_topbot IN ('Top', 'Bot')
          AND sp.game_date >= tdb.min_game_date
          AND sp.game_date < tdb.max_reference_date
    ),
    team_game_starters AS (
        SELECT DISTINCT ON (game_pk, pitcher_team_id)
            game_pk,
            pitcher_team_id,
            pitcher_id AS starter_id
        FROM historical_pitches
        WHERE pitcher_team_id IS NOT NULL
          AND inning = 1
        ORDER BY game_pk, pitcher_team_id, at_bat_number, pitch_number
    ),
    relief_pitches AS (
        SELECT hp.*
        FROM historical_pitches hp
        JOIN team_game_starters tgs
          ON tgs.game_pk = hp.game_pk
         AND tgs.pitcher_team_id = hp.pitcher_team_id
        WHERE hp.pitcher_id <> tgs.starter_id
    ),
    team_date_bp AS (
    SELECT
        tk.reference_date,
        tk.opp_team_id,
        {hr_30d} AS opp_bp_hr_per_pa_30d,
        {hr_season} AS opp_bp_hr_per_pa_season,
        {barrel_30d} AS opp_bp_barrel_pct_allowed_30d,
        {barrel_season} AS opp_bp_barrel_pct_allowed_season,
        {hardhit_30d} AS opp_bp_hardhit_pct_allowed_30d,
        {hardhit_season} AS opp_bp_hardhit_pct_allowed_season,
        {lhb_hr_season} AS opp_bp_lhb_hr_per_pa_season,
        {rhb_hr_season} AS opp_bp_rhb_hr_per_pa_season,
        COUNT(*) FILTER (WHERE {_LAST_3D})::float AS opp_bp_pitches_last_3d
    FROM team_date_keys tk
    LEFT JOIN relief_pitches sp
      ON sp.pitcher_team_id = tk.opp_team_id
     AND sp.game_date < tk.reference_date
     AND sp.game_date >= DATE_TRUNC('year', tk.reference_date)::date
    GROUP BY tk.reference_date, tk.opp_team_id
    )
    SELECT
        mk.game_pk,
        mk.batter_id,
        mk.pitcher_id,
        mk.reference_date,
        mk.opp_team_id,
        tdb.opp_bp_hr_per_pa_30d,
        tdb.opp_bp_hr_per_pa_season,
        tdb.opp_bp_barrel_pct_allowed_30d,
        tdb.opp_bp_barrel_pct_allowed_season,
        tdb.opp_bp_hardhit_pct_allowed_30d,
        tdb.opp_bp_hardhit_pct_allowed_season,
        tdb.opp_bp_lhb_hr_per_pa_season,
        tdb.opp_bp_rhb_hr_per_pa_season,
        tdb.opp_bp_pitches_last_3d
    FROM matchup_keys mk
    LEFT JOIN team_date_bp tdb
      ON tdb.reference_date = mk.reference_date
     AND tdb.opp_team_id = mk.opp_team_id
    """

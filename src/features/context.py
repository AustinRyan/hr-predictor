"""Context features: batting order PA projections, day/night, days rest, same-hand.

Pure Python for PA map + same_hand + day_night_letter; one small DB query
for days_since_last_game.

PA_BY_BATTING_ORDER values come from empirical 2021–2024 MLB averages.
TODO(phase4+): recompute annually from ``statcast_pitches``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

# Empirical PA expectations per batting order slot (2021–2024 average).
# TODO(phase4+): recompute annually from statcast_pitches.
PA_BY_BATTING_ORDER: dict[int, float] = {
    1: 4.60,
    2: 4.50,
    3: 4.40,
    4: 4.29,
    5: 4.19,
    6: 4.08,
    7: 3.97,
    8: 3.86,
    9: 3.75,
}


def projected_pa_for_slot(slot: int) -> float:
    """Expected PAs for a batter in ``slot`` (1–9).

    Raises ValueError for invalid slots.
    """
    if slot not in PA_BY_BATTING_ORDER:
        raise ValueError(f"batting order slot must be 1–9, got {slot}")
    return PA_BY_BATTING_ORDER[slot]


def same_hand(batter_stand: str | None, pitcher_throws: str | None) -> bool:
    """True iff batter and pitcher share handedness (L/L or R/R).

    Switch-hitters (``S``) and missing values always return False.
    """
    if batter_stand is None or pitcher_throws is None:
        return False
    if batter_stand not in {"L", "R"} or pitcher_throws not in {"L", "R"}:
        return False
    return batter_stand == pitcher_throws


def day_night_letter(game_start: datetime) -> str:
    """Coarse day/night heuristic based on UTC hour.

    Heuristic: games with UTC hour in [5, 20] (inclusive) are day games (D);
    all others (0-4, 21-23) are night games (N). This reflects that:
    - Hours 0-4 UTC: very early morning games (night games from prior ET evening)
    - Hours 5-20 UTC: daytime games (morning/afternoon in US)
    - Hours 21-23 UTC: evening games (night games)

    Treats tz-naive datetimes as UTC.
    """
    if game_start.tzinfo is None:
        game_start = game_start.replace(tzinfo=UTC)
    utc_hour = game_start.astimezone(UTC).hour
    return "D" if 5 <= utc_hour <= 20 else "N"


def days_since_last_game(
    player_id: int,
    reference_date: date,
    session: Session,
) -> int | None:
    """Days between ``reference_date`` and the player's most recent game
    strictly before it.

    Checks both batter and pitcher columns in ``statcast_pitches``. Returns
    None if the player has no prior game on record.

    Leakage contract: games on ``reference_date`` itself are NOT counted.
    """
    row = session.execute(
        text("""
            SELECT MAX(game_date)
            FROM statcast_pitches
            WHERE (batter = :pid OR pitcher = :pid)
              AND game_date < :ref
            """),
        {"pid": player_id, "ref": reference_date},
    ).scalar_one_or_none()
    if row is None:
        return None
    return (reference_date - row).days

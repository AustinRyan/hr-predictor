"""Park-factor feature joiners.

Reads Phase 2's ``park_factors`` + ``parks`` tables. All outputs are
per-batter-handedness HR factor values (raw) or derived aggregates
(3-year weighted). Elevation passes through from ``parks.elevation_ft``.

3-year weighting: seasons [ref, ref-1, ref-2] with weights [0.5, 0.3, 0.2].
When older seasons are missing, weights re-normalize across available
seasons (so a single-season fallback trivially returns that season's value).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# Descending weights for [ref_season, ref-1, ref-2]. Sum to 1.0.
THREE_YEAR_WEIGHTS: tuple[float, float, float] = (0.5, 0.3, 0.2)


def park_hr_factor_for(
    batter_hand: str,
    park_id: int,
    season: int,
    session: Session,
) -> float | None:
    """Raw HR park factor for (park, season, handedness) from park_factors.

    Returns None when no row exists (distinct from 100.0 "neutral").
    """
    row = session.execute(
        text("""
            SELECT value
            FROM park_factors
            WHERE park_id = :pid
              AND season = :season
              AND batter_handedness = :hand
              AND metric = 'hr'
            """),
        {"pid": park_id, "season": season, "hand": batter_hand},
    ).scalar_one_or_none()
    return row


def park_hr_factor_3yr_weighted(
    batter_hand: str,
    park_id: int,
    ref_season: int,
    session: Session,
) -> float | None:
    """3-year weighted HR factor with fallback across available seasons.

    Weights ``THREE_YEAR_WEIGHTS`` applied to seasons [ref, ref-1, ref-2].
    Missing seasons drop out and remaining weights re-normalize. Returns
    None only when all three seasons are missing.
    """
    seasons = [ref_season - offset for offset in range(3)]
    pairs: list[tuple[float, float]] = []  # (weight, value)
    for weight, season in zip(THREE_YEAR_WEIGHTS, seasons, strict=True):
        value = park_hr_factor_for(batter_hand, park_id, season, session)
        if value is not None:
            pairs.append((weight, value))

    if not pairs:
        return None

    total_weight = sum(w for w, _ in pairs)
    return sum(w * v for w, v in pairs) / total_weight


def park_elevation_ft(park_id: int, session: Session) -> int | None:
    """Elevation from ``parks.elevation_ft``, or None if unset / park missing."""
    return session.execute(
        text("SELECT elevation_ft FROM parks WHERE park_id = :pid"),
        {"pid": park_id},
    ).scalar_one_or_none()

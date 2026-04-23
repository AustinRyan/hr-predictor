"""Phase 3.5 targeted backfill for b_pulled_fb_pct_* columns.

Re-running the full builder would take 12 hours. This script runs one
UPDATE per window (7d/14d/30d/season), joining matchup_features to
statcast_pitches with the same strict-``<`` leakage guard and the
hc_x/hc_y pull-zone predicate introduced in
``src/features/batter_rolling.py``.

Usage:
    uv run python -u phases/phase3/pulled_fb_backfill.py \
        2>&1 | tee reports/phase3_5_pulled_fb_backfill.log

Safe to re-run -- UPDATEs are idempotent (same inputs -> same outputs).
Do NOT gate on `col IS NULL` because that prevents re-running to CORRECT
previously-wrong values (e.g., the first pass used a denominator that
included NULL-hc_x FBs, systematically deflating the ratio; this script
now requires hc_x IS NOT NULL on BOTH sides of the pulled/located ratio).
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# Make `src.*` importable when run as a plain script (not `python -m ...`).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402
from src.core.db import get_engine  # noqa: E402
from src.core.logging_config import configure_logging  # noqa: E402

# Center-field line boundary for pull-zone classification. Kept in sync with
# ``src.features.batter_rolling._PULL_HCX_CENTER`` intentionally -- the SQL
# below is a hand-written UPDATE mirror of that generator.
_PULL_HCX_CENTER = 125.42


# Each window specifies the name of the matchup_features column to fill and
# the SQL snippet that bounds ``sp.game_date`` relative to
# ``mf2.game_date``. Strict ``<`` on the upper bound preserves the leakage
# contract established by the feature generator.
_WINDOWS: list[tuple[str, str]] = [
    (
        "b_pulled_fb_pct_7d",
        "sp.game_date >= mf2.game_date - INTERVAL '7 days' " "AND sp.game_date < mf2.game_date",
    ),
    (
        "b_pulled_fb_pct_14d",
        "sp.game_date >= mf2.game_date - INTERVAL '14 days' " "AND sp.game_date < mf2.game_date",
    ),
    (
        "b_pulled_fb_pct_30d",
        "sp.game_date >= mf2.game_date - INTERVAL '30 days' " "AND sp.game_date < mf2.game_date",
    ),
    (
        "b_pulled_fb_pct_season",
        "sp.game_date >= DATE_TRUNC('year', mf2.game_date)::date "
        "AND sp.game_date < mf2.game_date",
    ),
]


def _update_sql(column: str, window_predicate: str) -> str:
    """Build a single UPDATE statement for one rolling window.

    Numerator: FB (launch_angle > 25, launch_speed IS NOT NULL,
      hc_x IS NOT NULL) in the pull zone for the batter's actual stand
      that PA.
    Denominator: located FB (hc_x IS NOT NULL) in the window.

    Critical: BOTH sides of the ratio must require ``hc_x IS NOT NULL``.
    ~60% of FBs have NULL hc_x (foul FBs, pop-ups that never left the
    infield, swinging strikes with FB-angle contact, etc.). Including
    them denominator-only deflates the ratio from the true ~40%
    (empirical) to a spurious ~16%.
    """
    return f"""
    UPDATE matchup_features mf
    SET {column} = sub.pct
    FROM (
        SELECT
            mf2.game_pk,
            mf2.batter_id,
            mf2.pitcher_id,
            COUNT(*) FILTER (
                WHERE sp.launch_angle > 25
                  AND sp.launch_speed IS NOT NULL
                  AND sp.hc_x IS NOT NULL
                  AND (
                    (sp.stand = 'R' AND sp.hc_x < {_PULL_HCX_CENTER})
                    OR (sp.stand = 'L' AND sp.hc_x > {_PULL_HCX_CENTER})
                  )
            )::float
            / NULLIF(
                COUNT(*) FILTER (
                    WHERE sp.launch_angle > 25
                      AND sp.launch_speed IS NOT NULL
                      AND sp.hc_x IS NOT NULL
                )::float,
                0
            ) AS pct
        FROM matchup_features mf2
        LEFT JOIN statcast_pitches sp
          ON sp.batter = mf2.batter_id
         AND {window_predicate}
        WHERE mf2.is_historical
        GROUP BY mf2.game_pk, mf2.batter_id, mf2.pitcher_id
    ) sub
    WHERE mf.game_pk = sub.game_pk
      AND mf.batter_id = sub.batter_id
      AND mf.pitcher_id = sub.pitcher_id
      AND mf.is_historical
    """


def main() -> int:
    configure_logging()
    logging.getLogger().setLevel("INFO")

    engine = get_engine()
    overall_t0 = time.monotonic()

    print("[start] pulled-FB backfill across 4 windows", flush=True)

    for column, window_predicate in _WINDOWS:
        print(f"[window] {column} -- running UPDATE", flush=True)
        t0 = time.monotonic()
        with engine.begin() as c:
            result = c.execute(text(_update_sql(column, window_predicate)))
            rowcount = result.rowcount
        elapsed = time.monotonic() - t0
        print(
            f"[window] {column} -- rows_updated={rowcount} "
            f"wall_s={elapsed:.1f} (~{elapsed/60:.1f} min)",
            flush=True,
        )

    overall = time.monotonic() - overall_t0
    print(
        f"[DONE] total wall_s={overall:.1f} (~{overall/60:.1f} min)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase 3.5 targeted backfill for ctx_batting_order / ctx_projected_pa /
p_tto_penalty on historical matchup_features rows.

Infers batting order from statcast_pitches.at_bat_number first-appearance
ordering within each (game_pk, inning_topbot) group. Pinch hitters past
slot 9 stay NULL.

Usage:
    uv run python -u phases/phase3/batting_order_backfill.py \
        2>&1 | tee reports/phase3_5_batting_order.log

Safe to re-run -- UPDATEs are idempotent.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402
from src.core.db import get_engine  # noqa: E402
from src.core.logging_config import configure_logging  # noqa: E402
from src.features.context import PA_BY_BATTING_ORDER  # noqa: E402
from src.features.pitcher_profile import tto_penalty_for  # noqa: E402


def _pa_case_sql() -> str:
    """CASE slot -> projected PAs, using PA_BY_BATTING_ORDER values."""
    whens = " ".join(f"WHEN {slot} THEN {pa}" for slot, pa in PA_BY_BATTING_ORDER.items())
    return f"CASE r.slot {whens} ELSE NULL END"


def _tto_case_sql() -> str:
    """CASE slot -> p_tto_penalty value. Same formula across slots 1-9
    because the first 3 PAs (all starter) dominate and PA 4+ is bullpen
    (dropped from the average). Computed once in Python + pasted as SQL
    literals."""
    whens = []
    for slot, pa in PA_BY_BATTING_ORDER.items():
        whens.append(f"WHEN {slot} THEN {tto_penalty_for(pa):.6f}")
    return f"CASE r.slot {' '.join(whens)} ELSE NULL END"


def main() -> int:
    configure_logging()
    logging.getLogger().setLevel("INFO")

    engine = get_engine()
    t0 = time.monotonic()
    print("[start] batting_order backfill", flush=True)

    with engine.begin() as c:
        pa_case = _pa_case_sql()
        tto_case = _tto_case_sql()
        sql = f"""
            WITH per_batter_first_ab AS (
                SELECT
                    sp.game_pk,
                    sp.inning_topbot,
                    sp.batter,
                    MIN(sp.at_bat_number) AS first_ab
                FROM statcast_pitches sp
                WHERE sp.inning_topbot IS NOT NULL
                GROUP BY sp.game_pk, sp.inning_topbot, sp.batter
            ),
            ranked AS (
                SELECT
                    pb.game_pk,
                    pb.batter AS batter_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY pb.game_pk, pb.inning_topbot
                        ORDER BY pb.first_ab
                    )::int AS slot
                FROM per_batter_first_ab pb
            )
            UPDATE matchup_features mf
            SET ctx_batting_order = r.slot,
                ctx_projected_pa = {pa_case},
                p_tto_penalty = {tto_case}
            FROM ranked r
            WHERE mf.game_pk = r.game_pk
              AND mf.batter_id = r.batter_id
              AND mf.is_historical
              AND r.slot <= 9
        """
        result = c.execute(text(sql))
        rowcount = result.rowcount

    elapsed = time.monotonic() - t0
    print(
        f"[DONE] rows_updated={rowcount} wall_s={elapsed:.1f} " f"(~{elapsed/60:.1f} min)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase 3.5 historical-weather backfill runner.

1. Pulls Open-Meteo `/v1/archive` for every park with lat/lon populated,
   storing each hourly observation in `weather_archive`.
2. Updates `matchup_features.wx_*` for every historical row by matching
   `games.game_start_utc` to the nearest archive hour.

Usage:
    uv run python -u phases/phase3/weather_archive_runner.py \
        2>&1 | tee reports/phase3_5_weather_backfill.log

Safe to re-run -- both the archive upsert and the wx_* UPDATE are
idempotent.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import date
from pathlib import Path

# Make `src.*` importable when run as a plain script (not `python -m ...`).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.core.logging_config import configure_logging  # noqa: E402
from src.ingestion.weather import (  # noqa: E402
    backfill_wx_for_historical,
    persist_weather_archive_all_parks,
)


def main() -> int:
    configure_logging()
    logging.getLogger().setLevel("INFO")

    start = date(2021, 4, 1)
    end = date.today()

    print(f"[start] weather archive backfill {start} -> {end}", flush=True)

    t0 = time.monotonic()
    archive_rows = persist_weather_archive_all_parks(start, end)
    t_archive = time.monotonic() - t0
    print(
        f"[archive] rows={archive_rows} wall_s={t_archive:.1f} " f"(~{t_archive/60:.1f} min)",
        flush=True,
    )

    t1 = time.monotonic()
    updated = backfill_wx_for_historical(start, end)
    t_update = time.monotonic() - t1
    print(
        f"[update] matchup_features rows touched={updated} "
        f"wall_s={t_update:.1f} (~{t_update/60:.1f} min)",
        flush=True,
    )

    total = time.monotonic() - t0
    print(f"[DONE] total wall_s={total:.1f} (~{total/60:.1f} min)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

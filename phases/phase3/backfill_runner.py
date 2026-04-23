"""Phase 3 historical feature backfill — run overnight.

Usage:
    uv run python -u phases/phase3/backfill_runner.py

Safe to re-run — `matchup_features` upsert is idempotent.

To pick up after a crash, find the last completed day and adjust the
`start` below, OR just re-run from `date(2021, 4, 1)` — already-written
rows are no-ops via ON CONFLICT DO UPDATE.
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
from src.features.builder import build_features_for_historical  # noqa: E402


def main() -> int:
    configure_logging()
    logging.getLogger().setLevel("INFO")

    start = date(2021, 4, 1)
    end = date.today()

    print(f"[start] backfill {start} -> {end}", flush=True)
    t0 = time.monotonic()

    try:
        total = build_features_for_historical(start, end)
        elapsed = time.monotonic() - t0
        print(
            f"[DONE] rows={total} wall_s={elapsed:.1f} " f"(~{elapsed/3600:.2f} hours)",
            flush=True,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - t0
        print(
            f"[ERROR] after {elapsed:.1f}s: {type(exc).__name__}: {exc}",
            flush=True,
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())

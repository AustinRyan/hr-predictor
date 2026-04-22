"""Refresh handedness-split park factors from Baseball Savant.

Endpoint and format
-------------------
Savant publishes handedness-split park factors on the HTML leaderboard at
``/leaderboard/statcast-park-factors``. There is no documented CSV/JSON
export for handedness splits (the ``csv=true`` query returns HTML, not
CSV — Savant's "Download CSV" button is client-side only). The page
embeds the full data set as a JavaScript literal::

    var data = [{..., "venue_id": "19", "key_bat_side": "R",
                 "index_hr": "107", "n_pa": "10456", ...}, ...];

We extract that literal with a narrow regex and parse it as JSON. Every
parked venue's factors for the requested (year, handedness) come back in
a single response — the ``venue=`` query param is UI-only and does not
filter the payload. One HTTP call per (season, handedness) pair is
sufficient for all 30 parks.

Query parameters we depend on:
  - ``batSide`` (camelCase, not ``bat_side``): ``L`` | ``R``
  - ``year``:   e.g. ``2024``
  - ``type=year``: fixes the grouping to per-season
  - ``rolling``: omitted — Savant's default is 3-year rolling.

Uses 3-year rolling factors (Savant default) — single-season numbers
are too noisy at the start of each year. See ``phases/phase2/NOTES.md``
"Park factors — Coors HR acceptance threshold calibration" for the
reasoning.

These are all server-rendered: the embedded ``var data`` reflects the
querystring. See ``phases/phase2/NOTES.md`` for the provenance trail and
the list of things to re-verify the next time this source changes shape.

Data shape
----------
``venue_id`` matches StatsAPI's venue id (confirmed by cross-referencing
our ``parks`` table: every Savant venue_id in 2024 is in the seeded set).
Metrics arrive as ``index_{name}`` integer strings (100 = league
average). We map a subset of interest to short metric names in
``_METRIC_COLUMNS``.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.db import get_engine
from src.core.models import ParkFactor

_log = logging.getLogger(__name__)

_BASE_URL = "https://baseballsavant.mlb.com/leaderboard/statcast-park-factors"

# Savant column name (inside the embedded JSON) → our metric string.
# Update if Savant renames these keys. All values are 100-scaled indexes.
_METRIC_COLUMNS: dict[str, str] = {
    "index_hr": "hr",
    "index_runs": "runs",
    "index_hits": "hits",
    "index_1b": "1b",
    "index_2b": "2b",
    "index_3b": "3b",
    "index_hardhit": "hard_hit",
    "index_woba": "woba",
    "index_wobacon": "wobacon",
    "index_xwobacon": "xwobacon",
    "index_bacon": "bacon",
    "index_xbacon": "xbacon",
    "index_obp": "obp",
    "index_bb": "bb",
    "index_so": "so",
}
_VENUE_ID_KEY = "venue_id"
_SAMPLE_SIZE_KEY = "n_pa"

# Matches ``var data = [ ... ];`` on a single line. Savant inlines the
# whole array on one line so the non-greedy ``.*?`` is safe and cheap.
_DATA_LITERAL_RE = re.compile(r"var\s+data\s*=\s*(\[.*?\]);", re.DOTALL)


def _extract_data_literal(html_text: str) -> list[dict[str, Any]]:
    """Pull the embedded ``var data = [...]`` JSON array out of Savant's HTML."""
    match = _DATA_LITERAL_RE.search(html_text)
    if match is None:
        raise ValueError(
            "Savant park-factor page did not contain a 'var data = [...]' literal; "
            "the page layout may have changed.",
        )
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Savant data literal was not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise ValueError(f"Expected list at 'var data', got {type(parsed).__name__}")
    return parsed


def _fetch_handedness_html(season: int, handedness: str) -> str:
    """Hit the Savant leaderboard for (season, handedness). Returns raw HTML.

    ``rolling`` is intentionally omitted — Savant's default is 3-year rolling,
    which is the stable operational view. Single-season (``rolling=1``) is
    too noisy in the first weeks of each year.
    """
    params = {
        "batSide": handedness,
        "year": str(season),
        "type": "year",
    }
    resp = requests.get(_BASE_URL, params=params, timeout=30.0)
    resp.raise_for_status()
    return resp.text


def _parse_savant_response(
    html_text: str, *, season: int, handedness: str
) -> Iterable[dict[str, Any]]:
    """Yield per-metric rows suitable for ``pg_insert(ParkFactor)``.

    ``html_text`` is the raw response body of the Savant leaderboard page.
    One input row (one park's slate of indices) fans out into multiple
    per-metric rows so the upsert matches the ``park_factors`` natural
    key ``(park_id, season, batter_handedness, metric)``.
    """
    now = datetime.now(UTC)
    records = _extract_data_literal(html_text)
    for record in records:
        venue_raw = record.get(_VENUE_ID_KEY)
        if not venue_raw:
            continue
        try:
            park_id = int(venue_raw)
        except (TypeError, ValueError):
            continue

        sample_raw = record.get(_SAMPLE_SIZE_KEY)
        sample_size: int | None
        try:
            sample_size = int(sample_raw) if sample_raw not in (None, "") else None
        except (TypeError, ValueError):
            sample_size = None

        # Sanity-check: the row's own key_bat_side should agree with the
        # handedness we asked for. If it doesn't, we likely fetched the
        # wrong page; drop the row rather than silently mislabel it.
        row_side = record.get("key_bat_side")
        if row_side and row_side != handedness:
            continue

        for savant_col, metric in _METRIC_COLUMNS.items():
            val_raw = record.get(savant_col)
            if val_raw is None or val_raw == "":
                continue
            try:
                value = float(val_raw)
            except (TypeError, ValueError):
                continue
            yield {
                "park_id": park_id,
                "season": season,
                "batter_handedness": handedness,
                "metric": metric,
                "value": value,
                "sample_size": sample_size,
                "updated_at": now,
            }


def _upsert_factors(session: Session, rows: list[dict[str, Any]]) -> int:
    """Upsert on (park_id, season, batter_handedness, metric). Idempotent."""
    if not rows:
        return 0
    stmt = pg_insert(ParkFactor).values(rows)
    update_cols = {
        "value": stmt.excluded.value,
        "sample_size": stmt.excluded.sample_size,
        "updated_at": stmt.excluded.updated_at,
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            ParkFactor.park_id,
            ParkFactor.season,
            ParkFactor.batter_handedness,
            ParkFactor.metric,
        ],
        set_=update_cols,
    )
    session.execute(stmt)
    return len(rows)


def refresh_park_factors(season: int, *, engine: Engine | None = None) -> int:
    """Refresh both L and R handedness factors for ``season``.

    Returns the total number of (park, metric) rows upserted. Two HTTP
    calls are made (one per handedness); each response covers all 30
    parks.
    """
    engine = engine or get_engine()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    total = 0
    with session_factory() as session:
        for handedness in ("L", "R"):
            html_text = _fetch_handedness_html(season, handedness)
            rows = list(_parse_savant_response(html_text, season=season, handedness=handedness))
            upserted = _upsert_factors(session, rows)
            total += upserted
            _log.info(
                "park factors upserted",
                extra={
                    "season": season,
                    "handedness": handedness,
                    "rows": upserted,
                },
            )
        session.commit()

    return total

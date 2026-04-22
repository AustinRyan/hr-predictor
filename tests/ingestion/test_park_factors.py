"""Savant park-factor parser + DB-upsert tests.

The fixture HTML files are real captures of::

    https://baseballsavant.mlb.com/leaderboard/statcast-park-factors
        ?batSide={L|R}&year=2024&type=year&rolling=1

captured on 2026-04-22. See ``phases/phase2/NOTES.md`` for refresh
guidance — the parser depends on an inlined ``var data = [...]``
literal that Savant renders server-side based on the querystring.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.ingestion import park_factors as pf_mod
from src.ingestion.park_factors import (
    _fetch_handedness_html,
    _parse_savant_response,
    _upsert_factors,
    refresh_park_factors,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_savant_response_returns_per_metric_rows() -> None:
    html_text = (FIXTURES / "savant_park_factors_R_2024.html").read_text()
    rows = list(_parse_savant_response(html_text, season=2024, handedness="R"))

    # 30 parks x 15 metrics = 450 rows; some metrics may be absent for
    # half-season venues (e.g. 2024 Tropicana). Use a loose lower bound.
    assert len(rows) >= 30 * 10
    metrics = {r["metric"] for r in rows}
    assert {"hr", "runs", "woba"}.issubset(metrics)

    # Every row is a complete natural key + value.
    for r in rows:
        assert r["batter_handedness"] == "R"
        assert r["season"] == 2024
        assert isinstance(r["park_id"], int)
        assert isinstance(r["value"], float)

    hr_rows = [r for r in rows if r["metric"] == "hr"]
    assert len(hr_rows) >= 28  # near-complete coverage across 30 parks

    # Regression guard: Coors (StatsAPI venue_id=19) RHB HR index for
    # single-season 2024 was 107 at capture time. Assert > 100 (still
    # above league-average) — the historical "Coors > 110" number is a
    # 3-year rolling headline; single-season year-to-year values swing.
    coors = next((r for r in hr_rows if r["park_id"] == 19), None)
    assert coors is not None, "Coors Field (park_id=19) missing from fixture"
    assert coors["value"] > 100, (
        f"Coors RHB HR index was {coors['value']}, expected >100 " "(fixture regression guard)"
    )

    # Extra guard: Yankee Stadium RHB HR at capture was 129. The short
    # right-field porch makes it consistently one of the top HR parks;
    # >110 is a safe floor across any plausible refresh.
    yankee = next((r for r in hr_rows if r["park_id"] == 3313), None)
    assert yankee is not None
    assert yankee["value"] > 110


def test_parse_savant_response_lhh_coverage() -> None:
    html_text = (FIXTURES / "savant_park_factors_L_2024.html").read_text()
    rows = list(_parse_savant_response(html_text, season=2024, handedness="L"))

    assert all(r["batter_handedness"] == "L" for r in rows)
    park_ids = {r["park_id"] for r in rows}
    # Two probe venues from the investigation plan:
    assert {19, 3313}.issubset(park_ids), "probe venues missing from LHH fixture"


def test_parse_savant_response_rejects_empty_literal() -> None:
    with pytest.raises(ValueError, match="var data"):
        list(_parse_savant_response("<html>no data here</html>", season=2024, handedness="R"))


@pytest.mark.integration
def test_upsert_factors_is_idempotent(seeded_parks_teams: Engine) -> None:
    Session_ = sessionmaker(bind=seeded_parks_teams, future=True, expire_on_commit=False)
    rows = [
        {
            "park_id": 19,
            "season": 2024,
            "batter_handedness": "R",
            "metric": "hr",
            "value": 118.0,
            "sample_size": 1200,
        },
        {
            "park_id": 19,
            "season": 2024,
            "batter_handedness": "R",
            "metric": "runs",
            "value": 112.0,
            "sample_size": 1200,
        },
    ]
    with Session_() as s:
        _upsert_factors(s, rows)
        _upsert_factors(s, rows)  # second call must not duplicate
        s.commit()

    with seeded_parks_teams.connect() as c:
        count = c.execute(text("SELECT COUNT(*) FROM park_factors WHERE park_id = 19")).scalar_one()
    assert count == 2  # one per metric, not four


@pytest.mark.integration
def test_upsert_factors_updates_changed_value(seeded_parks_teams: Engine) -> None:
    """Re-running with a changed value overwrites (not inserts)."""
    Session_ = sessionmaker(bind=seeded_parks_teams, future=True, expire_on_commit=False)
    base = {
        "park_id": 19,
        "season": 2024,
        "batter_handedness": "R",
        "metric": "hr",
        "sample_size": 1200,
    }
    with Session_() as s:
        _upsert_factors(s, [{**base, "value": 107.0}])
        s.commit()
    with Session_() as s:
        _upsert_factors(s, [{**base, "value": 112.0}])
        s.commit()

    with seeded_parks_teams.connect() as c:
        rows = c.execute(
            text(
                "SELECT value FROM park_factors WHERE park_id = 19 "
                "AND batter_handedness = 'R' AND metric = 'hr'"
            )
        ).all()
    assert len(rows) == 1
    assert rows[0][0] == pytest.approx(112.0)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None


def test_fetch_handedness_html_builds_expected_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_get(url: str, params: dict[str, str], timeout: float) -> _FakeResponse:
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return _FakeResponse("<html><script>var data = [];</script></html>")

    monkeypatch.setattr(pf_mod.requests, "get", _fake_get)

    html = _fetch_handedness_html(2024, "R")
    assert "var data" in html
    assert captured["url"].endswith("/leaderboard/statcast-park-factors")
    assert captured["params"] == {
        "batSide": "R",
        "year": "2024",
        "type": "year",
        "rolling": "1",
    }


@pytest.mark.integration
def test_refresh_park_factors_writes_both_handedness(
    seeded_parks_teams: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: fixture HTML → parse → upsert → both L/R rows land."""
    fixture_map = {
        "R": (FIXTURES / "savant_park_factors_R_2024.html").read_text(),
        "L": (FIXTURES / "savant_park_factors_L_2024.html").read_text(),
    }

    def _fake_fetch(season: int, handedness: str) -> str:
        assert season == 2024
        return fixture_map[handedness]

    monkeypatch.setattr(pf_mod, "_fetch_handedness_html", _fake_fetch)

    total = refresh_park_factors(2024, engine=seeded_parks_teams)
    assert total > 0

    with seeded_parks_teams.connect() as c:
        # Both L and R should be populated for Coors.
        by_side = dict(
            c.execute(
                text(
                    "SELECT batter_handedness, COUNT(*) "
                    "FROM park_factors WHERE park_id = 19 AND season = 2024 "
                    "GROUP BY batter_handedness"
                )
            ).all()
        )
    assert by_side.get("R", 0) >= 10
    assert by_side.get("L", 0) >= 10

    # Second call must be idempotent: row count unchanged.
    total2 = refresh_park_factors(2024, engine=seeded_parks_teams)
    assert total2 == total
    with seeded_parks_teams.connect() as c:
        after = c.execute(
            text("SELECT COUNT(*) FROM park_factors WHERE season = 2024")
        ).scalar_one()
    # Total across both handedness must equal the first-run total.
    assert after == total

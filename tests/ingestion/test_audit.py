"""Audit report generator — synthetic-data exercises for each section."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.core.models import Game, Park, Player, Team
from src.ingestion.audit import run_audit


def _seed_minimum(engine: Engine) -> None:
    Session_ = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    # Park/team prerequisites may already be seeded by the shared fixture.
    with Session_() as s:
        s.merge(
            Park(
                park_id=19,
                name="Coors Field",
                orientation_deg=4.0,
                elevation_ft=5190,
                roof_type="open",
            )
        )
        s.merge(Park(park_id=999, name="Mystery Park"))
        s.merge(Team(team_id=115, abbr="COL", name="Colorado Rockies", home_park_id=19))
        s.merge(
            Player(
                mlbam_id=592450,
                first_name="aaron",
                last_name="judge",
                full_name="Aaron Judge",
            )
        )
        s.merge(
            Player(
                mlbam_id=660271,
                first_name="shohei",
                last_name="ohtani",
                full_name="Shohei Ohtani",
            )
        )
        s.merge(
            Game(
                game_pk=700000,
                game_date=date(2023, 7, 4),
                season=2023,
                home_team_id=115,
                venue_id=19,
            )
        )
        s.merge(
            Game(
                game_pk=700001,
                game_date=date(2023, 7, 5),
                season=2023,
                home_team_id=115,
                venue_id=19,
            )
        )
        s.commit()

    # Insert synthetic pitches via raw SQL to exercise the partitioned path.
    with engine.begin() as c:
        # 200 Coors HRs in 2023 → satisfies the spot check threshold
        for i in range(200):
            c.execute(
                text("""
                    INSERT INTO statcast_pitches
                        (game_date, game_pk, at_bat_number, pitch_number,
                         batter, pitcher, launch_speed, launch_angle, events)
                    VALUES
                        ('2023-07-04', 700000, :ab, :pn, 592450, 660271, 102.5, 30.0, 'home_run')
                    """),
                {"ab": i + 1, "pn": 1},
            )
        # 60 Ohtani 2024 HRs — need a 2024 game and pitches in that partition
        c.execute(text("""INSERT INTO games (game_pk, game_date, season, venue_id)
                   VALUES (700002, '2024-06-15', 2024, 19)"""))
        for i in range(60):
            c.execute(
                text("""
                    INSERT INTO statcast_pitches
                        (game_date, game_pk, at_bat_number, pitch_number,
                         batter, pitcher, launch_speed, launch_angle, events)
                    VALUES
                        ('2024-06-15', 700002, :ab, :pn, 660271, 592450, 105.2, 32.0, 'home_run')
                    """),
                {"ab": i + 1, "pn": 1},
            )
        # Judge 62nd HR synthetic row — 2022-10-04
        c.execute(text("""INSERT INTO games (game_pk, game_date, season, venue_id)
                   VALUES (700003, '2022-10-04', 2022, 19)"""))
        c.execute(text("""
                INSERT INTO statcast_pitches
                    (game_date, game_pk, at_bat_number, pitch_number,
                     batter, pitcher, launch_speed, launch_angle, events)
                VALUES
                    ('2022-10-04', 700003, 1, 1, 592450, 660271, 100.2, 35.0, 'home_run')
                """))
        # A suspicious row: launch_speed > 125
        c.execute(text("""INSERT INTO games (game_pk, game_date, season, venue_id)
                   VALUES (700004, '2023-08-01', 2023, 19)"""))
        c.execute(text("""
                INSERT INTO statcast_pitches
                    (game_date, game_pk, at_bat_number, pitch_number,
                     batter, pitcher, launch_speed, launch_angle, events)
                VALUES
                    ('2023-08-01', 700004, 1, 1, 592450, 660271, 130.0, 25.0, 'home_run')
                """))


@pytest.fixture()
def seeded_engine(seeded_parks_teams: Engine):
    _seed_minimum(seeded_parks_teams)
    return seeded_parks_teams


def test_audit_writes_file(seeded_engine: Engine, tmp_path: Path) -> None:
    path = run_audit(engine=seeded_engine, out_dir=tmp_path)
    assert path.exists()
    assert path.name.startswith("phase1_audit_")


def test_audit_contains_required_sections(seeded_engine: Engine, tmp_path: Path) -> None:
    path = run_audit(engine=seeded_engine, out_dir=tmp_path)
    body = path.read_text()
    for heading in (
        "Row counts per season",
        "Null rates by column",
        "FK integrity",
        "Venue coverage",
        "Date coverage",
        "Suspicious values",
        "Spot checks",
    ):
        assert heading in body, f"missing section: {heading}"


def test_audit_flags_suspicious_launch_speed(seeded_engine: Engine, tmp_path: Path) -> None:
    body = run_audit(engine=seeded_engine, out_dir=tmp_path).read_text()
    # We seeded exactly one row with launch_speed=130.
    assert "launch_speed > 125 mph: **1**" in body


def test_audit_spot_checks_pass(seeded_engine: Engine, tmp_path: Path) -> None:
    body = run_audit(engine=seeded_engine, out_dir=tmp_path).read_text()
    # Judge 62nd HR: 1 row, launch_speed = 100.2 → PASS
    assert "Judge 62nd HR" in body and "PASS" in body
    # Ohtani 2024 HRs: 60 → PASS
    assert "Ohtani 2024 HRs" in body and "60" in body
    # Coors 2023 HRs: 200 + 1 suspicious = 201 → PASS
    assert "Coors Field 2023 HRs" in body

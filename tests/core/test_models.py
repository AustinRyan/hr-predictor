"""Schema-shape assertions for Phase 1 models.

These tests only read SQLAlchemy metadata; they do not open a DB
connection. DB roundtrips are exercised by the ingestion-tests suite.
"""

from __future__ import annotations

from src.core.models import (
    Base,
    Game,
    IngestionState,
    Park,
    Player,
    StatcastPitch,
    Team,
)


def test_all_tables_registered() -> None:
    names = set(Base.metadata.tables.keys())
    expected = {
        "parks",
        "teams",
        "players",
        "games",
        "statcast_pitches",
        "ingestion_state",
    }
    assert expected <= names, names


def test_statcast_pk_starts_with_game_date() -> None:
    pk_cols = [c.name for c in StatcastPitch.__table__.primary_key.columns]
    assert pk_cols == ["game_date", "game_pk", "at_bat_number", "pitch_number"], pk_cols


def test_statcast_is_partitioned() -> None:
    # Alembic creates the partition DDL; the ORM records the intent via
    # __table_args__. Assert our models.py encodes that.
    args = StatcastPitch.__table_args__
    assert isinstance(args, dict)
    assert args.get("postgresql_partition_by", "").lower().startswith("range")


def test_park_nullable_columns() -> None:
    # orientation_deg, elevation_ft, roof_type must all be nullable for
    # alternate venues.
    t = Park.__table__
    assert t.c.orientation_deg.nullable
    assert t.c.elevation_ft.nullable
    assert t.c.roof_type.nullable


def test_game_fks() -> None:
    fks = {fk.parent.name: fk.column.table.name for fk in Game.__table__.foreign_keys}
    # Only venue_id FK survives; team FKs were dropped in migration 0002
    # because All-Star/exhibition games carry team_ids outside the 30-team roster.
    assert fks == {"venue_id": "parks"}


def test_team_home_park_fk() -> None:
    fks = {fk.parent.name for fk in Team.__table__.foreign_keys}
    assert "home_park_id" in fks


def test_ingestion_state_key_is_string() -> None:
    col = IngestionState.__table__.c.operation_key
    assert col.primary_key is True
    # SQLAlchemy types carry their declared length.
    assert col.type.length == 64


def test_player_primary_key() -> None:
    pk = [c.name for c in Player.__table__.primary_key.columns]
    assert pk == ["mlbam_id"]

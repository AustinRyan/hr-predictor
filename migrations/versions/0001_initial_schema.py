"""initial schema: parks, teams, players, games, statcast_pitches (partitioned), ingestion_state.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-22
"""

from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


# Inclusive start-year for partitions; +1 past the current season is created
# as a buffer so next-season's first pitch has a home.
PARTITION_START_YEAR = 2021


def _partition_end_year() -> int:
    return date.today().year + 1


def upgrade() -> None:
    _create_non_partitioned_tables()
    _create_statcast_partitioned_table()
    _create_yearly_partitions()
    _create_statcast_indexes()


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_statcast_batter_hr")
    op.execute("DROP INDEX IF EXISTS idx_statcast_game_pk")
    op.execute("DROP INDEX IF EXISTS idx_statcast_pitcher_date")
    op.execute("DROP INDEX IF EXISTS idx_statcast_batter_date")

    for year in range(PARTITION_START_YEAR, _partition_end_year() + 1):
        op.execute(f"DROP TABLE IF EXISTS statcast_pitches_{year}")
    op.execute("DROP TABLE IF EXISTS statcast_pitches")

    op.drop_table("ingestion_state")
    op.drop_table("games")
    op.drop_table("players")
    op.drop_table("teams")
    op.drop_table("parks")


def _create_non_partitioned_tables() -> None:
    op.create_table(
        "parks",
        sa.Column("park_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("city", sa.String(64), nullable=True),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("orientation_deg", sa.Float(), nullable=True),
        sa.Column("elevation_ft", sa.Integer(), nullable=True),
        sa.Column("roof_type", sa.String(16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "teams",
        sa.Column("team_id", sa.Integer(), primary_key=True),
        sa.Column("abbr", sa.String(4), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column(
            "home_park_id",
            sa.Integer(),
            sa.ForeignKey("parks.park_id"),
            nullable=True,
        ),
        sa.Column("league", sa.String(32), nullable=True),
        sa.Column("division", sa.String(32), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "players",
        sa.Column("mlbam_id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(128), nullable=True),
        sa.Column("first_name", sa.String(64), nullable=True),
        sa.Column("last_name", sa.String(64), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("bats", sa.String(1), nullable=True),
        sa.Column("throws", sa.String(1), nullable=True),
        sa.Column("primary_position", sa.String(4), nullable=True),
        sa.Column("debut_date", sa.Date(), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "games",
        sa.Column("game_pk", sa.Integer(), primary_key=True),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("season", sa.SmallInteger(), nullable=False),
        sa.Column("home_team_id", sa.Integer(), nullable=True),
        sa.Column("away_team_id", sa.Integer(), nullable=True),
        sa.Column(
            "venue_id",
            sa.Integer(),
            sa.ForeignKey("parks.park_id"),
            nullable=True,
        ),
        sa.Column("game_type", sa.String(2), nullable=True),
        sa.Column("day_night", sa.String(1), nullable=True),
        sa.Column("game_start_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(24), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_games_game_date", "games", ["game_date"])
    op.create_index("ix_games_season", "games", ["season"])

    op.create_table(
        "ingestion_state",
        sa.Column("operation_key", sa.String(64), primary_key=True),
        sa.Column("last_completed_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.String(2048), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def _create_statcast_partitioned_table() -> None:
    # Hand-rolled DDL: Alembic's op.create_table does not emit
    # PARTITION BY RANGE, and Postgres refuses PK constraints on
    # partitioned tables unless the partition key is part of the PK.
    op.execute("""
        CREATE TABLE statcast_pitches (
            game_date DATE NOT NULL,
            game_pk INTEGER NOT NULL,
            at_bat_number INTEGER NOT NULL,
            pitch_number SMALLINT NOT NULL,
            batter INTEGER NOT NULL,
            pitcher INTEGER NOT NULL,
            pitch_type VARCHAR(5),
            release_speed DOUBLE PRECISION,
            release_spin_rate INTEGER,
            effective_speed DOUBLE PRECISION,
            launch_speed DOUBLE PRECISION,
            launch_angle DOUBLE PRECISION,
            hit_distance_sc DOUBLE PRECISION,
            hc_x DOUBLE PRECISION,
            hc_y DOUBLE PRECISION,
            events VARCHAR(32),
            description VARCHAR(48),
            balls SMALLINT,
            strikes SMALLINT,
            outs_when_up SMALLINT,
            inning SMALLINT,
            inning_topbot VARCHAR(3),
            stand VARCHAR(1),
            p_throws VARCHAR(1),
            estimated_woba_using_speedangle DOUBLE PRECISION,
            estimated_ba_using_speedangle DOUBLE PRECISION,
            woba_value DOUBLE PRECISION,
            woba_denom DOUBLE PRECISION,
            launch_speed_angle SMALLINT,
            zone SMALLINT,
            plate_x DOUBLE PRECISION,
            plate_z DOUBLE PRECISION,
            home_team VARCHAR(4),
            away_team VARCHAR(4),
            bat_speed DOUBLE PRECISION,
            swing_length DOUBLE PRECISION,
            PRIMARY KEY (game_date, game_pk, at_bat_number, pitch_number)
        ) PARTITION BY RANGE (game_date)
        """)


def _create_yearly_partitions() -> None:
    end = _partition_end_year()
    for year in range(PARTITION_START_YEAR, end + 1):
        op.execute(f"""
            CREATE TABLE statcast_pitches_{year}
            PARTITION OF statcast_pitches
            FOR VALUES FROM ('{year}-01-01') TO ('{year + 1}-01-01')
            """)


def _create_statcast_indexes() -> None:
    # Indexes on the partitioned parent propagate to every partition.
    op.execute(
        "CREATE INDEX idx_statcast_batter_date " "ON statcast_pitches (batter, game_date DESC)"
    )
    op.execute(
        "CREATE INDEX idx_statcast_pitcher_date " "ON statcast_pitches (pitcher, game_date DESC)"
    )
    op.execute("CREATE INDEX idx_statcast_game_pk ON statcast_pitches (game_pk)")
    op.execute(
        "CREATE INDEX idx_statcast_batter_hr "
        "ON statcast_pitches (batter, game_date DESC) "
        "WHERE events = 'home_run'"
    )

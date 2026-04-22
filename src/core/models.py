"""SQLAlchemy 2.x declarative models for the HR Predictor schema.

Every raw data table lives here. Feature / model artifact tables land in
later phases.

Notes
-----
* `statcast_pitches` is range-partitioned on `game_date`. Partitions are
  created explicitly in the Alembic migration; there is no ORM-level
  partition management.
* Postgres requires the partition key to appear in any unique/PK
  constraint, so the composite PK is
  `(game_date, game_pk, at_bat_number, pitch_number)`.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base shared by every table."""


class Park(Base):
    __tablename__ = "parks"

    park_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    city: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str | None] = mapped_column(String(64))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    orientation_deg: Mapped[float | None] = mapped_column(Float)
    elevation_ft: Mapped[int | None] = mapped_column(Integer)
    roof_type: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Team(Base):
    __tablename__ = "teams"

    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    abbr: Mapped[str] = mapped_column(String(4), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    home_park_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("parks.park_id"), nullable=True
    )
    league: Mapped[str | None] = mapped_column(String(32))
    division: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Player(Base):
    __tablename__ = "players"

    mlbam_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str | None] = mapped_column(String(128))
    first_name: Mapped[str | None] = mapped_column(String(64))
    last_name: Mapped[str | None] = mapped_column(String(64))
    birth_date: Mapped[date | None] = mapped_column(Date)
    bats: Mapped[str | None] = mapped_column(String(1))
    throws: Mapped[str | None] = mapped_column(String(1))
    primary_position: Mapped[str | None] = mapped_column(String(4))
    debut_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Game(Base):
    __tablename__ = "games"

    game_pk: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    season: Mapped[int] = mapped_column(SmallInteger, nullable=False, index=True)
    # No FK to teams: All-Star / exhibition games carry IDs (159/160) that
    # don't belong to the 30-team `teams` dimension.
    home_team_id: Mapped[int | None] = mapped_column(Integer)
    away_team_id: Mapped[int | None] = mapped_column(Integer)
    venue_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("parks.park_id"))
    game_type: Mapped[str | None] = mapped_column(String(2))
    day_night: Mapped[str | None] = mapped_column(String(1))
    game_start_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(24))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class StatcastPitch(Base):
    """Pitch-level Statcast row. Partitioned by game_date (yearly)."""

    __tablename__ = "statcast_pitches"
    __table_args__ = {"postgresql_partition_by": "RANGE (game_date)"}

    game_date: Mapped[date] = mapped_column(Date, primary_key=True)
    game_pk: Mapped[int] = mapped_column(Integer, primary_key=True)
    at_bat_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    pitch_number: Mapped[int] = mapped_column(SmallInteger, primary_key=True)

    batter: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    pitcher: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    pitch_type: Mapped[str | None] = mapped_column(String(5))
    release_speed: Mapped[float | None] = mapped_column(Float)
    release_spin_rate: Mapped[int | None] = mapped_column(Integer)
    effective_speed: Mapped[float | None] = mapped_column(Float)

    launch_speed: Mapped[float | None] = mapped_column(Float)
    launch_angle: Mapped[float | None] = mapped_column(Float)
    hit_distance_sc: Mapped[float | None] = mapped_column(Float)
    hc_x: Mapped[float | None] = mapped_column(Float)
    hc_y: Mapped[float | None] = mapped_column(Float)

    events: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(String(48))

    balls: Mapped[int | None] = mapped_column(SmallInteger)
    strikes: Mapped[int | None] = mapped_column(SmallInteger)
    outs_when_up: Mapped[int | None] = mapped_column(SmallInteger)
    inning: Mapped[int | None] = mapped_column(SmallInteger)
    inning_topbot: Mapped[str | None] = mapped_column(String(3))

    stand: Mapped[str | None] = mapped_column(String(1))
    p_throws: Mapped[str | None] = mapped_column(String(1))

    estimated_woba_using_speedangle: Mapped[float | None] = mapped_column(Float)
    estimated_ba_using_speedangle: Mapped[float | None] = mapped_column(Float)
    woba_value: Mapped[float | None] = mapped_column(Float)
    woba_denom: Mapped[float | None] = mapped_column(Float)
    launch_speed_angle: Mapped[int | None] = mapped_column(SmallInteger)
    zone: Mapped[int | None] = mapped_column(SmallInteger)
    plate_x: Mapped[float | None] = mapped_column(Float)
    plate_z: Mapped[float | None] = mapped_column(Float)

    home_team: Mapped[str | None] = mapped_column(String(4))
    away_team: Mapped[str | None] = mapped_column(String(4))

    bat_speed: Mapped[float | None] = mapped_column(Float)
    swing_length: Mapped[float | None] = mapped_column(Float)


class IngestionState(Base):
    __tablename__ = "ingestion_state"

    operation_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_completed_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(String(2048))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

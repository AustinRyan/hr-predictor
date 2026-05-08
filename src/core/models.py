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
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
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


class DailySchedule(Base):
    __tablename__ = "daily_schedule"

    game_pk: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    home_team_id: Mapped[int] = mapped_column(Integer, nullable=False)
    away_team_id: Mapped[int] = mapped_column(Integer, nullable=False)
    venue_id: Mapped[int] = mapped_column(Integer, ForeignKey("parks.park_id"), nullable=False)
    game_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    game_start_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    probable_home_pitcher_id: Mapped[int | None] = mapped_column(Integer)
    probable_away_pitcher_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    roof_status: Mapped[str | None] = mapped_column(String(16))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProjectedLineup(Base):
    __tablename__ = "projected_lineups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_pk: Mapped[int] = mapped_column(
        Integer, ForeignKey("daily_schedule.game_pk", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[int] = mapped_column(Integer, nullable=False)
    batter_id: Mapped[int] = mapped_column(Integer, nullable=False)
    batting_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WeatherForecast(Base):
    __tablename__ = "weather_forecasts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    park_id: Mapped[int] = mapped_column(Integer, ForeignKey("parks.park_id"), nullable=False)
    forecast_for_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    temperature_f: Mapped[float | None] = mapped_column(Float)
    feels_like_f: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    pressure_hpa: Mapped[float | None] = mapped_column(Float)
    wind_speed_mph: Mapped[float | None] = mapped_column(Float)
    wind_direction_deg: Mapped[float | None] = mapped_column(Float)
    precipitation_pct: Mapped[float | None] = mapped_column(Float)
    cloud_cover_pct: Mapped[float | None] = mapped_column(Float)


class WeatherArchive(Base):
    """Historical hourly weather per park from Open-Meteo /v1/archive.

    One-true observation per (park_id, valid_hour_utc). Distinct from
    `weather_forecasts`, which stores forecast revisions keyed by
    `fetched_at`. Phase 3.5 backfill source for historical `wx_*`
    columns on `matchup_features`.
    """

    __tablename__ = "weather_archive"

    park_id: Mapped[int] = mapped_column(Integer, ForeignKey("parks.park_id"), primary_key=True)
    valid_hour_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    temperature_f: Mapped[float | None] = mapped_column(Float)
    feels_like_f: Mapped[float | None] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    pressure_hpa: Mapped[float | None] = mapped_column(Float)
    wind_speed_mph: Mapped[float | None] = mapped_column(Float)
    wind_direction_deg: Mapped[float | None] = mapped_column(Float)
    precipitation_mm: Mapped[float | None] = mapped_column(Float)
    cloud_cover_pct: Mapped[float | None] = mapped_column(Float)


class ParkFactor(Base):
    __tablename__ = "park_factors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    park_id: Mapped[int] = mapped_column(Integer, ForeignKey("parks.park_id"), nullable=False)
    season: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    batter_handedness: Mapped[str] = mapped_column(String(1), nullable=False)
    metric: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    sample_size: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class MatchupFeature(Base):
    """Phase 3 wide feature row, one per (batter, pitcher) matchup per game.

    Partitioned by `game_date` yearly (same pattern as `statcast_pitches`);
    Postgres requires the partition key to appear in the PK, hence the
    composite `(game_date, game_pk, batter_id, pitcher_id)`.

    The ORM is descriptive-only — actual DDL is owned by migration
    `0004_feature_store`. See `phases/phase3/PROMPT.md` § "Schema
    additions" for the canonical column list and groupings.
    """

    __tablename__ = "matchup_features"
    __table_args__ = {"postgresql_partition_by": "RANGE (game_date)"}

    # Keys (part of composite PK)
    game_date: Mapped[date] = mapped_column(Date, primary_key=True)
    game_pk: Mapped[int] = mapped_column(Integer, primary_key=True)
    batter_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pitcher_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_historical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hr_on_pa: Mapped[bool | None] = mapped_column(Boolean)

    # Batter rolling windows (b_{metric}_{7d,14d,30d,season}) — all nullable floats
    b_barrel_pct_7d: Mapped[float | None] = mapped_column(Float)
    b_barrel_pct_14d: Mapped[float | None] = mapped_column(Float)
    b_barrel_pct_30d: Mapped[float | None] = mapped_column(Float)
    b_barrel_pct_season: Mapped[float | None] = mapped_column(Float)
    b_hardhit_pct_7d: Mapped[float | None] = mapped_column(Float)
    b_hardhit_pct_14d: Mapped[float | None] = mapped_column(Float)
    b_hardhit_pct_30d: Mapped[float | None] = mapped_column(Float)
    b_hardhit_pct_season: Mapped[float | None] = mapped_column(Float)
    b_avg_ev_7d: Mapped[float | None] = mapped_column(Float)
    b_avg_ev_14d: Mapped[float | None] = mapped_column(Float)
    b_avg_ev_30d: Mapped[float | None] = mapped_column(Float)
    b_avg_ev_season: Mapped[float | None] = mapped_column(Float)
    b_p90_ev_7d: Mapped[float | None] = mapped_column(Float)
    b_p90_ev_14d: Mapped[float | None] = mapped_column(Float)
    b_p90_ev_30d: Mapped[float | None] = mapped_column(Float)
    b_p90_ev_season: Mapped[float | None] = mapped_column(Float)
    b_avg_la_7d: Mapped[float | None] = mapped_column(Float)
    b_avg_la_14d: Mapped[float | None] = mapped_column(Float)
    b_avg_la_30d: Mapped[float | None] = mapped_column(Float)
    b_avg_la_season: Mapped[float | None] = mapped_column(Float)
    b_sweet_spot_pct_7d: Mapped[float | None] = mapped_column(Float)
    b_sweet_spot_pct_14d: Mapped[float | None] = mapped_column(Float)
    b_sweet_spot_pct_30d: Mapped[float | None] = mapped_column(Float)
    b_sweet_spot_pct_season: Mapped[float | None] = mapped_column(Float)
    b_pulled_fb_pct_7d: Mapped[float | None] = mapped_column(Float)
    b_pulled_fb_pct_14d: Mapped[float | None] = mapped_column(Float)
    b_pulled_fb_pct_30d: Mapped[float | None] = mapped_column(Float)
    b_pulled_fb_pct_season: Mapped[float | None] = mapped_column(Float)
    b_xwobacon_7d: Mapped[float | None] = mapped_column(Float)
    b_xwobacon_14d: Mapped[float | None] = mapped_column(Float)
    b_xwobacon_30d: Mapped[float | None] = mapped_column(Float)
    b_xwobacon_season: Mapped[float | None] = mapped_column(Float)
    b_xiso_7d: Mapped[float | None] = mapped_column(Float)
    b_xiso_14d: Mapped[float | None] = mapped_column(Float)
    b_xiso_30d: Mapped[float | None] = mapped_column(Float)
    b_xiso_season: Mapped[float | None] = mapped_column(Float)
    b_hr_per_pa_7d: Mapped[float | None] = mapped_column(Float)
    b_hr_per_pa_14d: Mapped[float | None] = mapped_column(Float)
    b_hr_per_pa_30d: Mapped[float | None] = mapped_column(Float)
    b_hr_per_pa_season: Mapped[float | None] = mapped_column(Float)
    b_pa_count_7d: Mapped[int | None] = mapped_column(Integer)
    b_pa_count_14d: Mapped[int | None] = mapped_column(Integer)
    b_pa_count_30d: Mapped[int | None] = mapped_column(Integer)
    b_pa_count_season: Mapped[int | None] = mapped_column(Integer)

    # Batter platoon splits (raw + regressed hr/pa)
    b_vs_lhp_barrel_pct: Mapped[float | None] = mapped_column(Float)
    b_vs_rhp_barrel_pct: Mapped[float | None] = mapped_column(Float)
    b_vs_lhp_xwoba: Mapped[float | None] = mapped_column(Float)
    b_vs_rhp_xwoba: Mapped[float | None] = mapped_column(Float)
    b_vs_lhp_hr_per_pa: Mapped[float | None] = mapped_column(Float)
    b_vs_rhp_hr_per_pa: Mapped[float | None] = mapped_column(Float)
    b_vs_lhp_hr_per_pa_reg: Mapped[float | None] = mapped_column(Float)
    b_vs_rhp_hr_per_pa_reg: Mapped[float | None] = mapped_column(Float)
    b_vs_lhp_pa_count: Mapped[int | None] = mapped_column(Integer)
    b_vs_rhp_pa_count: Mapped[int | None] = mapped_column(Integer)

    # Batter vs pitch-type (2-season window)
    b_xwoba_vs_ff: Mapped[float | None] = mapped_column(Float)
    b_xwoba_vs_si: Mapped[float | None] = mapped_column(Float)
    b_xwoba_vs_fc: Mapped[float | None] = mapped_column(Float)
    b_xwoba_vs_sl: Mapped[float | None] = mapped_column(Float)
    b_xwoba_vs_cu: Mapped[float | None] = mapped_column(Float)
    b_xwoba_vs_ch: Mapped[float | None] = mapped_column(Float)
    b_xwoba_vs_fs: Mapped[float | None] = mapped_column(Float)
    b_hr_rate_vs_ff: Mapped[float | None] = mapped_column(Float)
    b_hr_rate_vs_si: Mapped[float | None] = mapped_column(Float)
    b_hr_rate_vs_fc: Mapped[float | None] = mapped_column(Float)
    b_hr_rate_vs_sl: Mapped[float | None] = mapped_column(Float)
    b_hr_rate_vs_cu: Mapped[float | None] = mapped_column(Float)
    b_hr_rate_vs_ch: Mapped[float | None] = mapped_column(Float)
    b_hr_rate_vs_fs: Mapped[float | None] = mapped_column(Float)
    b_pa_count_vs_ff: Mapped[int | None] = mapped_column(Integer)
    b_pa_count_vs_si: Mapped[int | None] = mapped_column(Integer)
    b_pa_count_vs_fc: Mapped[int | None] = mapped_column(Integer)
    b_pa_count_vs_sl: Mapped[int | None] = mapped_column(Integer)
    b_pa_count_vs_cu: Mapped[int | None] = mapped_column(Integer)
    b_pa_count_vs_ch: Mapped[int | None] = mapped_column(Integer)
    b_pa_count_vs_fs: Mapped[int | None] = mapped_column(Integer)

    # Batter bat-tracking (2024+ only, nullable earlier)
    b_avg_bat_speed: Mapped[float | None] = mapped_column(Float)
    b_squared_up_pct: Mapped[float | None] = mapped_column(Float)
    b_blast_rate: Mapped[float | None] = mapped_column(Float)

    # Pitcher profile
    p_hr_per_9_season: Mapped[float | None] = mapped_column(Float)
    p_hr_per_9_career: Mapped[float | None] = mapped_column(Float)
    p_barrel_pct_allowed_season: Mapped[float | None] = mapped_column(Float)
    p_hardhit_pct_allowed_season: Mapped[float | None] = mapped_column(Float)
    p_fb_pct: Mapped[float | None] = mapped_column(Float)
    p_gb_pct: Mapped[float | None] = mapped_column(Float)
    p_k_pct: Mapped[float | None] = mapped_column(Float)
    p_bb_pct: Mapped[float | None] = mapped_column(Float)

    # Pitcher handedness splits
    p_vs_lhb_xwoba_allowed: Mapped[float | None] = mapped_column(Float)
    p_vs_rhb_xwoba_allowed: Mapped[float | None] = mapped_column(Float)
    p_vs_lhb_hr_rate: Mapped[float | None] = mapped_column(Float)
    p_vs_rhb_hr_rate: Mapped[float | None] = mapped_column(Float)

    # Pitcher pitch mix & velocity
    p_ff_usage: Mapped[float | None] = mapped_column(Float)
    p_si_usage: Mapped[float | None] = mapped_column(Float)
    p_fc_usage: Mapped[float | None] = mapped_column(Float)
    p_sl_usage: Mapped[float | None] = mapped_column(Float)
    p_cu_usage: Mapped[float | None] = mapped_column(Float)
    p_ch_usage: Mapped[float | None] = mapped_column(Float)
    p_fs_usage: Mapped[float | None] = mapped_column(Float)
    p_ff_velo_avg: Mapped[float | None] = mapped_column(Float)
    p_primary_pitch: Mapped[str | None] = mapped_column(String(5))

    # Pitcher TTO
    p_tto_penalty: Mapped[float | None] = mapped_column(Float)

    # Legacy opposing bullpen proxy
    bp_barrel_pct_allowed_season: Mapped[float | None] = mapped_column(Float)
    bp_hr_per_9_season: Mapped[float | None] = mapped_column(Float)

    # Opponent team bullpen
    opp_team_id: Mapped[int | None] = mapped_column(Integer)
    opp_bp_hr_per_pa_30d: Mapped[float | None] = mapped_column(Float)
    opp_bp_hr_per_pa_season: Mapped[float | None] = mapped_column(Float)
    opp_bp_barrel_pct_allowed_30d: Mapped[float | None] = mapped_column(Float)
    opp_bp_barrel_pct_allowed_season: Mapped[float | None] = mapped_column(Float)
    opp_bp_hardhit_pct_allowed_30d: Mapped[float | None] = mapped_column(Float)
    opp_bp_hardhit_pct_allowed_season: Mapped[float | None] = mapped_column(Float)
    opp_bp_lhb_hr_per_pa_season: Mapped[float | None] = mapped_column(Float)
    opp_bp_rhb_hr_per_pa_season: Mapped[float | None] = mapped_column(Float)
    opp_bp_pitches_last_3d: Mapped[float | None] = mapped_column(Float)

    # Park factors
    park_hr_factor_hand: Mapped[float | None] = mapped_column(Float)
    park_hr_factor_hand_3yr: Mapped[float | None] = mapped_column(Float)
    park_id: Mapped[int | None] = mapped_column(Integer)
    park_elevation_ft: Mapped[int | None] = mapped_column(Integer)

    # Weather
    wx_temperature_f: Mapped[float | None] = mapped_column(Float)
    wx_humidity_pct: Mapped[float | None] = mapped_column(Float)
    wx_pressure_hpa: Mapped[float | None] = mapped_column(Float)
    wx_air_density_relative: Mapped[float | None] = mapped_column(Float)
    wx_wind_speed_mph: Mapped[float | None] = mapped_column(Float)
    wx_wind_carry_lf: Mapped[float | None] = mapped_column(Float)
    wx_wind_carry_cf: Mapped[float | None] = mapped_column(Float)
    wx_wind_carry_rf: Mapped[float | None] = mapped_column(Float)
    wx_is_roof_closed: Mapped[bool | None] = mapped_column(Boolean)

    # Context
    ctx_batting_order: Mapped[int | None] = mapped_column(SmallInteger)
    ctx_projected_pa: Mapped[float | None] = mapped_column(Float)
    ctx_day_night: Mapped[str | None] = mapped_column(String(1))
    ctx_is_home: Mapped[bool | None] = mapped_column(Boolean)
    ctx_batter_days_rest: Mapped[int | None] = mapped_column(Integer)
    ctx_pitcher_days_rest: Mapped[int | None] = mapped_column(Integer)
    ctx_same_hand: Mapped[bool | None] = mapped_column(Boolean)

    # Audit
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Prediction(Base):
    """Per-(game, batter) HR probability output for a specific model version."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_pk: Mapped[int] = mapped_column(Integer, nullable=False)
    batter_id: Mapped[int] = mapped_column(Integer, nullable=False)
    pitcher_id: Mapped[int] = mapped_column(Integer, nullable=False)
    game_date: Mapped[date] = mapped_column(Date, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    matchup_components: Mapped[dict] = mapped_column(JSONB, nullable=False)
    projected_pas: Mapped[float | None] = mapped_column(Float)
    prob_at_least_one_hr: Mapped[float] = mapped_column(Float, nullable=False)
    prob_at_least_two_hr: Mapped[float | None] = mapped_column(Float)
    expected_hrs: Mapped[float | None] = mapped_column(Float)
    feature_contributions: Mapped[dict | None] = mapped_column(JSONB)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "game_pk",
            "batter_id",
            "model_version",
            name="uq_predictions_game_batter_model",
        ),
    )


class OddsSnapshot(Base):
    """Normalized sportsbook odds snapshot for a single prop outcome."""

    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    sport_key: Mapped[str] = mapped_column(String(32), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    game_pk: Mapped[int | None] = mapped_column(Integer)
    game_date: Mapped[date] = mapped_column(Date, nullable=False)
    commence_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    home_team: Mapped[str] = mapped_column(String(128), nullable=False)
    away_team: Mapped[str] = mapped_column(String(128), nullable=False)
    bookmaker_key: Mapped[str] = mapped_column(String(64), nullable=False)
    bookmaker_title: Mapped[str] = mapped_column(String(128), nullable=False)
    market_key: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_name: Mapped[str] = mapped_column(String(16), nullable=False)
    player_name: Mapped[str] = mapped_column(String(128), nullable=False)
    batter_id: Mapped[int | None] = mapped_column(Integer)
    price_american: Mapped[int] = mapped_column(Integer, nullable=False)
    point: Mapped[float | None] = mapped_column(Float)
    implied_probability: Mapped[float] = mapped_column(Float, nullable=False)
    no_vig_probability: Mapped[float | None] = mapped_column(Float)
    market_last_update: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    raw_outcome: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("snapshot_key", name="uq_odds_snapshots_snapshot_key"),
        Index(
            "ix_odds_snapshots_game_batter_market_fetched",
            "game_date",
            "game_pk",
            "batter_id",
            "market_key",
            "fetched_at",
        ),
        Index("ix_odds_snapshots_batter_date", "batter_id", "game_date"),
    )

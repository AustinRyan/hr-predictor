"""operational tables: daily_schedule, projected_lineups, weather_forecasts, park_factors.

Revision ID: 0003_operational_tables
Revises: 0002_drop_games_team_fks
Create Date: 2026-04-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_operational_tables"
down_revision = "0002_drop_games_team_fks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_schedule",
        sa.Column("game_pk", sa.Integer(), primary_key=True),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("home_team_id", sa.Integer(), nullable=False),
        sa.Column("away_team_id", sa.Integer(), nullable=False),
        sa.Column("venue_id", sa.Integer(), sa.ForeignKey("parks.park_id"), nullable=False),
        sa.Column("game_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("game_start_local", sa.DateTime(timezone=True), nullable=True),
        sa.Column("probable_home_pitcher_id", sa.Integer(), nullable=True),
        sa.Column("probable_away_pitcher_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("roof_status", sa.String(16), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_daily_schedule_game_date", "daily_schedule", ["game_date"])

    op.create_table(
        "projected_lineups",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "game_pk",
            sa.Integer(),
            sa.ForeignKey("daily_schedule.game_pk", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("batter_id", sa.Integer(), nullable=False),
        sa.Column("batting_order", sa.SmallInteger(), nullable=False),
        sa.Column("is_confirmed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "game_pk",
            "team_id",
            "batting_order",
            name="uq_projected_lineups_game_pk_team_id_batting_order",
        ),
    )
    op.create_index("ix_projected_lineups_game_pk", "projected_lineups", ["game_pk"])

    op.create_table(
        "weather_forecasts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("park_id", sa.Integer(), sa.ForeignKey("parks.park_id"), nullable=False),
        sa.Column("forecast_for_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("temperature_f", sa.Float(), nullable=True),
        sa.Column("feels_like_f", sa.Float(), nullable=True),
        sa.Column("humidity_pct", sa.Float(), nullable=True),
        sa.Column("pressure_hpa", sa.Float(), nullable=True),
        sa.Column("wind_speed_mph", sa.Float(), nullable=True),
        sa.Column("wind_direction_deg", sa.Float(), nullable=True),
        sa.Column("precipitation_pct", sa.Float(), nullable=True),
        sa.Column("cloud_cover_pct", sa.Float(), nullable=True),
        sa.UniqueConstraint(
            "park_id",
            "forecast_for_utc",
            "fetched_at",
            name="uq_weather_park_target_fetched",
        ),
    )
    op.create_index(
        "ix_weather_park_forecast_for",
        "weather_forecasts",
        ["park_id", "forecast_for_utc"],
    )

    op.create_table(
        "park_factors",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("park_id", sa.Integer(), sa.ForeignKey("parks.park_id"), nullable=False),
        sa.Column("season", sa.SmallInteger(), nullable=False),
        sa.Column("batter_handedness", sa.String(1), nullable=False),
        sa.Column("metric", sa.String(16), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "park_id",
            "season",
            "batter_handedness",
            "metric",
            name="uq_park_factors_park_season_hand_metric",
        ),
    )
    op.create_index("ix_park_factors_season_metric", "park_factors", ["season", "metric"])


def downgrade() -> None:
    op.drop_index("ix_park_factors_season_metric", table_name="park_factors")
    op.drop_table("park_factors")
    op.drop_index("ix_weather_park_forecast_for", table_name="weather_forecasts")
    op.drop_table("weather_forecasts")
    op.drop_index("ix_projected_lineups_game_pk", table_name="projected_lineups")
    op.drop_table("projected_lineups")
    op.drop_index("ix_daily_schedule_game_date", table_name="daily_schedule")
    op.drop_table("daily_schedule")

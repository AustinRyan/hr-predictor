"""weather_archive: hourly historical weather per park from Open-Meteo /v1/archive.

Revision ID: 0005_weather_archive
Revises: 0004_feature_store
Create Date: 2026-04-22

Separate from `weather_forecasts` (forecast revisions keyed by fetched_at)
-- archive rows are the one-true observed hourly value per (park, hour).
"""

from __future__ import annotations

from alembic import op

revision = "0005_weather_archive"
down_revision = "0004_feature_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE weather_archive (
            park_id INTEGER NOT NULL REFERENCES parks(park_id),
            valid_hour_utc TIMESTAMPTZ NOT NULL,
            temperature_f DOUBLE PRECISION,
            feels_like_f DOUBLE PRECISION,
            humidity_pct DOUBLE PRECISION,
            pressure_hpa DOUBLE PRECISION,
            wind_speed_mph DOUBLE PRECISION,
            wind_direction_deg DOUBLE PRECISION,
            precipitation_mm DOUBLE PRECISION,
            cloud_cover_pct DOUBLE PRECISION,
            PRIMARY KEY (park_id, valid_hour_utc)
        )
        """)
    op.execute(
        "CREATE INDEX idx_weather_archive_park_hour " "ON weather_archive (park_id, valid_hour_utc)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_weather_archive_park_hour")
    op.execute("DROP TABLE IF EXISTS weather_archive")

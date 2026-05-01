"""odds snapshots for sportsbook player props.

Revision ID: 0007_odds_snapshots
Revises: 0006_predictions
Create Date: 2026-05-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_odds_snapshots"
down_revision = "0006_predictions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "odds_snapshots",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("snapshot_key", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("sport_key", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("game_pk", sa.Integer, nullable=True),
        sa.Column("game_date", sa.Date, nullable=False),
        sa.Column("commence_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team", sa.String(128), nullable=False),
        sa.Column("away_team", sa.String(128), nullable=False),
        sa.Column("bookmaker_key", sa.String(64), nullable=False),
        sa.Column("bookmaker_title", sa.String(128), nullable=False),
        sa.Column("market_key", sa.String(64), nullable=False),
        sa.Column("outcome_name", sa.String(16), nullable=False),
        sa.Column("player_name", sa.String(128), nullable=False),
        sa.Column("batter_id", sa.Integer, nullable=True),
        sa.Column("price_american", sa.Integer, nullable=False),
        sa.Column("point", sa.Float, nullable=True),
        sa.Column("implied_probability", sa.Float, nullable=False),
        sa.Column("no_vig_probability", sa.Float, nullable=True),
        sa.Column("market_last_update", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("raw_outcome", JSONB, nullable=True),
    )
    op.create_unique_constraint(
        "uq_odds_snapshots_snapshot_key",
        "odds_snapshots",
        ["snapshot_key"],
    )
    op.create_index(
        "ix_odds_snapshots_game_batter_market_fetched",
        "odds_snapshots",
        ["game_date", "game_pk", "batter_id", "market_key", sa.text("fetched_at DESC")],
    )
    op.create_index(
        "ix_odds_snapshots_batter_date",
        "odds_snapshots",
        ["batter_id", "game_date"],
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_odds_snapshots_batter_date")
    op.execute("DROP INDEX IF EXISTS ix_odds_snapshots_game_batter_market_fetched")
    op.drop_constraint(
        "uq_odds_snapshots_snapshot_key",
        "odds_snapshots",
        type_="unique",
    )
    op.drop_table("odds_snapshots")

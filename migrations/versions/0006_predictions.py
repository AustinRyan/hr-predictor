"""predictions table — per-(batter, game, model_version) HR probability outputs.

Revision ID: 0006_predictions
Revises: 0005_weather_archive
Create Date: 2026-04-23

Schema decision (Phase 6 Task 1): dropped the PROMPT's per_pa_probabilities
column — Phase 5.5 established the model is per-matchup, not per-PA.
Replaced with matchup_components jsonb holding raw + calibrated probs
per matchup component (starter/bullpen), so audit trail is preserved.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_predictions"
down_revision = "0005_weather_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("game_pk", sa.Integer, nullable=False),
        sa.Column("batter_id", sa.Integer, nullable=False),
        sa.Column("pitcher_id", sa.Integer, nullable=False),
        sa.Column("game_date", sa.Date, nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("matchup_components", JSONB, nullable=False),
        sa.Column("projected_pas", sa.Float, nullable=True),
        sa.Column("prob_at_least_one_hr", sa.Float, nullable=False),
        sa.Column("prob_at_least_two_hr", sa.Float, nullable=True),
        sa.Column("expected_hrs", sa.Float, nullable=True),
        sa.Column("feature_contributions", JSONB, nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_unique_constraint(
        "uq_predictions_game_batter_model",
        "predictions",
        ["game_pk", "batter_id", "model_version"],
    )
    op.create_index(
        "ix_predictions_date_prob",
        "predictions",
        ["game_date", sa.text("prob_at_least_one_hr DESC")],
    )
    op.create_index(
        "ix_predictions_batter_date",
        "predictions",
        ["batter_id", "game_date"],
    )
    op.create_index(
        "ix_predictions_game_pk",
        "predictions",
        ["game_pk"],
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_predictions_game_pk")
    op.execute("DROP INDEX IF EXISTS ix_predictions_batter_date")
    op.execute("DROP INDEX IF EXISTS ix_predictions_date_prob")
    op.execute("DROP INDEX IF EXISTS uq_predictions_game_batter_model")
    op.execute("DROP TABLE IF EXISTS predictions")

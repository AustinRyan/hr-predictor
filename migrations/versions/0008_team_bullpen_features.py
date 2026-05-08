"""team bullpen features on matchup_features.

Revision ID: 0008_team_bullpen_features
Revises: 0007_odds_snapshots
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_team_bullpen_features"
down_revision = "0007_odds_snapshots"
branch_labels = None
depends_on = None


TEAM_BULLPEN_COLUMNS = (
    ("opp_team_id", sa.Integer()),
    ("opp_bp_hr_per_pa_30d", sa.Float()),
    ("opp_bp_hr_per_pa_season", sa.Float()),
    ("opp_bp_barrel_pct_allowed_30d", sa.Float()),
    ("opp_bp_barrel_pct_allowed_season", sa.Float()),
    ("opp_bp_hardhit_pct_allowed_30d", sa.Float()),
    ("opp_bp_hardhit_pct_allowed_season", sa.Float()),
    ("opp_bp_lhb_hr_per_pa_season", sa.Float()),
    ("opp_bp_rhb_hr_per_pa_season", sa.Float()),
    ("opp_bp_pitches_last_3d", sa.Float()),
)


def upgrade() -> None:
    for column_name, column_type in TEAM_BULLPEN_COLUMNS:
        op.add_column(
            "matchup_features",
            sa.Column(column_name, column_type, nullable=True),
        )
    op.create_index(
        "ix_matchup_features_date_opp_team",
        "matchup_features",
        ["game_date", "opp_team_id"],
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_matchup_features_date_opp_team")
    for column_name, _column_type in reversed(TEAM_BULLPEN_COLUMNS):
        op.drop_column("matchup_features", column_name)

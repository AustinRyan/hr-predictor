"""drop team FKs on games.

All-Star (game_type='A') and exhibition games carry MLB team_ids that
aren't part of the 30-franchise `teams` dimension table (e.g. 159 /
160 for the AL / NL All-Star sides). The FK was rejecting those rows
during backfill; drop it — `teams` remains a pure dimension table.

Revision ID: 0002_drop_games_team_fks
Revises: 0001_initial_schema
Create Date: 2026-04-22
"""

from __future__ import annotations

from alembic import op

revision = "0002_drop_games_team_fks"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `IF EXISTS` keeps the migration runnable against environments
    # whose 0001 already lacks the FKs (tests, fresh installs on the
    # updated spec).
    op.execute("ALTER TABLE games DROP CONSTRAINT IF EXISTS games_home_team_id_fkey")
    op.execute("ALTER TABLE games DROP CONSTRAINT IF EXISTS games_away_team_id_fkey")


def downgrade() -> None:
    op.create_foreign_key(
        "games_home_team_id_fkey",
        "games",
        "teams",
        ["home_team_id"],
        ["team_id"],
    )
    op.create_foreign_key(
        "games_away_team_id_fkey",
        "games",
        "teams",
        ["away_team_id"],
        ["team_id"],
    )

"""Schema tests for opponent team bullpen feature columns."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine
from src.core.models import MatchupFeature

EXPECTED_TEAM_BULLPEN_COLUMNS = {
    "opp_team_id",
    "opp_bp_hr_per_pa_30d",
    "opp_bp_hr_per_pa_season",
    "opp_bp_barrel_pct_allowed_30d",
    "opp_bp_barrel_pct_allowed_season",
    "opp_bp_hardhit_pct_allowed_30d",
    "opp_bp_hardhit_pct_allowed_season",
    "opp_bp_lhb_hr_per_pa_season",
    "opp_bp_rhb_hr_per_pa_season",
    "opp_bp_pitches_last_3d",
}


def test_matchup_feature_orm_has_team_bullpen_columns() -> None:
    columns = {column.name for column in MatchupFeature.__table__.columns}
    assert EXPECTED_TEAM_BULLPEN_COLUMNS.issubset(columns)


def test_matchup_features_table_has_team_bullpen_columns(test_engine: Engine) -> None:
    with test_engine.connect() as c:
        columns = set(
            c.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'matchup_features' AND table_schema = 'public'"
                )
            )
            .scalars()
            .all()
        )
    assert EXPECTED_TEAM_BULLPEN_COLUMNS.issubset(columns)


def test_matchup_features_team_bullpen_index_present(test_engine: Engine) -> None:
    with test_engine.connect() as c:
        indexes = set(
            c.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = 'matchup_features'"
                )
            )
            .scalars()
            .all()
        )
    assert "ix_matchup_features_date_opp_team" in indexes

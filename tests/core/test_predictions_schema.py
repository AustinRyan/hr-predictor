"""Smoke tests for the 0006_predictions migration."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def test_predictions_table_exists(test_engine: Engine) -> None:
    with test_engine.connect() as c:
        tables = (
            c.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'predictions'"
                )
            )
            .scalars()
            .all()
        )
    assert list(tables) == ["predictions"]


def test_predictions_columns_present(test_engine: Engine) -> None:
    expected = {
        "id",
        "game_pk",
        "batter_id",
        "pitcher_id",
        "game_date",
        "model_version",
        "matchup_components",
        "projected_pas",
        "prob_at_least_one_hr",
        "prob_at_least_two_hr",
        "expected_hrs",
        "feature_contributions",
        "generated_at",
    }
    with test_engine.connect() as c:
        cols = set(
            c.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'predictions' AND table_schema = 'public'"
                )
            )
            .scalars()
            .all()
        )
    assert expected.issubset(cols)


def test_predictions_unique_constraint_present(test_engine: Engine) -> None:
    with test_engine.connect() as c:
        rows = (
            c.execute(
                text(
                    "SELECT a.attname "
                    "FROM pg_constraint con "
                    "JOIN pg_attribute a ON a.attrelid = con.conrelid "
                    "AND a.attnum = ANY(con.conkey) "
                    "WHERE con.conrelid = 'predictions'::regclass AND con.contype = 'u' "
                    "ORDER BY array_position(con.conkey, a.attnum)"
                )
            )
            .scalars()
            .all()
        )
    assert list(rows) == ["game_pk", "batter_id", "model_version"]


def test_predictions_indexes_present(test_engine: Engine) -> None:
    expected = {
        "ix_predictions_date_prob",
        "ix_predictions_batter_date",
        "ix_predictions_game_pk",
    }
    with test_engine.connect() as c:
        idx = set(
            c.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = 'predictions'"
                )
            )
            .scalars()
            .all()
        )
    assert expected.issubset(idx)


def test_predictions_jsonb_roundtrip(test_engine: Engine, clean_tables) -> None:
    """Insert a row with jsonb columns, verify readback preserves structure."""
    from datetime import date

    from sqlalchemy.orm import sessionmaker
    from src.core.models import Prediction

    Session_ = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with Session_() as s:
        row = Prediction(
            game_pk=9999001,
            batter_id=999100,
            pitcher_id=999200,
            game_date=date(2026, 4, 23),
            model_version="v20260423_173917",
            matchup_components={
                "starter_raw_prob": 0.18,
                "starter_calibrated_prob": 0.14,
                "bullpen_raw_prob": None,
                "bullpen_calibrated_prob": None,
            },
            projected_pas=4.29,
            prob_at_least_one_hr=0.14,
            prob_at_least_two_hr=0.012,
            expected_hrs=0.16,
            feature_contributions={
                "b_barrel_pct_season": 0.05,
                "park_hr_factor_hand": 0.03,
            },
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        assert row.matchup_components["starter_calibrated_prob"] == 0.14
        assert row.feature_contributions["b_barrel_pct_season"] == 0.05

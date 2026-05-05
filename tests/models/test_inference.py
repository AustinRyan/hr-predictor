"""Tests for the inference pipeline."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xgboost
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from src.models.artifacts import save_model
from src.models.calibrate import fit_calibrator, save_calibrator
from src.models.data import FEATURE_COLUMNS
from src.models.inference import _validated_feature_schema, generate_predictions_for_date


def _train_tiny_model_and_calibrator(tmp_registry: Path) -> tuple[str, xgboost.Booster]:
    """Train a tiny model + calibrator, save to a test registry, return version."""
    rng = np.random.default_rng(seed=42)
    X = pd.DataFrame(rng.random((200, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS)
    y = (X[FEATURE_COLUMNS[0]] > 0.5).astype(int)

    dmat = xgboost.DMatrix(X.values, label=y.values, feature_names=FEATURE_COLUMNS)
    booster = xgboost.train(
        {"objective": "binary:logistic", "verbosity": 0, "seed": 42},
        dmat,
        num_boost_round=20,
    )

    ts = datetime(2026, 6, 1, tzinfo=UTC)
    version_dir = save_model(
        booster,
        config={},
        metrics={},
        feature_columns=FEATURE_COLUMNS,
        training_range=("2021-04-01", "2024-10-31"),
        data_hash="test_hash",
        registry_root=tmp_registry,
        timestamp=ts,
    )

    # Fit calibrator on same data (sanity — isotonic degenerates but works)
    raw = booster.predict(dmat)
    calibrator = fit_calibrator(raw, y.values)
    save_calibrator(calibrator, version_dir.name, registry_root=tmp_registry)
    return version_dir.name, booster


@pytest.fixture()
def tmp_registry(tmp_path: Path) -> Path:
    return tmp_path / "registry"


def test_validated_feature_schema_preserves_artifact_order() -> None:
    schema = ["park_hr_factor_hand", "b_barrel_pct_season", "ctx_projected_pa"]

    assert _validated_feature_schema(schema) == schema


def test_validated_feature_schema_rejects_unknown_columns() -> None:
    with pytest.raises(ValueError, match="missing_model_feature"):
        _validated_feature_schema(["b_barrel_pct_season", "missing_model_feature"])


@pytest.mark.integration
def test_generate_predictions_end_to_end(
    test_engine: Engine,
    clean_tables,
    tmp_registry: Path,
) -> None:
    """Seed a future matchup_features row, run inference, verify predictions row."""
    version, _ = _train_tiny_model_and_calibrator(tmp_registry)

    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    # Need a park so daily_schedule FK resolves.
    with session_factory() as s:
        s.execute(
            text("INSERT INTO parks (park_id, name) VALUES (99801, 'tp') ON CONFLICT DO NOTHING")
        )
        # Seed a daily_schedule + matchup_features row on 2026-04-23.
        s.execute(text("""
                INSERT INTO daily_schedule
                  (game_pk, game_date, home_team_id, away_team_id, venue_id, game_start_utc, status)
                VALUES (9990001, '2026-04-23', 1, 2, 99801, NOW(), 'Scheduled')
                """))
        # Minimal matchup_features row (all feature columns default to NULL, which
        # XGBoost handles natively via missing=NaN).
        s.execute(text("""
                INSERT INTO matchup_features
                  (game_date, game_pk, batter_id, pitcher_id, is_historical, park_id,
                   ctx_projected_pa, b_barrel_pct_season, b_avg_ev_season)
                VALUES ('2026-04-23', 9990001, 999100, 999200, FALSE, 99801,
                        4.29, 0.10, 92.0)
                """))
        s.commit()

    # Patch the _DEFAULT_REGISTRY for this test via registry_root; but our
    # generate_predictions_for_date doesn't take a registry_root arg for the
    # model loader. Workaround: monkeypatch the default.
    from src.models import artifacts

    orig_default = artifacts._DEFAULT_REGISTRY
    artifacts._DEFAULT_REGISTRY = tmp_registry
    try:
        n = generate_predictions_for_date(
            date(2026, 4, 23),
            model_version=version,
            engine=test_engine,
        )
    finally:
        artifacts._DEFAULT_REGISTRY = orig_default

    assert n == 1

    # Verify the row landed
    with session_factory() as s:
        row = s.execute(text("SELECT * FROM predictions WHERE game_pk = 9990001")).mappings().one()

    assert row["batter_id"] == 999100
    assert row["model_version"] == version
    assert 0.0 <= row["prob_at_least_one_hr"] <= 1.0
    assert row["matchup_components"]["starter_calibrated_prob"] is not None
    assert row["feature_contributions"] is None or isinstance(row["feature_contributions"], dict)
    assert row["projected_pas"] == pytest.approx(4.29)


@pytest.mark.integration
def test_generate_predictions_idempotent(
    test_engine: Engine,
    clean_tables,
    tmp_registry: Path,
) -> None:
    """Re-running produces same row count (upsert)."""
    version, _ = _train_tiny_model_and_calibrator(tmp_registry)

    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(
            text("INSERT INTO parks (park_id, name) VALUES (99802, 'tp2') ON CONFLICT DO NOTHING")
        )
        s.execute(text("""
                INSERT INTO daily_schedule
                  (game_pk, game_date, home_team_id, away_team_id, venue_id, game_start_utc, status)
                VALUES (9990002, '2026-04-23', 1, 2, 99802, NOW(), 'Scheduled')
                """))
        s.execute(text("""
                INSERT INTO matchup_features
                  (game_date, game_pk, batter_id, pitcher_id, is_historical, park_id,
                   ctx_projected_pa, b_barrel_pct_season)
                VALUES ('2026-04-23', 9990002, 999101, 999201, FALSE, 99802, 4.29, 0.08)
                """))
        s.commit()

    from src.models import artifacts

    orig = artifacts._DEFAULT_REGISTRY
    artifacts._DEFAULT_REGISTRY = tmp_registry
    try:
        n1 = generate_predictions_for_date(
            date(2026, 4, 23), model_version=version, engine=test_engine
        )
        n2 = generate_predictions_for_date(
            date(2026, 4, 23), model_version=version, engine=test_engine
        )
    finally:
        artifacts._DEFAULT_REGISTRY = orig

    with session_factory() as s:
        count = s.execute(
            text("SELECT COUNT(*) FROM predictions WHERE game_pk = 9990002")
        ).scalar_one()
    assert n1 == n2 == 1
    assert count == 1


@pytest.mark.integration
def test_generate_predictions_uses_latest_matchup_when_probable_changes(
    test_engine: Engine,
    clean_tables,
    tmp_registry: Path,
) -> None:
    """Stale probable-starter rows must not create duplicate prediction upserts."""
    version, _ = _train_tiny_model_and_calibrator(tmp_registry)

    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(text("""
                INSERT INTO matchup_features
                  (game_date, game_pk, batter_id, pitcher_id, is_historical,
                   ctx_projected_pa, b_barrel_pct_season, built_at)
                VALUES
                  ('2026-04-23', 9993001, 999301, 999401, FALSE,
                   4.00, 0.05, '2026-04-23 12:00:00+00'),
                  ('2026-04-23', 9993001, 999301, 999402, FALSE,
                   4.60, 0.10, '2026-04-23 13:00:00+00')
                """))
        s.commit()

    from src.models import artifacts

    orig = artifacts._DEFAULT_REGISTRY
    artifacts._DEFAULT_REGISTRY = tmp_registry
    try:
        n = generate_predictions_for_date(
            date(2026, 4, 23), model_version=version, engine=test_engine
        )
    finally:
        artifacts._DEFAULT_REGISTRY = orig

    with session_factory() as s:
        rows = (
            s.execute(
                text(
                    "SELECT batter_id, pitcher_id, projected_pas "
                    "FROM predictions WHERE game_pk = 9993001"
                )
            )
            .mappings()
            .all()
        )

    assert n == 1
    assert [dict(row) for row in rows] == [
        {"batter_id": 999301, "pitcher_id": 999402, "projected_pas": 4.6}
    ]


@pytest.mark.integration
def test_generate_predictions_prunes_stale_rows_for_model_date(
    test_engine: Engine,
    clean_tables,
    tmp_registry: Path,
) -> None:
    """Predictions for players no longer in the current feature set are removed."""
    version, _ = _train_tiny_model_and_calibrator(tmp_registry)

    session_factory = sessionmaker(bind=test_engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        s.execute(text("""
                INSERT INTO matchup_features
                  (game_date, game_pk, batter_id, pitcher_id, is_historical,
                   ctx_projected_pa, b_barrel_pct_season)
                VALUES
                  ('2026-04-23', 9994001, 999401, 999501, FALSE, 4.60, 0.10)
                """))
        s.execute(
            text("""
                INSERT INTO predictions
                  (game_pk, batter_id, pitcher_id, game_date, model_version,
                   matchup_components, projected_pas, prob_at_least_one_hr,
                   prob_at_least_two_hr, expected_hrs, feature_contributions)
                VALUES
                  (9994001, 999499, 999501, '2026-04-23', :version,
                   '{}'::jsonb, 4.0, 0.05, 0.0, 0.05, NULL)
                """),
            {"version": version},
        )
        s.commit()

    from src.models import artifacts

    orig = artifacts._DEFAULT_REGISTRY
    artifacts._DEFAULT_REGISTRY = tmp_registry
    try:
        n = generate_predictions_for_date(
            date(2026, 4, 23), model_version=version, engine=test_engine
        )
    finally:
        artifacts._DEFAULT_REGISTRY = orig

    with session_factory() as s:
        rows = (
            s.execute(
                text(
                    "SELECT batter_id FROM predictions "
                    "WHERE game_date = '2026-04-23' AND model_version = :version"
                ),
                {"version": version},
            )
            .scalars()
            .all()
        )

    assert n == 1
    assert rows == [999401]


@pytest.mark.integration
def test_generate_returns_zero_on_empty_date(
    test_engine: Engine,
    clean_tables,
    tmp_registry: Path,
) -> None:
    version, _ = _train_tiny_model_and_calibrator(tmp_registry)

    from src.models import artifacts

    orig = artifacts._DEFAULT_REGISTRY
    artifacts._DEFAULT_REGISTRY = tmp_registry
    try:
        n = generate_predictions_for_date(
            date(1970, 1, 1),
            model_version=version,
            engine=test_engine,
        )
    finally:
        artifacts._DEFAULT_REGISTRY = orig
    assert n == 0

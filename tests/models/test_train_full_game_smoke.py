"""Smoke tests for the full-game HR trainer."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
from src.models.full_game_data import FullGameFeatureFrame, FullGameTrainValTest
from src.models.train_full_game import FullGameTrainingConfig, train_full_game_model


def _frame(values: list[tuple[float, float, float, int]], day: date) -> FullGameFeatureFrame:
    rows = [
        {
            "b_hr_per_pa_season": batter_power,
            "p_hr_per_9_season": pitcher_hr9,
            "opp_bp_hr_per_pa_30d": bullpen_hr_rate,
        }
        for batter_power, pitcher_hr9, bullpen_hr_rate, _label in values
    ]
    labels = [label for *_features, label in values]
    dates = [day for _ in values]
    metadata = pd.DataFrame(
        {
            "game_date": dates,
            "game_pk": list(range(1, len(values) + 1)),
            "batter_id": list(range(100, 100 + len(values))),
            "starter_pitcher_id": list(range(200, 200 + len(values))),
        }
    )
    return FullGameFeatureFrame(
        X=pd.DataFrame(rows),
        y=pd.Series(labels),
        dates=pd.Series(dates),
        metadata=metadata,
    )


def test_train_full_game_model_writes_semantic_artifact_metadata(tmp_path) -> None:
    splits = FullGameTrainValTest(
        train=_frame(
            [
                (0.20, 2.0, 0.10, 1),
                (0.05, 0.4, 0.01, 0),
                (0.18, 1.6, 0.08, 1),
                (0.04, 0.3, 0.02, 0),
            ],
            date(2024, 4, 1),
        ),
        val=_frame(
            [
                (0.19, 1.8, 0.09, 1),
                (0.03, 0.2, 0.01, 0),
                (0.16, 1.4, 0.07, 1),
                (0.06, 0.5, 0.02, 0),
            ],
            date(2024, 5, 1),
        ),
        test=_frame(
            [
                (0.21, 2.1, 0.11, 1),
                (0.02, 0.1, 0.01, 0),
                (0.17, 1.5, 0.06, 1),
                (0.07, 0.6, 0.03, 0),
            ],
            date(2024, 6, 1),
        ),
    )
    config = FullGameTrainingConfig(
        n_estimators=8,
        max_depth=2,
        learning_rate=0.2,
        early_stopping_rounds=3,
        top_k_per_day=2,
        random_seed=7,
    )

    result = train_full_game_model(config=config, splits=splits, registry_root=tmp_path)

    metadata = json.loads((result.artifact_path / "training_metadata.json").read_text())
    assert metadata["target"] == "full_game_hr"
    assert metadata["uses_team_bullpen_features"] is True
    assert metadata["probability_semantics"] == "batter hits at least one HR in the full game"
    assert (result.artifact_path / "calibrator.joblib").exists()

    schema = json.loads((result.artifact_path / "feature_schema.json").read_text())
    assert schema["features"] == splits.train.X.columns.tolist()

"""Daily inference: generate predictions for all of today's games.

For each (batter, probable-opposing-starter, game) matchup on the target
date:
  1. Pull the matchup_features row (already computed nightly by
     Phase 3's builder or Phase 2's daily_runner).
  2. Apply the model + calibrator to get a calibrated starter-matchup prob.
  3. Compose into a per-game distribution via per_game_hr_distribution
     (bullpen prob is None - documented Phase 6 simplification).
  4. Compute top-10 feature contributions via SHAP.
  5. Upsert into the `predictions` table with ON CONFLICT DO UPDATE.

Idempotent: re-running for the same date + model_version produces
identical rows (modulo `generated_at` which advances).
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
import pandas as pd
import shap
import xgboost
from sqlalchemy import delete, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.db import get_engine
from src.core.models import MatchupFeature, Prediction
from src.core.time import current_mlb_date
from src.models.artifacts import load_model
from src.models.calibrate import apply_calibrator, load_calibrator
from src.models.per_game_hr import (
    GameMatchupInputs,
    full_game_hr_distribution,
    per_game_hr_distribution,
)

_log = logging.getLogger(__name__)

_SHAP_TOP_K = 10


def _validated_feature_schema(feature_schema: list[str]) -> list[str]:
    """Return artifact feature schema after checking every column exists."""
    valid_columns = {c.name for c in MatchupFeature.__table__.columns}
    missing = [c for c in feature_schema if c not in valid_columns]
    if missing:
        raise ValueError(
            f"model feature schema has columns absent from matchup_features: {missing}"
        )
    return list(feature_schema)


def _delete_stale_prediction_rows(
    session: Session,
    rows: list[dict[str, Any]],
    *,
    target_date: date,
    model_version: str,
) -> int:
    """Delete predictions for players no longer in the current model-date slate."""
    current_keys = sorted({(int(r["game_pk"]), int(r["batter_id"])) for r in rows})
    if not current_keys:
        return 0

    stmt = delete(Prediction).where(
        Prediction.game_date == target_date,
        Prediction.model_version == model_version,
        tuple_(Prediction.game_pk, Prediction.batter_id).notin_(current_keys),
    )
    result = session.execute(stmt)
    deleted = result.rowcount if result.rowcount is not None and result.rowcount > 0 else 0
    if deleted:
        _log.info(
            "inference pruned stale prediction rows",
            extra={
                "date": target_date.isoformat(),
                "model_version": model_version,
                "rows": deleted,
            },
        )
    return deleted


def generate_predictions_for_date(
    target_date: date,
    *,
    model_version: str | None = None,
    engine: Engine | None = None,
) -> int:
    """Produce predictions for all matchups on target_date. Returns row count written."""
    engine = engine or get_engine()
    loaded = load_model(version=model_version)
    try:
        calibrator = load_calibrator(loaded.version)
    except FileNotFoundError:
        _log.warning(
            "no calibrator for model; using raw probs",
            extra={"model_version": loaded.version},
        )
        calibrator = None

    is_full_game_model = loaded.training_metadata.get("target") == "full_game_hr"

    # Ensemble support (Option 3): if training_metadata declares an
    # ``ensemble`` block, look for a sibling LightGBM booster at
    # ``lightgbm.txt`` and average its probs with the XGBoost model's
    # probs at inference time (50/50, matching training-time composition).
    ensemble_meta = loaded.training_metadata.get("ensemble")
    lgbm_booster = None
    if ensemble_meta:
        lgbm_path = loaded.path / "lightgbm.txt"
        if lgbm_path.exists():
            import lightgbm as lgb

            lgbm_booster = lgb.Booster(model_file=str(lgbm_path))
            _log.info(
                "loaded ensemble LightGBM component",
                extra={"path": str(lgbm_path), "ensemble": ensemble_meta},
            )
        else:
            _log.warning(
                "ensemble metadata present but lightgbm.txt missing; "
                "falling back to XGBoost-only",
                extra={"model_version": loaded.version},
            )

    # Pull the batter x probable-starter tuples + their matchup_features row.
    # Key insight: matchup_features is keyed by (game_date, game_pk, batter_id,
    # pitcher_id). For future rows, is_historical=False and ctx_batting_order
    # is populated from projected_lineups.
    session_factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)

    with session_factory() as s:
        feature_schema = _validated_feature_schema(loaded.feature_schema)
        feat_cols_inner_sql = ", ".join(f"mf.{c}" for c in feature_schema)
        feat_cols_outer_sql = ", ".join(feature_schema)
        rows = (
            s.execute(
                text(f"""
                    WITH ranked_matchups AS (
                        SELECT
                            mf.game_pk,
                            mf.batter_id,
                            mf.pitcher_id,
                            mf.game_date,
                            mf.ctx_projected_pa AS projected_pa_for_output,
                            {feat_cols_inner_sql},
                            COUNT(*) OVER (
                                PARTITION BY mf.game_pk, mf.batter_id
                            ) AS duplicate_matchup_count,
                            ROW_NUMBER() OVER (
                                PARTITION BY mf.game_pk, mf.batter_id
                                ORDER BY mf.built_at DESC, mf.pitcher_id DESC
                            ) AS matchup_rank
                        FROM matchup_features mf
                        WHERE mf.game_date = :d
                          AND NOT mf.is_historical
                    )
                    SELECT
                        game_pk,
                        batter_id,
                        pitcher_id,
                        game_date,
                        projected_pa_for_output,
                        duplicate_matchup_count,
                        {feat_cols_outer_sql}
                    FROM ranked_matchups
                    WHERE matchup_rank = 1
                    ORDER BY game_pk, batter_id
                    """),
                {"d": target_date},
            )
            .mappings()
            .all()
        )

    if not rows:
        _log.info(
            "no matchup_features rows for target_date",
            extra={"date": target_date.isoformat()},
        )
        return 0

    _log.info(
        "inference input loaded",
        extra={"date": target_date.isoformat(), "rows": len(rows)},
    )
    stale_matchups_skipped = sum(
        int(r["duplicate_matchup_count"]) - 1 for r in rows if int(r["duplicate_matchup_count"]) > 1
    )
    if stale_matchups_skipped:
        _log.warning(
            "inference skipped stale duplicate matchup rows",
            extra={
                "date": target_date.isoformat(),
                "rows": stale_matchups_skipped,
            },
        )

    # Build feature DataFrame in the exact order saved with the model artifact.
    feature_schema = _validated_feature_schema(loaded.feature_schema)
    feat_df = pd.DataFrame(
        [{c: r[c] for c in feature_schema} for r in rows],
        columns=feature_schema,
    )
    dmat = xgboost.DMatrix(feat_df.values, feature_names=feature_schema)
    raw_xgb = loaded.model.predict(dmat)
    if lgbm_booster is not None:
        raw_lgb = lgbm_booster.predict(feat_df, num_iteration=lgbm_booster.best_iteration)
        raw_probs = 0.5 * raw_xgb + 0.5 * raw_lgb
    else:
        raw_probs = raw_xgb
    cal_probs = apply_calibrator(calibrator, raw_probs) if calibrator else raw_probs

    # SHAP top-k feature contributions per row. We prefer `shap.TreeExplainer`,
    # but it fails on some Booster metadata formats in XGBoost 2.x/3.x (see
    # abstract.md). Fallback to XGBoost's native `pred_contribs=True`, which
    # returns the same TreeSHAP output as an (n_rows, n_features + 1) array
    # where the last column is the bias term. Strip it and we have an
    # equivalent SHAP values matrix.
    shap_values: np.ndarray | None
    try:
        explainer = shap.TreeExplainer(loaded.model)
        shap_values = explainer.shap_values(feat_df)
        if isinstance(shap_values, list):  # multi-class fallback
            shap_values = shap_values[0]
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "SHAP TreeExplainer failed, falling back to Booster.pred_contribs",
            extra={"err": str(exc)},
        )
        try:
            contribs = loaded.model.predict(dmat, pred_contribs=True)
            # Drop trailing bias column
            shap_values = np.asarray(contribs[:, :-1])
        except Exception as exc2:  # noqa: BLE001
            _log.warning(
                "pred_contribs fallback also failed; predictions will have empty contributions",
                extra={"err": str(exc2)},
            )
            shap_values = None

    # Assemble prediction rows
    generated_at = datetime.now(UTC)
    to_write: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        raw_p = float(raw_probs[i])
        cal_p = float(cal_probs[i])
        projected_pa_value = r["projected_pa_for_output"]
        projected_pas = float(projected_pa_value) if projected_pa_value is not None else 4.0

        if is_full_game_model:
            dist = full_game_hr_distribution(cal_p)
            matchup_components = {
                "probability_semantics": "full_game_hr",
                "full_game_raw_prob": raw_p,
                "full_game_calibrated_prob": cal_p,
                # Backward-compatible diagnostic keys used by the API/UI.
                # For full-game artifacts these are aliases for the starter-row
                # feature snapshot, not an old starter-only model output.
                "starter_raw_prob": raw_p,
                "starter_calibrated_prob": cal_p,
                "starter_signal_source": "full_game_artifact_starter_row",
                "bullpen_raw_prob": None,
                "bullpen_calibrated_prob": None,
            }
        else:
            dist = per_game_hr_distribution(
                GameMatchupInputs(starter_prob=cal_p, bullpen_prob=None)
            )
            matchup_components = {
                "probability_semantics": "starter_matchup_hr",
                "starter_raw_prob": raw_p,
                "starter_calibrated_prob": cal_p,
                "bullpen_raw_prob": None,
                "bullpen_calibrated_prob": None,
            }

        # Top-K SHAP contributions by absolute value, preserve sign
        contributions: dict[str, float] = {}
        if shap_values is not None:
            row_shap = shap_values[i]
            idx_sorted = np.argsort(-np.abs(row_shap))[:_SHAP_TOP_K]
            for idx in idx_sorted:
                contributions[feature_schema[int(idx)]] = float(row_shap[int(idx)])

        to_write.append(
            {
                "game_pk": int(r["game_pk"]),
                "batter_id": int(r["batter_id"]),
                "pitcher_id": int(r["pitcher_id"]),
                "game_date": r["game_date"],
                "model_version": loaded.version,
                "matchup_components": matchup_components,
                "projected_pas": projected_pas,
                "prob_at_least_one_hr": dist.prob_at_least_one,
                "prob_at_least_two_hr": dist.prob_at_least_two,
                "expected_hrs": dist.expected_hrs,
                "feature_contributions": contributions or None,
                "generated_at": generated_at,
            }
        )

    # Upsert
    with session_factory() as s:
        stale_predictions_deleted = _delete_stale_prediction_rows(
            s,
            to_write,
            target_date=target_date,
            model_version=loaded.version,
        )
        stmt = pg_insert(Prediction).values(to_write)
        update_cols = {
            c.name: getattr(stmt.excluded, c.name)
            for c in Prediction.__table__.columns
            if c.name not in {"id", "game_pk", "batter_id", "model_version"}
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_predictions_game_batter_model",
            set_=update_cols,
        )
        s.execute(stmt)
        s.commit()

    _log.info(
        "predictions written",
        extra={
            "date": target_date.isoformat(),
            "model_version": loaded.version,
            "rows": len(to_write),
            "stale_predictions_deleted": stale_predictions_deleted,
        },
    )
    return len(to_write)


def main() -> int:  # pragma: no cover
    """CLI entry: python -m src.models.inference [--date YYYY-MM-DD] [--model-version v...]"""
    import argparse

    from src.core.logging_config import configure_logging

    configure_logging()
    logging.getLogger().setLevel("INFO")

    p = argparse.ArgumentParser(description="Generate daily HR predictions")
    p.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="Target game date (default: current MLB slate date in America/New_York)",
    )
    p.add_argument("--model-version", default=None, help="Explicit model version")
    args = p.parse_args()

    target = args.date or current_mlb_date()
    n = generate_predictions_for_date(target, model_version=args.model_version)
    print(f"[DONE] wrote {n} predictions for {target}", flush=True)
    return 0 if n > 0 else 0  # no error on zero - may be off-day


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""Compare today's top-5 predictions across OLD, NEW-default, and Option 3 winner.

Runs inference for 2026-04-23 (or --date) with each model version, joins
to batter/pitcher names, and prints a side-by-side top-5. Also pulls
feature-attribution (SHAP) for the Sánchez–Skubal and Ohtani–Webb
watch-matchups.

Does NOT touch PRODUCTION.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xgboost  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from src.core.db import get_engine  # noqa: E402
from src.models.artifacts import load_model  # noqa: E402
from src.models.calibrate import apply_calibrator, load_calibrator  # noqa: E402
from src.models.data import FEATURE_COLUMNS  # noqa: E402

OLD_VERSION = "v20260423_173917"
NEW_VERSION = "v20260423_230717"


def _names_for_ids(session, ids: list[int]) -> dict[int, str]:
    """Look up names in the `players` table keyed by `mlbam_id`."""
    if not ids:
        return {}
    rows = session.execute(
        text("SELECT mlbam_id, full_name FROM players WHERE mlbam_id = ANY(:ids)"),
        {"ids": list(set(ids))},
    ).all()
    return {r[0]: r[1] for r in rows}


def _predict(
    version: str,
    target_date: date,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Load model (+ optional ensemble sibling), predict for `target_date`.

    Returns (feature_df, raw_probs, cal_probs).
    """
    engine = get_engine()
    loaded = load_model(version=version)
    try:
        calibrator = load_calibrator(loaded.version)
    except FileNotFoundError:
        calibrator = None

    # Ensemble detection (matches src.models.inference).
    lgbm_booster = None
    if loaded.training_metadata.get("ensemble"):
        lgbm_path = loaded.path / "lightgbm.txt"
        if lgbm_path.exists():
            import lightgbm as lgb

            lgbm_booster = lgb.Booster(model_file=str(lgbm_path))

    session_factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        feat_cols_sql = ", ".join(f"mf.{c}" for c in FEATURE_COLUMNS)
        rows = (
            s.execute(
                text(f"""
                    SELECT mf.game_pk, mf.batter_id, mf.pitcher_id, mf.game_date,
                           {feat_cols_sql}
                    FROM matchup_features mf
                    WHERE mf.game_date = :d
                      AND NOT mf.is_historical
                """),
                {"d": target_date},
            )
            .mappings()
            .all()
        )

    feat_df = pd.DataFrame(
        [{c: r[c] for c in FEATURE_COLUMNS} for r in rows],
        columns=FEATURE_COLUMNS,
    )
    meta_df = pd.DataFrame(
        [
            {
                "game_pk": r["game_pk"],
                "batter_id": r["batter_id"],
                "pitcher_id": r["pitcher_id"],
            }
            for r in rows
        ]
    )

    dmat = xgboost.DMatrix(feat_df.values, feature_names=loaded.feature_schema)
    raw_xgb = loaded.model.predict(dmat)
    if lgbm_booster is not None:
        raw_lgb = lgbm_booster.predict(feat_df, num_iteration=lgbm_booster.best_iteration)
        raw_probs = 0.5 * raw_xgb + 0.5 * raw_lgb
    else:
        raw_probs = raw_xgb

    cal_probs = apply_calibrator(calibrator, raw_probs) if calibrator is not None else raw_probs
    meta_df["raw_prob"] = raw_probs
    meta_df["cal_prob"] = cal_probs
    return meta_df, raw_probs, cal_probs, feat_df, loaded, lgbm_booster


def _top5(df: pd.DataFrame, names: dict[int, str]) -> None:
    top = df.sort_values("cal_prob", ascending=False).head(5)
    for _, row in top.iterrows():
        b = names.get(int(row["batter_id"]), f"id:{int(row['batter_id'])}")
        p = names.get(int(row["pitcher_id"]), f"id:{int(row['pitcher_id'])}")
        print(
            f"  {b} vs {p}: cal={row['cal_prob']:.4f} raw={row['raw_prob']:.4f}",
            flush=True,
        )


def _shap_row(
    feat_df: pd.DataFrame,
    loaded,
    lgbm_booster,
    row_idx: int,
    top_k: int = 10,
) -> list[tuple[str, float]]:
    """Combined SHAP for one row: XGB (pred_contribs) + LGB (pred_contrib)
    each halved when ensembling, summed per feature.
    """
    schema = loaded.feature_schema
    dmat = xgboost.DMatrix(feat_df.iloc[[row_idx]].values, feature_names=schema)
    contrib_xgb = loaded.model.predict(dmat, pred_contribs=True)[0][:-1]  # drop bias
    total = np.array(contrib_xgb, dtype=float)
    if lgbm_booster is not None:
        contrib_lgb = lgbm_booster.predict(
            feat_df.iloc[[row_idx]],
            pred_contrib=True,
            num_iteration=lgbm_booster.best_iteration,
        )[0][:-1]
        # Ensemble averages probs, but for SHAP on RAW log-odds the
        # probs-average isn't strictly linear. Still, a half-and-half
        # aggregation is a reasonable diagnostic approximation.
        total = 0.5 * total + 0.5 * np.array(contrib_lgb, dtype=float)
    idx = np.argsort(-np.abs(total))[:top_k]
    return [(schema[int(i)], float(total[int(i)])) for i in idx]


def _find_matchup(meta_df: pd.DataFrame, names: dict[int, str], batter_sub: str) -> int | None:
    """Case-insensitive substring match on batter full_name. Returns row index or None."""
    batter_sub = batter_sub.lower()
    for i, bid in enumerate(meta_df["batter_id"].to_numpy()):
        nm = (names.get(int(bid)) or "").lower()
        if batter_sub in nm:
            return i
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date(2026, 4, 23),
    )
    ap.add_argument("--winner-version", required=True)
    args = ap.parse_args()

    target = args.date
    winner_v = args.winner_version

    # Gather predictions from each model.
    out = {}
    for label, ver in [
        ("OLD (120 feat, days_rest)", OLD_VERSION),
        ("NEW default (118 feat)", NEW_VERSION),
        ("WINNER (option 3)", winner_v),
    ]:
        # NEW/OLD used pre-days_rest data.py, which includes
        # ctx_*_days_rest in FEATURE_COLUMNS. Our current FEATURE_COLUMNS
        # excludes them. For OLD we can't truly reproduce its inference
        # here without reverting data.py. Instead, per the task, the
        # comparison is: "OLD's top-5 was produced when those features
        # were in; we already have it logged. NEW's top-5 was produced
        # with 118 features and is reproducible now."
        # The practical path: for OLD, read the feature_schema from its
        # artifact and fetch + predict using those columns directly.
        meta_df, raw_probs, cal_probs, feat_df, loaded, lgbm_booster = _predict_with_schema(
            ver, target
        )
        out[label] = (meta_df, feat_df, loaded, lgbm_booster)

    # Names lookup — union all (batter_id, pitcher_id) across the three runs.
    all_ids: list[int] = []
    for meta_df, *_ in out.values():
        all_ids.extend(meta_df["batter_id"].tolist())
        all_ids.extend(meta_df["pitcher_id"].tolist())
    engine = get_engine()
    session_factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        names = _names_for_ids(s, list(set(all_ids)))

    # Top-5 per model.
    for label, (meta_df, _feat_df, _loaded, _lgbm) in out.items():
        print(f"\n=== {label} top-5 ===", flush=True)
        _top5(meta_df, names)

    # Distribution summary.
    print("\n=== Distribution comparison (cal_prob) ===", flush=True)
    for label, (meta_df, *_rest) in out.items():
        arr = meta_df["cal_prob"].to_numpy()
        print(
            f"  {label}: min={arr.min():.4f} median={np.median(arr):.4f} "
            f"mean={arr.mean():.4f} max={arr.max():.4f} "
            f"n>=9%: {int((arr >= 0.09).sum())}",
            flush=True,
        )

    # Focus matchups.
    for focus in ["sánchez", "ohtani"]:
        print(f"\n=== focus: {focus} ===", flush=True)
        for label, (meta_df, feat_df, loaded, lgbm_booster) in out.items():
            ridx = _find_matchup(meta_df, names, focus)
            if ridx is None:
                print(f"  {label}: (no matchup found for '{focus}')", flush=True)
                continue
            row = meta_df.iloc[ridx]
            b = names.get(int(row["batter_id"]), f"id:{int(row['batter_id'])}")
            p = names.get(int(row["pitcher_id"]), f"id:{int(row['pitcher_id'])}")
            print(
                f"  {label}: {b} vs {p}: " f"cal={row['cal_prob']:.4f} raw={row['raw_prob']:.4f}",
                flush=True,
            )
            shap_top = _shap_row(feat_df, loaded, lgbm_booster, ridx, top_k=10)
            print("    Top 10 SHAP:", flush=True)
            for name, val in shap_top:
                print(f"      {name}: {val:+.4f}", flush=True)
    return 0


def _predict_with_schema(
    version: str,
    target_date: date,
):
    """Like _predict, but always uses the artifact's feature_schema — this
    handles OLD vs NEW differing in ``ctx_*_days_rest``. For the current
    data.py exclusion set, the intersecting columns from matchup_features
    are all we need; missing columns on OLD are re-queried explicitly.
    """
    engine = get_engine()
    loaded = load_model(version=version)
    try:
        calibrator = load_calibrator(loaded.version)
    except FileNotFoundError:
        calibrator = None

    lgbm_booster = None
    if loaded.training_metadata.get("ensemble"):
        lgbm_path = loaded.path / "lightgbm.txt"
        if lgbm_path.exists():
            import lightgbm as lgb

            lgbm_booster = lgb.Booster(model_file=str(lgbm_path))

    schema: list[str] = loaded.feature_schema
    session_factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with session_factory() as s:
        feat_cols_sql = ", ".join(f"mf.{c}" for c in schema)
        rows = (
            s.execute(
                text(f"""
                    SELECT mf.game_pk, mf.batter_id, mf.pitcher_id, mf.game_date,
                           {feat_cols_sql}
                    FROM matchup_features mf
                    WHERE mf.game_date = :d
                      AND NOT mf.is_historical
                """),
                {"d": target_date},
            )
            .mappings()
            .all()
        )

    feat_df = pd.DataFrame(
        [{c: r[c] for c in schema} for r in rows],
        columns=schema,
    )
    meta_df = pd.DataFrame(
        [
            {
                "game_pk": r["game_pk"],
                "batter_id": r["batter_id"],
                "pitcher_id": r["pitcher_id"],
            }
            for r in rows
        ]
    )

    dmat = xgboost.DMatrix(feat_df.values, feature_names=schema)
    raw_xgb = loaded.model.predict(dmat)
    if lgbm_booster is not None:
        raw_lgb = lgbm_booster.predict(feat_df, num_iteration=lgbm_booster.best_iteration)
        raw_probs = 0.5 * raw_xgb + 0.5 * raw_lgb
    else:
        raw_probs = raw_xgb

    cal_probs = apply_calibrator(calibrator, raw_probs) if calibrator is not None else raw_probs
    meta_df["raw_prob"] = raw_probs
    meta_df["cal_prob"] = cal_probs
    return meta_df, raw_probs, cal_probs, feat_df, loaded, lgbm_booster


if __name__ == "__main__":
    raise SystemExit(main())

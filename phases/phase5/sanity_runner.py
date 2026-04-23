"""Phase 5 sanity: identify the highest + lowest P(>=1 HR) games in
the test set to verify the full pipeline makes physical sense.

Usage:
    uv run python -u phases/phase5/sanity_runner.py

Runs end-to-end on the test slice: raw Booster predict -> isotonic
calibrate -> per-game rollup via per_game_hr_distribution. Phase 3's
`hr_on_pa` label is per-(batter, pitcher, game), so the model's
calibrated output IS already the per-matchup game-level probability.
We only predict vs the starter matchup row today, so P(>=1 HR) reduces
to the starter's matchup probability (bullpen contribution is implicit
in the matchup row's `bp_*` features). See `phases/phase5/NOTES.md`
"Rollup semantic bug" for the full narrative.

Joins matchup identity (game_pk, batter_id, pitcher_id, park_id) from
matchup_features + player/park name lookups so the top/bottom rows
read like actual lineups.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xgboost  # noqa: E402
from sqlalchemy import text  # noqa: E402
from src.core.db import get_engine  # noqa: E402
from src.models.artifacts import load_model  # noqa: E402
from src.models.calibrate import apply_calibrator, load_calibrator  # noqa: E402
from src.models.data import time_based_split  # noqa: E402
from src.models.per_game_hr import GameMatchupInputs, per_game_hr_distribution  # noqa: E402


def main() -> int:
    loaded = load_model()
    calibrator = load_calibrator(loaded.version)
    print(f"[load] model={loaded.version} + calibrator.joblib", flush=True)

    splits = time_based_split()
    test = splits.test
    print(f"[data] test rows={len(test.X):,}", flush=True)

    dmat = xgboost.DMatrix(test.X.values, feature_names=loaded.feature_schema)
    raw = loaded.model.predict(dmat)
    cal = apply_calibrator(calibrator, raw)

    print(
        "[note] starter-only composition; bullpen is implicit in the model's "
        "matchup-level prediction.",
        flush=True,
    )

    p_at_least_one = np.empty(len(cal), dtype=np.float64)
    for i in range(len(cal)):
        dist = per_game_hr_distribution(GameMatchupInputs(starter_prob=float(cal[i])))
        p_at_least_one[i] = dist.prob_at_least_one

    engine = get_engine()
    start, end = test.dates.min(), test.dates.max()
    with engine.connect() as c:
        ids = pd.read_sql(
            text(
                "SELECT game_date, hr_on_pa, game_pk, batter_id, pitcher_id, park_id "
                "FROM matchup_features "
                "WHERE is_historical = TRUE "
                "AND hr_on_pa IS NOT NULL "
                "AND game_date BETWEEN :s AND :e "
                "ORDER BY game_date"
            ),
            c,
            params={"s": start, "e": end},
        )
        assert len(ids) == len(cal), f"row count mismatch: ids={len(ids)} predictions={len(cal)}"

        player_ids = sorted(
            set(ids["batter_id"].unique().tolist()) | set(ids["pitcher_id"].unique().tolist())
        )
        player_names = pd.read_sql(
            text("SELECT mlbam_id, full_name FROM players WHERE mlbam_id = ANY(:ids)"),
            c,
            params={"ids": player_ids},
        )
        park_names = pd.read_sql(text("SELECT park_id, name FROM parks"), c)

    name_map = dict(zip(player_names.mlbam_id, player_names.full_name, strict=False))
    park_map = dict(zip(park_names.park_id, park_names.name, strict=False))

    ids["p_at_least_one"] = p_at_least_one
    ids["raw"] = raw
    ids["calibrated"] = cal
    ids["batter_name"] = ids["batter_id"].map(name_map)
    ids["pitcher_name"] = ids["pitcher_id"].map(name_map)
    ids["park_name"] = ids["park_id"].map(park_map)

    top5 = ids.nlargest(5, "p_at_least_one")
    bot5 = ids.nsmallest(5, "p_at_least_one")
    show_cols = [
        "game_date",
        "batter_name",
        "pitcher_name",
        "park_name",
        "calibrated",
        "p_at_least_one",
    ]
    print("=== TOP 5 P(>=1 HR) in test set ===", flush=True)
    print(top5[show_cols].to_string(index=False), flush=True)
    print()
    print("=== BOTTOM 5 P(>=1 HR) in test set ===", flush=True)
    print(bot5[show_cols].to_string(index=False), flush=True)
    print()
    print(
        f"Distribution: min={p_at_least_one.min():.4f} "
        f"median={np.median(p_at_least_one):.4f} "
        f"max={p_at_least_one.max():.4f} "
        f"mean={p_at_least_one.mean():.4f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

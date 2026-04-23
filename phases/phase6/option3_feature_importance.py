"""Print top-10 feature importances for the Option 3 winner's XGB and LGB components."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import lightgbm as lgb  # noqa: E402
import numpy as np  # noqa: E402
from src.models.artifacts import load_model  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    args = ap.parse_args()

    loaded = load_model(version=args.version)
    schema = loaded.feature_schema

    # XGBoost — gain-based importance.
    booster = loaded.model
    score = booster.get_score(importance_type="gain")
    # XGBoost names features f0, f1, ... when loaded via Booster without a
    # DMatrix; map those to schema via order.
    # Actually with feature_names stored, get_score returns the actual names.
    pairs = sorted(score.items(), key=lambda kv: -kv[1])[:10]
    print("=== XGBoost top-10 (gain) ===")
    for name, gain in pairs:
        # When feature_names aren't in the booster, names look like "f{i}".
        if name.startswith("f") and name[1:].isdigit():
            name = schema[int(name[1:])]
        print(f"  {name}: {gain:,.2f}")

    # LightGBM.
    lgbm_path = loaded.path / "lightgbm.txt"
    if lgbm_path.exists():
        lgbm = lgb.Booster(model_file=str(lgbm_path))
        gain = lgbm.feature_importance(importance_type="gain")
        names = lgbm.feature_name()
        order = np.argsort(-gain)[:10]
        print("\n=== LightGBM top-10 (gain) ===")
        for idx in order:
            print(f"  {names[idx]}: {gain[idx]:,.2f}")

    # Red-flag check: `ctx_*_days_rest` should NOT appear.
    flagged = [s for s in schema if "days_rest" in s]
    if flagged:
        print(f"\n[!] days_rest features in schema: {flagged} " "(should be excluded for Option 3)")
    else:
        print("\n[ok] no days_rest features in schema (118 feature set)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

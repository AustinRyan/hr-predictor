"""Phase 5: fit isotonic calibrator on Phase 4 model's val predictions,
evaluate on test, save next to the model artifact.

Usage:
    uv run python -u phases/phase5/calibrate_runner.py

Safe to re-run — overwrites calibrator.joblib next to the model artifact
and re-emits the pre/post reliability plot under reports/.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import xgboost  # noqa: E402
from src.core.logging_config import configure_logging  # noqa: E402
from src.models.artifacts import load_model  # noqa: E402
from src.models.calibrate import (  # noqa: E402
    apply_calibrator,
    fit_calibrator,
    save_calibrator,
)
from src.models.data import time_based_split  # noqa: E402
from src.models.eval import (  # noqa: E402
    brier_score,
    expected_calibration_error,
    log_loss,
    plot_reliability,
    reliability_curve,
)


def main() -> int:
    configure_logging()
    logging.getLogger().setLevel("INFO")
    t0 = time.monotonic()

    loaded = load_model()
    print(f"[load] model version={loaded.version}", flush=True)

    splits = time_based_split()
    val, test = splits.val, splits.test
    print(f"[data] val={len(val.X):,} test={len(test.X):,}", flush=True)

    dmat_val = xgboost.DMatrix(val.X.values, feature_names=loaded.feature_schema)
    dmat_test = xgboost.DMatrix(test.X.values, feature_names=loaded.feature_schema)
    raw_val = loaded.model.predict(dmat_val)
    raw_test = loaded.model.predict(dmat_test)

    cal = fit_calibrator(raw_val, val.y.values)
    path = save_calibrator(cal, loaded.version)
    print(f"[calibrator] saved to {path}", flush=True)

    cal_test = apply_calibrator(cal, raw_test)

    pre_ll = log_loss(test.y.values, raw_test)
    post_ll = log_loss(test.y.values, cal_test)
    pre_br = brier_score(test.y.values, raw_test)
    post_br = brier_score(test.y.values, cal_test)
    pre_ece = expected_calibration_error(test.y.values, raw_test)
    post_ece = expected_calibration_error(test.y.values, cal_test)
    print(
        f"[metrics] pre  ll={pre_ll:.5f} brier={pre_br:.5f} ece={pre_ece:.5f}",
        flush=True,
    )
    print(
        f"[metrics] post ll={post_ll:.5f} brier={post_br:.5f} ece={post_ece:.5f}",
        flush=True,
    )

    plot_path = Path("reports/phase5_reliability_pre_post.png")
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    plot_reliability(
        {
            "pre": reliability_curve(test.y.values, raw_test),
            "post": reliability_curve(test.y.values, cal_test),
        },
        plot_path,
        title="Pre- vs Post-calibration reliability (test)",
    )
    print(f"[plot] wrote {plot_path}", flush=True)

    elapsed = time.monotonic() - t0
    print(f"[DONE] wall_s={elapsed:.1f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

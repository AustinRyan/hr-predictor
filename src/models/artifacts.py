"""src/models/artifacts.py — versioned model artifact registry.

Registry layout:
    src/models/registry/
        v20260423_143022/
            model.xgb
            feature_schema.json
            training_metadata.json
            metrics.json
            reliability.png
            feature_importance.png
            shap_summary.png
            eval_report.md
        v20260423_151805/
            ...
        PRODUCTION   (optional; plain text containing one version string)
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import xgboost

_DEFAULT_REGISTRY = Path(__file__).parent / "registry"


@dataclass(slots=True)
class ModelVersion:
    version: str
    path: Path
    created_at: datetime
    metrics: dict[str, Any]


@dataclass(slots=True)
class LoadedModel:
    model: xgboost.Booster
    feature_schema: list[str]
    training_metadata: dict[str, Any]
    metrics: dict[str, Any]
    version: str
    path: Path


def save_model(
    model: xgboost.Booster | xgboost.XGBModel,
    config: dict[str, Any] | Any,
    metrics: dict[str, Any],
    feature_columns: list[str],
    training_range: tuple[str, str],  # ("2021-04-01", "2023-10-31") etc., iso strings
    data_hash: str,
    *,
    plot_paths: dict[str, Path] | None = None,  # name → source PNG path
    eval_report: str = "",
    registry_root: Path | None = None,
    timestamp: datetime | None = None,  # injectable for tests
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    """Create src/models/registry/v{ts}/ with all artifacts. Returns version dir."""
    root = registry_root or _DEFAULT_REGISTRY
    ts = timestamp or datetime.now(UTC)
    version = f"v{ts.strftime('%Y%m%d_%H%M%S')}"
    version_dir = root / version
    version_dir.mkdir(parents=True, exist_ok=False)

    # 1. Model binary
    # For native Booster: model.save_model(path)
    # For sklearn wrapper: model.save_model(path) also works in xgboost 2.x
    model.save_model(str(version_dir / "model.xgb"))

    # 2. Feature schema
    (version_dir / "feature_schema.json").write_text(
        json.dumps({"features": feature_columns}, indent=2)
    )

    # 3. Training metadata
    git_sha = _current_git_sha()
    if hasattr(config, "model_dump"):
        config_dict = config.model_dump()
    else:
        config_dict = dict(config)
    meta = {
        "version": version,
        "git_sha": git_sha,
        "data_hash": data_hash,
        "config": config_dict,
        "training_range": list(training_range),
        "num_features": len(feature_columns),
        "created_at_utc": ts.isoformat(),
    }
    if extra_metadata:
        meta.update(extra_metadata)
    (version_dir / "training_metadata.json").write_text(json.dumps(meta, indent=2))

    # 4. Metrics
    (version_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))

    # 5. Copy plots
    if plot_paths:
        for name, src in plot_paths.items():
            if src and Path(src).exists():
                shutil.copy2(src, version_dir / f"{name}.png")

    # 6. Eval report
    if eval_report:
        (version_dir / "eval_report.md").write_text(eval_report)

    return version_dir


def load_model(
    version: str | None = None,
    *,
    registry_root: Path | None = None,
) -> LoadedModel:
    """Load a specific version, or the production pointer when unset.

    If ``PRODUCTION`` is absent, falls back to newest-by-version directory so
    freshly-created local registries in tests and notebooks still work.
    """
    root = registry_root or _DEFAULT_REGISTRY
    if version is None:
        version = current_production(registry_root=root)
        if version is None:
            versions = list_versions(registry_root=root)
            if not versions:
                raise FileNotFoundError(f"No versions found in {root}")
            version = versions[0].version  # newest-first ordering fallback

    version_dir = root / version
    if not version_dir.exists():
        raise FileNotFoundError(f"Version {version} not found at {version_dir}")

    booster = xgboost.Booster()
    booster.load_model(str(version_dir / "model.xgb"))

    feature_schema = json.loads((version_dir / "feature_schema.json").read_text())["features"]
    training_metadata = json.loads((version_dir / "training_metadata.json").read_text())
    metrics = json.loads((version_dir / "metrics.json").read_text())

    return LoadedModel(
        model=booster,
        feature_schema=feature_schema,
        training_metadata=training_metadata,
        metrics=metrics,
        version=version,
        path=version_dir,
    )


def list_versions(registry_root: Path | None = None) -> list[ModelVersion]:
    """All versions sorted newest-first by directory name (lexicographic = chronological for v{YYYYMMDD_HHMMSS})."""
    root = registry_root or _DEFAULT_REGISTRY
    if not root.exists():
        return []
    out: list[ModelVersion] = []
    for d in sorted(root.iterdir(), reverse=True):
        if not d.is_dir() or not d.name.startswith("v"):
            continue
        meta_path = d / "training_metadata.json"
        metrics_path = d / "metrics.json"
        if not (meta_path.exists() and metrics_path.exists()):
            continue
        meta = json.loads(meta_path.read_text())
        out.append(
            ModelVersion(
                version=d.name,
                path=d,
                created_at=datetime.fromisoformat(meta["created_at_utc"]),
                metrics=json.loads(metrics_path.read_text()),
            )
        )
    return out


def promote_to_production(version: str, *, registry_root: Path | None = None) -> None:
    """Write PRODUCTION file pointing at `version`. Raises if version missing."""
    root = registry_root or _DEFAULT_REGISTRY
    version_dir = root / version
    if not version_dir.exists():
        raise FileNotFoundError(f"{version} not found")
    (root / "PRODUCTION").write_text(version)


def current_production(registry_root: Path | None = None) -> str | None:
    """Read PRODUCTION pointer. Returns None if unset or file missing."""
    root = registry_root or _DEFAULT_REGISTRY
    prod = root / "PRODUCTION"
    if not prod.exists():
        return None
    return prod.read_text().strip() or None


def compute_data_hash(X: pd.DataFrame, y: pd.Series) -> str:  # noqa: N803
    """SHA256 of first + middle + last rows concat. Fast, identity-sensitive.

    Uses row at index 0, n//2, and n-1. Shape is appended so different row
    counts of same edges still hash differently.
    """
    n = len(X)
    if n == 0:
        return hashlib.sha256(b"empty").hexdigest()
    idxs = [0, n // 2, n - 1]
    parts: list[bytes] = [f"shape={X.shape},y_len={len(y)}".encode()]
    for i in idxs:
        row_bytes = (
            pd.concat([X.iloc[[i]], y.iloc[[i]].rename("__label__").to_frame()], axis=1)
            .to_csv(index=False)
            .encode()
        )
        parts.append(row_bytes)
    return hashlib.sha256(b"\n".join(parts)).hexdigest()


def _current_git_sha() -> str:
    """Best-effort git SHA; returns 'unknown' if not a git repo or git unavailable."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).parent,
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"

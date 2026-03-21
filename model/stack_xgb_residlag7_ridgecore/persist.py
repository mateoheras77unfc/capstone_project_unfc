"""
Persist 98g ridge-core stack: joblib (sklearn / LightGBM / XGB meta) + Keras TCN file + hyperparam copies.

Training and serving should use compatible xgboost, lightgbm, tensorflow, and scikit-learn versions.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

BUNDLE_VERSION = 1

# Allowlist only; never copy best_xgb_meta_residlag7_ridgecore.json.
HYPERPARAM_FILENAMES = (
    "best_lgb_params.json",
    "best_ridge_core_params.json",
    "best_tcn_params.parquet",
    "best_xgb_meta_residlag7.json",
)

TCN_FILENAME = "tcn_model.keras"
JOBLIB_FILENAME = "stack_bundle.joblib"


class XGBBoosterWrapper:
    """Wrap xgboost.Booster like the notebook _XGBBoosterWrapper (module-level for pickle)."""

    def __init__(self, booster: Any, n_features: int):
        self.booster = booster
        self.n_features = int(n_features)

    def predict(self, X: np.ndarray) -> np.ndarray:
        import xgboost as xgb

        d = xgb.DMatrix(X)
        return self.booster.predict(d)

    @property
    def feature_importances_(self) -> np.ndarray:
        try:
            scores = self.booster.get_score(importance_type="gain")
        except Exception:
            scores = {}
        importances = np.zeros(self.n_features, dtype=np.float32)
        for k, v in scores.items():
            if not k.startswith("f"):
                continue
            try:
                idx = int(k[1:])
            except Exception:
                continue
            if 0 <= idx < self.n_features:
                importances[idx] = float(v)
        return importances


def _rebind_linear_models(linear_models: Optional[List[Any]]) -> Optional[List[Any]]:
    if not linear_models:
        return linear_models
    out: List[Any] = []
    for m in linear_models:
        if hasattr(m, "booster") and hasattr(m, "n_features"):
            out.append(XGBBoosterWrapper(m.booster, m.n_features))
        else:
            out.append(m)
    return out


def save_stack_bundle(
    global_stack: Optional[Dict[str, Any]],
    experiments_artifacts_dir: Path,
    bundle_root: Path,
    *,
    include_meta_debug: bool = True,
    forecast_horizon: Optional[int] = None,
) -> None:
    if global_stack is None:
        print("save_stack_bundle: global_stack is None, skip.")
        return

    artifacts_dir = bundle_root / "artifacts"
    hyperparams_dir = bundle_root / "hyperparams"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    hyperparams_dir.mkdir(parents=True, exist_ok=True)

    tcn = global_stack.get("tcn_model")
    tcn_path = artifacts_dir / TCN_FILENAME
    if tcn is not None:
        tcn.save(str(tcn_path))
        tcn_rel = TCN_FILENAME
    else:
        if tcn_path.exists():
            tcn_path.unlink(missing_ok=True)
        tcn_rel = None

    payload = dict(global_stack)
    payload["tcn_model"] = None
    payload["linear_models"] = _rebind_linear_models(payload.get("linear_models"))
    payload["bundle_version"] = BUNDLE_VERSION
    payload["tcn_relative_path"] = tcn_rel

    if forecast_horizon is not None:
        payload["FORECAST_HORIZON"] = forecast_horizon
    elif payload.get("FORECAST_HORIZON") is None:
        tc = payload.get("target_cols")
        if tc:
            payload["FORECAST_HORIZON"] = len(tc)

    if not include_meta_debug:
        payload.pop("meta_X_h1", None)

    joblib.dump(payload, artifacts_dir / JOBLIB_FILENAME)

    experiments_artifacts_dir = Path(experiments_artifacts_dir)
    for name in HYPERPARAM_FILENAMES:
        src = experiments_artifacts_dir / name
        if src.exists():
            shutil.copy2(src, hyperparams_dir / name)
            print("Copied hyperparam:", name)
        else:
            print("Hyperparam missing (skip):", name)

    print("Saved stack bundle:", artifacts_dir / JOBLIB_FILENAME)
    if tcn_rel:
        print("Saved TCN:", tcn_path)


def load_stack_bundle(bundle_root: Path) -> Dict[str, Any]:
    bundle_root = Path(bundle_root)
    artifacts_dir = bundle_root / "artifacts"
    data = joblib.load(artifacts_dir / JOBLIB_FILENAME)
    data = dict(data)
    tcn_path = artifacts_dir / TCN_FILENAME
    if tcn_path.exists():
        try:
            from tensorflow.keras.models import load_model
        except ImportError:
            from keras.models import load_model

        data["tcn_model"] = load_model(str(tcn_path))
    return data

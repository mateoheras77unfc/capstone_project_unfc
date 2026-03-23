"""
XGB meta + TCN + LightGBM + Ridge-core stack (98g notebook parity) — bundle I/O, features, predict, forecaster.

Default bundle: ``<repo>/stock-model/stack_xgb_residlag7_ridgecore`` or ``<repo>/model/...`` if present.
Training-time pickles may reference ``stack_xgb_residlag7_ridgecore.persist.XGBBoosterWrapper``; see
``_install_legacy_persist_module``.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BUNDLE_VERSION = 1
HYPERPARAM_FILENAMES = (
    "best_lgb_params.json",
    "best_ridge_core_params.json",
    "best_tcn_params.parquet",
    "best_xgb_meta_residlag7.json",
)
TCN_FILENAME = "tcn_model.keras"
JOBLIB_FILENAME = "stack_bundle.joblib"

# 98g ridge-core stack
LAG_RETURNS = 5
RSI_PERIOD = 7
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
ROLL_VOL_WINDOW = 7
FORECAST_HORIZON = 7
RESID_LAG = 7
MIN_CONTEXT_ROWS = 100


class XGBBoosterWrapper:
    """Wrap xgboost.Booster for sklearn-like predict (pickle-stable when saved from this module)."""

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


def _install_legacy_persist_module() -> None:
    """Old joblibs reference stack_xgb_residlag7_ridgecore.persist.XGBBoosterWrapper."""
    pkg_name = "stack_xgb_residlag7_ridgecore"
    mod_name = "stack_xgb_residlag7_ridgecore.persist"
    if mod_name in sys.modules:
        return
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = []
    sys.modules[pkg_name] = pkg
    sub = types.ModuleType(mod_name)
    sub.XGBBoosterWrapper = XGBBoosterWrapper
    sys.modules[mod_name] = sub


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


def default_bundle_root() -> Path:
    env = os.environ.get("STACK_XGB_RIDGECORE_BUNDLE_ROOT")
    if env:
        return Path(env)
    root = Path(__file__).resolve().parents[4]
    for sub in ("stock-model", "model"):
        p = root / sub / "stack_xgb_residlag7_ridgecore"
        joblib_p = p / "artifacts" / JOBLIB_FILENAME
        if joblib_p.exists():
            return p
    return root / "stock-model" / "stack_xgb_residlag7_ridgecore"


def save_stack_bundle(
    global_stack: Optional[Dict[str, Any]],
    experiments_artifacts_dir: Path,
    bundle_root: Path,
    *,
    include_meta_debug: bool = True,
    forecast_horizon: Optional[int] = None,
) -> None:
    if global_stack is None:
        logger.info("save_stack_bundle: global_stack is None, skip.")
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
            logger.info("Copied hyperparam: %s", name)
        else:
            logger.info("Hyperparam missing (skip): %s", name)

    logger.info("Saved stack bundle: %s", artifacts_dir / JOBLIB_FILENAME)


def load_stack_bundle(bundle_root: Path) -> Dict[str, Any]:
    _install_legacy_persist_module()
    bundle_root = Path(bundle_root)
    artifacts_dir = bundle_root / "artifacts"
    path = artifacts_dir / JOBLIB_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"Stack bundle not found: {path}")
    data = joblib.load(path)
    data = dict(data)
    tcn_path = artifacts_dir / TCN_FILENAME
    if tcn_path.exists():
        # TCN uses a Lambda layer (notebook); Keras 3 refuses lambda deserialization unless safe_mode=False.
        # Only load bundles you trust (same as training pipeline).
        try:
            from tensorflow.keras.models import load_model as _keras_load_model
        except ImportError:
            from keras.models import load_model as _keras_load_model

        p = str(tcn_path)
        try:
            data["tcn_model"] = _keras_load_model(p, safe_mode=False)
        except TypeError:
            data["tcn_model"] = _keras_load_model(p)
    return data


def _lgb_X_frame(X: np.ndarray, feature_cols_lgb: List[str]) -> pd.DataFrame:
    """LightGBM in MultiOutputRegressor may be fitted with named features; avoid sklearn warnings."""
    return pd.DataFrame(X, columns=feature_cols_lgb)


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / np.where(avg_loss != 0, avg_loss, 1e-10)
    return 100 - (100 / (1 + rs))


def build_feature_df(
    grp: pd.DataFrame,
) -> tuple[pd.DataFrame, List[str], List[str], List[str]]:
    """
    98g feature table. When ``vix`` is missing, use finite placeholders so ``dropna()`` keeps rows (backend).
    """
    df = grp.sort_values("timestamp").copy()
    df["close"] = df["close"].astype(float)
    df["return"] = df["close"].pct_change()
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    for i in range(1, LAG_RETURNS + 1):
        df[f"ret_lag_{i}"] = df["log_return"].shift(i)
    if "volume" in df.columns:
        df["volume_lag_1"] = df["volume"].astype(float).shift(1)
    else:
        df["volume_lag_1"] = np.nan
    df["rsi"] = _rsi(df["close"], RSI_PERIOD)
    ema_fast = df["close"].ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = df["close"].ewm(span=MACD_SLOW, adjust=False).mean()
    df["macd_line"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd_line"].ewm(span=MACD_SIGNAL, adjust=False).mean()
    if "vix" in df.columns:
        vix = df["vix"].astype(np.float64)
        df["vix_sma_5"] = vix.shift(1).rolling(5).mean()
        df["vix_velocity"] = vix.diff(1)
        df["vix_momentum"] = vix - df["vix_sma_5"]
    else:
        df["vix_sma_5"] = 0.0
        df["vix_velocity"] = 0.0
        df["vix_momentum"] = 0.0
    df["month"] = pd.to_datetime(df["timestamp"]).dt.month
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    if "fear_greed" not in df.columns:
        df["fear_greed"] = 50.0
    else:
        df["fear_greed"] = df["fear_greed"].fillna(50.0)
    df["fear_greed_lag_1"] = df["fear_greed"].shift(1)
    df["fear_greed_lag_5"] = df["fear_greed"].shift(5)
    df["fear_greed_change"] = df["fear_greed_lag_1"] - df["fear_greed_lag_5"]
    df["rolling_vol"] = (
        df["log_return"].rolling(ROLL_VOL_WINDOW, min_periods=1).std().fillna(0).astype(np.float32)
    )
    for h in range(1, FORECAST_HORIZON + 1):
        df[f"target_{h}"] = df["log_return"].shift(-h)
    feature_cols_tcn = [f"ret_lag_{i}" for i in range(1, LAG_RETURNS + 1)] + [
        "volume_lag_1",
        "rsi",
        "macd_line",
        "macd_signal",
    ]
    feature_cols_lgb = [
        "vix_sma_5",
        "vix_velocity",
        "vix_momentum",
        "month_sin",
        "month_cos",
        "fear_greed_change",
    ]
    target_cols = [f"target_{h}" for h in range(1, FORECAST_HORIZON + 1)]
    base_cols = (
        ["timestamp", "close", "return", "log_return", "rolling_vol"]
        + feature_cols_tcn
        + feature_cols_lgb
        + target_cols
    )
    out = df[[c for c in base_cols if c in df.columns]].copy()
    return out.dropna(), feature_cols_tcn, feature_cols_lgb, target_cols


def predict_stack_global(
    context_df: pd.DataFrame, horizon: int, global_stack: Dict[str, Any]
) -> List[float]:
    """Bases + XGB meta on log returns; prices via ``p0 * exp(cumsum(pred_log_returns))``."""
    if global_stack is None or not global_stack.get("linear_models"):
        return []
    try:
        feat_df, feature_cols_tcn, feature_cols_lgb, _ = build_feature_df(context_df)
    except Exception:
        logger.exception("build_feature_df failed")
        return []

    seq_len = int(global_stack.get("seq_len", 30))
    if len(feat_df) < seq_len + 1:
        return []

    _ridge_def = [f"ret_lag_{i}" for i in range(1, LAG_RETURNS + 1)]
    feature_cols_ridge = global_stack.get("feature_cols_ridge", _ridge_def)
    scaler_lgb = global_stack.get("scaler_lgb")
    scaler_tcn = global_stack.get("scaler_tcn")
    scaler_ridge = global_stack.get("scaler_ridge")
    if scaler_lgb is None or scaler_tcn is None or scaler_ridge is None:
        return []

    lgb_multi = global_stack["lgb_multi"]
    tcn_model = global_stack.get("tcn_model")
    ridge_multi = global_stack["ridge_multi"]
    linear_models = global_stack["linear_models"]

    X_lgb = feat_df[feature_cols_lgb].values.astype(np.float32)
    X_tcn = feat_df[feature_cols_tcn].values.astype(np.float32)
    X_ridge = feat_df[feature_cols_ridge].values.astype(np.float64)
    X_lgb_s = scaler_lgb.transform(X_lgb)
    X_tcn_s = scaler_tcn.transform(X_tcn)
    X_ridge_s = scaler_ridge.transform(X_ridge)

    last_idx = len(feat_df) - 1
    j_lag = last_idx - RESID_LAG
    if j_lag < 0:
        return []

    last_row_lgb = X_lgb_s[last_idx : last_idx + 1]
    last_row_ridge = X_ridge_s[last_idx : last_idx + 1]
    lgb_h = lgb_multi.predict(_lgb_X_frame(last_row_lgb, feature_cols_lgb)).ravel()
    ridge_h = ridge_multi.predict(last_row_ridge).ravel()
    if tcn_model is not None and last_idx >= seq_len:
        tcn_h = tcn_model.predict(
            X_tcn_s[last_idx - seq_len : last_idx].reshape(1, seq_len, -1), verbose=0
        ).ravel()
    else:
        tcn_h = lgb_h

    target_cols_pred = global_stack.get(
        "target_cols", [f"target_{k}" for k in range(1, horizon + 1)]
    )
    row_last = feat_df.iloc[last_idx]
    vix_vel = np.nan_to_num(float(row_last["vix_velocity"]), nan=0.0)
    roll_vol = float(row_last["rolling_vol"]) if "rolling_vol" in feat_df.columns else 0.0
    ctx_meta = np.array(
        [
            float(row_last["month_sin"]),
            float(row_last["month_cos"]),
            float(vix_vel),
            float(roll_vol),
        ],
        dtype=np.float32,
    )

    meta_rows: List[np.ndarray] = []
    for h in range(horizon):
        if h >= len(target_cols_pred):
            break
        th = target_cols_pred[h]
        av = feat_df[th].iloc[j_lag]
        if np.isnan(av):
            av = 0.0
        actual_h = float(av)
        pl = float(
            lgb_multi.predict(_lgb_X_frame(X_lgb_s[j_lag : j_lag + 1], feature_cols_lgb))[0, h]
        )
        pr = float(ridge_multi.predict(X_ridge_s[j_lag : j_lag + 1])[0, h])
        if tcn_model is not None and j_lag >= seq_len:
            pt = float(
                tcn_model.predict(
                    X_tcn_s[j_lag - seq_len : j_lag].reshape(1, seq_len, -1), verbose=0
                ).ravel()[h]
            )
        else:
            pt = pl
        rl7 = np.array([actual_h - pl, actual_h - pt, actual_h - pr], dtype=np.float64)
        rk = pd.Series(np.abs(rl7)).rank(method="min").values.astype(np.float32)
        base_last = np.array([lgb_h[h], tcn_h[h], ridge_h[h]], dtype=np.float32)
        row = np.concatenate([base_last, rl7.astype(np.float32), rk, ctx_meta]).reshape(1, -1)
        meta_rows.append(row)

    if len(meta_rows) < horizon:
        return []

    try:
        final_log_returns = np.array(
            [float(linear_models[h].predict(meta_rows[h])[0]) for h in range(horizon)],
            dtype=np.float64,
        )
    except Exception:
        logger.exception("meta XGB predict failed")
        return []

    p0 = float(context_df["close"].iloc[-1])
    prices = p0 * np.exp(np.cumsum(final_log_returns))
    return [float(p) for p in prices[:horizon]]


class XGBStackForecaster:
    """Load 98g stack bundle; ``fit(context_df)`` then ``forecast(periods)`` (clamped to 7)."""

    _cached_root: Optional[Path] = None
    _cached_stack: Optional[Dict[str, Any]] = None

    def __init__(self, bundle_root: Optional[Path] = None) -> None:
        self._bundle_root = Path(bundle_root) if bundle_root else default_bundle_root()
        self._context_df: Optional[pd.DataFrame] = None

    def _load_stack(self) -> Dict[str, Any]:
        if (
            XGBStackForecaster._cached_root != self._bundle_root
            or XGBStackForecaster._cached_stack is None
        ):
            XGBStackForecaster._cached_stack = load_stack_bundle(self._bundle_root)
            XGBStackForecaster._cached_root = self._bundle_root
        return XGBStackForecaster._cached_stack

    def fit(self, context_df: pd.DataFrame) -> None:
        if context_df is None or len(context_df) < 2:
            raise ValueError("context_df must have at least 2 rows.")
        df = context_df.copy()
        if "close" not in df.columns and "close_price" in df.columns:
            df = df.rename(columns={"close_price": "close"})
        if "timestamp" not in df.columns:
            raise ValueError("context_df must include 'timestamp' and 'close'.")

        stack = self._load_stack()
        seq_len = int(stack.get("seq_len", 30))
        feat_df, _, _, _ = build_feature_df(df)
        need = max(MIN_CONTEXT_ROWS, seq_len + 1, RESID_LAG + 1)
        if len(feat_df) < need:
            raise ValueError(
                f"context_df must yield at least {need} feature rows after dropna; got {len(feat_df)}."
            )
        self._context_df = df

    def forecast(self, periods: int = 7) -> Dict[str, Any]:
        if self._context_df is None:
            raise ValueError("Call fit(context_df) before forecast().")
        stack = self._load_stack()
        horizon = min(int(periods), FORECAST_HORIZON)
        prices = predict_stack_global(self._context_df, horizon, stack)
        if not prices:
            raise ValueError("Stack prediction returned no values.")
        while len(prices) < periods:
            prices.append(prices[-1])
        prices = prices[:periods]
        last_ts = pd.to_datetime(self._context_df["timestamp"].iloc[-1])
        dates = [
            (last_ts + pd.Timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(1, periods + 1)
        ]
        return {
            "dates": dates,
            "point_forecast": prices,
            "lower_bound": prices,
            "upper_bound": prices,
            "confidence_level": 0.95,
        }

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "model_name": "XGBStackForecaster",
            "version": "1.0",
            "bundle_root": str(self._bundle_root),
            "forecast_horizon": FORECAST_HORIZON,
        }

"""
Stack (LGB + LSTM + Ridge + EWM bases, Ridge meta) — inference only.

Loads artifacts from this package directory (joblib + optional LSTM Keras save).
Feature building matches model/experiments-pool/98c-stack-ridge-meta-logreturn-pool.ipynb.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_STOCK_DIR = Path(__file__).resolve().parent
ARTIFACT_PATH = _STOCK_DIR / "stack_ridge_meta_logreturn_artifact.joblib"

# Match 98c notebook
LAG_RETURNS = 5
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
SEQ_LEN = 30
ROLL_VOL_WINDOW = 21
EWM_SPAN = 20
FORECAST_HORIZON = 21


def _rsi(series: pd.Series, period: int) -> pd.Series:
    """RSI = 100 - 100/(1 + RS), RS = avg gain / avg loss (Wilder)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / np.where(avg_loss != 0, avg_loss, 1e-10)
    return 100 - (100 / (1 + rs))


def build_feature_df(grp: pd.DataFrame) -> tuple:
    """
    Build features for stack prediction. Expects columns: timestamp, close;
    optional: volume, vix, fear_greed. Returns (feat_df, feature_cols_lstm, feature_cols_lgb, target_cols).
    """
    df = grp.sort_values("timestamp").copy()
    df["close"] = df["close"].astype(float)
    df["return"] = df["close"].pct_change()
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    for i in range(1, LAG_RETURNS + 1):
        df[f"ret_lag_{i}"] = df["return"].shift(i)
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
        df["vix_sma_5"] = np.nan
        df["vix_velocity"] = np.nan
        df["vix_momentum"] = np.nan
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
    feature_cols_lstm = [f"ret_lag_{i}" for i in range(1, LAG_RETURNS + 1)] + [
        "volume_lag_1", "rsi", "macd_line", "macd_signal"
    ]
    feature_cols_lgb = [
        "vix_sma_5", "vix_velocity", "vix_momentum", "month_sin", "month_cos", "fear_greed_change"
    ]
    target_cols = [f"target_{h}" for h in range(1, FORECAST_HORIZON + 1)]
    base_cols = (
        ["timestamp", "close", "return", "log_return", "rolling_vol"]
        + feature_cols_lstm
        + feature_cols_lgb
        + target_cols
    )
    out = df[[c for c in base_cols if c in df.columns]].copy()
    return out.dropna(), feature_cols_lstm, feature_cols_lgb, target_cols


def predict_stack_ridge_global(
    context_df: pd.DataFrame, horizon: int, global_stack: Dict[str, Any]
) -> List[float]:
    """
    Run stack prediction: bases + Ridge meta output log returns; convert to price.
    global_stack must contain fitted models and scalers; lstm_model may be None.
    """
    if not global_stack.get("linear_models") or global_stack.get("meta_scaler") is None:
        return []
    try:
        feat_df, feature_cols_lstm, feature_cols_lgb, _ = build_feature_df(context_df)
    except Exception:
        return []
    if len(feat_df) < SEQ_LEN + 1:
        return []
    feature_cols_ridge = global_stack.get(
        "feature_cols_ridge", feature_cols_lstm + feature_cols_lgb
    )
    scaler_lgb = global_stack.get("scaler_lgb")
    scaler_lstm = global_stack.get("scaler_lstm")
    scaler_ridge = global_stack.get("scaler_ridge")
    if scaler_lgb is None or scaler_lstm is None or scaler_ridge is None:
        return []
    lgb_multi = global_stack["lgb_multi"]
    lstm_model = global_stack.get("lstm_model")
    ridge_multi = global_stack["ridge_multi"]
    linear_models = global_stack["linear_models"]
    ewm_span = global_stack.get("EWM_SPAN", EWM_SPAN)

    X_lgb_s = scaler_lgb.transform(feat_df[feature_cols_lgb].values.astype(np.float32))
    X_lstm_s = scaler_lstm.transform(feat_df[feature_cols_lstm].values.astype(np.float32))
    X_ridge_s = scaler_ridge.transform(feat_df[feature_cols_ridge].values.astype(np.float64))
    last_idx = len(feat_df) - 1
    last_row_lgb = X_lgb_s[last_idx : last_idx + 1]
    last_row_ridge = X_ridge_s[last_idx : last_idx + 1]
    lgb_21 = lgb_multi.predict(last_row_lgb).ravel()
    ridge_21 = ridge_multi.predict(last_row_ridge).ravel()
    log_ret_series = feat_df["log_return"].values.astype(np.float64)
    if len(log_ret_series) >= ewm_span:
        ewm_val = float(pd.Series(log_ret_series).ewm(span=ewm_span).mean().iloc[-1])
        ewm_21 = np.full(horizon, ewm_val, dtype=np.float32)
    else:
        ewm_21 = np.full(
            horizon,
            float(np.nanmean(log_ret_series)) if len(log_ret_series) else 0.0,
            dtype=np.float32,
        )
    if lstm_model is not None and last_idx >= SEQ_LEN:
        seq = X_lstm_s[last_idx - SEQ_LEN : last_idx]
        lstm_21 = lstm_model.predict(seq.reshape(1, SEQ_LEN, -1), verbose=0).ravel()
    else:
        lstm_21 = lgb_21
    vv = feat_df["vix_velocity"].iloc[-1]
    vix_vel = np.nan_to_num(float(vv), nan=0.0)
    roll_vol = float(feat_df["rolling_vol"].iloc[-1]) if "rolling_vol" in feat_df.columns else 0.0
    ctx_last = np.concatenate([
        feat_df[["month_sin", "month_cos"]].iloc[-1].values.astype(np.float32),
        [np.float32(vix_vel), np.float32(roll_vol)],
    ])
    meta_vec = np.array([
        np.concatenate([
            np.array([
                lgb_21[h], lstm_21[h], ridge_21[h], ewm_21[h],
                np.std([lgb_21[h], lstm_21[h], ridge_21[h], ewm_21[h]]),
            ], dtype=np.float32),
            ctx_last,
        ])
        for h in range(horizon)
    ])
    meta_vec_s = global_stack["meta_scaler"].transform(meta_vec)
    final_log_returns = np.array([
        linear_models[h].predict(meta_vec_s[h : h + 1])[0] for h in range(horizon)
    ])
    p0 = float(context_df["close"].iloc[-1])
    prices = p0 * np.exp(np.cumsum(final_log_returns))
    return [float(p) for p in prices[:horizon]]


class StackRidgeMetaForecaster:
    """
    Stack (Ridge meta) forecaster — inference only, loads pre-trained artifact.
    fit(context_df) stores context; forecast(periods) returns point_forecast and bounds.
    """

    _artifact: Optional[Dict[str, Any]] = None
    _artifact_path: Optional[Path] = None

    def __init__(self, artifact_path: Optional[Path] = None) -> None:
        self._path = Path(artifact_path) if artifact_path else ARTIFACT_PATH
        self._context_df: Optional[pd.DataFrame] = None

    def _load_artifact(self) -> Dict[str, Any]:
        if (
            StackRidgeMetaForecaster._artifact is None
            or StackRidgeMetaForecaster._artifact_path != self._path
        ):
            try:
                import joblib
            except ImportError as e:
                raise ImportError(
                    "joblib is required to load stack artifact. pip install joblib"
                ) from e
            if not self._path.exists():
                raise FileNotFoundError(
                    f"Stack artifact not found: {self._path}. "
                    "Run the export cell in model/experiments-pool/98c-stack-ridge-meta-logreturn-pool.ipynb."
                )
            art = joblib.load(self._path)
            lstm_path = art.get("lstm_path")
            if lstm_path:
                lstm_file = self._path.parent / lstm_path
                if lstm_file.exists():
                    try:
                        from tensorflow.keras.models import load_model
                        art["lstm_model"] = load_model(lstm_file)
                    except Exception as e:
                        logger.warning("Could not load LSTM from %s: %s", lstm_file, e)
                        art["lstm_model"] = None
                else:
                    art["lstm_model"] = None
            else:
                art["lstm_model"] = None
            StackRidgeMetaForecaster._artifact = art
            StackRidgeMetaForecaster._artifact_path = self._path
        return StackRidgeMetaForecaster._artifact

    def fit(self, context_df: pd.DataFrame) -> None:
        """Set context for prediction. Requires timestamp, close; optional volume, vix, fear_greed."""
        if context_df is None or len(context_df) < SEQ_LEN + 1:
            raise ValueError(
                f"context_df must have at least {SEQ_LEN + 1} rows (after feature dropna)."
            )
        if "close" not in context_df.columns and "close_price" in context_df.columns:
            context_df = context_df.rename(columns={"close_price": "close"})
        if "timestamp" not in context_df.columns:
            raise ValueError("context_df must have 'timestamp' and 'close' (or 'close_price').")
        self._context_df = context_df.copy()

    def forecast(self, periods: int = 21) -> Dict[str, Any]:
        """Run stack prediction; return dict with dates, point_forecast, lower_bound, upper_bound."""
        if self._context_df is None:
            raise ValueError("Call fit(context_df) before forecast().")
        art = self._load_artifact()
        horizon = min(periods, FORECAST_HORIZON)
        prices = predict_stack_ridge_global(self._context_df, horizon, art)
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
            "model_name": "StackRidgeMetaForecaster",
            "version": "1.0",
            "artifact_path": str(self._path),
            "forecast_horizon": FORECAST_HORIZON,
        }

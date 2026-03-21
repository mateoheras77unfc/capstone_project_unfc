"""
analytics/forecasting/crypto/tft_forecaster.py
───────────────────────────────────────────────
Temporal Fusion Transformer (TFT) forecaster for cryptocurrency prices.

Uses the Nixtla neuralforecast implementation of TFT — serializable with
joblib, unlike pytorch_forecasting which generates dynamic classes at
runtime that cannot be pickled.

Architecture
------------
- Historical exogenous features: RSI-14, MACD, BB%, ATR-14, vol_ratio,
  log returns, realised volatility — known for past, not future.
- Future exogenous features: day_of_week, day_of_month, month — calendar
  features known in advance for the forecast horizon.
- Loss: MQLoss (multi-quantile) — native calibrated confidence intervals
  without Monte Carlo sampling.

References
----------
- Lim et al. (2021). "Temporal Fusion Transformers for Interpretable
  Multi-horizon Time Series Forecasting." International Journal of
  Forecasting, 37(4), 1748-1764.
- Köse (2025). Journal of Forecasting, Wiley. (TFT ranked best overall
  for BTC across ML+DL benchmarks.)
- PMC / ScienceDirect (2024). ADE-TFT outperformed LSTM on MAPE, MSE,
  RMSE for Bitcoin.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from analytics.forecasting.base import BaseForecastor

logger = logging.getLogger(__name__)

# ── Optional imports ──────────────────────────────────────────────────────────
try:
    from neuralforecast import NeuralForecast
    from neuralforecast.models import TFT
    from neuralforecast.losses.pytorch import MQLoss
    _TFT_AVAILABLE = True
except ImportError:
    _TFT_AVAILABLE = False


# ── Feature engineering ───────────────────────────────────────────────────────

_HIST_EXOG = [
    "returns", "rsi_14", "macd", "macd_signal",
    "bb_pct", "atr_14", "vol_ratio", "realised_vol_7",
]
_FUTR_EXOG = ["day_of_week", "day_of_month", "month"]


def _build_features(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """
    Build neuralforecast-compatible DataFrame with exogenous features.

    Returns DataFrame with columns:
        unique_id, ds, y  — required by NeuralForecast
        + hist_exog cols  — technical indicators (past only)
        + futr_exog cols  — calendar features (past + future)
    """
    df = ohlcv.copy().sort_index()
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    vol   = df["Volume"]

    out = pd.DataFrame(index=df.index)

    # Target
    out["y"] = close

    # Log returns
    log_ret = np.log(close / close.shift(1))
    out["returns"] = log_ret

    # RSI-14
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    out["rsi_14"] = 100 - (100 / (1 + gain / (loss + 1e-8)))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    out["macd"]        = macd
    out["macd_signal"] = macd.ewm(span=9, adjust=False).mean()

    # Bollinger Bands %B
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    out["bb_pct"] = (close - (sma20 - 2 * std20)) / (4 * std20 + 1e-8)

    # ATR-14
    tr = pd.concat(
        [(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    out["atr_14"]        = tr.rolling(14).mean() / (close + 1e-8)
    out["vol_ratio"]     = vol / (vol.rolling(20).mean() + 1e-8)
    out["realised_vol_7"] = log_ret.rolling(7).std()

    # Calendar (future-known)
    out["day_of_week"]  = df.index.dayofweek.astype(float)
    out["day_of_month"] = df.index.day.astype(float)
    out["month"]        = df.index.month.astype(float)

    out = out.dropna()

    # neuralforecast required columns
    out.insert(0, "unique_id", "crypto")
    out.insert(1, "ds", out.index)
    out = out.reset_index(drop=True)

    return out


def _build_future_exog(last_date: pd.Timestamp, periods: int, freq_days: int) -> pd.DataFrame:
    """Build future calendar features for the forecast horizon."""
    step  = timedelta(days=freq_days)
    dates = [last_date + step * i for i in range(1, periods + 1)]
    return pd.DataFrame({
        "unique_id":    "crypto",
        "ds":           dates,
        "day_of_week":  [float(d.weekday()) for d in dates],
        "day_of_month": [float(d.day)       for d in dates],
        "month":        [float(d.month)     for d in dates],
    })


# ── Main forecaster ───────────────────────────────────────────────────────────

class TFTForecaster(BaseForecastor):
    """
    Temporal Fusion Transformer forecaster using Nixtla neuralforecast.

    Serializable with joblib — safe to use inside CryptoAssemblyForecaster.

    Args:
        max_horizon:      Forecast horizon trained (periods must be ≤ this).
        input_size:       Encoder context window in days.
        hidden_size:      TFT hidden layer size.
        n_head:           Multi-head attention heads.
        dropout:          Dropout probability.
        max_steps:        Training gradient steps.
        batch_size:       Mini-batch size.
        confidence_level: CI probability mass (e.g. 0.95 → 95% CI).

    Example
    -------
    >>> forecaster = TFTForecaster(max_horizon=21, max_steps=200)
    >>> forecaster.fit(ohlcv_df)
    >>> result = forecaster.forecast(periods=7)
    """

    def __init__(
        self,
        max_horizon:      int   = 21,
        input_size:       int   = 60,
        hidden_size:      int   = 32,
        n_head:           int   = 4,
        dropout:          float = 0.1,
        max_steps:        int   = 200,
        batch_size:       int   = 32,
        confidence_level: float = 0.95,
        # kept for assembly.py compat (was max_prediction_length)
        max_prediction_length: Optional[int] = None,
    ) -> None:
        if not _TFT_AVAILABLE:
            raise ImportError(
                "neuralforecast is required for TFTForecaster.\n"
                "Install with: pip install neuralforecast"
            )
        if max_prediction_length is not None:
            max_horizon = max_prediction_length

        self.max_horizon      = max_horizon
        self.input_size       = input_size
        self.hidden_size      = hidden_size
        self.n_head           = n_head
        self.dropout          = dropout
        self.max_steps        = max_steps
        self.batch_size       = batch_size
        self.confidence_level = confidence_level

        self._nf:        Optional[NeuralForecast] = None
        self._last_date: Optional[pd.Timestamp]  = None
        self._freq_days: int   = 1
        self._is_fitted: bool  = False

    # ── fit ──────────────────────────────────────────────────────────────

    def fit(self, ohlcv: pd.DataFrame) -> None:
        """
        Train TFT on historical OHLCV data.

        Args:
            ohlcv: pd.DataFrame [Open, High, Low, Close, Volume] with
                   DatetimeIndex sorted oldest → newest. Min 120 rows.
        """
        self._validate_ohlcv(ohlcv)
        self._last_date = ohlcv.index[-1]
        self._freq_days = self._infer_freq_days(ohlcv.index)

        df = _build_features(ohlcv)

        alpha    = 1 - self.confidence_level
        lower_q  = round(alpha / 2, 3)
        upper_q  = round(1 - alpha / 2, 3)
        levels   = [int(self.confidence_level * 100)]   # e.g. [95]

        tft = TFT(
            h              = self.max_horizon,
            input_size     = self.input_size,
            hidden_size    = self.hidden_size,
            n_head         = self.n_head,
            dropout        = self.dropout,
            max_steps      = self.max_steps,
            batch_size     = self.batch_size,
            hist_exog_list = _HIST_EXOG,
            futr_exog_list = _FUTR_EXOG,
            loss           = MQLoss(level=levels),
            valid_loss     = MQLoss(level=levels),
            logger         = False,
        )

        self._nf = NeuralForecast(models=[tft], freq="D")
        self._nf.fit(df, val_size=0)

        self._is_fitted = True
        logger.info(
            "TFTForecaster (neuralforecast) fitted on %d samples", len(ohlcv)
        )

    # ── forecast ─────────────────────────────────────────────────────────

    def forecast(self, periods: int = 7) -> Dict[str, Any]:
        """
        Generate multi-horizon quantile forecasts.

        Args:
            periods: Steps ahead. Must be ≤ max_horizon.

        Returns:
            Standard dict: dates, point_forecast, lower_bound,
            upper_bound, confidence_level.
        """
        if not self._is_fitted or self._nf is None:
            raise ValueError("Call fit() before forecast()")
        if periods > self.max_horizon:
            raise ValueError(
                f"periods={periods} > max_horizon={self.max_horizon}. "
                f"Re-instantiate with max_horizon>={periods} and refit."
            )

        futr_df = _build_future_exog(self._last_date, self.max_horizon, self._freq_days)

        pred_df = self._nf.predict(futr_df=futr_df)
        pred_df = pred_df.reset_index(drop=True).head(self.max_horizon)

        # Column names: "TFT", "TFT-lo-{level}", "TFT-hi-{level}"
        level       = int(self.confidence_level * 100)
        col_pt      = "TFT"
        col_lo      = f"TFT-lo-{level}"
        col_hi      = f"TFT-hi-{level}"

        # Fallback if column names differ
        num_cols = [c for c in pred_df.columns if c not in ("unique_id", "ds")]
        if col_pt not in pred_df.columns and len(num_cols) >= 3:
            col_lo, col_pt, col_hi = sorted(num_cols)[:3]

        step = timedelta(days=self._freq_days)
        dates, pts, lbs, ubs = [], [], [], []

        for h in range(periods):
            date = self._last_date + step * (h + 1)
            pt   = float(pred_df[col_pt].iloc[h])
            lb   = float(pred_df[col_lo].iloc[h]) if col_lo in pred_df.columns else pt
            ub   = float(pred_df[col_hi].iloc[h]) if col_hi in pred_df.columns else pt
            lb   = min(lb, pt)
            ub   = max(ub, pt)
            dates.append(date.strftime("%Y-%m-%dT%H:%M:%S"))
            pts.append(round(pt, 4))
            lbs.append(round(lb, 4))
            ubs.append(round(ub, 4))

        return {
            "dates":            dates,
            "point_forecast":   pts,
            "lower_bound":      lbs,
            "upper_bound":      ubs,
            "confidence_level": self.confidence_level,
        }

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _validate_ohlcv(ohlcv: pd.DataFrame) -> None:
        required = {"Open", "High", "Low", "Close", "Volume"}
        if not isinstance(ohlcv, pd.DataFrame):
            raise TypeError("ohlcv must be a pd.DataFrame")
        if not isinstance(ohlcv.index, pd.DatetimeIndex):
            raise TypeError("ohlcv must have a DatetimeIndex")
        missing = required - set(ohlcv.columns)
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        if len(ohlcv) < 120:
            raise ValueError(
                "Need at least 120 rows for TFT (encoder + indicators + warmup)"
            )

    def get_model_info(self) -> Dict[str, Any]:
        info = super().get_model_info()
        info.update({
            "display_name":   "TFT (neuralforecast)",
            "max_horizon":    self.max_horizon,
            "input_size":     self.input_size,
            "hidden_size":    self.hidden_size,
            "n_head":         self.n_head,
            "max_steps":      self.max_steps,
            "confidence_level": self.confidence_level,
            "is_fitted":      self._is_fitted,
            "hist_exog":      _HIST_EXOG,
            "futr_exog":      _FUTR_EXOG,
        })
        return info

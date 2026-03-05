"""
analytics/forecasting/xgboost.py
────────────────────────────────
XGBoost forecaster using a local artifact copy (xgboost_pool.joblib).

Artifact is stored in this directory; originally from
model/experiments-pool/03b-xgboost-pool.ipynb. Features: vix_lag_1, month_sin,
month_cos, fear_greed. Backend has no VIX/fear_greed → use neutral defaults (50).
Direct multi-step: predict 21 returns, convert to prices, slice to requested periods.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from analytics.forecasting.base import BaseForecastor

logger = logging.getLogger(__name__)

_FORECASTING_DIR = Path(__file__).resolve().parent
_DEFAULT_ARTIFACT_PATH = _FORECASTING_DIR / "xgboost_pool.joblib"

# Artifact trains on 21-step horizon.
ARTIFACT_HORIZON = 21


class XGBoostForecaster(BaseForecastor):
    """
    XGBoost forecaster using xgboost_pool.joblib in the forecasting folder.

    Predicts returns via MultiOutputRegressor then converts to price levels.
    VIX and fear_greed are not available in backend → use 50.0 (neutral).
    """

    _artifact: Optional[Dict[str, Any]] = None
    _artifact_path: Optional[Path] = None

    def __init__(
        self,
        confidence_level: float = 0.95,
        artifact_path: Optional[Path] = None,
    ) -> None:
        self.confidence_level = confidence_level
        self._path = Path(artifact_path) if artifact_path else _DEFAULT_ARTIFACT_PATH
        self._prices: Optional[pd.Series] = None
        self._freq_days: int = 7
        self._is_fitted: bool = False

    def _load_artifact(self) -> Dict[str, Any]:
        if (
            XGBoostForecaster._artifact is None
            or XGBoostForecaster._artifact_path != self._path
        ):
            try:
                import joblib
            except ImportError as e:
                raise ImportError(
                    "joblib is required to load XGBoost artifact. pip install joblib"
                ) from e
            if not self._path.exists():
                raise FileNotFoundError(
                    f"XGBoost artifact not found: {self._path}. "
                    "Copy xgboost_pool.joblib from model/experiments-pool/artifacts/ into this folder."
                )
            XGBoostForecaster._artifact = joblib.load(self._path)
            XGBoostForecaster._artifact_path = self._path
        return XGBoostForecaster._artifact

    def fit(self, prices: pd.Series) -> None:
        """Store price history; no training (model is pre-trained)."""
        self._validate_prices(prices, min_samples=100)  # MIN_TRAIN_STACK + horizon
        self._prices = prices.sort_index().copy()
        self._freq_days = self._infer_freq_days(self._prices.index)
        self._is_fitted = True
        logger.info("XGBoostForecaster context set with %d samples", len(self._prices))

    def forecast(self, periods: int = 4) -> Dict[str, Any]:
        """
        Build last-row features (vix_lag_1, month_sin, month_cos, fear_greed),
        predict returns, convert to price levels. CI from heuristic spread.
        """
        if not self._is_fitted or self._prices is None:
            raise ValueError("Call fit() before forecast()")

        art = self._load_artifact()
        model = art["model"]
        scaler = art["scaler"]
        feature_cols = art["feature_cols_xgb"]
        horizon = int(art.get("FORECAST_HORIZON", ARTIFACT_HORIZON))

        # Build minimal context: timestamp, close. No VIX/fear_greed in backend.
        ts = self._prices.index
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        context_df = pd.DataFrame({
            "timestamp": pd.to_datetime(ts),
            "close": self._prices.values.astype(np.float64),
        })
        context_df["vix_lag_1"] = 50.0
        context_df["month"] = context_df["timestamp"].dt.month
        context_df["month_sin"] = np.sin(2 * np.pi * context_df["month"] / 12)
        context_df["month_cos"] = np.cos(2 * np.pi * context_df["month"] / 12)
        context_df["fear_greed"] = 50.0

        X_last = context_df[feature_cols].iloc[-1:].values.astype(np.float32)
        X_scaled = scaler.transform(X_last)
        pred_returns = model.predict(X_scaled).ravel()
        pred_returns = np.asarray(pred_returns[:horizon])

        p0 = float(self._prices.iloc[-1])
        prices_out = p0 * np.cumprod(np.concatenate([[1.0], 1.0 + pred_returns]))[1:]
        point_forecast = [round(float(p), 4) for p in prices_out[:periods]]

        # Pad if periods > horizon
        while len(point_forecast) < periods:
            point_forecast.append(point_forecast[-1] if point_forecast else p0)

        # Heuristic CI: symmetric band scaling with step
        z = 1.96  # ~95%
        spread = 0.02 * np.sqrt(np.arange(1, len(point_forecast) + 1))
        lower_bound = [round(point_forecast[i] * (1 - z * spread[i]), 4) for i in range(periods)]
        upper_bound = [round(point_forecast[i] * (1 + z * spread[i]), 4) for i in range(periods)]

        last_date = self._prices.index[-1]
        if hasattr(last_date, "tz") and last_date.tz is not None:
            last_date = last_date.tz_localize(None)
        step = pd.Timedelta(days=self._freq_days)
        dates = [
            (last_date + step * (i + 1)).strftime("%Y-%m-%dT%H:%M:%S")
            for i in range(periods)
        ]

        return {
            "dates": dates,
            "point_forecast": point_forecast,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "confidence_level": self.confidence_level,
        }

    def get_model_info(self) -> Dict[str, Any]:
        info = super().get_model_info()
        info.update({
            "display_name": "XGBoost",
            "artifact_path": str(self._path),
            "is_fitted": self._is_fitted,
        })
        return info

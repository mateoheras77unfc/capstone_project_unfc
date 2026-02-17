"""
=============================================================================
BASE FORECASTER - Abstract Interface + Simple Baseline Model
=============================================================================

Contains:
  1. BaseForecastor  — abstract interface all models must implement
  2. SimpleForecaster — concrete "Base" model (EWM, no heavy deps)
=============================================================================
"""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any, Dict, List

import numpy as np
import pandas as pd


# ─── Abstract Base Class ─────────────────────────────────────────────────────

class BaseForecastor(ABC):
    """
    Abstract base class for forecasting models.
    All forecasting implementations (LSTM, Prophet, etc.) must inherit
    from this and implement fit() and forecast().
    """

    @abstractmethod
    def fit(self, prices: pd.Series) -> None:
        """
        Fit the model to historical price data.

        Args:
            prices: pd.Series with DatetimeIndex (oldest → newest),
                    closing prices as values.
        """
        pass

    @abstractmethod
    def forecast(self, periods: int = 4) -> Dict[str, Any]:
        """
        Generate forecasts for future periods.

        Returns:
            {
                "dates":            List[str],
                "point_forecast":   List[float],
                "lower_bound":      List[float],
                "upper_bound":      List[float],
                "confidence_level": float,
            }
        """
        pass

    def get_model_info(self) -> Dict[str, Any]:
        """Return metadata about the model."""
        return {
            "model_name": self.__class__.__name__,
            "version": "1.0",
        }

    # ─── Shared helpers (used by all subclasses) ─────────────────────────

    @staticmethod
    def _validate_prices(prices: pd.Series, min_samples: int = 5) -> None:
        """Common input validation."""
        if not isinstance(prices, pd.Series):
            raise TypeError("prices must be a pandas Series")
        if not isinstance(prices.index, pd.DatetimeIndex):
            raise TypeError("prices must have a DatetimeIndex")
        if len(prices) < min_samples:
            raise ValueError(
                f"Need at least {min_samples} data points, got {len(prices)}"
            )
        if prices.isnull().any():
            raise ValueError("prices contains NaN values — clean data first")

    @staticmethod
    def _infer_freq_days(index: pd.DatetimeIndex) -> int:
        """Infer median step size in days (works for daily/weekly/monthly)."""
        diffs = np.diff(index.values).astype("timedelta64[D]").astype(int)
        return max(int(np.median(diffs)), 1)


# ─── Concrete "Base" Model ───────────────────────────────────────────────────

class SimpleForecaster(BaseForecastor):
    """
    Lightweight baseline forecaster using Exponential Weighted Moving Average.
    No TensorFlow needed — fast, good as a sanity-check benchmark.
    Confidence intervals widen with sqrt(horizon) based on residual std.
    """

    def __init__(
        self,
        span: int = 20,
        confidence_level: float = 0.95,
    ):
        self.span = span
        self.confidence_level = confidence_level

        self._prices: pd.Series | None = None
        self._residual_std: float = 0.0
        self._last_ema: float = 0.0
        self._freq_days: int = 7
        self._is_fitted = False

    def fit(self, prices: pd.Series) -> None:
        self._validate_prices(prices, min_samples=self.span)
        self._prices = prices.copy()

        ema = prices.ewm(span=self.span, adjust=False).mean()
        residuals = prices - ema
        self._residual_std = float(residuals.std())
        self._last_ema = float(ema.iloc[-1])
        self._freq_days = self._infer_freq_days(prices.index)
        self._is_fitted = True

    def forecast(self, periods: int = 4) -> Dict[str, Any]:
        if not self._is_fitted or self._prices is None:
            raise ValueError("Call fit() before forecast()")

        from scipy.stats import norm

        z = norm.ppf((1 + self.confidence_level) / 2)
        last_date = self._prices.index[-1]

        dates: List[str] = []
        point_forecast: List[float] = []
        lower_bound: List[float] = []
        upper_bound: List[float] = []

        for i in range(1, periods + 1):
            dt = last_date + timedelta(days=self._freq_days * i)
            dates.append(dt.isoformat())

            forecast_val = self._last_ema
            margin = z * self._residual_std * np.sqrt(i)

            point_forecast.append(round(forecast_val, 4))
            lower_bound.append(round(forecast_val - margin, 4))
            upper_bound.append(round(forecast_val + margin, 4))

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
            "span": self.span,
            "confidence_level": self.confidence_level,
            "is_fitted": self._is_fitted,
        })
        return info
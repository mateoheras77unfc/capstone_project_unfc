"""
analytics/forecasting/base.py
─────────────────────────────
Abstract base class and lightweight EWM baseline forecaster.

Classes
-------
BaseForecastor
    Abstract interface every model must implement.
SimpleForecaster
    Concrete EWM baseline — no heavy ML dependencies required.
"""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy.stats import norm


# ─── Abstract Base ────────────────────────────────────────────────────────────


class BaseForecastor(ABC):
    """
    Abstract base class for all time-series forecasting models.

    Enforces a fit → forecast lifecycle and provides shared helpers
    so every subclass inherits input validation and frequency inference.
    """

    @abstractmethod
    def fit(self, prices: pd.Series) -> None:
        """
        Train the model on historical price data.

        Args:
            prices: pd.Series with a DatetimeIndex sorted oldest → newest.
                    Values are closing prices.

        Raises:
            TypeError:  If prices is not a pd.Series with DatetimeIndex.
            ValueError: If fewer than the required minimum samples are given,
                        or if NaNs are present.
        """

    @abstractmethod
    def forecast(self, periods: int = 4) -> Dict[str, Any]:
        """
        Generate forward-looking forecasts (direct multi-step: all ``periods`` from the
        same fitted context; no recursive use of prior-step predictions as inputs).

        Args:
            periods: Number of future time steps to predict.

        Returns:
            A dict with keys:
                dates            – List[str]   ISO-8601 forecast dates.
                point_forecast   – List[float] Central estimates.
                lower_bound      – List[float] Lower CI boundary.
                upper_bound      – List[float] Upper CI boundary.
                confidence_level – float       Probability mass of the interval.

        Raises:
            ValueError: If called before fit().
        """

    def get_model_info(self) -> Dict[str, Any]:
        """
        Return model metadata for logging / API responses.

        Returns:
            Dict with at least ``model_name`` and ``version`` keys.
        """
        return {"model_name": self.__class__.__name__, "version": "1.0"}

    # ── Shared validation helpers ─────────────────────────────────────────

    @staticmethod
    def _validate_prices(prices: pd.Series, min_samples: int = 5) -> None:
        """
        Validate that `prices` is a non-null pd.Series with DatetimeIndex.

        Args:
            prices:      The series to validate.
            min_samples: Minimum required data points.

        Raises:
            TypeError:  Wrong type or wrong index type.
            ValueError: Too few rows, or NaN values present.
        """
        if not isinstance(prices, pd.Series):
            raise TypeError("prices must be a pandas Series")
        if not isinstance(prices.index, pd.DatetimeIndex):
            raise TypeError("prices must have a DatetimeIndex")
        if len(prices) < min_samples:
            raise ValueError(
                f"Need at least {min_samples} data points, got {len(prices)}"
            )
        if prices.isnull().any():
            raise ValueError("prices contains NaN values — clean data before fitting")

    @staticmethod
    def _infer_freq_days(index: pd.DatetimeIndex) -> int:
        """
        Infer the median step size in calendar days.

        Works for daily, weekly, and monthly series without needing
        a pandas freq string.

        Args:
            index: DatetimeIndex of the price series.

        Returns:
            Median gap between consecutive timestamps, at minimum 1 day.
        """
        diffs = np.diff(index.values).astype("timedelta64[D]").astype(int)
        return max(int(np.median(diffs)), 1)


# ─── Concrete Baseline Model ──────────────────────────────────────────────────


class SimpleForecaster(BaseForecastor):
    """
    Lightweight EWM (Exponential Weighted Moving Average) forecaster.

    Used as a fast sanity-check benchmark. Confidence intervals widen
    with ``sqrt(horizon)`` scaled by the historical residual standard
    deviation.

    Args:
        span:             EWM span parameter (controls smoothing strength).
        confidence_level: Probability mass for the confidence interval.
    """

    def __init__(self, span: int = 20, confidence_level: float = 0.95) -> None:
        self.span = span
        self.confidence_level = confidence_level

        self._prices: pd.Series | None = None
        self._ewm_value: float = 0.0
        self._residual_std: float = 0.0
        self._freq_days: int = 7
        self._is_fitted: bool = False

    # ── fit ──────────────────────────────────────────────────────────────

    def fit(self, prices: pd.Series) -> None:
        """
        Compute the EWM trend and residual spread on historical data.

        Args:
            prices: pd.Series with DatetimeIndex, oldest → newest.
        """
        self._validate_prices(prices, min_samples=5)

        self._prices = prices.copy()
        self._freq_days = self._infer_freq_days(prices.index)

        ewm_series = prices.ewm(span=self.span).mean()
        self._ewm_value = float(ewm_series.iloc[-1])

        residuals = prices - ewm_series
        self._residual_std = float(residuals.std())
        self._is_fitted = True

    # ── forecast ─────────────────────────────────────────────────────────

    def forecast(self, periods: int = 4) -> Dict[str, Any]:
        """
        Project the EWM value forward and build confidence intervals.

        Args:
            periods: Number of future time steps to forecast.

        Returns:
            Standard forecast dict (see BaseForecastor.forecast docstring).

        Raises:
            ValueError: If called before fit().
        """
        if not self._is_fitted or self._prices is None:
            raise ValueError("Call fit() before forecast()")

        z = norm.ppf((1 + self.confidence_level) / 2)
        last_date = self._prices.index[-1]
        step = timedelta(days=self._freq_days)

        dates: List[str] = []
        point_forecast: List[float] = []
        lower_bound: List[float] = []
        upper_bound: List[float] = []

        for h in range(1, periods + 1):
            date = last_date + step * h
            margin = z * self._residual_std * np.sqrt(h)

            dates.append(date.strftime("%Y-%m-%dT%H:%M:%S"))
            point_forecast.append(round(self._ewm_value, 4))
            lower_bound.append(round(self._ewm_value - margin, 4))
            upper_bound.append(round(self._ewm_value + margin, 4))

        return {
            "dates": dates,
            "point_forecast": point_forecast,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "confidence_level": self.confidence_level,
        }

    def get_model_info(self) -> Dict[str, Any]:
        """Return EWM model metadata."""
        info = super().get_model_info()
        info.update(
            {
                "span": self.span,
                "confidence_level": self.confidence_level,
                "is_fitted": self._is_fitted,
                "residual_std": round(self._residual_std, 6) if self._is_fitted else None,
            }
        )
        return info

"""
analytics/forecasting/base.py
──────────────────────────────
Base class for all forecasting models.

Provides shared utilities used by GRUForecaster, LightGBMForecaster,
TFTForecaster, and CryptoAssemblyForecaster.
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd


class BaseForecastor:
    """
    Abstract base for all forecasters.

    Subclasses must implement:
        fit(ohlcv: pd.DataFrame) -> None
        forecast(periods: int) -> Dict[str, Any]

    Provides shared helpers:
        _infer_freq_days  — infers bar frequency from a DatetimeIndex
        get_model_info    — returns basic model metadata dict
    """

    def fit(self, ohlcv: pd.DataFrame) -> None:
        raise NotImplementedError

    def forecast(self, periods: int) -> Dict[str, Any]:
        raise NotImplementedError

    # ── shared helpers ────────────────────────────────────────────────────

    @staticmethod
    def _infer_freq_days(index: pd.DatetimeIndex) -> int:
        """
        Infer the bar frequency in calendar days from a DatetimeIndex.

        Uses the median gap between consecutive timestamps to be robust
        against missing days (weekends, holidays).

        Returns:
            1  for daily data
            7  for weekly data
            30 for monthly data (approximate)
        """
        if len(index) < 2:
            return 1
        deltas = np.diff(index.asi8) / 1e9 / 86400  # nanoseconds → days
        median_days = float(np.median(deltas))
        if median_days < 3:
            return 1
        if median_days < 10:
            return 7
        return 30

    def get_model_info(self) -> Dict[str, Any]:
        """Return basic model metadata. Subclasses extend this dict."""
        return {
            "class": self.__class__.__name__,
        }

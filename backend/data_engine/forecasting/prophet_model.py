"""
Prophet Forecaster — Facebook's Prophet for time series forecasting.
"""

import logging
from typing import Any, Dict, List

import pandas as pd

from .base_forecaster import BaseForecastor

logger = logging.getLogger(__name__)


class ProphetForecaster(BaseForecastor):

    def __init__(self, confidence_level: float = 0.95):
        self.confidence_level = confidence_level
        self._prices: pd.Series | None = None
        self._model = None
        self._freq_days: int = 7
        self._is_fitted = False

    def fit(self, prices: pd.Series) -> None:
        from prophet import Prophet

        self._validate_prices(prices, min_samples=10)
        self._prices = prices.copy()
        self._freq_days = self._infer_freq_days(prices.index)

        df = pd.DataFrame({
             "ds": prices.index.tz_localize(None),
            "y": prices.values,
        })

        self._model = Prophet(
            interval_width=self.confidence_level,
            weekly_seasonality=True,
            daily_seasonality=False,
        )
        self._model.fit(df)
        self._is_fitted = True

    def forecast(self, periods: int = 4) -> Dict[str, Any]:
        if not self._is_fitted or self._model is None:
            raise ValueError("Call fit() before forecast()")

        future = self._model.make_future_dataframe(
            periods=periods, freq=f"{self._freq_days}D"
        )
        prediction = self._model.predict(future)
        forecast_rows = prediction.tail(periods)

        return {
            "dates": forecast_rows["ds"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist(),
            "point_forecast": forecast_rows["yhat"].round(4).tolist(),
            "lower_bound": forecast_rows["yhat_lower"].round(4).tolist(),
            "upper_bound": forecast_rows["yhat_upper"].round(4).tolist(),
            "confidence_level": self.confidence_level,
        }

    def get_model_info(self) -> Dict[str, Any]:
        info = super().get_model_info()
        info.update({
            "confidence_level": self.confidence_level,
            "is_fitted": self._is_fitted,
        })
        return info
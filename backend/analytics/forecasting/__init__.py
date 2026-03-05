"""
analytics/forecasting — Time-series forecasting models.

Public API
----------
    from analytics.forecasting import BaseForecastor, SimpleForecaster
    from analytics.forecasting import ProphetForecaster
    from analytics.forecasting import XGBoostForecaster
    from analytics.forecasting import ChronosForecaster
"""

from analytics.forecasting.base import BaseForecastor, SimpleForecaster
from analytics.forecasting.chronos import ChronosForecaster
from analytics.forecasting.prophet import ProphetForecaster
from analytics.forecasting.xgboost import XGBoostForecaster

__all__ = [
    "BaseForecastor",
    "ChronosForecaster",
    "SimpleForecaster",
    "ProphetForecaster",
    "XGBoostForecaster",
]

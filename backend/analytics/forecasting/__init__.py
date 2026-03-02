"""
analytics/forecasting — Time-series forecasting models.

Public API
----------
    from analytics.forecasting import BaseForecastor, SimpleForecaster
    from analytics.forecasting import ProphetForecaster
    from analytics.forecasting import ProphetXGBForecaster
"""

from analytics.forecasting.base import BaseForecastor, SimpleForecaster
from analytics.forecasting.prophet import ProphetForecaster
from analytics.forecasting.prophet_xgb import ProphetXGBForecaster

__all__ = [
    "BaseForecastor",
    "SimpleForecaster",
    "ProphetForecaster",
    "ProphetXGBForecaster",
]

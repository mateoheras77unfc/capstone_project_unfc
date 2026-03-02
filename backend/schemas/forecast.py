"""
Pydantic schemas for forecast request / response.

Forecast endpoints (base, prophet, prophet-xgb) share identical I/O
shapes so the frontend only needs to change the URL to switch models.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Interval configuration
# ---------------------------------------------------------------------------
# min_samples     – minimum DB rows required before any model training.
# label_singular  – used in human-readable horizon strings (1 period).
# label_plural    – used in human-readable horizon strings (n > 1 periods).
# ---------------------------------------------------------------------------
INTERVAL_CONFIG: Dict[str, Dict[str, Any]] = {
    "1d": {
        "min_samples": 60,   # ~3 months of trading days — enough for valid stats
        "label_singular": "day",
        "label_plural": "days",
    },
    "1wk": {
        "min_samples": 52,
        "label_singular": "week",
        "label_plural": "weeks",
    },
    "1mo": {
        "min_samples": 24,
        "label_singular": "month",
        "label_plural": "months",
    },
}


class ForecastRequest(BaseModel):
    """
    Payload sent by the client to any forecast endpoint.

    The server fetches historical prices from the database using ``symbol``
    and ``interval``, so clients do **not** supply raw price arrays.
    This guarantees every model trains on verified, correctly-labelled
    data for the requested symbol.

    Attributes:
        symbol:           Ticker (e.g. ``AAPL``, ``BTC-USD``).  Must be
                          synced first via POST /api/v1/assets/sync/{symbol}.
        interval:         Bar interval used during sync — drives minimum-
                          data validation and horizon labels.
        periods:          Number of future time steps to forecast.
        lookback_window:  Optional (ignored by EWM / Prophet).
        epochs:           Optional (ignored by EWM / Prophet).
        confidence_level: Probability mass for the confidence interval.
    """

    symbol: str
    interval: Literal["1d", "1wk", "1mo"] = "1d"
    periods: int = Field(default=4, ge=1, le=365)
    lookback_window: int = Field(default=20, ge=5, le=60)
    epochs: int = Field(default=50, ge=10, le=200)
    confidence_level: float = Field(default=0.95, ge=0.5, le=0.99)

    @field_validator("symbol")
    @classmethod
    def normalise_symbol(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("symbol must not be empty")
        return v


class ForecastResponse(BaseModel):
    """
    Standardised forecast result returned by every forecast endpoint.

    Attributes:
        symbol:                 Ticker the forecast was built for.
        interval:               Bar interval used (``1d``, ``1wk``, or ``1mo``).
        periods_ahead:          Number of future steps forecasted.
        forecast_horizon_label: Human-readable horizon string
                                (e.g. ``"10 days (~2 weeks ahead)"`` for daily,
                                ``"4 weeks (~1 month ahead)"`` for weekly).
        data_points_used:       Historical rows the model trained on.
        dates:                  ISO-8601 dates for each forecast period.
        point_forecast:         Central estimate for each period.
        lower_bound:            Lower confidence-interval bound.
        upper_bound:            Upper confidence-interval bound.
        confidence_level:       Confidence level used for the interval.
        model_info:             Free-form model metadata dict.
    """

    symbol: str
    interval: str
    periods_ahead: int
    forecast_horizon_label: str
    data_points_used: int
    dates: List[str]
    point_forecast: List[float]
    lower_bound: List[float]
    upper_bound: List[float]
    confidence_level: float
    model_info: Dict[str, Any]


# ---------------------------------------------------------------------------
# Walk-forward metrics (Error Metrics Comparison + Forecast Bounds)
# ---------------------------------------------------------------------------


class ForecastMetricsRequest(BaseModel):
    """Request for walk-forward 1-step backtest and forecast bounds."""

    symbol: str
    interval: Literal["1d", "1wk", "1mo"] = "1wk"
    last_n_weeks: int = Field(default=20, ge=5, le=52, description="Walk-forward test window size")
    lookback_window: int = Field(default=20, ge=5, le=60)
    epochs: int = Field(default=30, ge=10, le=200)
    confidence_level: float = Field(default=0.95, ge=0.5, le=0.99)
    models: Optional[List[Literal["base", "prophet", "prophet_xgb"]]] = Field(
        default=None,
        description="Models to run. Default is base+prophet only for faster response.",
    )
    bounds_horizon_periods: Optional[int] = Field(
        default=None,
        ge=1,
        le=52,
        description="Forecast bounds horizon (number of periods). If not set, uses 12 for 1wk and 4 for 1mo.",
    )

    @field_validator("symbol")
    @classmethod
    def normalise_symbol(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("symbol must not be empty")
        return v


class ModelMetricRow(BaseModel):
    """One row in the error metrics comparison table."""

    model: str
    mae: float
    rmse: float
    mape: float


class ModelBoundsRow(BaseModel):
    """Forecast bounds for one model (lower, point, upper) over the horizon."""

    model: str
    lower: List[float]
    forecast: List[float]
    upper: List[float]


class ForecastMetricsResponse(BaseModel):
    """Response for walk-forward metrics and forecast bounds."""

    symbol: str
    interval: str
    last_n_weeks: int
    bounds_horizon_weeks: int
    metrics: List[ModelMetricRow]
    bounds: List[ModelBoundsRow]
    error: Optional[str] = None

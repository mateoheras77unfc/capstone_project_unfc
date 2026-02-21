"""
Pydantic schemas for forecast request / response.

All three forecast endpoints (base, LSTM, Prophet) share identical I/O
shapes so the frontend only needs to change the URL to switch models.
"""

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Interval configuration
# ---------------------------------------------------------------------------
# min_samples     – minimum DB rows required before any model training.
# label_singular  – used in human-readable horizon strings (1 period).
# label_plural    – used in human-readable horizon strings (n > 1 periods).
# ---------------------------------------------------------------------------
INTERVAL_CONFIG: Dict[str, Dict[str, Any]] = {
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
        lookback_window:  LSTM sequence length (ignored by EWM / Prophet).
        epochs:           LSTM training epochs (ignored by EWM / Prophet).
        confidence_level: Probability mass for the confidence interval.
    """

    symbol: str
    interval: Literal["1wk", "1mo"] = "1wk"
    periods: int = Field(default=4, ge=1, le=52)
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
        interval:               Bar interval used (``1wk`` or ``1mo``).
        periods_ahead:          Number of future steps forecasted.
        forecast_horizon_label: Human-readable horizon string
                                (e.g. ``"4 weeks (~1 month ahead)"``).
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

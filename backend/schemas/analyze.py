"""
schemas/analyze.py
───────────────────
Pydantic schemas for the unified analyze endpoint.

The analyze endpoint combines auto-sync + forecasting into a single
request/response cycle so the user never has to manually pre-populate
the database before forecasting.
"""

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, field_validator


class AnalyzeRequest(BaseModel):
    """
    Payload for POST /api/v1/analyze/{symbol}.

    The server:
      1. Checks whether ``symbol`` already exists in the database.
      2. If not → automatically syncs it from Yahoo Finance.
      3. Validates that enough rows exist for the chosen interval.
      4. Runs the requested forecast model.
      5. Returns sync metadata + full forecast in one response.

    Attributes:
        interval:         Bar interval — drives sync granularity, minimum-
                          data validation, and forecast horizon labels.
        periods:          Number of future time steps to forecast.
        model:            Which forecasting model to use.
        asset_type:       Used only when creating a new asset record in the
                          database for the first time.
        lookback_window:  LSTM sequence length (ignored by base and Prophet).
        epochs:           LSTM training epochs (ignored by base and Prophet).
        confidence_level: Probability mass for the confidence interval.
    """

    interval: Literal["1wk", "1mo"] = "1wk"
    periods: int = Field(default=4, ge=1, le=52)
    model: Literal["base", "lstm", "prophet"] = "base"
    asset_type: Literal["stock", "crypto", "index"] = "stock"
    lookback_window: int = Field(default=20, ge=5, le=60)
    epochs: int = Field(default=50, ge=10, le=200)
    confidence_level: float = Field(default=0.95, ge=0.5, le=0.99)


class SyncSummary(BaseModel):
    """
    Metadata about the auto-sync step that preceded the forecast.

    Attributes:
        performed:   ``True`` if a sync was triggered (symbol was new).
        rows_synced: Number of rows written; 0 when symbol already existed.
        message:     Human-readable summary of the sync outcome.
    """

    performed: bool
    rows_synced: int
    message: str


class AnalyzeResponse(BaseModel):
    """
    Combined sync + forecast result returned by POST /api/v1/analyze/{symbol}.

    Attributes:
        symbol:                 Normalised ticker (upper-case).
        sync:                   Metadata about the auto-sync step.
        interval:               Bar interval used for sync and forecast.
        model:                  Forecasting model that was run.
        periods_ahead:          Number of future steps forecasted.
        forecast_horizon_label: Human-readable horizon string
                                (e.g. ``"8 weeks (~2 months ahead)"``).
        data_points_used:       Historical rows the model trained on.
        dates:                  ISO-8601 dates for each forecast period.
        point_forecast:         Central estimate per period.
        lower_bound:            Lower CI bound per period.
        upper_bound:            Upper CI bound per period.
        confidence_level:       Probability mass of the CI.
        model_info:             Free-form model metadata dict.
    """

    symbol: str
    sync: SyncSummary
    interval: str
    model: str
    periods_ahead: int
    forecast_horizon_label: str
    data_points_used: int
    dates: List[str]
    point_forecast: List[float]
    lower_bound: List[float]
    upper_bound: List[float]
    confidence_level: float
    model_info: Dict[str, Any]

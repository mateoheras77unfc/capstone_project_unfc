"""
app/api/v1/endpoints/forecast.py
──────────────────────────────────
Forecast endpoints.

No forecast model is configured; POST /forecast/metrics returns empty
metrics and bounds so the frontend can call it without error.
"""

import logging

from fastapi import APIRouter

from schemas.forecast import ForecastMetricsRequest, ForecastMetricsResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/metrics",
    response_model=ForecastMetricsResponse,
    summary="Walk-forward metrics (empty — no model configured)",
)
async def forecast_metrics(
    request: ForecastMetricsRequest,
) -> ForecastMetricsResponse:
    """
    Return empty metrics and bounds. No forecast model is configured.
    """
    return ForecastMetricsResponse(
        symbol=request.symbol,
        interval=request.interval,
        last_n_weeks=request.last_n_weeks,
        bounds_horizon_weeks=0,
        metrics=[],
        bounds=[],
        error=None,
    )

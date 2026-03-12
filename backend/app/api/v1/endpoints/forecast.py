"""
app/api/v1/endpoints/forecast.py
──────────────────────────────────
Forecast endpoints.

POST /api/v1/forecast/stack-ridge-meta   Pre-trained stack (LGB + LSTM + Ridge + EWM, Ridge meta).
POST /api/v1/forecast/metrics             Walk-forward metrics (stub).
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from analytics.forecasting.stock import StackRidgeMetaForecaster
from app.api.dependencies import get_db
from schemas.forecast import (
    INTERVAL_CONFIG,
    ForecastRequest,
    ForecastResponse,
    ForecastMetricsRequest,
    ForecastMetricsResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="forecast")


def _horizon_label(periods: int, interval: str) -> str:
    """Build human-readable forecast horizon (e.g. '21 days (~1 month ahead)')."""
    cfg = INTERVAL_CONFIG.get(interval, INTERVAL_CONFIG["1d"])
    unit = cfg["label_singular"] if periods == 1 else cfg["label_plural"]
    if interval == "1d":
        cal_days = periods * (365 / 252)
        if cal_days >= 365:
            years = cal_days / 365
            approx = f"~{years:.1f} year{'s' if years >= 2 else ''} ahead"
        elif cal_days >= 28:
            months = round(cal_days / 30.44)
            approx = f"~{months} month{'s' if months != 1 else ''} ahead"
        elif cal_days >= 7:
            weeks = round(cal_days / 7)
            approx = f"~{weeks} week{'s' if weeks != 1 else ''} ahead"
        else:
            approx = "~days ahead"
    elif interval == "1wk":
        months = periods / 4.33
        m = round(months)
        if m >= 12:
            years = m / 12
            approx = f"~{years:.1f} year{'s' if years >= 2 else ''} ahead"
        elif m >= 1:
            approx = f"~{m} month{'s' if m != 1 else ''} ahead"
        else:
            approx = "~days ahead"
    else:
        if periods >= 12:
            years = periods / 12
            approx = f"~{years:.1f} year{'s' if years >= 2 else ''} ahead"
        else:
            approx = f"~{periods} month{'s' if periods != 1 else ''} ahead"
    return f"{periods} {unit} ({approx})"


async def _fetch_context_df_ohlcv(symbol: str, db: Client) -> pd.DataFrame:
    """Load OHLCV for symbol from Supabase. Returns DataFrame with timestamp, close, volume."""
    try:
        asset_res = (
            db.table("assets")
            .select("id")
            .eq("symbol", symbol)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {exc}") from exc

    if not asset_res.data:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol '{symbol}' not found. Use POST /api/v1/assets/sync/{symbol} to cache it first.",
        )

    asset_id = asset_res.data[0]["id"]

    try:
        price_res = (
            db.table("historical_prices")
            .select("timestamp, open_price, high_price, low_price, close_price, volume")
            .eq("asset_id", asset_id)
            .order("timestamp", desc=True)
            .limit(2000)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {exc}") from exc

    if not price_res.data:
        raise HTTPException(
            status_code=404,
            detail=f"No price data found for '{symbol}'. Use POST /api/v1/assets/sync/{symbol} to populate it.",
        )

    rows = list(reversed(price_res.data))
    df = pd.DataFrame(rows)
    df = df.rename(columns={"close_price": "close"})
    if "volume" not in df.columns:
        df["volume"] = np.nan
    logger.info("Loaded %d OHLCV rows for %s", len(df), symbol)
    return df


def _build_response(result: Dict[str, Any], req: ForecastRequest, n_points: int) -> ForecastResponse:
    """Build ForecastResponse from model result and request."""
    return ForecastResponse(
        symbol=req.symbol,
        interval=req.interval,
        periods_ahead=req.periods,
        forecast_horizon_label=_horizon_label(req.periods, req.interval),
        data_points_used=n_points,
        **result,
    )


def _run_stack_ridge_meta(context_df: pd.DataFrame, req: ForecastRequest) -> Dict[str, Any]:
    """Run StackRidgeMetaForecaster in thread pool."""
    model = StackRidgeMetaForecaster()
    model.fit(context_df)
    result = model.forecast(periods=req.periods)
    result["model_info"] = model.get_model_info()
    return result


@router.post(
    "/stack-ridge-meta",
    response_model=ForecastResponse,
    summary="Stack (Ridge meta) forecast",
)
async def stack_ridge_meta_forecast(
    request: ForecastRequest,
    db: Client = Depends(get_db),
) -> ForecastResponse:
    """
    Pre-trained stack (LGB + LSTM + Ridge + EWM bases, Ridge meta). Uses OHLCV from DB.
    Artifacts must exist in backend/analytics/forecasting/stock/ (run 98c notebook export cell).
    """
    context_df = await _fetch_context_df_ohlcv(request.symbol, db)
    min_rows = INTERVAL_CONFIG.get(request.interval, {}).get("min_samples", 60)
    if len(context_df) < min_rows:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{request.symbol}' has only {len(context_df)} rows — "
                f"need at least {min_rows} for stack forecast. Sync more history."
            ),
        )

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor, _run_stack_ridge_meta, context_df, request
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Stack artifact not found. Run the export cell in model/experiments-pool/98c-stack-ridge-meta-logreturn-pool.ipynb.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Stack-ridge-meta forecast failed for %s", request.symbol)
        raise HTTPException(status_code=500, detail="Forecast computation failed") from exc

    return _build_response(result, request, len(context_df))


@router.post(
    "/metrics",
    response_model=ForecastMetricsResponse,
    summary="Walk-forward metrics (empty — no model configured)",
)
async def forecast_metrics(
    request: ForecastMetricsRequest,
) -> ForecastMetricsResponse:
    """Return empty metrics and bounds. No forecast model is configured."""
    return ForecastMetricsResponse(
        symbol=request.symbol,
        interval=request.interval,
        last_n_weeks=request.last_n_weeks,
        bounds_horizon_weeks=0,
        metrics=[],
        bounds=[],
        error=None,
    )

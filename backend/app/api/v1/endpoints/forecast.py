"""
app/api/v1/endpoints/forecast.py
──────────────────────────────────
Walk-forward backtest metrics and forecast bounds using Chronos-2.

Route
-----
POST /api/v1/forecast/metrics

Flow
----
1. Fetch historical close prices for ``symbol`` from Supabase.
2. Walk-forward backtest over the last ``last_n_weeks`` windows:
   - For each step i, train on prices[:end-last_n+i], predict 1 step ahead.
   - Compare prediction vs actual → collect errors.
3. Compute aggregate MAE, RMSE, MAPE from walk-forward errors.
4. Run Chronos once on full history for ``bounds_horizon_periods`` ahead.
5. Return ForecastMetricsResponse with metrics and bounds rows.
"""

import asyncio
import logging
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from analytics.forecasting import chronos2
from app.api.dependencies import get_db
from schemas.forecast import (
    ForecastMetricsRequest,
    ForecastMetricsResponse,
    ModelBoundsRow,
    ModelMetricRow,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="forecast")


# ── helpers ───────────────────────────────────────────────────────────────────


async def _fetch_prices(symbol: str, db: Client) -> pd.Series:
    """Load historical close prices for symbol from Supabase (oldest → newest)."""
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
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found.")

    asset_id = asset_res.data[0]["id"]

    try:
        price_res = (
            db.table("historical_prices")
            .select("timestamp, close_price")
            .eq("asset_id", asset_id)
            .order("timestamp", desc=True)
            .limit(2000)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {exc}") from exc

    if not price_res.data:
        raise HTTPException(status_code=404, detail=f"No price data for '{symbol}'.")

    rows = list(reversed(price_res.data))
    index = pd.to_datetime([r["timestamp"] for r in rows], utc=True)
    values = [float(r["close_price"]) for r in rows]
    return pd.Series(values, index=index, name="close")


def _compute_walk_forward(
    prices: pd.Series,
    last_n: int,
    confidence_level: float,
    interval: str,
) -> ModelMetricRow:
    """
    Run a 1-step-ahead walk-forward backtest over the last ``last_n`` windows.

    For each step i in [0, last_n):
      - Train on prices[: -(last_n - i)]
      - Predict 1 step ahead
      - Compare vs actual prices[-(last_n - i)]

    Returns ModelMetricRow with MAE, RMSE, MAPE.
    """
    errors = []
    actuals = []
    predictions = []

    n = len(prices)
    for i in range(last_n):
        train_end = n - last_n + i
        if train_end < 30:
            continue
        train = prices.iloc[:train_end]
        actual = float(prices.iloc[train_end])

        try:
            result = chronos2.forecast(train, 1, confidence_level, interval)
            predicted = result["point_forecast"][0]
        except Exception as exc:
            logger.warning("Walk-forward step %d failed: %s", i, exc)
            continue

        errors.append(abs(actual - predicted))
        actuals.append(actual)
        predictions.append(predicted)

    if not errors:
        return ModelMetricRow(model="chronos", mae=0.0, rmse=0.0, mape=0.0)

    mae = float(np.mean(errors))
    rmse = float(math.sqrt(np.mean([(a - p) ** 2 for a, p in zip(actuals, predictions)])))
    mape = float(
        np.mean([abs(a - p) / abs(a) * 100 for a, p in zip(actuals, predictions) if a != 0])
    )

    return ModelMetricRow(model="chronos", mae=round(mae, 4), rmse=round(rmse, 4), mape=round(mape, 4))


def _compute_bounds(
    prices: pd.Series,
    horizon: int,
    confidence_level: float,
    interval: str,
) -> ModelBoundsRow:
    """Run Chronos on full history and return bounds for the horizon."""
    result = chronos2.forecast(prices, horizon, confidence_level, interval)
    return ModelBoundsRow(
        model="chronos",
        lower=result["lower_bound"],
        forecast=result["point_forecast"],
        upper=result["upper_bound"],
    )


# ── endpoint ──────────────────────────────────────────────────────────────────


@router.post(
    "/metrics",
    response_model=ForecastMetricsResponse,
    summary="Walk-forward backtest metrics and forecast bounds (Chronos-2)",
)
async def forecast_metrics(
    request: ForecastMetricsRequest,
    db: Client = Depends(get_db),
) -> ForecastMetricsResponse:
    """
    Run a walk-forward backtest and return error metrics + forecast bounds.

    Walk-forward: slides a training window over the last ``last_n_weeks``
    periods, predicts 1 step ahead each time, and aggregates MAE/RMSE/MAPE.

    Bounds: runs Chronos once on full history for ``bounds_horizon_periods``
    steps ahead and returns lower, point, upper arrays.
    """
    symbol = request.symbol.upper()
    prices = await _fetch_prices(symbol, db)

    bounds_horizon = request.bounds_horizon_periods or (
        12 if request.interval == "1wk" else 4
    )

    loop = asyncio.get_event_loop()

    try:
        metrics_row, bounds_row = await asyncio.gather(
            loop.run_in_executor(
                _executor,
                lambda: _compute_walk_forward(
                    prices,
                    request.last_n_weeks,
                    request.confidence_level,
                    request.interval,
                ),
            ),
            loop.run_in_executor(
                _executor,
                lambda: _compute_bounds(
                    prices,
                    bounds_horizon,
                    request.confidence_level,
                    request.interval,
                ),
            ),
        )
    except Exception as exc:
        logger.exception("forecast_metrics failed for %s", symbol)
        raise HTTPException(status_code=503, detail=f"Metrics computation failed: {exc}") from exc

    return ForecastMetricsResponse(
        symbol=symbol,
        interval=request.interval,
        last_n_weeks=request.last_n_weeks,
        bounds_horizon_weeks=bounds_horizon,
        metrics=[metrics_row],
        bounds=[bounds_row],
        error=None,
    )

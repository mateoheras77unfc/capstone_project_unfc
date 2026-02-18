"""
=============================================================================
FORECAST ROUTES - /api/forecast/base and /api/forecast/lstm
=============================================================================

Both endpoints use the same request/response schema so the frontend
can swap models by just changing the URL.

Training runs in a thread pool to avoid blocking FastAPI's event loop.
=============================================================================
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..data_engine.forecasting.base_forecaster import SimpleForecaster
from ..data_engine.forecasting.lstm_model import LSTMForecastor
from ..data_engine.forecasting.prophet_model import ProphetForecaster

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/forecast", tags=["forecast"])

# Thread pool — model training is CPU-bound, don't block the event loop
_executor = ThreadPoolExecutor(max_workers=2)


# ─── Request / Response schemas ──────────────────────────────────────────────

class ForecastRequest(BaseModel):
    ticker: str
    prices: List[float]
    dates: List[str]                                        # ISO-8601
    periods: int = Field(default=4, ge=1, le=52)
    lookback_window: int = Field(default=20, ge=5, le=60)   # LSTM param
    epochs: int = Field(default=50, ge=10, le=200)          # LSTM param
    confidence_level: float = Field(default=0.95, ge=0.5, le=0.99)


class ForecastResponse(BaseModel):
    ticker: str
    dates: List[str]
    point_forecast: List[float]
    lower_bound: List[float]
    upper_bound: List[float]
    confidence_level: float
    model_info: Dict[str, Any]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _build_series(req: ForecastRequest) -> pd.Series:
    """Convert request lists into a pd.Series with DatetimeIndex."""
    if len(req.prices) != len(req.dates):
        raise ValueError("prices and dates must have the same length")
    index = pd.to_datetime(req.dates)
    return pd.Series(req.prices, index=index, name="close").sort_index()


def _run_base(req: ForecastRequest) -> ForecastResponse:
    prices = _build_series(req)
    model = SimpleForecaster(
        span=min(req.lookback_window, len(prices) - 1),
        confidence_level=req.confidence_level,
    )
    model.fit(prices)
    result = model.forecast(periods=req.periods)
    return ForecastResponse(ticker=req.ticker, model_info=model.get_model_info(), **result)


def _run_lstm(req: ForecastRequest) -> ForecastResponse:
    prices = _build_series(req)
    model = LSTMForecastor(
        lookback_window=req.lookback_window,
        epochs=req.epochs,
        confidence_level=req.confidence_level,
    )
    model.fit(prices)
    result = model.forecast(periods=req.periods)
    return ForecastResponse(ticker=req.ticker, model_info=model.get_model_info(), **result)

def _run_prophet(req: ForecastRequest) -> ForecastResponse:
    prices = _build_series(req)
    model = ProphetForecaster(confidence_level=req.confidence_level)
    model.fit(prices)
    result = model.forecast(periods=req.periods)
    return ForecastResponse(ticker=req.ticker, model_info=model.get_model_info(), **result)
# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/base", response_model=ForecastResponse)
async def base_forecast(request: ForecastRequest):
    """
    Baseline forecast (Exponential Weighted Moving Average).
    Fast, no TensorFlow needed.
    """
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _run_base, request)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Base forecast failed")
        raise HTTPException(status_code=500, detail=f"Forecast error: {exc}")


@router.post("/lstm", response_model=ForecastResponse)
async def lstm_forecast(request: ForecastRequest):
    """
    LSTM neural-network forecast.
    Runs in a thread pool so training doesn't block the server.
    """
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _run_lstm, request)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="TensorFlow not installed on this server",
        )
    except Exception as exc:
        logger.exception("LSTM forecast failed")
        raise HTTPException(status_code=500, detail=f"Forecast error: {exc}")

@router.post("/prophet", response_model=ForecastResponse)
async def prophet_forecast(request: ForecastRequest):
    """Facebook Prophet forecast."""
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _run_prophet, request)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ImportError:
        raise HTTPException(status_code=501, detail="Prophet not installed")
    except Exception as exc:
        logger.exception("Prophet forecast failed")
        raise HTTPException(status_code=500, detail=f"Forecast error: {exc}")    
    
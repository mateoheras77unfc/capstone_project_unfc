"""
app/api/v1/endpoints/forecast.py
──────────────────────────────────
Forecast endpoints.

Routes
------
POST /api/v1/forecast/base    EWM baseline forecast (no GPU needed).
POST /api/v1/forecast/lstm    LSTM neural-network forecast.
POST /api/v1/forecast/prophet Facebook Prophet trend/seasonality forecast.

All three share identical request and response shapes (ForecastRequest /
ForecastResponse) so the frontend only needs to change the URL to switch
models.

Design
------
1. Prices are fetched from Supabase by ``symbol`` so models always train
   on verified, correctly-labelled data — not whatever the client sends.
2. Minimum data-point requirements are enforced *per interval* before any
   model training starts (60 rows for 1d, 52 rows for 1wk, 24 for 1mo).
3. Each response includes ``interval``, ``periods_ahead``, a human-readable
   ``forecast_horizon_label``, and ``data_points_used``.
4. Model training is CPU/GPU-bound — offloaded to a thread-pool executor
   so FastAPI's asyncio event loop is never blocked.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from analytics.forecasting import LSTMForecastor, ProphetForecaster, SimpleForecaster, Chronos2Forecaster
from app.api.dependencies import get_db
from schemas.forecast import INTERVAL_CONFIG, ForecastRequest, ForecastResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# A small pool — model training is CPU-bound, not I/O-bound.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="forecast")


# ── helpers ───────────────────────────────────────────────────────────────────


def _horizon_label(periods: int, interval: str) -> str:
    """
    Build a human-readable forecast horizon description.

    Examples::

        _horizon_label(10, "1d")  -> "10 days (~2 weeks ahead)"
        _horizon_label(63, "1d")  -> "63 days (~3 months ahead)"
        _horizon_label(4,  "1wk") -> "4 weeks (~1 month ahead)"
        _horizon_label(13, "1wk") -> "13 weeks (~3 months ahead)"
        _horizon_label(52, "1wk") -> "52 weeks (~1.0 years ahead)"
        _horizon_label(4,  "1mo") -> "4 months (~4 months ahead)"
        _horizon_label(12, "1mo") -> "12 months (~1.0 years ahead)"
    """
    cfg = INTERVAL_CONFIG[interval]
    unit = cfg["label_singular"] if periods == 1 else cfg["label_plural"]

    if interval == "1d":
        # Convert trading days to a calendar approximation (252 trading days ≈ 365 calendar days)
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
        m = round(months)  # round first so 4 wks → 1 month, not "days"
        if m >= 12:
            years = m / 12
            approx = f"~{years:.1f} year{'s' if years >= 2 else ''} ahead"
        elif m >= 1:
            approx = f"~{m} month{'s' if m != 1 else ''} ahead"
        else:
            approx = "~days ahead"
    else:  # 1mo
        if periods >= 12:
            years = periods / 12
            approx = f"~{years:.1f} year{'s' if years >= 2 else ''} ahead"
        else:
            approx = f"~{periods} month{'s' if periods != 1 else ''} ahead"

    return f"{periods} {unit} ({approx})"


async def _fetch_prices(symbol: str, db: Client) -> pd.Series:
    """
    Load all historical close prices for ``symbol`` from Supabase.

    Prices are ordered oldest → newest so models receive chronological data.

    Args:
        symbol: Normalised ticker (already upper-cased by the schema validator).
        db:     Supabase client from DI.

    Returns:
        pd.Series with UTC-aware DatetimeIndex, oldest → newest.

    Raises:
        HTTPException 404: Symbol not found or has no price rows.
        HTTPException 503: Supabase query failed.
    """
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
            detail=(
                f"Symbol '{symbol}' not found. "
                f"Use POST /api/v1/assets/sync/{symbol} to cache it first."
            ),
        )

    asset_id = asset_res.data[0]["id"]

    try:
        price_res = (
            db.table("historical_prices")
            .select("timestamp, close_price")
            .eq("asset_id", asset_id)
            .order("timestamp", desc=True)   # newest first so limit captures recent data
            .limit(2000)                       # ~8 years of daily bars; avoids Supabase 1 000-row default cap
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {exc}") from exc

    if not price_res.data:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No price data found for '{symbol}'. "
                f"Use POST /api/v1/assets/sync/{symbol} to populate it."
            ),
        )

    rows = list(reversed(price_res.data))  # restore chronological order (oldest → newest)
    index = pd.to_datetime([r["timestamp"] for r in rows], utc=True)
    values = [float(r["close_price"]) for r in rows]
    logger.info("Loaded %d price rows for %s", len(rows), symbol)
    return pd.Series(values, index=index, name="close")


def _validate_interval_minimums(series: pd.Series, interval: str, symbol: str) -> None:
    """
    Enforce minimum data-point counts per interval before any training.

    Args:
        series:   Historical price series fetched from the database.
        interval: Bar interval (``1wk`` or ``1mo``).
        symbol:   Ticker symbol (used in the error message only).

    Raises:
        HTTPException 422: Fewer rows available than the minimum required.
    """
    cfg = INTERVAL_CONFIG[interval]
    min_rows = cfg["min_samples"]
    if len(series) < min_rows:
        unit = cfg["label_plural"]
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{symbol}' has only {len(series)} {interval} rows in the database — "
                f"need at least {min_rows} {unit} for a reliable forecast. "
                f"Sync more history or choose a different interval."
            ),
        )


def _build_response(
    result: Dict[str, Any],
    req: ForecastRequest,
    n_points: int,
) -> ForecastResponse:
    """Assemble a ForecastResponse from raw model output + request context."""
    return ForecastResponse(
        symbol=req.symbol,
        interval=req.interval,
        periods_ahead=req.periods,
        forecast_horizon_label=_horizon_label(req.periods, req.interval),
        data_points_used=n_points,
        **result,
    )


# ── thread-pool workers ───────────────────────────────────────────────────────


def _run_base(prices: pd.Series, req: ForecastRequest) -> Dict[str, Any]:
    """Run SimpleForecaster synchronously (called inside thread pool)."""
    model = SimpleForecaster(
        span=min(req.lookback_window, len(prices) - 1),
        confidence_level=req.confidence_level,
    )
    model.fit(prices)
    result = model.forecast(periods=req.periods)
    result["model_info"] = model.get_model_info()
    return result


def _run_lstm(prices: pd.Series, req: ForecastRequest) -> Dict[str, Any]:
    """Run LSTMForecastor synchronously (called inside thread pool)."""
    model = LSTMForecastor(
        lookback_window=req.lookback_window,
        epochs=req.epochs,
        confidence_level=req.confidence_level,
    )
    model.fit(prices)
    result = model.forecast(periods=req.periods)
    result["model_info"] = model.get_model_info()
    return result


def _run_prophet(prices: pd.Series, req: ForecastRequest) -> Dict[str, Any]:
    """Run ProphetForecaster synchronously (called inside thread pool)."""
    model = ProphetForecaster(confidence_level=req.confidence_level)
    model.fit(prices)
    result = model.forecast(periods=req.periods)
    result["model_info"] = model.get_model_info()
    return result

def _run_chronos2(prices: pd.Series, req: ForecastRequest) -> Dict[str, Any]:
    """
    Run Chronos-2 synchronously (called inside thread pool).
    Uses req.lookback_window as a context cap for predictable latency.
    """
    # Optional: cap series length by lookback_window for speed
    if req.lookback_window and len(prices) > req.lookback_window:
        prices = prices.iloc[-req.lookback_window :]

    model = Chronos2Forecaster(confidence_level=req.confidence_level)
    model.fit(prices)
    result = model.forecast(periods=req.periods)
    result["model_info"] = model.get_model_info()
    return result


# ── endpoints ─────────────────────────────────────────────────────────────────


@router.post("/base", response_model=ForecastResponse, summary="EWM baseline forecast")
async def base_forecast(
    request: ForecastRequest,
    db: Client = Depends(get_db),
) -> ForecastResponse:
    """
    Exponential Weighted Moving Average (EWM) forecast.

    Fast — no TensorFlow required. Good sanity-check benchmark.
    Prices are fetched from the database by ``symbol`` so the model
    always uses the correct, verified data.

    Args:
        request: Symbol, interval, and forecast parameters.

    Returns:
        Point forecast with widening confidence bounds plus interval metadata.

    Raises:
        HTTPException 404: Symbol not synced yet.
        HTTPException 422: Insufficient rows for the requested interval.
    """
    prices = await _fetch_prices(request.symbol, db)
    _validate_interval_minimums(prices, request.interval, request.symbol)

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, _run_base, prices, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Base forecast failed for %s", request.symbol)
        raise HTTPException(status_code=500, detail="Forecast computation failed") from exc

    return _build_response(result, request, len(prices))


@router.post(
    "/lstm",
    response_model=ForecastResponse,
    summary="LSTM neural-network forecast",
)
async def lstm_forecast(
    request: ForecastRequest,
    db: Client = Depends(get_db),
) -> ForecastResponse:
    """
    LSTM deep-learning forecast.

    Requires TensorFlow (``pip install tensorflow``). Training runs in a
    thread pool to avoid blocking the event loop.
    Prices are fetched from the database by ``symbol``.

    Args:
        request: Symbol, interval, and forecast parameters.

    Returns:
        Point forecast with residual-based confidence bounds.

    Raises:
        HTTPException 503: TensorFlow not installed.
        HTTPException 404: Symbol not synced yet.
        HTTPException 422: Insufficient rows for the requested interval.
    """
    prices = await _fetch_prices(request.symbol, db)
    _validate_interval_minimums(prices, request.interval, request.symbol)

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, _run_lstm, prices, request)
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="TensorFlow is not installed on this server. Use /forecast/base instead.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("LSTM forecast failed for %s", request.symbol)
        raise HTTPException(status_code=500, detail="Forecast computation failed") from exc

    return _build_response(result, request, len(prices))


@router.post(
    "/prophet",
    response_model=ForecastResponse,
    summary="Facebook Prophet forecast",
)
async def prophet_forecast(
    request: ForecastRequest,
    db: Client = Depends(get_db),
) -> ForecastResponse:
    """
    Facebook Prophet trend + seasonality forecast.

    Handles missing data and outliers well.
    Prices are fetched from the database by ``symbol``.

    Args:
        request: Symbol, interval, and forecast parameters.

    Returns:
        Point forecast with native Prophet confidence bounds.

    Raises:
        HTTPException 503: prophet package not installed.
        HTTPException 404: Symbol not synced yet.
        HTTPException 422: Insufficient rows for the requested interval.
    """
    prices = await _fetch_prices(request.symbol, db)
    _validate_interval_minimums(prices, request.interval, request.symbol)

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, _run_prophet, prices, request)
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="'prophet' is not installed on this server.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Prophet forecast failed for %s", request.symbol)
        raise HTTPException(status_code=500, detail="Forecast computation failed") from exc

    return _build_response(result, request, len(prices))


@router.post("/chronos2", response_model=ForecastResponse, summary="Chronos-2 foundation model forecast")
async def chronos2_forecast(
    request: ForecastRequest,
    db: Client = Depends(get_db),
) -> ForecastResponse:
    prices = await _fetch_prices(request.symbol, db)
    _validate_interval_minimums(prices, request.interval, request.symbol)

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(_executor, _run_chronos2, prices, request)
        return _build_response(result, request, n_points=len(prices))
    except ImportError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Chronos-2 forecast failed")
        raise HTTPException(status_code=500, detail=f"Forecast error: {exc}")
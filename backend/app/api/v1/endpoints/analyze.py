"""
app/api/v1/endpoints/analyze.py
─────────────────────────────────
Unified analyze endpoint — auto-sync only (no forecast model configured).

Route
-----
POST /api/v1/analyze/{symbol}

Flow
----
1. Normalise ``symbol`` to upper-case.
2. Check whether the asset already exists in the database.
   - **Miss** → auto-sync from Yahoo Finance (yfinance → Supabase).
   - **Hit**  → skip sync; ``sync.performed = False``.
3. Validate minimum row count for the chosen ``interval``
   (52 rows for ``1wk``, 24 rows for ``1mo``).
4. Return sync metadata and empty forecast structure (no model configured).

Error codes
-----------
404  Symbol is brand-new AND yfinance has no history for it.
422  Not enough rows in the DB for the chosen interval.
     Malformed request body (Pydantic validation).
503  Supabase unreachable.
500  Unexpected internal error.

Design decisions
----------------
- Sync is offloaded to a shared ``ThreadPoolExecutor`` (I/O-bound).
- Helpers ``_fetch_prices`` and ``_validate_interval_minimums`` are kept
  local to avoid cross-module coupling.
- ``DataCoordinator`` is instantiated once at module load (stateless).
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from app.api.dependencies import get_db
from data_engine.coordinator import DataCoordinator
from schemas.analyze import AnalyzeRequest, AnalyzeResponse, SyncSummary
from schemas.forecast import INTERVAL_CONFIG

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared thread pool — sync (I/O + network) and training (CPU) both block.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analyze")
_coordinator = DataCoordinator()


# ── private helpers ───────────────────────────────────────────────────────────


def _horizon_label(periods: int, interval: str) -> str:
    """
    Build a human-readable forecast horizon string.

    Args:
        periods:  Number of future time steps.
        interval: Bar interval (``"1d"``, ``"1wk"`` or ``"1mo"``).

    Returns:
        Examples: ``"30 days (~1 month ahead)"``,
                  ``"8 weeks (~2 months ahead)"``.
    """
    cfg = INTERVAL_CONFIG[interval]
    unit = cfg["label_singular"] if periods == 1 else cfg["label_plural"]

    if interval == "1d":
        m = round(periods / 21)   # ~21 trading days per month
        if m >= 12:
            years = m / 12
            approx = f"~{years:.1f} year{'s' if years >= 2 else ''} ahead"
        elif m >= 1:
            approx = f"~{m} month{'s' if m != 1 else ''} ahead"
        else:
            approx = f"~{periods} trading day{'s' if periods != 1 else ''} ahead"
    elif interval == "1wk":
        m = round(periods / 4.33)
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
    Load all historical close prices for ``symbol`` from the database.

    Prices are returned oldest → newest so models receive chronological data.

    Args:
        symbol: Normalised ticker (upper-case).
        db:     Supabase client from DI.

    Returns:
        pd.Series with UTC-aware DatetimeIndex.

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
                f"Symbol '{symbol}' could not be synced — yfinance returned "
                f"no data. Check that the ticker is valid."
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
            detail=f"Sync completed but produced no price rows for '{symbol}'.",
        )

    rows = list(reversed(price_res.data))  # restore chronological order (oldest → newest)
    index = pd.to_datetime([r["timestamp"] for r in rows], utc=True)
    values = [float(r["close_price"]) for r in rows]
    logger.info("Loaded %d price rows for %s", len(rows), symbol)
    return pd.Series(values, index=index, name="close")


def _validate_interval_minimums(
    series: pd.Series, interval: str, symbol: str
) -> None:
    """
    Enforce minimum row counts before any model training.

    Args:
        series:   Historical price series.
        interval: Bar interval (``"1wk"`` or ``"1mo"``).
        symbol:   Ticker (used in the error message only).

    Raises:
        HTTPException 422: Fewer rows than the interval minimum.
    """
    cfg = INTERVAL_CONFIG[interval]
    min_rows = cfg["min_samples"]
    if len(series) < min_rows:
        unit = cfg["label_plural"]
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{symbol}' has only {len(series)} {interval} rows — "
                f"need at least {min_rows} {unit} for a reliable forecast. "
                f"Try a different interval or wait for more history."
            ),
        )


# ── thread-pool workers ───────────────────────────────────────────────────────


def _do_sync(symbol: str, asset_type: str, interval: str) -> int:
    """
    Run DataCoordinator.sync_asset() synchronously inside the thread pool.

    Args:
        symbol:     Normalised ticker.
        asset_type: ``"stock"``, ``"crypto"``, or ``"index"``.
        interval:   ``"1wk"`` or ``"1mo"``.

    Returns:
        Number of rows upserted.

    Raises:
        ValueError:   yfinance returned no data (bad ticker).
        RuntimeError: Supabase connection / permission problem.
    """
    return _coordinator.sync_asset(symbol, asset_type, interval)


def _empty_forecast_result(confidence_level: float) -> Dict[str, Any]:
    """Return empty forecast structure (no forecast model configured)."""
    return {
        "dates": [],
        "point_forecast": [],
        "lower_bound": [],
        "upper_bound": [],
        "confidence_level": confidence_level,
        "model_info": {},
    }


# ── endpoint ──────────────────────────────────────────────────────────────────


@router.post(
    "/{symbol}",
    response_model=AnalyzeResponse,
    summary="Auto-sync (no forecast model configured)",
    responses={
        200: {"description": "Forecast returned (sync may or may not have run)"},
        404: {"description": "Symbol not found in Yahoo Finance"},
        422: {"description": "Insufficient data for the interval or bad request"},
        503: {"description": "Supabase unreachable or optional ML package absent"},
        500: {"description": "Unexpected server error"},
    },
)
async def analyze(
    symbol: str,
    request: AnalyzeRequest,
    db: Client = Depends(get_db),
) -> AnalyzeResponse:
    """
    Sync a stock or crypto from Yahoo Finance and return sync metadata.

    If ``symbol`` is not yet in the database, historical data is pulled
    automatically from Yahoo Finance. If the symbol already exists, the
    sync step is skipped. No forecast model is configured; forecast
    fields in the response are empty.

    **Request body** — all fields optional (defaults shown):
    ```json
    {
      "interval":   "1d",       // "1d" | "1wk" | "1mo"
      "periods":    4,
      "model":      "chronos",
      "asset_type": "stock"    // "stock" | "crypto" | "index"
    }
    ```

    Returns:
        Sync metadata plus empty forecast structure (dates, point_forecast, etc. empty).

    Raises:
        HTTPException 404: Ticker not recognised by Yahoo Finance.
        HTTPException 422: Too few rows for the requested interval.
        HTTPException 503: Database unreachable.
        HTTPException 500: Unexpected internal error.
    """
    symbol = symbol.strip().upper()
    loop = asyncio.get_event_loop()

    # ── 1. Check whether symbol is already cached ─────────────────────────
    try:
        check_res = (
            db.table("assets")
            .select("id")
            .eq("symbol", symbol)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database error during asset lookup: {exc}",
        ) from exc

    symbol_exists = bool(check_res.data)

    # ── 2. Auto-sync if symbol is new ─────────────────────────────────────
    sync_summary: SyncSummary
    if not symbol_exists:
        logger.info(
            "'%s' not in DB — triggering auto-sync (%s, %s)",
            symbol,
            request.interval,
            request.asset_type,
        )
        try:
            rows_synced = await loop.run_in_executor(
                _executor,
                _do_sync,
                symbol,
                request.asset_type,
                request.interval,
            )
        except ValueError as exc:
            # yfinance returned no data → ticker is invalid
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Symbol '{symbol}' not found on Yahoo Finance. "
                    f"Check the ticker spelling. Details: {exc}"
                ),
            ) from exc
        except RuntimeError as exc:
            # Supabase connection / permission problem
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Auto-sync failed for %s", symbol)
            raise HTTPException(
                status_code=500,
                detail=f"Auto-sync failed unexpectedly: {exc}",
            ) from exc

        sync_summary = SyncSummary(
            performed=True,
            rows_synced=rows_synced,
            message=f"Synced {symbol} ({request.interval}) — {rows_synced} rows written",
        )
        logger.info("Auto-sync complete for %s: %d rows", symbol, rows_synced)
    else:
        sync_summary = SyncSummary(
            performed=False,
            rows_synced=0,
            message=f"'{symbol}' already cached — sync skipped",
        )
        logger.info("'%s' already in DB — skipping sync", symbol)

    # ── 3. Fetch prices from DB ───────────────────────────────────────────
    prices = await _fetch_prices(symbol, db)

    # ── 4. Validate minimum data points for the interval ──────────────────
    _validate_interval_minimums(prices, request.interval, symbol)

    # ── 5. No forecast model configured — return sync + empty forecast ─────
    result = _empty_forecast_result(request.confidence_level)

    # ── 6. Assemble and return the unified response ───────────────────────
    return AnalyzeResponse(
        symbol=symbol,
        sync=sync_summary,
        interval=request.interval,
        model=request.model,
        periods_ahead=0,
        forecast_horizon_label="",
        data_points_used=len(prices),
        **result,
    )

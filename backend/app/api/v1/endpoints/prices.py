"""
app/api/v1/endpoints/prices.py
────────────────────────────────
Historical price endpoints.

Routes
------
GET /api/v1/prices/{symbol}   Return cached OHLCV rows for a symbol.
"""

import logging
from datetime import date as Date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_cache.decorator import cache
from supabase import Client

from app.api.dependencies import get_db
from schemas.assets import PriceOut

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/{symbol}",
    response_model=list[PriceOut],
    summary="Historical prices for a symbol",
)
@cache(expire=300)
def get_prices(
    symbol: str,
    limit: int = Query(default=750, ge=1, le=2500, description="Max rows to return (newest first). Default 750 (~3 years daily). Hard cap 2 500."),
    from_date: Optional[str] = Query(default=None, description="Oldest bar to include, ISO 8601 (YYYY-MM-DD)."),
    to_date: Optional[str] = Query(default=None, description="Most recent bar to include, ISO 8601 (YYYY-MM-DD)."),
    db: Client = Depends(get_db),
) -> list[PriceOut]:
    """
    Return the cached OHLCV history for ``symbol``.

    Results are ordered newest → oldest. Use ``/assets/sync/{symbol}``
    first if the asset has not been cached yet.

    Args:
        symbol:    Ticker symbol (e.g. ``AAPL``, ``BTC-USD``).
        limit:     Maximum rows to return (default 750, hard cap 2 500).
        from_date: Optional ISO-8601 start date inclusive (e.g. ``2022-01-01``).
        to_date:   Optional ISO-8601 end date inclusive (e.g. ``2024-12-31``).

    Returns:
        List of OHLCV price rows, newest first.

    Raises:
        HTTPException 400: Invalid date format or ``from_date ≥ to_date``.
        HTTPException 404: Symbol not in the database.
    """
    symbol = symbol.upper()

    # ── validate and parse date params ──────────────────────────────────
    parsed_from: Optional[Date] = None
    parsed_to: Optional[Date] = None
    try:
        if from_date:
            parsed_from = Date.fromisoformat(from_date)
        if to_date:
            parsed_to = Date.fromisoformat(to_date)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: {exc}. Use ISO 8601 (YYYY-MM-DD).",
        ) from exc

    if parsed_from and parsed_to and parsed_from >= parsed_to:
        raise HTTPException(
            status_code=400,
            detail="'from_date' must be strictly earlier than 'to_date'.",
        )

    # ── asset lookup ───────────────────────────────────────────────────
    asset_res = (
        db.table("assets").select("id").eq("symbol", symbol).limit(1).execute()
    )
    if not asset_res.data:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol '{symbol}' not found. Use POST /api/v1/assets/sync/{symbol} to cache it.",
        )

    asset_id = asset_res.data[0]["id"]

    # ── price query with optional date filters ───────────────────────────
    price_query = (
        db.table("historical_prices")
        .select("*")
        .eq("asset_id", asset_id)
    )
    if parsed_from:
        price_query = price_query.gte("timestamp", parsed_from.isoformat())
    if parsed_to:
        # Include the full to_date day by filtering strictly before the next day.
        price_query = price_query.lt(
            "timestamp", (parsed_to + timedelta(days=1)).isoformat()
        )
    price_res = price_query.order("timestamp", desc=True).limit(limit).execute()

    logger.info("Returned %d price rows for %s", len(price_res.data), symbol)
    return price_res.data

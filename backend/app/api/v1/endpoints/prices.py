"""
app/api/v1/endpoints/prices.py
────────────────────────────────
Historical price endpoints.

Routes
------
GET /api/v1/prices/{symbol}   Return cached OHLCV rows for a symbol.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
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
def get_prices(
    symbol: str,
    limit: int = 200,
    db: Client = Depends(get_db),
) -> list[PriceOut]:
    """
    Return the cached weekly OHLCV history for ``symbol``.

    Results are ordered newest → oldest. Use ``/assets/sync/{symbol}``
    first if the asset has not been cached yet.

    Args:
        symbol: Ticker symbol (e.g. ``AAPL``, ``BTC-USD``).
        limit:  Maximum rows to return (default 200, max 1 000).

    Returns:
        List of OHLCV price rows.

    Raises:
        HTTPException 404: If the symbol is not found in the database.
    """
    symbol = symbol.upper()
    limit = min(limit, 1000)  # hard cap

    # Resolve asset id — use .limit(1) not .single() to avoid APIError on 0 rows
    asset_res = (
        db.table("assets").select("id").eq("symbol", symbol).limit(1).execute()
    )
    if not asset_res.data:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol '{symbol}' not found. Use POST /api/v1/assets/sync/{symbol} to cache it.",
        )

    asset_id = asset_res.data[0]["id"]

    price_res = (
        db.table("historical_prices")
        .select("*")
        .eq("asset_id", asset_id)
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )

    logger.info("Returned %d price rows for %s", len(price_res.data), symbol)
    return price_res.data

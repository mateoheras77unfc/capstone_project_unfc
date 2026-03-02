"""
app/api/v1/endpoints/assets.py
────────────────────────────────
Asset management endpoints.

Routes
------
GET    /api/v1/assets               List all cached assets.
GET    /api/v1/assets/search?q=...  Fuzzy symbol / name search (autocomplete).
GET    /api/v1/assets/{symbol}      Single asset detail.
DELETE /api/v1/assets/{symbol}      Remove asset + full price history.
POST   /api/v1/assets/sync/{symbol} Fetch & cache data for a symbol.

IMPORTANT: /search and /sync/{symbol} are registered BEFORE /{symbol}
so FastAPI does not interpret the literal strings as path parameters.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi_cache.decorator import cache
from supabase import Client

from app.api.dependencies import get_db
from data_engine.coordinator import DataCoordinator
from schemas.assets import AssetOut, SyncResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Single coordinator instance reused across requests (stateless calls).
_coordinator = DataCoordinator()


@router.get("/", response_model=list[AssetOut], summary="List all cached assets")
@cache(expire=60)
def list_assets(db: Client = Depends(get_db)) -> list[AssetOut]:
    """
    Return every asset row currently cached in the database.

    Cached for 60 seconds to reduce Supabase query load.

    Returns:
        List of asset records ordered by symbol.
    """
    res = db.table("assets").select("*").order("symbol").execute()
    return res.data


# NOTE: registered before /{symbol} to prevent path-param collision.
@router.get(
    "/search",
    response_model=list[AssetOut],
    summary="Search assets by symbol or name",
)
def search_assets(
    q: Optional[str] = Query(
        default=None,
        min_length=1,
        max_length=20,
        description="Partial symbol or name to search (case-insensitive).",
    ),
    limit: int = Query(default=10, ge=1, le=50, description="Max results to return."),
    db: Client = Depends(get_db),
) -> list[AssetOut]:
    """
    Return up to ``limit`` assets whose **symbol** or **name** contains ``q``.

    Useful for autocomplete / symbol discovery. When ``q`` is omitted the
    most-recently-updated assets are returned instead.

    Args:
        q:     Search term. Case-insensitive substring match on symbol first,
               then name if symbol search returns nothing.
        limit: Maximum results (default 10, max 50).

    Returns:
        List of matching asset records.
    """
    if q:
        # Symbol search (case-insensitive substring)
        res = (
            db.table("assets")
            .select("*")
            .ilike("symbol", f"%{q.upper()}%")
            .order("symbol")
            .limit(limit)
            .execute()
        )
        # Fall back to name search if nothing matched on symbol
        if not res.data:
            res = (
                db.table("assets")
                .select("*")
                .ilike("name", f"%{q}%")
                .order("symbol")
                .limit(limit)
                .execute()
            )
    else:
        res = (
            db.table("assets")
            .select("*")
            .order("last_updated", desc=True)
            .limit(limit)
            .execute()
        )
    return res.data


@router.get(
    "/{symbol}",
    response_model=AssetOut,
    summary="Get a single asset by symbol",
)
def get_asset(
    symbol: str,
    db: Client = Depends(get_db),
) -> AssetOut:
    """
    Return full asset metadata for ``symbol``.

    Args:
        symbol: Ticker (case-insensitive, normalised to uppercase).

    Returns:
        Single asset record.

    Raises:
        HTTPException 404: Symbol not in the database.
    """
    res = (
        db.table("assets")
        .select("*")
        .eq("symbol", symbol.upper())
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Symbol '{symbol.upper()}' not found. "
                f"Use POST /api/v1/assets/sync/{symbol.upper()} to cache it."
            ),
        )
    return res.data[0]


@router.delete(
    "/{symbol}",
    status_code=204,
    summary="Delete an asset and its full price history",
)
def delete_asset(
    symbol: str,
    db: Client = Depends(get_db),
) -> Response:
    """
    Permanently remove ``symbol`` from the database.

    ``historical_prices`` uses ``ON DELETE CASCADE`` so all price rows
    are removed automatically when the parent asset row is deleted.

    Args:
        symbol: Ticker to delete (case-insensitive).

    Returns:
        HTTP 204 No Content on success.

    Raises:
        HTTPException 404: Symbol not in the database.
    """
    symbol = symbol.upper()

    asset_res = (
        db.table("assets").select("id").eq("symbol", symbol).limit(1).execute()
    )
    if not asset_res.data:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol '{symbol}' not found — nothing to delete.",
        )

    asset_id = asset_res.data[0]["id"]
    db.table("assets").delete().eq("id", asset_id).execute()
    logger.info("Deleted asset %s (id=%s)", symbol, asset_id)
    return Response(status_code=204)


@router.post(
    "/sync/{symbol}",
    response_model=SyncResponse,
    summary="Sync asset data from Yahoo Finance",
)
def sync_asset(
    symbol: str,
    asset_type: str = "stock",
    interval: str = "1d",
) -> SyncResponse:
    """
    Fetch historical OHLCV data from Yahoo Finance and cache it in Supabase.

    - If the asset already exists, only missing dates are upserted.
    - Supported ``asset_type`` values: ``stock``, ``crypto``, ``index``.
    - Supported ``interval`` values: ``1d`` (default), ``1wk``, ``1mo``.

    Args:
        symbol:     Ticker symbol (e.g. ``AAPL``, ``BTC-USD``).
        asset_type: Asset category used for database labelling.
        interval:   yfinance data interval.

    Returns:
        Confirmation message with the synced symbol.

    Raises:
        HTTPException 422: If yfinance returns no data for the symbol.
    """
    try:
        rows = _coordinator.sync_asset(symbol.upper(), asset_type, interval)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Sync failed for %s", symbol)
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}") from exc

    return SyncResponse(
        status="success",
        message=f"Synced {symbol.upper()} ({interval}) — {rows} rows written",
        symbol=symbol.upper(),
        rows_synced=rows,
    )

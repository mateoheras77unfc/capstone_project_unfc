"""
app/api/v1/endpoints/assets.py
────────────────────────────────
Asset management endpoints.

Routes
------
GET  /api/v1/assets            List all cached assets.
POST /api/v1/assets/sync/{symbol}  Fetch & cache data for a symbol.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from app.api.dependencies import get_db
from data_engine.coordinator import DataCoordinator
from schemas.assets import AssetOut, SyncResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Single coordinator instance reused across requests (stateless calls).
_coordinator = DataCoordinator()


@router.get("/", response_model=list[AssetOut], summary="List all cached assets")
def list_assets(db: Client = Depends(get_db)) -> list[AssetOut]:
    """
    Return every asset row currently cached in the database.

    Returns:
        List of asset records ordered by symbol.
    """
    res = db.table("assets").select("*").order("symbol").execute()
    return res.data


@router.post(
    "/sync/{symbol}",
    response_model=SyncResponse,
    summary="Sync asset data from Yahoo Finance",
)
def sync_asset(
    symbol: str,
    asset_type: str = "stock",
    interval: str = "1wk",
) -> SyncResponse:
    """
    Fetch historical OHLCV data from Yahoo Finance and cache it in Supabase.

    - If the asset already exists, only missing dates are upserted.
    - Supported ``asset_type`` values: ``stock``, ``crypto``, ``index``.
    - Supported ``interval`` values: ``1wk``, ``1mo``.

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
        # yfinance returned no data for the symbol
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        # Supabase connection / permission problem
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

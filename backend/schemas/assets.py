"""
Pydantic schemas for asset and price data.

These schemas define the API contract for the /assets and /prices
endpoints. They are decoupled from the database models for flexibility.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AssetOut(BaseModel):
    """Read schema for an asset record."""

    id: str
    symbol: str
    name: Optional[str] = None
    asset_type: str
    currency: str = "USD"
    last_updated: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PriceOut(BaseModel):
    """Read schema for a single OHLCV price row."""

    id: str
    asset_id: str
    timestamp: datetime
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: float
    volume: Optional[int] = None

    model_config = {"from_attributes": True}


class SyncResponse(BaseModel):
    """Response for the sync endpoint."""

    status: str = Field(..., examples=["success"])
    message: str
    symbol: str
    rows_synced: int = 0

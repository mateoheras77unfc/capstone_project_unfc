"""
=============================================================================
INVESTMENT ANALYTICS API - FastAPI Backend
=============================================================================

ENDPOINTS:
----------
GET  /                      - Health check
GET  /assets                - List all cached assets
GET  /prices/{symbol}       - Get historical prices for an asset
POST /sync/{symbol}         - Fetch and cache new asset data
POST /api/forecast/base     - Baseline EWM forecast        ← NEW
POST /api/forecast/lstm     - LSTM neural network forecast  ← NEW
=============================================================================
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from ..core.config import get_settings
from ..core.database import get_supabase_client
from ..data_engine.data_coordinator import DataCoordinator
from .forecast_routes import router as forecast_router

settings = get_settings()

# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
)

# -----------------------------------------------------------------------------
# CORS Configuration  (origins managed centrally in core/config.py)
# -----------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Data Coordinator Instance
# -----------------------------------------------------------------------------
coordinator = DataCoordinator()


# =============================================================================
# REGISTER ROUTERS
# =============================================================================
app.include_router(forecast_router)                              # ← NEW


# =============================================================================
# EXISTING ENDPOINTS (unchanged)
# =============================================================================

@app.get("/")
def read_root():
    """Health check endpoint."""
    return {"message": "Welcome to the Investment Analytics API"}


@app.get("/assets")
def get_assets():
    """Returns all assets currently cached in the database."""
    supabase = get_supabase_client()
    res = supabase.table("assets").select("*").execute()
    return res.data


@app.get("/prices/{symbol}")
def get_prices(symbol: str):
    """Returns historical weekly prices for a given asset."""
    supabase = get_supabase_client()

    asset_res = supabase.table("assets").select("id").eq("symbol", symbol).execute()
    if not asset_res.data:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset_id = asset_res.data[0]['id']

    price_res = supabase.table("historical_prices") \
        .select("*") \
        .eq("asset_id", asset_id) \
        .order("timestamp", desc=True) \
        .execute()

    return price_res.data


@app.post("/sync/{symbol}")
def sync_asset(symbol: str, asset_type: str = "stock"):
    """Fetches and caches historical data for a new or existing asset."""
    try:
        coordinator.sync_asset(symbol, asset_type, "1wk")
        return {"status": "success", "message": f"Synced {symbol}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
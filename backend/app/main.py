from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from ..core.database import get_supabase_client
from ..data_engine.data_coordinator import DataCoordinator

app = FastAPI(title="Investment Analytics API")

# Allow Streamlit (usually localhost:8501) and Vite (localhost:5173) just in case
origins = [
    "http://localhost:8501",
    "http://localhost:5173",
    "http://127.0.0.1:8501"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

coordinator = DataCoordinator()

@app.get("/")
def read_root():
    return {"message": "Welcome to the Investment Analytics API"}

@app.get("/assets")
def get_assets():
    supabase = get_supabase_client()
    res = supabase.table("assets").select("*").execute()
    return res.data

@app.get("/prices/{symbol}")
def get_prices(symbol: str):
    supabase = get_supabase_client()
    
    # Get asset ID
    asset_res = supabase.table("assets").select("id").eq("symbol", symbol).execute()
    if not asset_res.data:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    asset_id = asset_res.data[0]['id']
    
    # Get prices (weekly data only)
    price_res = supabase.table("historical_prices") \
        .select("*") \
        .eq("asset_id", asset_id) \
        .order("timestamp", desc=True) \
        .execute()
        
    return price_res.data

@app.post("/sync/{symbol}")
def sync_asset(symbol: str, asset_type: str = "stock"):
    try:
        coordinator.sync_asset(symbol, asset_type, "1wk")
        return {"status": "success", "message": f"Synced {symbol}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


"""
=============================================================================
DATA COORDINATOR - Core Data Layer Interface
=============================================================================

WARNING: ISOLATION BOUNDARY
---------------------------
This module is the PRIMARY INTERFACE for data retrieval and caching.
Phase 3 (Forecasting) and Phase 4 (Optimization) teams should ONLY interact
with data through this coordinator or the API endpoints. 

DO NOT:
- Modify this file without consulting the data team
- Create direct yfinance calls outside of this module
- Create direct Supabase queries for historical prices outside of this module

FOR PHASE 3/4 DEVELOPERS:
-------------------------
Use the following methods to get data:
1. API Endpoint: GET /prices/{symbol} - Returns cached historical prices
2. API Endpoint: POST /sync/{symbol} - Fetches and caches new data

The data returned is WEEKLY closing prices. Do not assume any other interval.
=============================================================================
"""

import pandas as pd
from typing import List, Dict, Optional
import logging
from data_engine.yfinance_fetcher import YFinanceFetcher
from core.database import get_supabase_client
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataCoordinator:
    """
    Coordinates data flow between yfinance and Supabase.
    Implements the "Smart Retrieval" logic.
    
    This is the SINGLE SOURCE OF TRUTH for fetching and caching market data.
    All other modules (forecasting, optimization) should consume data through
    the API layer, not by calling these methods directly.
    """
    
    def __init__(self):
        """Initialize the coordinator with fetcher and database client."""
        self.fetcher = YFinanceFetcher()
        self.supabase = get_supabase_client()

    def sync_asset(self, symbol: str, asset_type: str, interval: str = "1wk"):
        """
        Synchronizes an asset's historical data from yfinance to Supabase.
        
        This method:
        1. Ensures the asset exists in the 'assets' table (creates if not)
        2. Fetches full history from yfinance
        3. Upserts all records to 'historical_prices' table
        
        Args:
            symbol: The ticker symbol (e.g., 'AAPL', 'BTC-USD')
            asset_type: Either 'stock' or 'crypto'
            interval: Data interval - currently only '1wk' is supported
            
        Note:
            This performs a FULL historical sync. For production optimization,
            implement incremental sync using the 'last_updated' field.
        """
        # Step 1: Ensure asset exists in database
        asset_id = self._get_or_create_asset(symbol, asset_type)
        if not asset_id:
            logger.error(f"Could not resolve asset_id for {symbol}")
            return

        # Step 2: Fetch historical data from yfinance
        # TODO: Optimize to only pull since last_updated
        logger.info(f"Fetching {interval} history for {symbol}...")
        df = self.fetcher.fetch_history(symbol, interval=interval)
        
        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return

        # Step 3: Transform data for Supabase format
        records = []
        for _, row in df.iterrows():
            records.append({
                "asset_id": asset_id,
                "timestamp": row['timestamp'].isoformat(),
                "open_price": float(row['open']),
                "high_price": float(row['high']),
                "low_price": float(row['low']),
                "close_price": float(row['close']),
                "volume": int(row['volume']) if 'volume' in row else 0
            })

        # Step 4: Upsert into Supabase
        # The UNIQUE constraint (asset_id, timestamp) handles duplicates
        logger.info(f"Upserting {len(records)} records into Supabase...")
        try:
            res = self.supabase.table("historical_prices").upsert(
                records, 
                on_conflict="asset_id,timestamp"
            ).execute()
            
            # Update the last_updated timestamp on the asset
            self.supabase.table("assets").update({
                "last_updated": datetime.now().isoformat()
            }).eq("id", asset_id).execute()
            
            logger.info(f"Successfully synced {symbol}")
        except Exception as e:
            logger.error(f"Error upserting data: {e}")

    def _get_or_create_asset(self, symbol: str, asset_type: str) -> Optional[str]:
        """
        Returns the UUID of the asset, creating it if it doesn't exist.
        
        This is a private method - do not call directly from outside this module.
        """
        try:
            # Check if asset already exists
            res = self.supabase.table("assets").select("id").eq("symbol", symbol).execute()
            if res.data:
                return res.data[0]['id']
            
            # Create new asset record
            new_asset = {
                "symbol": symbol,
                "asset_type": asset_type,
                "name": symbol  # Default name to symbol; can be updated later
            }
            res = self.supabase.table("assets").insert(new_asset).execute()
            if res.data:
                return res.data[0]['id']
        except Exception as e:
            logger.error(f"Database error in _get_or_create_asset: {e}")
        return None


# =============================================================================
# FOR TESTING ONLY - Do not use in production
# =============================================================================
if __name__ == "__main__":
    # Simple test script
    # coord = DataCoordinator()
    # coord.sync_asset("AAPL", "stock", "1wk")
    pass

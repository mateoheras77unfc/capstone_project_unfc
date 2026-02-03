import pandas as pd
from typing import List, Dict, Optional
import logging
from .yfinance_fetcher import YFinanceFetcher
from ..core.database import get_supabase_client
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataCoordinator:
    """
    Coordinates data flow between yfinance and Supabase.
    Implements the "Smart Retrieval" logic.
    """
    
    def __init__(self):
        self.fetcher = YFinanceFetcher()
        self.supabase = get_supabase_client()

    def sync_asset(self, symbol: str, asset_type: str, interval: str = "1wk"):
        """
        Synchronizes an asset's historical data.
        1. Ensures asset exists in 'assets' table.
        2. Checks for missing data.
        3. Fetches and saves to 'historical_prices'.
        """
        # 1. Ensure asset exists
        asset_id = self._get_or_create_asset(symbol, asset_type)
        if not asset_id:
            logger.error(f"Could not resolve asset_id for {symbol}")
            return

        # 2. Fetch data (For MVP/Phase 1, we pull 'max' and upsert)
        # TODO: Optimize to only pull since last_updated
        logger.info(f"Fetching {interval} history for {symbol}...")
        df = self.fetcher.fetch_history(symbol, interval=interval)
        
        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return

        # 3. Prepare for Supabase (weekly data only, no interval column)
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

        # 4. Upsert into historical_prices
        # Supabase Python client uses .upsert() which requires the 
        # unique constraint (asset_id, timestamp) to be hit.
        logger.info(f"Upserting {len(records)} records into Supabase...")
        try:
            res = self.supabase.table("historical_prices").upsert(
                records, 
                on_conflict="asset_id,timestamp"
            ).execute()
            
            # Update last_updated in assets table
            self.supabase.table("assets").update({
                "last_updated": datetime.now().isoformat()
            }).eq("id", asset_id).execute()
            
            logger.info(f"Successfully synced {symbol}")
        except Exception as e:
            logger.error(f"Error upserting data: {e}")

    def _get_or_create_asset(self, symbol: str, asset_type: str) -> Optional[str]:
        """Returns the UUID of the asset, creating it if it doesn't exist."""
        try:
            res = self.supabase.table("assets").select("id").eq("symbol", symbol).execute()
            if res.data:
                return res.data[0]['id']
            
            # Create it
            new_asset = {
                "symbol": symbol,
                "asset_type": asset_type,
                "name": symbol # Defaulting name to symbol for now
            }
            res = self.supabase.table("assets").insert(new_asset).execute()
            if res.data:
                return res.data[0]['id']
        except Exception as e:
            logger.error(f"Database error in _get_or_create_asset: {e}")
        return None

if __name__ == "__main__":
    from datetime import datetime # Needed for update
    # Simple test script
    # coord = DataCoordinator()
    # coord.sync_asset("AAPL", "stock", "1wk")
    pass

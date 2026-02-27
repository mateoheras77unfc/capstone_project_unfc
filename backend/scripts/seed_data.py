"""
Seed script to populate Supabase with some initial test data for Phase 2 validation.
"""
import sys
import os

# Add the parent directory to sys.path so we can import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data_engine.coordinator import DataCoordinator
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed():
    coord = DataCoordinator()
    
    test_assets = [
        {"symbol": "AAPL", "type": "stock"},
        {"symbol": "BTC-USD", "type": "crypto"},
        {"symbol": "MSFT", "type": "stock"},
        {"symbol": "ETH-USD", "type": "crypto"}
    ]
    
    for asset in test_assets:
        logger.info(f"Seeding {asset['symbol']}...")
        try:
            # Sync daily data — single source of truth; the frontend
            # aggregates to weekly/monthly views on the client side.
            coord.sync_asset(asset['symbol'], asset['type'], interval="1d")
        except Exception as e:
            logger.error(f"Failed to seed {asset['symbol']}: {e}")

if __name__ == "__main__":
    seed()

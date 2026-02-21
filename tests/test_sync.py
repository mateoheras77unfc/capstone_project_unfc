import os
import sys

# Ensure backend is in the path
sys.path.append(os.path.join(os.getcwd()))

from backend.data_engine.data_coordinator import DataCoordinator
import logging

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO)

def test_sync():
    """
    Test script to sync Apple and Bitcoin data.
    """
    coordinator = DataCoordinator()
    
    # Sync Apple Weekly
    print("--- Syncing AAPL (Weekly) ---")
    coordinator.sync_asset("AAPL", "stock", interval="1wk")
    
    # Sync Bitcoin Monthly
    print("\n--- Syncing BTC-USD (Monthly) ---")
    coordinator.sync_asset("BTC-USD", "crypto", interval="1mo")

if __name__ == "__main__":
    test_sync()

"""
Download and save fixed 5-year daily pool data, VIX, and Fear & Greed so that
experiments use the same input every run. Run once from this directory:

    python download_fixed_pool_data.py

Output: artifacts/pool_data_5y_fixed.parquet, artifacts/vix_5y_fixed.parquet,
        artifacts/fear_greed_5y_fixed.parquet
"""
from _pool_common import (
    download_and_save_fixed_pool_data,
    POOL_DATA_FIXED_PATH,
    VIX_DATA_FIXED_PATH,
    FEAR_GREED_FIXED_PATH,
    FIXED_START_DATE,
    FIXED_END_DATE,
)

if __name__ == "__main__":
    df = download_and_save_fixed_pool_data()
    print(f"Fixed window: {FIXED_START_DATE} to {FIXED_END_DATE}")
    print(f"Saved pool data: {POOL_DATA_FIXED_PATH} ({len(df)} rows)")
    if VIX_DATA_FIXED_PATH.exists():
        print(f"Saved VIX data: {VIX_DATA_FIXED_PATH}")
    if FEAR_GREED_FIXED_PATH.exists():
        print(f"Saved Fear & Greed data: {FEAR_GREED_FIXED_PATH}")

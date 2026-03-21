"""
Sync the 8 crypto tickers into Supabase historical_prices.
Run from the backend/ directory:
    python scripts/sync_crypto.py
"""
import sys
import os
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_engine.coordinator import DataCoordinator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CRYPTO_TICKERS = [
    "BTC-USD",
    "ETH-USD",
    "BNB-USD",
    "SOL-USD",
    "XRP-USD",
    "ADA-USD",
    "AVAX-USD",
    "DOGE-USD",
]


def main() -> None:
    coord = DataCoordinator()
    success, failed = [], []

    for ticker in CRYPTO_TICKERS:
        logger.info("Syncing %s ...", ticker)
        try:
            rows = coord.sync_asset(ticker, "crypto", interval="1d")
            logger.info("%s — %d rows synced", ticker, rows)
            success.append(ticker)
        except Exception as exc:
            logger.error("FAILED %s: %s", ticker, exc)
            failed.append(ticker)

    print("\n── Sync complete ──────────────────")
    print(f"✅  Success ({len(success)}): {', '.join(success)}")
    if failed:
        print(f"❌  Failed  ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    main()

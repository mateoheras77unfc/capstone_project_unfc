"""
data_engine/fetcher.py
───────────────────────
Thin wrapper around ``yfinance`` — the ONLY place in the codebase that
calls Yahoo Finance directly.

All other modules must go through :class:`DataCoordinator` or the REST
API, not import this class directly.
"""

import logging
from typing import Literal

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Type alias for the supported intervals.
Interval = Literal["1d", "1wk", "1mo"]


class YFinanceFetcher:
    """
    Fetch OHLCV data from Yahoo Finance for a single ticker.

    Supported intervals
    -------------------
    - ``"1d"``  — Daily data (primary, used throughout the application).
    - ``"1wk"`` — Weekly data.
    - ``"1mo"`` — Monthly data.

    Example:
        >>> fetcher = YFinanceFetcher()
        >>> df = fetcher.fetch_history("AAPL", interval="1d")
        >>> df.columns
        Index(['timestamp', 'open', 'high', 'low', 'close', 'volume'], ...)
    """

    # ── public API ────────────────────────────────────────────────────────

    def fetch_history(
        self,
        symbol: str,
        interval: Interval = "1d",
        period: str = "max",
    ) -> pd.DataFrame:
        """
        Download full OHLCV history for ``symbol``.

        Args:
            symbol:   Ticker (e.g. ``"AAPL"``, ``"BTC-USD"``, ``"^GSPC"``).
            interval: Aggregation interval — ``"1d"``, ``"1wk"`` or ``"1mo"``.
            period:   How far back to fetch (``"max"``, ``"5y"``, ``"2y"``…).

        Returns:
            DataFrame with columns: ``timestamp``, ``open``, ``high``,
            ``low``, ``close``, ``volume``.  Empty DataFrame on failure.

        Raises:
            ValueError: If ``interval`` is not ``"1d"``, ``"1wk"`` or ``"1mo"``.
        """
        if interval not in ("1d", "1wk", "1mo"):
            raise ValueError(
                f"Unsupported interval '{interval}'. Use '1d', '1wk' or '1mo'."
            )

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(interval=interval, period=period)
        except Exception:
            logger.exception("yfinance fetch failed for %s", symbol)
            return pd.DataFrame()

        if df.empty:
            logger.warning("yfinance returned empty data for %s", symbol)
            return df

        # Reset index so Date becomes a regular column.
        df = df.reset_index()
        # Normalise column names: "Adj Close" → "adj_close", etc.
        df.columns = [col.lower().replace(" ", "_") for col in df.columns]
        # Rename 'date' → 'timestamp' to match the DB schema.
        if "date" in df.columns:
            df = df.rename(columns={"date": "timestamp"})

        logger.info("Fetched %d rows for %s (%s)", len(df), symbol, interval)
        return df

    def get_latest_price(self, symbol: str) -> float:
        """
        Return the most recent closing price for ``symbol``.

        Used for quick staleness checks; not part of the caching workflow.

        Args:
            symbol: Ticker symbol.

        Returns:
            Latest close price, or ``0.0`` if unavailable.
        """
        try:
            data = yf.Ticker(symbol).history(period="1d")
            if not data.empty:
                return float(data["Close"].iloc[-1])
        except Exception:
            logger.exception("Could not fetch latest price for %s", symbol)
        return 0.0

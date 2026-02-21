"""
data_engine/coordinator.py
───────────────────────────
Smart-cache data coordinator — the SINGLE entry point for all market data.

Workflow (per sync call)
------------------------
1. Ensure the asset exists in ``assets`` table (create if missing).
2. Fetch full OHLCV history from Yahoo Finance via :class:`YFinanceFetcher`.
3. Upsert records into ``historical_prices``; the DB unique constraint
   (asset_id, timestamp) handles deduplication automatically.
4. Stamp ``assets.last_updated`` so staleness checks are fast.

Downstream consumers (forecasting, optimisation) MUST read data only
through the REST API (``GET /api/v1/prices/{symbol}``) — not by importing
this module directly.  This preserves the isolation boundary and lets the
data layer evolve independently.
"""

import logging
from datetime import datetime

from core.database import get_supabase_client
from data_engine.fetcher import YFinanceFetcher

logger = logging.getLogger(__name__)


class DataCoordinator:
    """
    Orchestrates fetching and caching of market data.

    Args:
        None — dependencies are resolved lazily so tests can patch them.

    Example:
        >>> coordinator = DataCoordinator()
        >>> coordinator.sync_asset("AAPL", "stock", interval="1wk")
    """

    def __init__(self) -> None:
        self._fetcher = YFinanceFetcher()

    # ── public API ────────────────────────────────────────────────────────

    def sync_asset(
        self, symbol: str, asset_type: str, interval: str = "1wk"
    ) -> int:
        """
        Fetch and cache historical OHLCV data for ``symbol``.

        Args:
            symbol:     Ticker (e.g. ``"AAPL"``, ``"BTC-USD"``).
            asset_type: One of ``"stock"``, ``"crypto"``, or ``"index"``.
            interval:   yfinance interval — ``"1wk"`` (default) or ``"1mo"``.

        Returns:
            Number of rows upserted.

        Raises:
            RuntimeError: If the asset row cannot be resolved or created.
            ValueError:   If yfinance returns no data for the symbol.
            Exception:    Propagates Supabase upsert errors.
        """
        db = get_supabase_client()

        # 1. Resolve (or create) the asset row and get its UUID.
        asset_id = self._get_or_create_asset(db, symbol, asset_type)
        # _get_or_create_asset raises on failure; None should never happen,
        # but guard defensively.
        if not asset_id:
            raise RuntimeError(f"Could not resolve asset_id for {symbol}")

        # 2. Pull history from yfinance.
        logger.info("Fetching %s history for %s…", interval, symbol)
        df = self._fetcher.fetch_history(symbol, interval=interval)

        if df.empty:
            raise ValueError(
                f"yfinance returned no data for '{symbol}'. "
                "Check the symbol spelling and try again."
            )

        # 3. Transform to the Supabase schema.
        records = [
            {
                "asset_id": asset_id,
                "timestamp": row["timestamp"].isoformat(),
                "open_price": float(row["open"]),
                "high_price": float(row["high"]),
                "low_price": float(row["low"]),
                "close_price": float(row["close"]),
                "volume": int(row.get("volume", 0)),
            }
            for _, row in df.iterrows()
        ]

        # 4. Upsert (idempotent — duplicate timestamps are ignored).
        logger.info("Upserting %d records for %s…", len(records), symbol)
        try:
            db.table("historical_prices").upsert(
                records, on_conflict="asset_id,timestamp"
            ).execute()

            db.table("assets").update(
                {"last_updated": datetime.utcnow().isoformat()}
            ).eq("id", asset_id).execute()

            logger.info("Sync complete for %s (%d rows)", symbol, len(records))
            return len(records)
        except Exception:
            logger.exception("Upsert failed for %s", symbol)
            raise

    # ── private helpers ───────────────────────────────────────────────────

    def _get_or_create_asset(
        self, db, symbol: str, asset_type: str
    ) -> str:
        """
        Return the UUID of the asset row, creating it if necessary.

        Args:
            db:         Supabase client.
            symbol:     Ticker symbol.
            asset_type: Asset category.

        Returns:
            UUID string.

        Raises:
            RuntimeError: If the DB lookup or insert fails.
        """
        try:
            # Use .limit(1) instead of .single() — .single() raises an
            # APIError when 0 rows are returned, masking "not found" as an
            # exception and causing the whole sync to abort silently.
            res = (
                db.table("assets")
                .select("id")
                .eq("symbol", symbol)
                .limit(1)
                .execute()
            )
            if res.data:
                return res.data[0]["id"]

            # Not found — insert a new row.
            insert_res = (
                db.table("assets")
                .insert(
                    {
                        "symbol": symbol,
                        "asset_type": asset_type,
                        "name": symbol,
                        "currency": "USD",
                    }
                )
                .execute()
            )
            new_id: str = insert_res.data[0]["id"]
            logger.info("Created asset record for %s (id=%s)", symbol, new_id)
            return new_id

        except Exception as exc:
            logger.exception("DB error while resolving asset for %s", symbol)
            raise RuntimeError(
                f"Failed to resolve/create asset '{symbol}' in Supabase. "
                "Check SUPABASE_URL, SUPABASE_KEY, and DB permissions."
            ) from exc

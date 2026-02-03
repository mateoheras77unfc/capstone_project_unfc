# Phase 1: Foundation - Data Engine & Supabase Setup

## Purpose
To establish a persistent and efficient data layer that bridges external market data (via `yfinance`) with an internal database (`Supabase`). This phase focuses on the "Smart Retrieval" logic at a **Weekly** and **Monthly** scale.

## Key Objectives
1.  **Database Schema Design:** Create tables in Supabase for `assets` (metadata) and `historical_prices` (time-series data).
2.  **Smart Fetcher Utility:** Develop a Python script/service using `yfinance` that:
    *   Checks Supabase for existing data first.
    *   Fetches missing data using `interval='1wk'` or `interval='1mo'`.
    *   Upserts new data into the database.
3.  **Authentication:** Set up basic Supabase client connectivity.

## Technical Requirements
*   **Database Migration:** Use `supabase migration up` to apply the schema.
*   **Interval Handling:** The system MUST support switching between weekly and monthly data pulls.
*   **Stale Data Check:** Logic to identify if the last record in the database aligns with the most recent full week/month.
*   **Rate Limiting:** Ensure calls to `yfinance` are handled gracefully to avoid blocking.

## Verification / Tests
*   **Migration Test:** Verify `supabase migration up` completes without errors and tables exist.
*   **API Connection Test:** Verify that `yfinance` can retrieve 5 years of weekly data for 'IBM'.
*   **Persistence Test:** Fetch data for 'BTC-USD' (Weekly), save to Supabase, and confirm the row count matches the expected timeframe.
*   **Duplicate Prevention:** Run the fetcher twice for the same asset and verify no duplicate primary keys (date + symbol + interval) are created.

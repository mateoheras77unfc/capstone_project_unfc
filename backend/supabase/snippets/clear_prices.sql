-- clear_prices.sql
-- Removes all historical price rows while preserving the table schema.
-- Run this when migrating from weekly to daily data granularity so that
-- no mixed-interval rows coexist in the same table.
--
-- Usage (Supabase dashboard → SQL Editor):
--   Run this script, then re-sync assets via POST /api/v1/assets/sync/{symbol}

TRUNCATE TABLE historical_prices;

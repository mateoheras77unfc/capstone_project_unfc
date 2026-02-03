-- Migration: Phase 1 Foundations
-- Description: Sets up the assets and historical_prices tables for Weekly tracking.

-- 1. Assets Metadata Table
CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT UNIQUE NOT NULL, -- e.g., 'AAPL', 'BTC-USD'
    name TEXT,
    asset_type TEXT CHECK (asset_type IN ('stock', 'crypto', 'index')),
    currency TEXT DEFAULT 'USD',
    last_updated TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Historical Prices Table (Weekly data only)
CREATE TABLE IF NOT EXISTS historical_prices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    open_price DECIMAL(20, 6),
    high_price DECIMAL(20, 6),
    low_price DECIMAL(20, 6),
    close_price DECIMAL(20, 6) NOT NULL,
    volume BIGINT,
    
    -- Ensure unique entries for an asset at a specific time
    UNIQUE(asset_id, timestamp)
);

-- Indexing for performance
CREATE INDEX IF NOT EXISTS idx_prices_asset_timestamp ON historical_prices(asset_id, timestamp DESC);


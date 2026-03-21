-- Migration: Model Training Infrastructure
-- Description: Tables for tracking assembly model training jobs and metrics.

-- 1. Model Training Jobs — tracks background training status per job
CREATE TABLE IF NOT EXISTS model_training_jobs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status       TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed'))
                 DEFAULT 'pending',
    tickers      TEXT[] NOT NULL,                  -- e.g. ['BTC-USD', 'ETH-USD', ...]
    started_at   TIMESTAMPTZ DEFAULT NOW(),
    finished_at  TIMESTAMPTZ,
    error        TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Model Metrics — stores MAE/RMSE/MAPE per symbol after training
CREATE TABLE IF NOT EXISTS model_metrics (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol       TEXT NOT NULL,                    -- e.g. 'BTC-USD'
    model        TEXT NOT NULL,                    -- 'assembly' or 'chronos'
    mae          DECIMAL(20, 6) NOT NULL,
    rmse         DECIMAL(20, 6) NOT NULL,
    mape         DECIMAL(20, 6) NOT NULL,          -- percentage, e.g. 1.8
    trained_at   TIMESTAMPTZ DEFAULT NOW(),
    job_id       UUID REFERENCES model_training_jobs(id) ON DELETE SET NULL,

    -- One metrics row per symbol+model (upsert on retrain)
    UNIQUE(symbol, model)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_training_jobs_status  ON model_training_jobs(status);
CREATE INDEX IF NOT EXISTS idx_model_metrics_symbol  ON model_metrics(symbol);

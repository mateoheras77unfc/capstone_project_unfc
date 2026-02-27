"""
Shared config, data loading, backtest, and metrics for experiments-pool.
All models use the same TEST_SIZE and walk-forward one-step backtest for fair comparison.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from math import sqrt

# ─── Config ─────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

# Ticker pool: crypto, stocks, ETF
TICKERS = [
    "BTC-USD", "ETH-USD",   # crypto
    "NVDA", "AAPL", "MSFT", # stocks
    "SPY", "QQQ",           # ETF
]
INTERVAL = "1wk"
PERIOD = "5y"

# Same backtest for all models
TEST_SIZE = 30
MIN_TRAIN_BASELINE = 20   # EWM span
MIN_TRAIN_PROPHET = 10
MIN_CONTEXT_CHRONOS = 64


def load_pool_data(tickers=None, period=PERIOD, interval=INTERVAL, with_vix=False):
    """Download yfinance for each ticker, stack into one DataFrame with columns: timestamp, symbol, close[, vix]."""
    tickers = tickers or TICKERS
    rows = []
    for sym in tickers:
        try:
            df = yf.download(sym, period=period, interval=interval, progress=False, auto_adjust=False, multi_level_index=False)
            if df.empty or len(df) < MIN_CONTEXT_CHRONOS:
                continue
            df = df.reset_index()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df = df.rename(columns={"Date": "timestamp", "Close": "close"})
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["symbol"] = sym
            df = df[["timestamp", "symbol", "close"]].dropna()
            rows.append(df)
        except Exception as e:
            print(f"Skip {sym}: {e}")
    if not rows:
        raise ValueError("No data loaded for any ticker.")
    out = pd.concat(rows, ignore_index=True)
    out = out.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    if with_vix:
        vix_df = yf.download("^VIX", period=period, interval=interval, progress=False, auto_adjust=False, multi_level_index=False)
        if not vix_df.empty:
            vix_df = vix_df.reset_index()
            if isinstance(vix_df.columns, pd.MultiIndex):
                vix_df.columns = [c[0] if isinstance(c, tuple) else c for c in vix_df.columns]
            vix_df = vix_df.rename(columns={"Date": "timestamp", "Close": "vix"})
            vix_df["timestamp"] = pd.to_datetime(vix_df["timestamp"])
            vix_df = vix_df[["timestamp", "vix"]].dropna()
            if isinstance(out.columns, pd.MultiIndex):
                out.columns = [c[0] if isinstance(c, tuple) else c for c in out.columns]
            out = out.merge(vix_df, on="timestamp", how="left")
            out["vix"] = out["vix"].ffill().bfill()
    return out


def backtest_one_step(prices_full: pd.Series, test_size: int, model_factory, min_train: int):
    """
    Walk-forward one-step backtest: for each test index i, train on [0:i], predict i.
    Returns DataFrame with columns timestamp, y_true, y_pred.
    """
    preds = []
    split_idx = len(prices_full) - test_size
    for i in range(split_idx, len(prices_full)):
        train = prices_full.iloc[:i]
        actual = float(prices_full.iloc[i])
        ts = prices_full.index[i]
        if len(train) < min_train:
            continue
        try:
            model = model_factory()
            model.fit(train)
            fc = model.forecast(periods=1)
            if fc is None:
                continue
            point = fc.get("point_forecast") if isinstance(fc, dict) else None
            if not point or len(point) < 1:
                continue
            yhat = float(point[0])
        except (TypeError, KeyError, IndexError, ValueError) as e:
            continue
        preds.append({"timestamp": ts, "y_true": actual, "y_pred": yhat})
    return pd.DataFrame(preds)


def compute_metrics(pred_df):
    """MAE, RMSE, MAPE (same formula for all models)."""
    y = pred_df["y_true"].to_numpy()
    yhat = pred_df["y_pred"].to_numpy()
    mae = np.mean(np.abs(y - yhat))
    rmse = sqrt(np.mean((y - yhat) ** 2))
    mape = np.mean(np.abs((y - yhat) / np.where(y != 0, y, 1e-8))) * 100
    return {"MAE": float(mae), "RMSE": float(rmse), "MAPE_%": float(mape)}


def metrics_to_parquet(metrics_rows, path):
    """Save list of dicts (model, symbol, MAE, RMSE, MAPE_%) to parquet."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(metrics_rows)
    df.to_parquet(path, index=False)

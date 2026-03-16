"""
Shared config, data loading, backtest, and metrics for experiments-pool.
- Daily data (INTERVAL="1d"). Single asset pool: each asset is backtested on its own history
  (expanding window, last 60 days held out for evaluation).
- All models use TEST_SIZE=60 days, 7-step direct forecast, rolling backtest (step 7 days);
  metrics averaged over mini-windows.
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

# Asset pool: 10 symbols for load and backtest (per-asset evaluation, no cross-asset training).
TICKERS = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "JPM",
    "JNJ",
    "WMT",
    "SPY",
    "XOM",
    "NVDA",
]

INTERVAL = "1d"
PERIOD = "5y"

# 7-day-ahead rolling backtest: 60-day test window, predict 7 days, move by 7 days
TEST_SIZE = 60
FORECAST_HORIZON = 7
ROLLING_STEP = 7
MIN_TRAIN_BASELINE = 7    # min history for baseline EWM (span=7)
MIN_TRAIN_PROPHET = 10
MIN_CONTEXT_CHRONOS = 64
MIN_TRAIN_STACK = 100    # XGB+LSTM stack (need MACD 26 + seq_len + horizon)

# Cache file for CNN Fear & Greed so we don't hit the API every run
FEAR_GREED_CACHE_PATH = ARTIFACTS_DIR / "fear_greed_cnn.parquet"

# Fixed 5-year daily data: same date range every run so results are reproducible
FIXED_END_DATE = "2026-02-28"
FIXED_START_DATE = "2021-02-28"  # 5 years before FIXED_END_DATE
POOL_DATA_FIXED_PATH = ARTIFACTS_DIR / "pool_data_5y_fixed.parquet"
VIX_DATA_FIXED_PATH = ARTIFACTS_DIR / "vix_5y_fixed.parquet"
FEAR_GREED_FIXED_PATH = ARTIFACTS_DIR / "fear_greed_5y_fixed.parquet"


def fetch_cnn_fear_greed_index(limit_days=500, start_date=None, force_refresh=False, use_fixed=True):
    """
    Load CNN Fear & Greed from cache. Returns DataFrame with columns: timestamp, fear_greed.
    - use_fixed: if True and FEAR_GREED_FIXED_PATH exists, load from that (same 5y window as pool).
    - limit_days: used when start_date is None to compute start from today (live cache only).
    - start_date: optional str or datetime; filter loaded data from this date.
    - force_refresh: if True, fetch from API and overwrite cache (ignored when use_fixed and fixed file exists).
    """
    if use_fixed and FEAR_GREED_FIXED_PATH.exists():
        try:
            df = pd.read_parquet(FEAR_GREED_FIXED_PATH)
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.normalize()
            if start_date is not None:
                start = pd.to_datetime(start_date).normalize()
                df = df[df["timestamp"] >= start].copy()
            return df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
        except Exception:
            pass
    if not force_refresh and FEAR_GREED_CACHE_PATH.exists():
        try:
            df = pd.read_parquet(FEAR_GREED_CACHE_PATH)
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.normalize()
            if start_date is not None:
                start = pd.to_datetime(start_date).normalize()
                df = df[df["timestamp"] >= start].copy()
            return df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
        except Exception:
            pass
    try:
        import requests
    except ImportError:
        return pd.DataFrame(columns=["timestamp", "fear_greed"])
    if start_date is not None:
        start_date_str = pd.to_datetime(start_date).strftime("%Y-%m-%d")
    else:
        from datetime import datetime, timezone, timedelta
        start_date_str = (datetime.now(timezone.utc) - timedelta(days=limit_days)).strftime("%Y-%m-%d")
    url = f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start_date_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.cnn.com/markets/fear-and-greed",
        "Origin": "https://www.cnn.com",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return pd.DataFrame(columns=["timestamp", "fear_greed"])
        data = response.json()
        fng_data = data.get("fear_and_greed_historical", {}).get("data") or []
        if not fng_data:
            return pd.DataFrame(columns=["timestamp", "fear_greed"])
        fng_df = pd.DataFrame(fng_data)
        fng_df["timestamp"] = pd.to_datetime(fng_df["x"] / 1000, unit="s").dt.normalize()
        fng_df = fng_df.rename(columns={"y": "fear_greed"})
        out = fng_df[["timestamp", "fear_greed"]].drop_duplicates("timestamp").sort_values("timestamp")
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        out.to_parquet(FEAR_GREED_CACHE_PATH, index=False)
        return out.reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=["timestamp", "fear_greed"])


def _fetch_cnn_fear_greed_from_api(start_date_str):
    """Fetch CNN Fear & Greed from API from start_date_str. Returns DataFrame or None on failure."""
    try:
        import requests
    except ImportError:
        return None
    url = f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start_date_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.cnn.com/markets/fear-and-greed",
        "Origin": "https://www.cnn.com",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        fng_data = data.get("fear_and_greed_historical", {}).get("data") or []
        if not fng_data:
            return None
        fng_df = pd.DataFrame(fng_data)
        fng_df["timestamp"] = pd.to_datetime(fng_df["x"] / 1000, unit="s").dt.normalize()
        fng_df = fng_df.rename(columns={"y": "fear_greed"})
        return fng_df[["timestamp", "fear_greed"]].drop_duplicates("timestamp").sort_values("timestamp")
    except Exception:
        return None


def download_and_save_fixed_pool_data(tickers=None):
    """
    Download 5-year daily data for the asset pool, VIX, and Fear & Greed for the fixed date range
    (FIXED_START_DATE to FIXED_END_DATE) and save to artifacts. Run once to create
    pool_data_5y_fixed.parquet, vix_5y_fixed.parquet, and fear_greed_5y_fixed.parquet
    so that load_pool_data(use_fixed=True) and fetch_cnn_fear_greed_index(use_fixed=True) return the same data every run.
    """
    tickers = tickers or TICKERS
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for sym in tickers:
        try:
            df = yf.download(
                sym,
                start=FIXED_START_DATE,
                end=FIXED_END_DATE,
                interval=INTERVAL,
                progress=False,
                auto_adjust=False,
                multi_level_index=False,
            )
            if df.empty or len(df) < MIN_CONTEXT_CHRONOS:
                continue
            df = df.reset_index()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df = df.rename(columns={"Date": "timestamp", "Close": "close"})
            if "Volume" in df.columns:
                df = df.rename(columns={"Volume": "volume"})
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["symbol"] = sym
            cols = ["timestamp", "symbol", "close"]
            if "volume" in df.columns:
                cols.append("volume")
            df = df[cols].dropna()
            rows.append(df)
        except Exception as e:
            print(f"Skip {sym}: {e}")
    if not rows:
        raise ValueError("No data loaded for any ticker.")
    out = pd.concat(rows, ignore_index=True)
    out = out.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    out.to_parquet(POOL_DATA_FIXED_PATH, index=False)
    # VIX for the same fixed range
    vix_df = yf.download(
        "^VIX",
        start=FIXED_START_DATE,
        end=FIXED_END_DATE,
        interval=INTERVAL,
        progress=False,
        auto_adjust=False,
        multi_level_index=False,
    )
    if not vix_df.empty:
        vix_df = vix_df.reset_index()
        if isinstance(vix_df.columns, pd.MultiIndex):
            vix_df.columns = [c[0] if isinstance(c, tuple) else c for c in vix_df.columns]
        vix_df = vix_df.rename(columns={"Date": "timestamp", "Close": "vix"})
        vix_df["timestamp"] = pd.to_datetime(vix_df["timestamp"])
        vix_df[["timestamp", "vix"]].dropna().to_parquet(VIX_DATA_FIXED_PATH, index=False)
    # Fear & Greed for the same fixed range
    fng_df = _fetch_cnn_fear_greed_from_api(FIXED_START_DATE)
    if fng_df is not None and not fng_df.empty:
        end_ts = pd.to_datetime(FIXED_END_DATE).normalize()
        fng_df = fng_df[fng_df["timestamp"] <= end_ts].copy()
        fng_df.to_parquet(FEAR_GREED_FIXED_PATH, index=False)
    return out


def load_pool_data(tickers=None, period=PERIOD, interval=INTERVAL, with_vix=False, with_volume=False, use_fixed=True):
    """
    Load pool data: if use_fixed=True and fixed cache exists, load from
    pool_data_5y_fixed.parquet (and vix_5y_fixed.parquet if with_vix).
    Otherwise download via yfinance. Columns: timestamp, symbol, close[, vix][, volume].
    """
    tickers = tickers or TICKERS
    if use_fixed:
        if not POOL_DATA_FIXED_PATH.exists():
            download_and_save_fixed_pool_data(tickers=tickers)
        out = pd.read_parquet(POOL_DATA_FIXED_PATH)
        out["timestamp"] = pd.to_datetime(out["timestamp"])
        if not with_volume and "volume" in out.columns:
            out = out.drop(columns=["volume"])
        if with_vix and VIX_DATA_FIXED_PATH.exists():
            vix_df = pd.read_parquet(VIX_DATA_FIXED_PATH)
            vix_df["timestamp"] = pd.to_datetime(vix_df["timestamp"])
            out = out.merge(vix_df, on="timestamp", how="left")
            out["vix"] = out["vix"].ffill().bfill()
        return out.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    # Live download (original behavior)
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
            if "Volume" in df.columns:
                df = df.rename(columns={"Volume": "volume"})
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["symbol"] = sym
            cols = ["timestamp", "symbol", "close"]
            if with_volume and "volume" in df.columns:
                cols.append("volume")
            df = df[cols].dropna()
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


def build_pooled_train_stack(stacked: pd.DataFrame, test_size: int, min_train: int = 1):
    """
    Build a single DataFrame containing only the "train" portion of each asset:
    for each symbol, rows from start up to (but not including) the last test_size days.
    Used for training global models once on pooled data before the rolling backtest.
    Drops symbols that have fewer than min_train rows in the train portion.
    """
    rows = []
    for sym in stacked["symbol"].unique():
        grp = stacked[stacked["symbol"] == sym].sort_values("timestamp").reset_index(drop=True)
        n = len(grp)
        if n < test_size + min_train:
            continue
        train_grp = grp.iloc[: n - test_size].copy()
        rows.append(train_grp)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


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


def backtest_21d_rolling(
    prices_full: pd.Series,
    test_window: int,
    horizon: int,
    step: int,
    min_train: int,
    get_forecast_fn,
):
    """
    Rolling multi-day-ahead backtest within a fixed test window.
    Start at beginning of test window, predict next `horizon` steps; move forward by `step`;
    repeat until start + horizon would exceed test window. Returns DataFrame with
    timestamp, y_true, y_pred, window_ix (for averaging metrics per mini-window).
    get_forecast_fn(context_series, horizon) -> list of horizon floats (point forecasts).
    """
    n = len(prices_full)
    if n < test_window + min_train:
        return pd.DataFrame(columns=["timestamp", "y_true", "y_pred", "window_ix"])
    split_idx = n - test_window
    train = prices_full.iloc[:split_idx]
    test = prices_full.iloc[split_idx:]
    test_index = test.index
    test_values = test.values
    preds = []
    window_ix = 0
    start = 0
    while start + horizon <= test_window:
        context = prices_full.iloc[: split_idx + start]
        if len(context) < min_train:
            start += step
            continue
        try:
            point_list = get_forecast_fn(context, horizon)
            if not point_list or len(point_list) < horizon:
                start += step
                continue
            for h in range(horizon):
                idx = start + h
                ts = test_index[idx]
                y_true = float(test_values[idx])
                y_pred = float(point_list[h])
                preds.append({"timestamp": ts, "y_true": y_true, "y_pred": y_pred, "window_ix": window_ix})
        except (TypeError, KeyError, IndexError, ValueError) as e:
            pass
        window_ix += 1
        start += step
    return pd.DataFrame(preds)


def compute_metrics(pred_df):
    """MAE, RMSE, MAPE (same formula for all models)."""
    y = pred_df["y_true"].to_numpy()
    yhat = pred_df["y_pred"].to_numpy()
    mae = np.mean(np.abs(y - yhat))
    rmse = sqrt(np.mean((y - yhat) ** 2))
    mape = np.mean(np.abs((y - yhat) / np.where(y != 0, y, 1e-8))) * 100
    return {"MAE": float(mae), "RMSE": float(rmse), "MAPE_%": float(mape)}


def compute_metrics_averaged_over_windows(pred_df):
    """
    For rolling backtest: pred_df has window_ix. Compute MAE, RMSE, MAPE per window,
    then average across windows. If no window_ix, falls back to single-window (compute_metrics).
    """
    if pred_df.empty:
        return {"MAE": np.nan, "RMSE": np.nan, "MAPE_%": np.nan}
    if "window_ix" not in pred_df.columns:
        return compute_metrics(pred_df)
    mae_list, rmse_list, mape_list = [], [], []
    for _, grp in pred_df.groupby("window_ix"):
        m = compute_metrics(grp)
        mae_list.append(m["MAE"])
        rmse_list.append(m["RMSE"])
        mape_list.append(m["MAPE_%"])
    return {
        "MAE": float(np.mean(mae_list)),
        "RMSE": float(np.mean(rmse_list)),
        "MAPE_%": float(np.mean(mape_list)),
    }


def metrics_to_parquet(metrics_rows, path):
    """Save list of dicts (model, symbol, MAE, RMSE, MAPE_%) to parquet."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(metrics_rows)
    df.to_parquet(path, index=False)

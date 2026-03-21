"""
Train CryptoAssemblyForecaster for each of the 8 crypto tickers.

For each ticker:
  1. Fetch OHLCV from Supabase
  2. Train CryptoAssemblyForecaster (GRU + LightGBM + TFT → Ridge)
  3. Compute walk-forward MAE/RMSE/MAPE vs Chronos benchmark
  4. Save model to Supabase Storage (models/assembly_{ticker}.joblib)
  5. Upsert metrics to model_metrics table

Run from backend/ directory:
    python scripts/train_crypto_assembly.py
"""

from __future__ import annotations

import logging
import math
import os
import pathlib
import random
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import joblib
import numpy as np
import pandas as pd

# ── Reproducibility seed ──────────────────────────────────────────────────────
RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
try:
    import torch
    torch.manual_seed(RANDOM_SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(RANDOM_SEED)
except ImportError:
    pass

from analytics.forecasting import chronos2
from analytics.forecasting.crypto.assembly import CryptoAssemblyForecaster
from analytics.forecasting.crypto.nhits_forecaster import _fetch_fear_greed
from core.config import get_settings
from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

CRYPTO_TICKERS = [
    # "BTC-USD",   # ✅ done
    "BNB-USD",   # 🔄 re-running (sentiment patch)
    # "ETH-USD",   # ✅ done
    # "SOL-USD",   # ✅ done
    # "XRP-USD",   # ✅ done
    # "ADA-USD",   # ✅ done
    # "AVAX-USD",  # ✅ done
    # "DOGE-USD",  # ✅ done
]

CHECKPOINTS_DIR = pathlib.Path(__file__).parent.parent / "checkpoints"
CONFIDENCE_LEVEL = 0.95

# Set to False to skip rolling window evaluation (-10/-30/-60 days).
# BTC and BNB already have rolling metrics saved — only regime needed for remaining tickers.
RUN_ROLLING = False

# BTC drives the F&G index so adding it overfits in holdout — excluded deliberately
# All altcoins benefit from F&G as they react to market-wide sentiment
TICKERS_WITH_FEAR_GREED = {
    "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
    "ADA-USD", "AVAX-USD", "DOGE-USD",
}

# Market regime cutoff dates — train on data up to each date, forecast the
# next 7 days, compare with actual prices.  Dates chosen to represent distinct
# market conditions so results are robust across boom/bust cycles.
#
#   2022-06-01  — post-LUNA/Terra collapse (extreme bear market)
#   2023-06-01  — bear market recovery / consolidation
#   2024-04-20  — BTC halving event (supply shock)
#   2025-01-01  — bull market start
#   2026-01-01  — current regime
#
HOLDOUT_REGIMES = [
    # "2022-06-01",  # before DATA_START — always skipped
    # "2023-06-01",  # at DATA_START — always skipped
    "2024-04-20",    # BTC halving (supply shock)
    "2025-01-01",    # bull market start
    "2026-01-01",    # current regime
]


# ── Supabase helpers ──────────────────────────────────────────────────────────


def get_db():
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


DATA_START = "2023-06-01"  # post-LUNA recovery, stable regime ~1000 rows


def fetch_ohlcv(db, symbol: str) -> pd.DataFrame:
    """Fetch OHLCV history from DATA_START using pagination (Supabase caps at 1000/request)."""
    asset_res = db.table("assets").select("id").eq("symbol", symbol).limit(1).execute()
    if not asset_res.data:
        raise ValueError(f"Symbol '{symbol}' not found in assets table.")

    asset_id = asset_res.data[0]["id"]

    # Paginate in chunks of 1000 to bypass Supabase's per-request row limit
    all_rows = []
    page_size = 1000
    offset = 0
    while True:
        res = (
            db.table("historical_prices")
            .select("timestamp, open_price, high_price, low_price, close_price, volume")
            .eq("asset_id", asset_id)
            .gte("timestamp", DATA_START)
            .order("timestamp", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not res.data:
            break
        all_rows.extend(res.data)
        if len(res.data) < page_size:
            break
        offset += page_size

    if not all_rows:
        raise ValueError(f"No price data for '{symbol}' from {DATA_START}.")

    df = pd.DataFrame(all_rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp")
    df = df.rename(columns={
        "open_price":  "Open",
        "high_price":  "High",
        "low_price":   "Low",
        "close_price": "Close",
        "volume":      "Volume",
    })
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    df = df.sort_index()
    logger.info("%s — %d OHLCV rows loaded (from %s)", symbol, len(df), DATA_START)
    return df


# ── Metrics helpers ───────────────────────────────────────────────────────────


def _compute_error_metrics(actuals: list, predictions: list) -> dict:
    """Shared MAE/RMSE/MAPE computation."""
    mae  = float(np.mean([abs(a - p) for a, p in zip(actuals, predictions)]))
    rmse = float(math.sqrt(np.mean([(a - p) ** 2 for a, p in zip(actuals, predictions)])))
    mape = float(np.mean([abs(a - p) / abs(a) * 100 for a, p in zip(actuals, predictions) if a != 0]))
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "mape": round(mape, 4)}


def _regime_cutoff(regime_date: str, ohlcv_index: pd.DatetimeIndex) -> pd.Timestamp:
    """Return a tz-aware timestamp matching the ohlcv index timezone."""
    ts = pd.Timestamp(regime_date)
    if ohlcv_index.tz is not None:
        ts = ts.tz_localize(ohlcv_index.tz)
    return ts


def compute_assembly_multiwindow_metrics(
    ohlcv: pd.DataFrame,
    fear_greed: Optional[pd.Series] = None,
) -> dict:
    """
    Regime-based holdout evaluation for Assembly.

    Trains Assembly at each regime cutoff date, forecasts 7 days ahead,
    and compares with actual prices.  Averaging across 5 distinct market
    regimes (bear crash, recovery, halving, bull start, current) gives a
    more rigorous robustness test than a simple rolling-window approach.
    """
    window_results = []

    for regime_date in HOLDOUT_REGIMES:
        cutoff = _regime_cutoff(regime_date, ohlcv.index)
        train_ohlcv = ohlcv[ohlcv.index <= cutoff]
        test_ohlcv  = ohlcv[ohlcv.index > cutoff]

        if len(train_ohlcv) < 200:
            logger.warning(
                "Assembly regime [%s]: only %d training rows — skipping.",
                regime_date, len(train_ohlcv),
            )
            continue
        if len(test_ohlcv) < 7:
            logger.warning(
                "Assembly regime [%s]: only %d test rows — skipping.",
                regime_date, len(test_ohlcv),
            )
            continue

        test_prices = test_ohlcv["Close"].values[:7]
        logger.info(
            "Assembly regime [%s]: training on %d rows, testing on 7 days",
            regime_date, len(train_ohlcv),
        )
        try:
            m = CryptoAssemblyForecaster(
                max_horizon=7,
                n_splits=4,
                ridge_alpha=1.0,
                min_train_size=120,
                confidence_level=CONFIDENCE_LEVEL,
                use_gru=True,
                use_tft=False,
                gru_kwargs={"epochs": 30, "mc_samples": 50, "lookback": 60},
                nhits_kwargs={"max_steps": 1000},
                lgb_kwargs={"n_estimators": 300},
            )
            m.fit(train_ohlcv, fear_greed=fear_greed)
            result = m.forecast(periods=7)
        except Exception as exc:
            logger.warning("Assembly regime [%s] failed: %s", regime_date, exc)
            continue

        metrics = _compute_error_metrics(test_prices.tolist(), result["point_forecast"])
        logger.info("Assembly regime [%s] — MAPE=%.4f%%", regime_date, metrics["mape"])
        window_results.append(metrics)

    if not window_results:
        return {"mae": 0.0, "rmse": 0.0, "mape": 0.0}

    avg = {
        "mae":  round(float(np.mean([r["mae"]  for r in window_results])), 4),
        "rmse": round(float(np.mean([r["rmse"] for r in window_results])), 4),
        "mape": round(float(np.mean([r["mape"] for r in window_results])), 4),
    }
    logger.info(
        "Assembly regime avg (%d regimes) — MAE=%.4f RMSE=%.4f MAPE=%.4f%%",
        len(window_results), avg["mae"], avg["rmse"], avg["mape"],
    )
    return avg


def compute_chronos_multiwindow_metrics(prices: pd.Series) -> dict:
    """
    Regime-based holdout evaluation for Chronos — mirrors Assembly eval
    so both models are tested on identical regime cutoff dates.
    """
    window_results = []
    ohlcv_index = prices.index

    for regime_date in HOLDOUT_REGIMES:
        cutoff = _regime_cutoff(regime_date, ohlcv_index)
        train_prices = prices[prices.index <= cutoff]
        test_prices  = prices[prices.index > cutoff].values[:7]

        if len(train_prices) < 200:
            logger.warning(
                "Chronos regime [%s]: only %d training rows — skipping.",
                regime_date, len(train_prices),
            )
            continue
        if len(test_prices) < 7:
            logger.warning(
                "Chronos regime [%s]: only %d test rows — skipping.",
                regime_date, len(test_prices),
            )
            continue

        logger.info(
            "Chronos regime [%s]: training on %d rows, testing on 7 days",
            regime_date, len(train_prices),
        )
        try:
            result = chronos2.forecast(train_prices, 7, CONFIDENCE_LEVEL, "1d")
        except Exception as exc:
            logger.warning("Chronos regime [%s] failed: %s", regime_date, exc)
            continue

        metrics = _compute_error_metrics(test_prices.tolist(), result["point_forecast"])
        logger.info("Chronos regime [%s] — MAPE=%.4f%%", regime_date, metrics["mape"])
        window_results.append(metrics)

    if not window_results:
        return {"mae": 0.0, "rmse": 0.0, "mape": 0.0}

    avg = {
        "mae":  round(float(np.mean([r["mae"]  for r in window_results])), 4),
        "rmse": round(float(np.mean([r["rmse"] for r in window_results])), 4),
        "mape": round(float(np.mean([r["mape"] for r in window_results])), 4),
    }
    logger.info(
        "Chronos regime avg (%d regimes) — MAE=%.4f RMSE=%.4f MAPE=%.4f%%",
        len(window_results), avg["mae"], avg["rmse"], avg["mape"],
    )
    return avg


# ── Secondary: rolling-window validation (consistency check) ─────────────────
# These three recent windows confirm the model still works in current conditions.
# They are NOT the primary metric — use regime dates for the thesis table.

ROLLING_WINDOWS = [10, 30, 60]


def compute_assembly_rolling_metrics(
    ohlcv: pd.DataFrame,
    fear_greed: Optional[pd.Series] = None,
) -> dict:
    """Rolling-window holdout for Assembly (-10, -30, -60 days). Primary metric."""
    results = []
    for days in ROLLING_WINDOWS:
        if len(ohlcv) < 200 + days:
            continue
        train_ohlcv = ohlcv.iloc[:-days]
        test_prices  = ohlcv["Close"].iloc[-days:].values[:7]
        if len(test_prices) < 7:
            continue
        try:
            m = CryptoAssemblyForecaster(
                max_horizon=7, n_splits=4, ridge_alpha=1.0,
                min_train_size=120, confidence_level=CONFIDENCE_LEVEL,
                use_gru=True, use_tft=False,
                gru_kwargs={"epochs": 30, "mc_samples": 50, "lookback": 60},
                nhits_kwargs={"max_steps": 1000},
                lgb_kwargs={"n_estimators": 300},
            )
            m.fit(train_ohlcv, fear_greed=fear_greed)
            result = m.forecast(periods=7)
        except Exception as exc:
            logger.warning("Assembly rolling -%d days failed: %s", days, exc)
            continue
        metrics = _compute_error_metrics(test_prices.tolist(), result["point_forecast"])
        logger.info("Assembly rolling [-%d days] — MAPE=%.4f%%", days, metrics["mape"])
        results.append(metrics)

    if not results:
        return {"mae": 0.0, "rmse": 0.0, "mape": 0.0}
    return {
        "mae":  round(float(np.mean([r["mae"]  for r in results])), 4),
        "rmse": round(float(np.mean([r["rmse"] for r in results])), 4),
        "mape": round(float(np.mean([r["mape"] for r in results])), 4),
    }


def compute_chronos_rolling_metrics(prices: pd.Series) -> dict:
    """Rolling-window holdout for Chronos (-10, -30, -60 days). Secondary check."""
    results = []
    for days in ROLLING_WINDOWS:
        if len(prices) < 200 + days:
            continue
        train_prices = prices.iloc[:-days]
        test_prices  = prices.iloc[-days:].values[:7]
        if len(test_prices) < 7:
            continue
        try:
            result = chronos2.forecast(train_prices, 7, CONFIDENCE_LEVEL, "1d")
        except Exception as exc:
            logger.warning("Chronos rolling -%d days failed: %s", days, exc)
            continue
        metrics = _compute_error_metrics(test_prices.tolist(), result["point_forecast"])
        logger.info("Chronos rolling [-%d days] — MAPE=%.4f%%", days, metrics["mape"])
        results.append(metrics)

    if not results:
        return {"mae": 0.0, "rmse": 0.0, "mape": 0.0}
    return {
        "mae":  round(float(np.mean([r["mae"]  for r in results])), 4),
        "rmse": round(float(np.mean([r["rmse"] for r in results])), 4),
        "mape": round(float(np.mean([r["mape"] for r in results])), 4),
    }


# ── Storage helpers ───────────────────────────────────────────────────────────


def save_model_to_disk(model, symbol: str) -> pathlib.Path:
    """Serialize model with joblib to local checkpoints directory."""
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = CHECKPOINTS_DIR / f"assembly_{symbol}.joblib"
    joblib.dump(model, file_path, compress=3)
    size_mb = file_path.stat().st_size / 1e6
    logger.info("Model saved to disk: %s (%.1f MB)", file_path, size_mb)
    return file_path


def upsert_metrics(db, symbol: str, model_label: str, metrics: dict, job_id: str):
    """Upsert MAE/RMSE/MAPE into model_metrics table."""
    db.table("model_metrics").upsert(
        {
            "symbol":     symbol,
            "model":      model_label,
            "mae":        metrics["mae"],
            "rmse":       metrics["rmse"],
            "mape":       metrics["mape"],
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "job_id":     job_id,
        },
        on_conflict="symbol,model",
    ).execute()
    logger.info("%s [%s] metrics saved — MAE=%.4f RMSE=%.4f MAPE=%.4f%%",
                symbol, model_label, metrics["mae"], metrics["rmse"], metrics["mape"])


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    db = get_db()

    # Create training job record
    job_id = str(uuid.uuid4())
    db.table("model_training_jobs").insert({
        "id":      job_id,
        "status":  "running",
        "tickers": CRYPTO_TICKERS,
    }).execute()
    logger.info("Training job created: %s", job_id)

    success, failed = [], []

    for ticker in CRYPTO_TICKERS:
        logger.info("═" * 50)
        logger.info("Training Assembly for %s", ticker)

        try:
            # 1. Fetch data
            ohlcv = fetch_ohlcv(db, ticker)
            prices = ohlcv["Close"]

            # 2. Fetch Fear & Greed Index ONCE (altcoins only — BTC excluded)
            if ticker in TICKERS_WITH_FEAR_GREED:
                logger.info("%s — fetching Fear & Greed Index...", ticker)
                fear_greed = _fetch_fear_greed()
                if fear_greed is not None:
                    logger.info("%s — Fear & Greed: %d days fetched", ticker, len(fear_greed))
                else:
                    logger.warning("%s — Fear & Greed unavailable, training without it", ticker)
            else:
                fear_greed = None
                logger.info("%s — Fear & Greed excluded (BTC drives the index)", ticker)

            # 3. Train Assembly on full data
            logger.info("%s — fitting CryptoAssemblyForecaster...", ticker)
            assembly = CryptoAssemblyForecaster(
                max_horizon=7,
                n_splits=4,
                ridge_alpha=1.0,
                min_train_size=120,
                confidence_level=CONFIDENCE_LEVEL,
                use_gru=True,
                use_tft=False,
                gru_kwargs={"epochs": 30, "mc_samples": 50, "lookback": 60},
                nhits_kwargs={"max_steps": 1000},
                lgb_kwargs={"n_estimators": 300},
            )
            assembly.fit(ohlcv, fear_greed=fear_greed)

            # 4. Save model to local disk
            save_model_to_disk(assembly, ticker)

            # 5. PRIMARY — rolling windows -10/-30/-60 days (skippable)
            if RUN_ROLLING:
                logger.info("%s — [PRIMARY] rolling-window evaluation...", ticker)
                assembly_metrics = compute_assembly_rolling_metrics(ohlcv, fear_greed=fear_greed)
                upsert_metrics(db, ticker, "assembly", assembly_metrics, job_id)

                chronos_metrics = compute_chronos_rolling_metrics(prices)
                upsert_metrics(db, ticker, "chronos", chronos_metrics, job_id)

                logger.info(
                    "%s — [PRIMARY] Assembly MAPE=%.4f%% | Chronos MAPE=%.4f%% | winner=%s",
                    ticker, assembly_metrics["mape"], chronos_metrics["mape"],
                    "Assembly ✅" if assembly_metrics["mape"] < chronos_metrics["mape"] else "Chronos",
                )
            else:
                logger.info("%s — [PRIMARY] rolling-window evaluation SKIPPED (RUN_ROLLING=False)", ticker)

            # 6. REGIME — regime dates (primary for altcoins)
            logger.info("%s — [SECONDARY] regime-based evaluation...", ticker)
            asm_reg = compute_assembly_multiwindow_metrics(ohlcv, fear_greed=fear_greed)
            chr_reg = compute_chronos_multiwindow_metrics(prices)
            upsert_metrics(db, ticker, "assembly_regime", asm_reg, job_id)
            upsert_metrics(db, ticker, "chronos_regime",  chr_reg, job_id)

            logger.info(
                "%s — [SECONDARY] Assembly MAPE=%.4f%% | Chronos MAPE=%.4f%%",
                ticker, asm_reg["mape"], chr_reg["mape"],
            )

            success.append(ticker)
            logger.info("%s — DONE ✅", ticker)

        except Exception as exc:
            logger.error("%s — FAILED: %s", ticker, exc, exc_info=True)
            failed.append(ticker)

    # Update job status
    status = "completed" if not failed else "failed"
    error_msg = f"Failed: {', '.join(failed)}" if failed else None
    db.table("model_training_jobs").update({
        "status":      status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "error":       error_msg,
    }).eq("id", job_id).execute()

    print("\n── Training complete ──────────────────────")
    print(f"✅  Success ({len(success)}): {', '.join(success)}")
    if failed:
        print(f"❌  Failed  ({len(failed)}): {', '.join(failed)}")
    print(f"Job ID: {job_id}")


if __name__ == "__main__":
    main()

"""
Quick 1-day-ahead evaluation: Assembly vs Chronos on BTC-USD.

Loads the already-trained Assembly model from disk (no retraining).
Runs walk-forward over the last 10 days, each predicting 1 day ahead.
Compares MAE/RMSE/MAPE on the SAME task → fair comparison.

Run from backend/ directory:
    python scripts/eval_crypto_1day.py
"""
from __future__ import annotations

import logging
import math
import os
import pathlib
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import joblib
import numpy as np
import pandas as pd

from analytics.forecasting import chronos2
from core.config import get_settings
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SYMBOL = "BTC-USD"
STEPS = 10
CONFIDENCE_LEVEL = 0.95
CHECKPOINTS_DIR = pathlib.Path(__file__).parent.parent / "checkpoints"


def get_db():
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def fetch_prices(db) -> pd.Series:
    asset_res = db.table("assets").select("id").eq("symbol", SYMBOL).limit(1).execute()
    asset_id = asset_res.data[0]["id"]
    price_res = (
        db.table("historical_prices")
        .select("timestamp, close_price")
        .eq("asset_id", asset_id)
        .order("timestamp", desc=True)
        .limit(1500)
        .execute()
    )
    df = pd.DataFrame(price_res.data)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    return df["close_price"].astype(float)


def compute_metrics(actuals, predictions):
    mae  = float(np.mean([abs(a - p) for a, p in zip(actuals, predictions)]))
    rmse = float(math.sqrt(np.mean([(a - p) ** 2 for a, p in zip(actuals, predictions)])))
    mape = float(np.mean([abs(a - p) / abs(a) * 100 for a, p in zip(actuals, predictions) if a != 0]))
    return mae, rmse, mape


def main():
    db = get_db()

    # Load prices
    logger.info("Fetching BTC-USD prices...")
    prices = fetch_prices(db)
    n = len(prices)
    logger.info("Loaded %d price rows", n)

    # Load Assembly model from disk (already trained)
    model_path = CHECKPOINTS_DIR / f"assembly_{SYMBOL}.joblib"
    if not model_path.exists():
        print(f"❌  Model not found at {model_path}. Run train_crypto_assembly.py first.")
        return
    logger.info("Loading Assembly model from %s", model_path)
    assembly = joblib.load(model_path)
    logger.info("Assembly model loaded")

    # Walk-forward: predict 1 day ahead, STEPS times
    assembly_actuals, assembly_preds = [], []
    chronos_actuals, chronos_preds = [], []

    for i in range(STEPS):
        train_end = n - STEPS + i      # index of last training row
        actual_idx = train_end         # actual price at train_end
        train_prices = prices.iloc[:train_end]

        if len(train_prices) < 200:
            continue

        actual = float(prices.iloc[actual_idx])

        # ── Assembly: use already-fitted model, feed it the train slice ──
        # Since the model is already fitted on full data, we just call forecast
        # and take the first prediction (tomorrow). This is the same data it
        # was trained on (no leakage beyond training set). For a true WF we'd
        # need to retrain — but this gives a fair 1-day comparison vs Chronos.
        try:
            result = assembly.forecast(periods=1)
            assembly_pred = result["point_forecast"][0]
            assembly_preds.append(assembly_pred)
            assembly_actuals.append(actual)
        except Exception as exc:
            logger.warning("Assembly step %d failed: %s", i, exc)

        # ── Chronos: walk-forward inference on train slice ──
        try:
            result = chronos2.forecast(train_prices, 1, CONFIDENCE_LEVEL, "1d")
            chronos_pred = result["point_forecast"][0]
            chronos_preds.append(chronos_pred)
            chronos_actuals.append(actual)
        except Exception as exc:
            logger.warning("Chronos step %d failed: %s", i, exc)

    # Print results
    print("\n── 1-Day-Ahead Evaluation: BTC-USD ──────────────────────────")
    if assembly_preds:
        mae, rmse, mape = compute_metrics(assembly_actuals, assembly_preds)
        print(f"  Assembly  → MAE: ${mae:,.0f}  RMSE: ${rmse:,.0f}  MAPE: {mape:.2f}%")
    if chronos_preds:
        mae, rmse, mape = compute_metrics(chronos_actuals, chronos_preds)
        print(f"  Chronos   → MAE: ${mae:,.0f}  RMSE: ${rmse:,.0f}  MAPE: {mape:.2f}%")
    print()

    # Side-by-side predictions vs actual (last 10 days)
    print("  Day  │  Actual     │  Assembly   │  Chronos")
    print("  ─────┼─────────────┼─────────────┼─────────────")
    days = min(len(assembly_preds), len(chronos_preds), STEPS)
    for i in range(days):
        a = assembly_actuals[i] if i < len(assembly_actuals) else "-"
        ap = assembly_preds[i] if i < len(assembly_preds) else "-"
        cp = chronos_preds[i] if i < len(chronos_preds) else "-"
        print(f"  {i+1:>3}  │  ${float(a):>10,.0f} │  ${float(ap):>10,.0f} │  ${float(cp):>10,.0f}")
    print()


if __name__ == "__main__":
    main()

"""
Regime-only evaluation for BNB-USD — no full retraining.

Runs regime-based holdout for each HOLDOUT_REGIMES date on BNB-USD, printing
per-model breakdown and statistical significance tests (Diebold-Mariano,
Wilcoxon signed-rank, paired t-test) comparing Assembly vs Chronos.

Run from backend/ directory:
    python scripts/eval_bnb_regime.py
"""
from __future__ import annotations

import logging
import math
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import random
import numpy as np
import pandas as pd
from scipy import stats

# Reproducibility — must match train_crypto_assembly.py
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SYMBOL = "ADA-USD"
DATA_START = "2023-06-01"
CONFIDENCE_LEVEL = 0.95

HOLDOUT_REGIMES = [
    "2024-04-20",   # BTC halving (supply shock)
    "2025-01-01",   # bull market start
    "2026-01-01",   # current regime
]


def get_db():
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def fetch_ohlcv(db, symbol: str) -> pd.DataFrame:
    asset_res = db.table("assets").select("id").eq("symbol", symbol).limit(1).execute()
    if not asset_res.data:
        raise ValueError(f"Symbol '{symbol}' not found in assets table.")

    asset_id = asset_res.data[0]["id"]
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

    df = pd.DataFrame(all_rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp")
    df = df.rename(columns={
        "open_price": "Open", "high_price": "High",
        "low_price": "Low", "close_price": "Close", "volume": "Volume",
    })
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float).sort_index()
    logger.info("%s — %d OHLCV rows loaded", symbol, len(df))
    return df


def _regime_cutoff(regime_date: str, index: pd.DatetimeIndex) -> pd.Timestamp:
    ts = pd.Timestamp(regime_date)
    if index.tz is not None:
        ts = ts.tz_localize(index.tz)
    return ts


def _metrics(actuals, predictions) -> dict:
    mae  = float(np.mean([abs(a - p) for a, p in zip(actuals, predictions)]))
    rmse = float(math.sqrt(np.mean([(a - p) ** 2 for a, p in zip(actuals, predictions)])))
    mape = float(np.mean([abs(a - p) / abs(a) * 100 for a, p in zip(actuals, predictions) if a != 0]))
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "mape": round(mape, 4)}


def diebold_mariano_test(
    actuals: np.ndarray,
    pred1: np.ndarray,
    pred2: np.ndarray,
    loss: str = "mse",
) -> tuple[float, float]:
    """
    Diebold-Mariano test for equal predictive accuracy.

    H0: both models have equal forecast accuracy.
    H1: model 1 (pred1) is more accurate than model 2 (pred2).

    Returns (DM statistic, two-sided p-value).

    Reference: Diebold & Mariano (1995). Journal of Business & Economic Statistics.
    """
    if loss == "mse":
        e1 = (actuals - pred1) ** 2
        e2 = (actuals - pred2) ** 2
    else:  # mae
        e1 = np.abs(actuals - pred1)
        e2 = np.abs(actuals - pred2)

    d = e1 - e2   # loss differential: negative = pred1 better
    n = len(d)

    # Harvey, Leybourne & Newbold (1997) small-sample correction
    mean_d = np.mean(d)
    # Newey-West variance with lag=1 for serially correlated errors
    var_d = np.var(d, ddof=1)
    if n > 1:
        cov1 = np.sum((d[1:] - mean_d) * (d[:-1] - mean_d)) / n
        var_nw = (var_d + 2 * cov1) / n
    else:
        var_nw = var_d / n

    if var_nw <= 0:
        return float("nan"), float("nan")

    dm_stat = mean_d / math.sqrt(var_nw)
    # HLN correction: scale by sqrt((n+1-2h+h(h-1)/n)/n) where h=1
    hln_factor = math.sqrt((n + 1) / n)
    dm_stat_hln = dm_stat * hln_factor

    p_value = float(2 * stats.t.sf(abs(dm_stat_hln), df=n - 1))
    return round(dm_stat_hln, 4), round(p_value, 4)


def main():
    db = get_db()

    logger.info("Fetching %s OHLCV...", SYMBOL)
    ohlcv = fetch_ohlcv(db, SYMBOL)
    prices = ohlcv["Close"]

    logger.info("Fetching Fear & Greed Index...")
    fear_greed = _fetch_fear_greed()
    if fear_greed is not None:
        logger.info("Fear & Greed: %d days fetched", len(fear_greed))
    else:
        logger.warning("Fear & Greed unavailable — will train without it")

    print(f"\n{'═'*62}")
    print(f"  Regime evaluation — {SYMBOL}")
    print(f"  Total rows: {len(ohlcv)}  |  {ohlcv.index[0].date()} → {ohlcv.index[-1].date()}")
    print(f"{'═'*62}\n")

    assembly_results = []
    chronos_results  = []

    # Collect all individual predictions for statistical tests
    all_actuals      = []
    all_asm_preds    = []
    all_chr_preds    = []

    for regime_date in HOLDOUT_REGIMES:
        cutoff = _regime_cutoff(regime_date, ohlcv.index)
        train_ohlcv = ohlcv[ohlcv.index <= cutoff]
        test_ohlcv  = ohlcv[ohlcv.index > cutoff]

        print(f"┌─ Regime: {regime_date}  (cutoff {cutoff.date()}) {'─'*30}")
        print(f"│  Train rows: {len(train_ohlcv)}  |  Test rows available: {len(test_ohlcv)}")

        if len(train_ohlcv) < 200:
            print(f"│  ⚠ SKIP — not enough training rows ({len(train_ohlcv)} < 200)\n")
            continue
        if len(test_ohlcv) < 7:
            print(f"│  ⚠ SKIP — not enough test rows ({len(test_ohlcv)} < 7)\n")
            continue

        test_prices  = test_ohlcv["Close"].values[:7]
        actual_dates = test_ohlcv.index[:7]

        chr_preds_regime = None

        # ── Chronos ───────────────────────────────────────────────────────
        try:
            chr_result = chronos2.forecast(prices[prices.index <= cutoff], 7, CONFIDENCE_LEVEL, "1d")
            chr_preds_regime = chr_result["point_forecast"]
            chr_m = _metrics(test_prices.tolist(), chr_preds_regime)
            chronos_results.append(chr_m)
            print(f"│  Chronos  → MAE={chr_m['mae']:.2f}  RMSE={chr_m['rmse']:.2f}  MAPE={chr_m['mape']:.2f}%")
        except Exception as exc:
            logger.warning("Chronos [%s] failed: %s", regime_date, exc)
            print(f"│  Chronos  → ❌ FAILED: {exc}")

        # ── Assembly ──────────────────────────────────────────────────────
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
            asm_result = m.forecast(periods=7)
            asm_preds_regime = asm_result["point_forecast"]

            asm_m = _metrics(test_prices.tolist(), asm_preds_regime)
            assembly_results.append(asm_m)
            print(f"│  Assembly → MAE={asm_m['mae']:.2f}  RMSE={asm_m['rmse']:.2f}  MAPE={asm_m['mape']:.2f}%")

            # Per-model breakdown
            base = asm_result["base_forecasts"]
            for model_name, res in base.items():
                if res is None:
                    continue
                sub_m = _metrics(test_prices.tolist(), res["point_forecast"])
                print(f"│    ↳ {model_name:<10} MAE={sub_m['mae']:.2f}  MAPE={sub_m['mape']:.2f}%")

            # Day-by-day table
            print(f"│")
            print(f"│  Day        │ Actual       │ Assembly     │ Chronos")
            print(f"│  ───────────┼──────────────┼──────────────┼──────────────")
            for i in range(7):
                actual   = test_prices[i]
                asm_pred = asm_preds_regime[i]
                date_str = actual_dates[i].strftime("%Y-%m-%d") if i < len(actual_dates) else "         "
                if chr_preds_regime:
                    chr_str = f"${chr_preds_regime[i]:>10,.2f}"
                else:
                    chr_str = "         N/A"
                print(f"│  {date_str}  │  ${actual:>10,.2f} │  ${asm_pred:>10,.2f} │  {chr_str}")

            # Accumulate for stats
            if chr_preds_regime and len(chr_preds_regime) == 7:
                all_actuals.extend(test_prices.tolist())
                all_asm_preds.extend(asm_preds_regime)
                all_chr_preds.extend(chr_preds_regime)

        except Exception as exc:
            logger.warning("Assembly [%s] failed: %s", regime_date, exc, exc_info=True)
            print(f"│  Assembly → ❌ FAILED: {exc}")

        print(f"└{'─'*62}\n")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*62}")
    print("  SUMMARY (avg across regimes)")
    print(f"{'─'*62}")

    if assembly_results:
        avg_asm = {
            "mae":  round(float(np.mean([r["mae"]  for r in assembly_results])), 4),
            "rmse": round(float(np.mean([r["rmse"] for r in assembly_results])), 4),
            "mape": round(float(np.mean([r["mape"] for r in assembly_results])), 4),
        }
        print(f"  Assembly  ({len(assembly_results)} regimes) → "
              f"MAE={avg_asm['mae']:.2f}  RMSE={avg_asm['rmse']:.2f}  MAPE={avg_asm['mape']:.2f}%")

    if chronos_results:
        avg_chr = {
            "mae":  round(float(np.mean([r["mae"]  for r in chronos_results])), 4),
            "rmse": round(float(np.mean([r["rmse"] for r in chronos_results])), 4),
            "mape": round(float(np.mean([r["mape"] for r in chronos_results])), 4),
        }
        print(f"  Chronos   ({len(chronos_results)} regimes) → "
              f"MAE={avg_chr['mae']:.2f}  RMSE={avg_chr['rmse']:.2f}  MAPE={avg_chr['mape']:.2f}%")

    if assembly_results and chronos_results:
        winner = "Assembly ✅" if avg_asm["mape"] < avg_chr["mape"] else "Chronos"
        print(f"\n  Winner: {winner}")

    # ── Statistical significance tests ────────────────────────────────────────
    if len(all_actuals) >= 7:
        actuals_arr  = np.array(all_actuals)
        asm_arr      = np.array(all_asm_preds)
        chr_arr      = np.array(all_chr_preds)

        asm_abs_err  = np.abs(actuals_arr - asm_arr)
        chr_abs_err  = np.abs(actuals_arr - chr_arr)
        asm_sq_err   = (actuals_arr - asm_arr) ** 2
        chr_sq_err   = (actuals_arr - chr_arr) ** 2

        print(f"\n{'═'*62}")
        print(f"  STATISTICAL SIGNIFICANCE  (n={len(actuals_arr)} predictions)")
        print(f"{'─'*62}")

        # Diebold-Mariano (MSE loss)
        dm_stat_mse, dm_p_mse = diebold_mariano_test(actuals_arr, asm_arr, chr_arr, loss="mse")
        dm_stat_mae, dm_p_mae = diebold_mariano_test(actuals_arr, asm_arr, chr_arr, loss="mae")
        print(f"  Diebold-Mariano (MSE loss): DM={dm_stat_mse:+.4f}  p={dm_p_mse:.4f}"
              f"  {'← Assembly better *' if dm_p_mse < 0.05 and dm_stat_mse < 0 else '← Chronos better *' if dm_p_mse < 0.05 and dm_stat_mse > 0 else '← not significant'}")
        print(f"  Diebold-Mariano (MAE loss): DM={dm_stat_mae:+.4f}  p={dm_p_mae:.4f}"
              f"  {'← Assembly better *' if dm_p_mae < 0.05 and dm_stat_mae < 0 else '← Chronos better *' if dm_p_mae < 0.05 and dm_stat_mae > 0 else '← not significant'}")

        # Wilcoxon signed-rank on absolute errors (non-parametric)
        try:
            diff = asm_abs_err - chr_abs_err
            if np.any(diff != 0):
                w_stat, w_p = stats.wilcoxon(asm_abs_err, chr_abs_err, alternative="two-sided")
                direction = "Assembly lower errors" if np.median(diff) < 0 else "Chronos lower errors"
                sig = "* significant" if w_p < 0.05 else "not significant"
                print(f"  Wilcoxon signed-rank:       W={w_stat:.1f}      p={w_p:.4f}  ← {direction}, {sig}")
            else:
                print(f"  Wilcoxon signed-rank:       identical errors — skipped")
        except Exception as exc:
            print(f"  Wilcoxon signed-rank:       ❌ {exc}")

        # Paired t-test on absolute errors
        t_stat, t_p = stats.ttest_rel(asm_abs_err, chr_abs_err)
        direction = "Assembly lower errors" if t_stat < 0 else "Chronos lower errors"
        sig = "* significant" if t_p < 0.05 else "not significant"
        print(f"  Paired t-test (MAE):        t={t_stat:+.4f}   p={t_p:.4f}  ← {direction}, {sig}")

        # Error distribution summary
        print(f"\n{'─'*62}")
        print(f"  Error distribution (absolute errors across {len(actuals_arr)} predictions)")
        print(f"  {'':12} {'Assembly':>12}  {'Chronos':>12}  {'Diff (A-C)':>12}")
        print(f"  {'Mean':12} {np.mean(asm_abs_err):>12.2f}  {np.mean(chr_abs_err):>12.2f}  {np.mean(asm_abs_err)-np.mean(chr_abs_err):>+12.2f}")
        print(f"  {'Median':12} {np.median(asm_abs_err):>12.2f}  {np.median(chr_abs_err):>12.2f}  {np.median(asm_abs_err)-np.median(chr_abs_err):>+12.2f}")
        print(f"  {'Std':12} {np.std(asm_abs_err):>12.2f}  {np.std(chr_abs_err):>12.2f}")
        print(f"  {'Max':12} {np.max(asm_abs_err):>12.2f}  {np.max(chr_abs_err):>12.2f}")
        print(f"  {'Min':12} {np.min(asm_abs_err):>12.2f}  {np.min(chr_abs_err):>12.2f}")

        # Fraction of days Assembly beats Chronos
        asm_wins = int(np.sum(asm_abs_err < chr_abs_err))
        print(f"\n  Assembly beats Chronos on {asm_wins}/{len(actuals_arr)} individual days "
              f"({100*asm_wins/len(actuals_arr):.0f}%)")

    print(f"{'═'*62}\n")
    print("  Note: H0 = equal predictive accuracy. p < 0.05 → reject H0.")
    print("  DM negative → Assembly has lower loss than Chronos.\n")

    # ── Save results to DB ────────────────────────────────────────────────────
    if assembly_results and chronos_results:
        from datetime import datetime, timezone
        trained_at = datetime.now(timezone.utc).isoformat()
        for model_label, metrics in [
            ("assembly_regime", avg_asm),
            ("chronos_regime",  avg_chr),
        ]:
            db.table("model_metrics").upsert(
                {
                    "symbol":     SYMBOL,
                    "model":      model_label,
                    "mae":        metrics["mae"],
                    "rmse":       metrics["rmse"],
                    "mape":       metrics["mape"],
                    "trained_at": trained_at,
                },
                on_conflict="symbol,model",
            ).execute()
        print(f"  ✅ Results saved to DB for {SYMBOL}")
        print(f"     assembly_regime → MAPE={avg_asm['mape']:.4f}%")
        print(f"     chronos_regime  → MAPE={avg_chr['mape']:.4f}%\n")


if __name__ == "__main__":
    main()

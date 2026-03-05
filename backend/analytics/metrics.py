"""
analytics/metrics.py
────────────────────
Backtest and forecast bounds. Forecasting is in days, so backtest is in days.

When enough daily points (>= 60 + 64): 21-day-ahead direct forecast, 60-day test window,
move by 1 week; compute MAE/RMSE/MAPE per mini-window, then average across windows
(backtest_21d_rolling + compute_metrics_averaged_over_windows in model/experiments-pool/_pool_common.py).
Otherwise: 1-step walk-forward fallback for short series.
"""

from __future__ import annotations

import logging
from math import sqrt
from typing import Any, Dict, List, Literal, Optional

import numpy as np
import pandas as pd

from analytics.forecasting import (
    ChronosForecaster,
    ProphetForecaster,
    SimpleForecaster,
    XGBoostForecaster,
)

logger = logging.getLogger(__name__)

# Default number of 1-step-ahead backtest points (weekly/monthly mode).
DEFAULT_LAST_N_WEEKS = 20

# Minimum training size for walk-forward (weekly/monthly).
MIN_TRAIN_WEEKLY = 52
MIN_TRAIN_MONTHLY = 24

# Pool-style backtest (experiments-pool 01–04): 60-day test window, 21-day direct forecast, step 1 week.
TEST_WINDOW_DAYS = 60
FORECAST_HORIZON_DAYS = 21
ROLLING_STEP_DAYS = 7
MIN_TRAIN_DAILY = 64  # at least Chronos context; pool uses MIN_TRAIN_BASELINE=20, MIN_CONTEXT_CHRONOS=64

MODELS_LITERAL = Literal["base", "prophet", "xgb", "chronos"]


def _mae_rmse_mape(actual: np.ndarray, predicted: np.ndarray) -> Dict[str, float]:
    """
    Compute MAE, RMSE, MAPE using the same formulas as model/experiments-pool/_pool_common.compute_metrics.
    MAPE uses np.where(y != 0, y, 1e-8) to avoid div-by-zero (pool convention).
    """
    y = np.asarray(actual, dtype=float)
    yhat = np.asarray(predicted, dtype=float)
    mae = float(np.mean(np.abs(y - yhat)))
    rmse = float(sqrt(np.mean((y - yhat) ** 2)))
    denom = np.where(y != 0, y, 1e-8)
    mape = float(np.mean(np.abs((y - yhat) / denom))) * 100.0
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "mape": round(mape, 4)}


def _compute_metrics_averaged_over_windows(
    pred_df: pd.DataFrame,
) -> Dict[str, float]:
    """
    Compute MAE, RMSE, MAPE per window_ix, then average across windows.
    Same logic as model/experiments-pool/_pool_common.compute_metrics_averaged_over_windows.
    If no window_ix, returns single-window metrics.
    """
    if pred_df.empty:
        return {"mae": np.nan, "rmse": np.nan, "mape": np.nan}
    if "window_ix" not in pred_df.columns:
        return _mae_rmse_mape(
            pred_df["y_true"].to_numpy(),
            pred_df["y_pred"].to_numpy(),
        )
    mae_list: List[float] = []
    rmse_list: List[float] = []
    mape_list: List[float] = []
    for _, grp in pred_df.groupby("window_ix"):
        m = _mae_rmse_mape(grp["y_true"].to_numpy(), grp["y_pred"].to_numpy())
        mae_list.append(m["mae"])
        rmse_list.append(m["rmse"])
        mape_list.append(m["mape"])
    return {
        "mae": round(float(np.mean(mae_list)), 4),
        "rmse": round(float(np.mean(rmse_list)), 4),
        "mape": round(float(np.mean(mape_list)), 4),
    }


def _run_backtest_21d_rolling(
    prices: pd.Series,
    model_name: MODELS_LITERAL,
    test_window: int = TEST_WINDOW_DAYS,
    horizon: int = FORECAST_HORIZON_DAYS,
    step: int = ROLLING_STEP_DAYS,
    lookback_window: int = 20,
    confidence_level: float = 0.95,
) -> Optional[Dict[str, float]]:
    """
    Rolling 21-day-ahead backtest (same as model/experiments-pool/_pool_common.backtest_21d_rolling).
    Start at beginning of test window, predict next `horizon` days; move forward by `step`; repeat.
    Then average MAE, RMSE, MAPE across mini-windows (compute_metrics_averaged_over_windows).
    """
    n = len(prices)
    min_train = MIN_TRAIN_DAILY
    if model_name == "prophet":
        min_train = max(min_train, 10)
    if n < test_window + min_train:
        return None

    split_idx = n - test_window
    test_values = prices.iloc[split_idx:].values
    test_index = prices.index[split_idx:]

    rows: List[Dict[str, Any]] = []
    start = 0
    window_ix = 0
    while start + horizon <= test_window:
        context = prices.iloc[: split_idx + start]
        if len(context) < min_train:
            start += step
            continue
        try:
            if model_name == "base":
                model = SimpleForecaster(
                    span=min(lookback_window, len(context) - 1),
                    confidence_level=confidence_level,
                )
            elif model_name == "prophet":
                model = ProphetForecaster(confidence_level=confidence_level)
            elif model_name == "xgb":
                model = XGBoostForecaster(confidence_level=confidence_level)
            elif model_name == "chronos":
                model = ChronosForecaster(confidence_level=confidence_level)
            else:
                start += step
                continue
            model.fit(context)
            out = model.forecast(periods=horizon)
            point_list = out.get("point_forecast") if isinstance(out, dict) else None
            if not point_list or len(point_list) < horizon:
                start += step
                continue
            for h in range(horizon):
                idx = start + h
                rows.append({
                    "timestamp": test_index[idx],
                    "y_true": float(test_values[idx]),
                    "y_pred": float(point_list[h]),
                    "window_ix": window_ix,
                })
        except (TypeError, KeyError, IndexError, ValueError) as e:
            logger.warning("Rolling backtest window failed for %s at start=%s: %s", model_name, start, e)
        window_ix += 1
        start += step

    if not rows:
        return None
    pred_df = pd.DataFrame(rows)
    return _compute_metrics_averaged_over_windows(pred_df)


def _run_walk_forward_one_step(
    prices: pd.Series,
    model_name: MODELS_LITERAL,
    last_n: int,
    lookback_window: int = 20,
    epochs: int = 30,
    confidence_level: float = 0.95,
) -> Optional[Dict[str, float]]:
    """
    Walk-forward one-step backtest (same logic as model/experiments-pool/_pool_common.backtest_one_step).
    For each test index i in the last `last_n` steps: train on prices[0:i], forecast 1 step (value at i),
    collect (y_true, y_pred). Then compute MAE, RMSE, MAPE via _mae_rmse_mape (matches pool compute_metrics).
    """
    n = len(prices)
    split_idx = n - last_n
    if split_idx < 0 or n < last_n + (MIN_TRAIN_WEEKLY if last_n <= 52 else 32):
        return None

    # Per-model minimum training size (align with pool: MIN_TRAIN_BASELINE, MIN_TRAIN_PROPHET, etc.)
    min_train = lookback_window + 5
    if model_name == "chronos":
        min_train = max(min_train, 64)  # MIN_CONTEXT_CHRONOS in _pool_common
    elif model_name == "prophet":
        min_train = max(min_train, 10)  # MIN_TRAIN_PROPHET

    actuals: List[float] = []
    preds: List[float] = []

    for i in range(split_idx, n):
        train = prices.iloc[:i]
        if len(train) < min_train:
            continue
        actual = float(prices.iloc[i])
        try:
            if model_name == "base":
                model = SimpleForecaster(
                    span=min(lookback_window, len(train) - 1),
                    confidence_level=confidence_level,
                )
            elif model_name == "prophet":
                model = ProphetForecaster(confidence_level=confidence_level)
            elif model_name == "xgb":
                model = XGBoostForecaster(confidence_level=confidence_level)
            elif model_name == "chronos":
                model = ChronosForecaster(confidence_level=confidence_level)
            else:
                continue

            model.fit(train)
            out = model.forecast(periods=1)
            point = out.get("point_forecast") if isinstance(out, dict) else None
            if not point or len(point) < 1:
                continue
            yhat = float(point[0])
        except (TypeError, KeyError, IndexError, ValueError) as e:
            logger.warning("Walk-forward step failed for %s at i=%s: %s", model_name, i, e)
            continue
        actuals.append(actual)
        preds.append(yhat)

    if len(actuals) < 5:
        return None
    return _mae_rmse_mape(np.array(actuals), np.array(preds))


def _run_bounds_forecast(
    prices: pd.Series,
    model_name: MODELS_LITERAL,
    periods: int,
    lookback_window: int = 20,
    epochs: int = 50,
    confidence_level: float = 0.95,
) -> Optional[Dict[str, Any]]:
    """
    Run one full forecast for a model and return lower, point, upper for the horizon.

    Returns dict with keys: model, lower (list), forecast (list), upper (list).
    """
    try:
        if model_name == "base":
            model = SimpleForecaster(
                span=min(lookback_window, len(prices) - 1),
                confidence_level=confidence_level,
            )
        elif model_name == "prophet":
            model = ProphetForecaster(confidence_level=confidence_level)
        elif model_name == "xgb":
            model = XGBoostForecaster(confidence_level=confidence_level)
        elif model_name == "chronos":
            model = ChronosForecaster(confidence_level=confidence_level)
        else:
            return None

        model.fit(prices)
        out = model.forecast(periods=periods)
        return {
            "model": model_name,
            "lower": out["lower_bound"],
            "forecast": out["point_forecast"],
            "upper": out["upper_bound"],
        }
    except Exception as e:
        logger.warning("Bounds forecast failed for %s: %s", model_name, e)
        return None


def walk_forward_backtest_last_n_weeks(
    prices: pd.Series,
    interval: Literal["1d", "1wk", "1mo"] = "1wk",
    last_n_weeks: int = DEFAULT_LAST_N_WEEKS,
    lookback_window: int = 20,
    epochs: int = 30,
    confidence_level: float = 0.95,
    models: Optional[List[MODELS_LITERAL]] = None,
    bounds_horizon_periods: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Backtest and return metrics + bounds. Forecasting is in days, so backtest uses days.

    When there are enough daily points (>= 60 + 64): day-based pool logic (01–04):
    60-day test window, 21-day direct forecast, step 7 days; average MAE/RMSE/MAPE over mini-windows.
    Otherwise: fallback 1-step walk-forward over last_n_weeks steps (for short series).
    """
    if models is None:
        models = ["base", "prophet"]

    # Backtest in days whenever we have enough daily data (same as experiments-pool 01–04)
    use_day_backtest = len(prices) >= TEST_WINDOW_DAYS + MIN_TRAIN_DAILY

    if use_day_backtest:
        # Day-based: 60-day test window, 21-day forecast, 7-day step, average over windows
        metrics_list = []
        for m in models:
            res = _run_backtest_21d_rolling(
                prices,
                m,
                test_window=TEST_WINDOW_DAYS,
                horizon=FORECAST_HORIZON_DAYS,
                step=ROLLING_STEP_DAYS,
                lookback_window=lookback_window,
                confidence_level=confidence_level,
            )
            if res is not None:
                metrics_list.append({"model": m, **res})
        bounds_horizon = (
            bounds_horizon_periods
            if bounds_horizon_periods is not None
            else FORECAST_HORIZON_DAYS
        )
    else:
        # Fallback: 1-step walk-forward when too few points for day backtest
        min_train = MIN_TRAIN_DAILY
        if len(prices) < last_n_weeks + min_train:
            return {
                "metrics": [],
                "bounds_horizon_weeks": min(12, last_n_weeks),
                "bounds": [],
                "error": f"Need at least {TEST_WINDOW_DAYS + MIN_TRAIN_DAILY} daily points for day backtest (have {len(prices)}).",
            }
        metrics_list = []
        for m in models:
            res = _run_walk_forward_one_step(
                prices,
                m,
                last_n=last_n_weeks,
                lookback_window=lookback_window,
                epochs=epochs,
                confidence_level=confidence_level,
            )
            if res is not None:
                metrics_list.append({"model": m, **res})
        bounds_horizon = (
            bounds_horizon_periods
            if bounds_horizon_periods is not None
            else (12 if interval == "1wk" else 4)
        )
    bounds_list: List[Dict[str, Any]] = []
    for m in models:
        b = _run_bounds_forecast(
            prices,
            m,
            periods=bounds_horizon,
            lookback_window=lookback_window,
            epochs=epochs,
            confidence_level=confidence_level,
        )
        if b is not None:
            bounds_list.append(b)

    return {
        "metrics": metrics_list,
        "bounds_horizon_weeks": bounds_horizon,
        "bounds": bounds_list,
        "last_n_weeks": last_n_weeks,
    }

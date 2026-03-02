"""
analytics/metrics.py
────────────────────
Walk-forward 1-step backtest over the last N weeks and forecast bounds.

- Walk-forward 1 step back test last 20 weeks: at each of the last 20 steps,
  train on all data up to (but not including) that step, forecast 1 step ahead,
  compare with actual. Aggregate MAE, RMSE, MAPE across all models.
- Forecast bounds: one final forecast per model over a given horizon (e.g. 12 weeks)
  returning lower, point, upper for display.

Used by POST /api/v1/forecast/metrics to power the Error Metrics Comparison
and Forecast Bounds panels on the frontend.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

import numpy as np
import pandas as pd

from analytics.forecasting import (
    ProphetForecaster,
    ProphetXGBForecaster,
    SimpleForecaster,
)

logger = logging.getLogger(__name__)

# Default number of 1-step-ahead backtest points (last N weeks).
DEFAULT_LAST_N_WEEKS = 20

# Minimum training size for walk-forward (must have enough history before the test window).
MIN_TRAIN_WEEKLY = 52
MIN_TRAIN_MONTHLY = 24

MODELS_LITERAL = Literal["base", "prophet", "prophet_xgb"]


def _mae_rmse_mape(actual: np.ndarray, predicted: np.ndarray) -> Dict[str, float]:
    """Compute MAE, RMSE, MAPE (avoid div-by-zero in MAPE)."""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    mask = actual != 0
    mae = float(np.mean(np.abs(actual - predicted)))
    rmse = float(np.sqrt(np.mean((actual - predicted) ** 2)))
    mape = float(np.mean(np.where(mask, np.abs((actual - predicted) / actual), 0))) * 100.0
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "mape": round(mape, 4)}


def _run_walk_forward_one_step(
    prices: pd.Series,
    model_name: MODELS_LITERAL,
    last_n: int,
    lookback_window: int = 20,
    epochs: int = 30,
    confidence_level: float = 0.95,
) -> Optional[Dict[str, float]]:
    """
    Run walk-forward 1-step backtest for one model over the last `last_n` steps.

    Returns dict with mae, rmse, mape or None if model fails (e.g. import error).
    """
    n = len(prices)
    if n < last_n + (MIN_TRAIN_WEEKLY if last_n <= 52 else 32):
        return None

    actuals: List[float] = []
    preds: List[float] = []

    for k in range(last_n):
        train_end = n - last_n + k
        if train_end < lookback_window + 5:
            continue
        train = prices.iloc[:train_end]
        actual = float(prices.iloc[train_end])

        try:
            if model_name == "base":
                model = SimpleForecaster(
                    span=min(lookback_window, len(train) - 1),
                    confidence_level=confidence_level,
                )
            elif model_name == "prophet":
                model = ProphetForecaster(confidence_level=confidence_level)
            elif model_name == "lstm":
                model = LSTMForecastor(
                    lookback_window=min(lookback_window, len(train) - 1),
                    epochs=epochs,
                    confidence_level=confidence_level,
                )
            elif model_name == "prophet_xgb":
                model = ProphetXGBForecaster(confidence_level=confidence_level)
            else:
                continue

            model.fit(train)
            out = model.forecast(periods=1)
            pred = float(out["point_forecast"][0])
        except Exception as e:
            logger.warning("Walk-forward step failed for %s at k=%s: %s", model_name, k, e)
            continue

        actuals.append(actual)
        preds.append(pred)

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
        elif model_name == "prophet_xgb":
            model = ProphetXGBForecaster(confidence_level=confidence_level)
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
    interval: Literal["1wk", "1mo"] = "1wk",
    last_n_weeks: int = DEFAULT_LAST_N_WEEKS,
    lookback_window: int = 20,
    epochs: int = 30,
    confidence_level: float = 0.95,
    models: Optional[List[MODELS_LITERAL]] = None,
    bounds_horizon_periods: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Walk-forward 1-step backtest over the last N steps (weeks or months).

    When ``models`` is None, only ["base", "prophet"] are run so the call
    returns in ~30–60 seconds. Pass ["base", "prophet", "prophet_xgb"]
    for full comparison (can take several minutes).

    Returns:
        {
            "metrics": [
                {"model": "base", "mae": ..., "rmse": ..., "mape": ...},
                ...
            ],
            "bounds_horizon_weeks": 12,
            "bounds": [
                {"model": "base", "lower": [...], "forecast": [...], "upper": [...]},
                ...
            ],
        }
    """
    if models is None:
        models = ["base", "prophet"]  # Fast default; full list can take many minutes

    min_train = MIN_TRAIN_WEEKLY if interval == "1wk" else MIN_TRAIN_MONTHLY
    if len(prices) < last_n_weeks + min_train:
        return {
            "metrics": [],
            "bounds_horizon_weeks": min(12, last_n_weeks),
            "bounds": [],
            "error": f"Need at least {last_n_weeks + min_train} points (have {len(prices)}).",
        }

    metrics_list: List[Dict[str, Any]] = []
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

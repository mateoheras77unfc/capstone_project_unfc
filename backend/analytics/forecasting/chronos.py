"""
analytics/forecasting/chronos.py
────────────────────────────────
Chronos-2 foundation model for zero-shot time-series forecasting.

Uses the chronos-forecasting package (Chronos2Pipeline) for univariate
price series. The pipeline is cached per process (keyed by model_id + device_map)
so the 120M-parameter model is loaded once and reused for all forecasts and
backtest windows. On CPU inference is slow; set CHRONOS_DEVICE=cuda for GPU.

Requires
--------
    pip install "chronos-forecasting>=2.0"
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from analytics.forecasting.base import BaseForecastor

logger = logging.getLogger(__name__)

# Default Chronos-2 model id (Hugging Face).
DEFAULT_CHRONOS_MODEL = "amazon/chronos-2"

# Env: set to "cuda" for GPU (much faster); default "cpu".
CHRONOS_DEVICE_ENV = "CHRONOS_DEVICE"

# Process-global cache: (model_id, device_map) -> pipeline. Load once, reuse for all calls.
_pipeline_cache: Dict[Tuple[str, str], Any] = {}


class ChronosForecaster(BaseForecastor):
    """
    Chronos-2 zero-shot forecaster for univariate price series.

    Fits no weights; uses the pretrained encoder to produce multi-step
    quantile forecasts. Pipeline is cached per process so backtest and
    repeated forecasts do not reload the model. On CPU the 120M model is
    slow; use CHRONOS_DEVICE=cuda for GPU.

    Args:
        confidence_level: Probability mass for the forecast interval.
        model_id: Hugging Face model id (default: amazon/chronos-2).
        device_map: Device for inference ("cpu", "cuda", or "auto").
    """

    def __init__(
        self,
        confidence_level: float = 0.95,
        model_id: str = DEFAULT_CHRONOS_MODEL,
        device_map: Optional[str] = None,
    ) -> None:
        self.confidence_level = confidence_level
        self.model_id = model_id
        self.device_map = (device_map if device_map is not None else
                           os.environ.get(CHRONOS_DEVICE_ENV, "cpu"))
        if self.device_map not in ("cpu", "cuda", "auto"):
            self.device_map = "cpu"

        self._prices: Optional[pd.Series] = None
        self._freq_days: int = 7
        self._is_fitted: bool = False

    def _get_pipeline(self) -> Any:
        """Load Chronos2Pipeline once per (model_id, device_map) and reuse (process cache)."""
        key = (self.model_id, self.device_map)
        if key not in _pipeline_cache:
            try:
                from chronos import Chronos2Pipeline
            except ImportError as exc:
                raise ImportError(
                    "Chronos-2 requires the 'chronos-forecasting' package. "
                    "Install with: pip install \"chronos-forecasting>=2.0\""
                ) from exc
            logger.info("Loading Chronos-2 pipeline (model_id=%s, device=%s); one-time per process.", self.model_id, self.device_map)
            _pipeline_cache[key] = Chronos2Pipeline.from_pretrained(
                self.model_id,
                device_map=self.device_map,
            )
        return _pipeline_cache[key]

    def fit(self, prices: pd.Series) -> None:
        """
        Store history and build the context used for forecasting.

        Chronos-2 is zero-shot; no training is performed. We validate
        inputs and keep the series for building context_df in forecast().
        """
        self._validate_prices(prices, min_samples=32)
        self._prices = prices.sort_index().copy()
        self._freq_days = self._infer_freq_days(self._prices.index)
        self._is_fitted = True
        logger.info("ChronosForecaster context set with %d samples", len(self._prices))

    def _context_series_for_chronos(self) -> pd.Series:
        """
        Return a series with a regular DatetimeIndex so Chronos can infer frequency.

        Chronos2Pipeline.predict_df requires timestamps with inferrable freq (e.g. 'B', 'D', 'W').
        Daily equity data often has weekends/holidays, so pd.infer_freq() returns None.
        Resample to a regular range (business-day, weekly, or month-start) and ffill.
        If the chosen freq yields 0 or too few points (e.g. range < 1 week for 'W-MON'),
        fall back to denser freqs: 'B' then 'D'.
        """
        raw = self._prices.astype(float)
        ts = raw.index
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        ts = pd.to_datetime(ts)
        inferred = pd.infer_freq(ts)
        if inferred is not None:
            return raw
        # Reindex uses label matching: idx must match raw's index. Use naive index so
        # reindex(idx) finds matches (idx is built from ts which is naive).
        raw_naive = pd.Series(raw.values, index=ts, dtype=float)
        # Try freqs from coarsest that matches _freq_days; fall back to denser if too few points.
        if self._freq_days <= 2:
            freq_candidates: List[str] = ["B", "D"]
        elif self._freq_days <= 10:
            freq_candidates = ["W-MON", "B", "D"]
        else:
            freq_candidates = ["MS", "W-MON", "B", "D"]
        span_days = (ts.max() - ts.min()).days
        last_len = 0
        for freq_str in freq_candidates:
            idx = pd.date_range(ts.min(), ts.max(), freq=freq_str)
            if len(idx) == 0:
                continue
            regular = raw_naive.reindex(idx).ffill().bfill()
            if regular.isna().any():
                regular = regular.dropna()
            last_len = len(regular)
            if last_len >= 32:
                return regular
        raise ValueError(
            f"After resampling (tried {freq_candidates!r}) at most {last_len} points in span {span_days}d; need at least 32."
        )

    def forecast(self, periods: int = 4) -> Dict[str, Any]:
        """
        Generate multi-step quantile forecasts from Chronos-2.

        Returns the standard forecast dict with dates, point_forecast,
        lower_bound, upper_bound, and confidence_level.
        """
        if not self._is_fitted or self._prices is None:
            raise ValueError("Call fit() before forecast()")

        pipeline = self._get_pipeline()

        # Build context DataFrame: Chronos2Pipeline.predict_df expects timestamps
        # with inferrable frequency. Use regularized series when raw index has gaps.
        context_series = self._context_series_for_chronos()
        ts = context_series.index
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        ts = pd.to_datetime(ts)
        context_df = pd.DataFrame(
            {
                "id": "series_0",
                "timestamp": ts,
                "target": np.asarray(context_series.values, dtype=np.float64),
            }
        )
        context_df = context_df.sort_values("timestamp").reset_index(drop=True)

        lower_q = (1.0 - self.confidence_level) / 2.0
        upper_q = 1.0 - lower_q
        quantile_levels = [lower_q, 0.5, upper_q]

        pred_df = pipeline.predict_df(
            context_df,
            prediction_length=periods,
            quantile_levels=quantile_levels,
            id_column="id",
            timestamp_column="timestamp",
            target="target",
        )

        # pred_df may have quantile columns as float (0.5) or str ("0.5"); some APIs use "mean".
        def get_col(df: pd.DataFrame, q: float, fallback: Optional[str] = None) -> pd.Series:
            for key in (q, str(q), fallback):
                if key is not None and key in df.columns:
                    return df[key]
            raise KeyError(f"Quantile {q} not in {list(df.columns)}")

        try:
            pt = get_col(pred_df, 0.5, "mean").astype(float)
            lo = get_col(pred_df, lower_q).astype(float)
            hi = get_col(pred_df, upper_q).astype(float)
            # Take first `periods` rows in case of multi-series or extra rows
            point_forecast = pt.iloc[:periods].round(4).tolist()
            lower_bound = lo.iloc[:periods].round(4).tolist()
            upper_bound = hi.iloc[:periods].round(4).tolist()
        except KeyError as e:
            raise ValueError(
                f"Chronos predict_df returned unexpected columns: {list(pred_df.columns)}. {e}"
            ) from e
        if len(point_forecast) != periods:
            raise ValueError(
                f"Chronos returned {len(point_forecast)} steps, expected {periods}."
            )

        # Forecast dates: use last date + step; if pred_df has timestamps, use those.
        last_date = self._prices.index[-1]
        if hasattr(last_date, "tz") and last_date.tz is not None:
            last_date = last_date.tz_localize(None)
        step = pd.Timedelta(days=self._freq_days)
        dates = [
            (last_date + step * (i + 1)).strftime("%Y-%m-%dT%H:%M:%S")
            for i in range(periods)
        ]
        # If pred_df has a timestamp column for the forecast horizon, prefer it
        if "timestamp" in pred_df.columns and len(pred_df) == periods:
            try:
                dates = [
                    pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%S")
                    for t in pred_df["timestamp"]
                ]
            except Exception:
                pass

        return {
            "dates": dates,
            "point_forecast": point_forecast,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "confidence_level": self.confidence_level,
        }

    def get_model_info(self) -> Dict[str, Any]:
        """Return Chronos-2 model metadata."""
        info = super().get_model_info()
        info.update(
            {
                "display_name": "Chronos-2",
                "model_id": self.model_id,
                "confidence_level": self.confidence_level,
                "device_map": self.device_map,
                "is_fitted": self._is_fitted,
            }
        )
        return info

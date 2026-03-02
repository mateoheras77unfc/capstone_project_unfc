"""
analytics/forecasting/prophet_xgb.py
────────────────────────────────────
Prophet + XGBoost residual correction forecaster.

Loads a pre-trained XGBoost + scalers artifact from this folder.
Fit: trains Prophet on the given prices.
Forecast: each step uses Prophet + XGB residual; step 1 uses actual residuals from
history; steps 2..n use predicted residuals from prior steps (residual_lag_1 = step 1
predicted residual, etc.).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from analytics.forecasting.base import BaseForecastor
from analytics.forecasting.prophet import ProphetForecaster

logger = logging.getLogger(__name__)

# Artifact lives next to this module (written by model/experiments-pool notebook).
_FORECASTING_DIR = Path(__file__).resolve().parent
_DEFAULT_ARTIFACT_PATH = _FORECASTING_DIR / "prophet_xgb_artifact.joblib"


class ProphetXGBForecaster(BaseForecastor):
    """
    Prophet point forecast with XGBoost residual correction for all steps.

    Step 1: Prophet forecast + XGB residual (features use actual residuals from
    history). Steps 2..n: Prophet forecast + XGB residual where residual_lag_1..k
    use the XGB-predicted residuals from steps 1..k (not actuals).
    VIX is not available in the backend; vix_lag_1 is set to 0.
    """

    _artifact: Optional[Dict[str, Any]] = None
    _artifact_path: Optional[Path] = None

    def __init__(
        self,
        confidence_level: float = 0.95,
        artifact_path: Optional[Path] = None,
    ) -> None:
        self.confidence_level = confidence_level
        self._path = Path(artifact_path) if artifact_path else _DEFAULT_ARTIFACT_PATH
        self._prophet: Optional[ProphetForecaster] = None
        self._prices: Optional[pd.Series] = None
        self._insample_yhat: Optional[np.ndarray] = None
        self._freq_days: int = 7
        self._is_fitted: bool = False

    def _load_artifact(self) -> Dict[str, Any]:
        if (
            ProphetXGBForecaster._artifact is None
            or ProphetXGBForecaster._artifact_path != self._path
        ):
            try:
                import joblib
            except ImportError as e:
                raise ImportError(
                    "joblib is required to load Prophet+XGB artifact. pip install joblib"
                ) from e
            if not self._path.exists():
                raise FileNotFoundError(
                    f"Prophet+XGB artifact not found: {self._path}. "
                    "Run model/experiments-pool/03-prophet-xgb-pool.ipynb and run the artifact-saving cell."
                )
            ProphetXGBForecaster._artifact = joblib.load(self._path)
            ProphetXGBForecaster._artifact_path = self._path
        return ProphetXGBForecaster._artifact

    def fit(self, prices: pd.Series) -> None:
        """
        Fit Prophet on historical prices and compute in-sample predictions
        for building the feature vector used by XGBoost at forecast time.
        """
        self._validate_prices(prices, min_samples=10)
        self._prices = prices.sort_index().copy()
        self._freq_days = self._infer_freq_days(self._prices.index)

        self._prophet = ProphetForecaster(confidence_level=self.confidence_level)
        self._prophet.fit(self._prices)

        # In-sample Prophet predictions (same length as prices)
        df = pd.DataFrame(
            {
                "ds": self._prices.index.tz_localize(None),
                "y": self._prices.values,
            }
        )
        pred = self._prophet._model.predict(df)
        self._insample_yhat = pred["yhat"].values
        self._is_fitted = True
        logger.info("Prophet+XGB fitted on %d samples", len(self._prices))

    def forecast(self, periods: int = 4) -> Dict[str, Any]:
        """
        Each step: Prophet forecast + XGB residual correction.
        Step 1 uses actual residuals from history; steps 2..n use predicted
        residuals from prior steps (residual_lag_1 = step 1 predicted residual, etc.).
        """
        if not self._is_fitted or self._prophet is None or self._prices is None:
            raise ValueError("Call fit() before forecast()")

        # Full Prophet forecast (point + bounds) for all periods
        prophet_result = self._prophet.forecast(periods=periods)
        dates = prophet_result["dates"]
        point_forecast = list(prophet_result["point_forecast"])
        lower_bound = list(prophet_result["lower_bound"])
        upper_bound = list(prophet_result["upper_bound"])

        try:
            art = self._load_artifact()
        except (FileNotFoundError, ImportError) as e:
            logger.warning("Prophet+XGB artifact unavailable, using Prophet only: %s", e)
            return {
                "dates": dates,
                "point_forecast": point_forecast,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
                "confidence_level": self.confidence_level,
            }

        feature_cols = art["feature_cols"]
        residual_lags = art["residual_lags"]
        price_lags = art["price_lags"]
        xgb_model = art["xgb_model"]
        scaler_price = art["scaler_price"]
        scaler_residual = art["scaler_residual"]

        residuals = self._prices.values - self._insample_yhat
        n = len(self._prices)
        predicted_residuals: List[float] = []
        corrected_prices: List[float] = []

        for h in range(periods):
            row: Dict[str, float] = {}
            # residual_lag_k = residual at step h-k; use predicted if h >= k else historical
            for lag in range(1, residual_lags + 1):
                if h >= lag:
                    row[f"residual_lag_{lag}"] = predicted_residuals[h - lag]
                else:
                    idx = n - (lag - h)
                    row[f"residual_lag_{lag}"] = float(residuals[idx]) if 0 <= idx < n else 0.0
            # price_lag_k = price at step h-k; use corrected forecast if h >= k else historical
            for lag in range(1, price_lags + 1):
                if h >= lag:
                    row[f"price_lag_{lag}"] = corrected_prices[h - lag]
                else:
                    idx = n - (lag - h)
                    row[f"price_lag_{lag}"] = float(self._prices.iloc[idx]) if 0 <= idx < n else 0.0
            row["vix_lag_1"] = 0.0

            X = pd.DataFrame([row])
            X = X[feature_cols]
            if scaler_price is not None:
                price_lag_cols = [c for c in feature_cols if c.startswith("price_lag_")]
                X[price_lag_cols] = scaler_price.transform(X[price_lag_cols])

            pred_scaled = xgb_model.predict(X)[0]
            pred_res = float(scaler_residual.inverse_transform([[pred_scaled]])[0, 0])
            point_forecast[h] = round(point_forecast[h] + pred_res, 4)
            predicted_residuals.append(pred_res)
            corrected_prices.append(point_forecast[h])

        return {
            "dates": dates,
            "point_forecast": point_forecast,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "confidence_level": self.confidence_level,
        }

    def get_model_info(self) -> Dict[str, Any]:
        info = super().get_model_info()
        info.update(
            {
                "display_name": "Prophet + XGBoost",
                "confidence_level": self.confidence_level,
                "artifact_path": str(self._path),
                "is_fitted": self._is_fitted,
            }
        )
        return info

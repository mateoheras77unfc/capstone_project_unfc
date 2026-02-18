"""
=============================================================================
LSTM FORECASTER - Long Short-Term Memory Neural Network for Price Prediction
=============================================================================

Architecture:
  Input (lookback_window, 1) → LSTM(64) → Dropout → LSTM(32) → Dropout
  → Dense(16, relu) → Dense(1) → scaled price [0,1]

Uncertainty is estimated from validation-set residuals, not a fixed %.
=============================================================================
"""

import logging
import warnings
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers

    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    warnings.warn("TensorFlow not installed — LSTM forecasting unavailable.")

from sklearn.preprocessing import MinMaxScaler
from .base_forecaster import BaseForecastor

logger = logging.getLogger(__name__)


class LSTMForecastor(BaseForecastor):
    """
    LSTM-based forecasting model for stock price prediction.

    Generates multi-step-ahead forecasts with confidence intervals
    derived from actual validation residuals.
    """

    def __init__(
        self,
        lookback_window: int = 20,
        epochs: int = 50,
        batch_size: int = 16,
        test_size: float = 0.2,
        confidence_level: float = 0.95,
        random_state: int = 42,
    ):
        if not TENSORFLOW_AVAILABLE:
            raise ImportError(
                "TensorFlow is required. Install with: pip install tensorflow"
            )

        self.lookback_window = lookback_window
        self.epochs = epochs
        self.batch_size = batch_size
        self.test_size = test_size
        self.confidence_level = confidence_level
        self.random_state = random_state

        self.model: Optional[keras.Model] = None
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self._scaled_prices: Optional[np.ndarray] = None
        self._prices: Optional[pd.Series] = None
        self._val_residual_std: float = 0.0
        self._freq_days: int = 7
        self._is_fitted = False

        tf.random.set_seed(random_state)
        np.random.seed(random_state)

    # ── fit ────────────────────────────────────────────────────────────────

    def fit(self, prices: pd.Series) -> None:
        min_needed = self.lookback_window + 1
        self._validate_prices(prices, min_samples=min_needed)

        logger.info("Fitting LSTM on %d samples", len(prices))
        self._prices = prices.copy()
        self._freq_days = self._infer_freq_days(prices.index)

        # Scale to [0, 1]
        arr = prices.values.reshape(-1, 1).astype(np.float64)
        self._scaled_prices = self.scaler.fit_transform(arr)

        # Build sequences
        X, y = self._create_sequences(self._scaled_prices)
        if len(X) == 0:
            raise ValueError(
                f"No sequences created — reduce lookback_window (currently {self.lookback_window})"
            )

        # Train / validation split (temporal, no shuffle)
        split = int(len(X) * (1 - self.test_size))
        X_train, y_train = X[:split], y[:split]
        X_val, y_val = X[split:], y[split:]

        # Build & train
        self._build_model()
        self.model.fit(
            X_train, y_train,
            epochs=self.epochs,
            batch_size=self.batch_size,
            validation_data=(X_val, y_val) if len(X_val) > 0 else None,
            verbose=0,
        )

        # Compute validation residual std (in original scale) for CI
        if len(X_val) > 0:
            preds_scaled = self.model.predict(X_val, verbose=0)
            preds = self.scaler.inverse_transform(preds_scaled).flatten()
            actuals = self.scaler.inverse_transform(y_val).flatten()
            self._val_residual_std = float(np.std(actuals - preds))
        else:
            # Fallback: 5% of price range
            self._val_residual_std = float(
                (prices.max() - prices.min()) * 0.05
            )

        self._is_fitted = True
        logger.info(
            "LSTM fitted — val residual std: %.4f", self._val_residual_std
        )

    # ── forecast ──────────────────────────────────────────────────────────

    def forecast(self, periods: int = 4) -> Dict[str, Any]:
        if not self._is_fitted or self.model is None:
            raise ValueError("Call fit() before forecast()")

        from scipy.stats import norm

        z = norm.ppf((1 + self.confidence_level) / 2)
        last_date = self._prices.index[-1]

        # Iterative multi-step prediction
        seq = self._scaled_prices[-self.lookback_window:].flatten().copy()
        raw_preds: List[float] = []

        for _ in range(periods):
            X_in = seq[-self.lookback_window:].reshape(
                1, self.lookback_window, 1
            )
            pred = self.model.predict(X_in, verbose=0)[0, 0]
            raw_preds.append(pred)
            seq = np.append(seq, pred)

        # Inverse-transform to original scale
        preds_arr = np.array(raw_preds).reshape(-1, 1)
        point_forecast = self.scaler.inverse_transform(preds_arr).flatten()

        # Build output
        dates: List[str] = []
        lower_bound: List[float] = []
        upper_bound: List[float] = []

        for i in range(periods):
            dt = last_date + timedelta(days=self._freq_days * (i + 1))
            dates.append(dt.isoformat())

            # Widen CI further into the future
            margin = z * self._val_residual_std * np.sqrt(i + 1)
            lower_bound.append(round(float(point_forecast[i] - margin), 4))
            upper_bound.append(round(float(point_forecast[i] + margin), 4))

        return {
            "dates": dates,
            "point_forecast": [round(float(v), 4) for v in point_forecast],
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "confidence_level": self.confidence_level,
        }

    # ── internals ─────────────────────────────────────────────────────────

    def _build_model(self) -> None:
        self.model = keras.Sequential([
            layers.LSTM(
                64,
                activation="relu",
                input_shape=(self.lookback_window, 1),
                return_sequences=True,
            ),
            layers.Dropout(0.2),
            layers.LSTM(32, activation="relu"),
            layers.Dropout(0.2),
            layers.Dense(16, activation="relu"),
            layers.Dense(1),
        ])
        self.model.compile(optimizer="adam", loss="mse", metrics=["mae"])

    def _create_sequences(
        self, data: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        X, y = [], []
        flat = data.flatten()
        for i in range(len(flat) - self.lookback_window):
            X.append(flat[i : i + self.lookback_window])
            y.append(flat[i + self.lookback_window])
        X_arr = np.array(X).reshape(-1, self.lookback_window, 1)
        y_arr = np.array(y).reshape(-1, 1)
        return X_arr, y_arr

    def get_model_info(self) -> Dict[str, Any]:
        info = super().get_model_info()
        info.update({
            "lookback_window": self.lookback_window,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "confidence_level": self.confidence_level,
            "is_fitted": self._is_fitted,
        })
        return info
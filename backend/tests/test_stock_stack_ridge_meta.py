"""
tests/test_stock_stack_ridge_meta.py
────────────────────────────────────
Tests for the stack (Ridge meta) forecaster module.

Run from backend directory:
    uv run pytest tests/test_stock_stack_ridge_meta.py -v
"""

import pytest
import pandas as pd
import numpy as np


class TestStockStackRidgeMetaModule:
    """Import and contract tests for analytics.forecasting.stock."""

    def test_module_imports(self) -> None:
        """analytics.forecasting.stock can be imported."""
        from analytics.forecasting.stock import (
            StackRidgeMetaForecaster,
            predict_stack_ridge_global,
        )
        from analytics.forecasting.stock.stack_ridge_meta import build_feature_df
        assert StackRidgeMetaForecaster is not None
        assert callable(predict_stack_ridge_global)
        assert callable(build_feature_df)

    def test_build_feature_df_returns_expected_shape(self) -> None:
        """build_feature_df returns (feat_df, cols_lstm, cols_lgb, target_cols) with required columns."""
        from analytics.forecasting.stock.stack_ridge_meta import (
            build_feature_df,
            FORECAST_HORIZON,
        )
        # Enough rows so after dropna (targets need 21 future rows) we have data
        n = 150
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        np.random.seed(42)
        close = 100.0 * np.exp(np.cumsum(np.random.randn(n) * 0.01))
        df = pd.DataFrame({
            "timestamp": dates,
            "close": close,
            "volume": np.random.randint(1_000_000, 10_000_000, size=n),
        })
        feat_df, cols_lstm, cols_lgb, target_cols = build_feature_df(df)
        assert feat_df is not None and len(feat_df) > 0
        assert len(cols_lstm) == 9  # 5 ret_lag + volume_lag_1, rsi, macd_line, macd_signal
        assert len(cols_lgb) == 6
        assert len(target_cols) == FORECAST_HORIZON
        for c in cols_lstm + cols_lgb:
            assert c in feat_df.columns

    def test_predict_stack_ridge_global_empty_without_artifact(self) -> None:
        """predict_stack_ridge_global returns [] when global_stack is missing linear_models or meta_scaler."""
        from analytics.forecasting.stock import predict_stack_ridge_global
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=50, freq="D"),
            "close": 100.0 + np.arange(50) * 0.5,
        })
        empty_stack = {}
        assert predict_stack_ridge_global(df, 21, empty_stack) == []
        assert predict_stack_ridge_global(df, 21, {"linear_models": []}) == []

    def test_forecaster_fit_requires_context(self) -> None:
        """StackRidgeMetaForecaster.fit() raises if context_df too short or missing required columns."""
        from analytics.forecasting.stock import StackRidgeMetaForecaster
        forecaster = StackRidgeMetaForecaster()
        # Too few rows
        short = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=10, freq="D"),
            "close": [100.0] * 10,
        })
        with pytest.raises(ValueError, match="at least"):
            forecaster.fit(short)
        # Missing timestamp
        with pytest.raises(ValueError, match="timestamp"):
            forecaster.fit(pd.DataFrame({"close": [100.0, 101.0]}))

    def test_forecaster_forecast_requires_fit(self) -> None:
        """StackRidgeMetaForecaster.forecast() raises if fit() was not called."""
        from analytics.forecasting.stock import StackRidgeMetaForecaster
        forecaster = StackRidgeMetaForecaster()
        with pytest.raises(ValueError, match="fit"):
            forecaster.forecast(periods=4)


class TestStockStackRidgeMetaWithArtifact:
    """Tests that require the artifact (joblib + LSTM). Skip if artifact missing."""

    @pytest.fixture
    def artifact_path(self):
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent / "analytics" / "forecasting" / "stock" / "stack_ridge_meta_logreturn_artifact.joblib"
        return p

    def test_forecaster_full_flow_when_artifact_present(self, artifact_path) -> None:
        """If artifact exists, fit + forecast returns expected keys and lengths."""
        if not artifact_path.exists():
            pytest.skip("Stack artifact not found; run 98c notebook export cell.")
        pytest.importorskip("lightgbm", reason="lightgbm required to load artifact")
        from analytics.forecasting.stock import StackRidgeMetaForecaster
        n = 100
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        np.random.seed(123)
        close = 100.0 * np.exp(np.cumsum(np.random.randn(n) * 0.01))
        context_df = pd.DataFrame({
            "timestamp": dates,
            "close": close,
            "volume": np.random.randint(1_000_000, 5_000_000, size=n),
        })
        forecaster = StackRidgeMetaForecaster(artifact_path=artifact_path)
        forecaster.fit(context_df)
        result = forecaster.forecast(periods=4)
        assert "dates" in result
        assert "point_forecast" in result
        assert "lower_bound" in result
        assert "upper_bound" in result
        assert len(result["dates"]) == 4
        assert len(result["point_forecast"]) == 4
        assert all(isinstance(x, (int, float)) for x in result["point_forecast"])

"""
tests/test_stack_xgb_stock.py
Tests for XGB stack (98g bundle) forecaster.

Run from backend:
    uv run pytest tests/test_stack_xgb_stock.py -v
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


class TestStackXgbStockModule:
    def test_module_imports(self) -> None:
        from analytics.forecasting.stock import (
            XGBStackForecaster,
            build_feature_df,
            default_bundle_root,
            load_stack_bundle,
            predict_stack_global,
        )

        assert XGBStackForecaster is not None
        assert callable(build_feature_df)
        assert callable(predict_stack_global)
        assert default_bundle_root() is not None

    def test_build_feature_df_shape(self) -> None:
        from analytics.forecasting.stock.stack_xgb_stock import (
            FORECAST_HORIZON,
            build_feature_df,
        )

        n = 120
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        np.random.seed(42)
        close = 100.0 * np.exp(np.cumsum(np.random.randn(n) * 0.01))
        df = pd.DataFrame(
            {
                "timestamp": dates,
                "close": close,
                "volume": np.random.randint(1_000_000, 10_000_000, size=n),
            }
        )
        feat_df, cols_tcn, cols_lgb, target_cols = build_feature_df(df)
        assert len(feat_df) > 0
        assert len(target_cols) == FORECAST_HORIZON
        for c in cols_tcn + cols_lgb:
            assert c in feat_df.columns

    def test_predict_empty_stack(self) -> None:
        from analytics.forecasting.stock import predict_stack_global

        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=120, freq="D"),
                "close": 100.0 + np.arange(120) * 0.1,
            }
        )
        assert predict_stack_global(df, 7, {}) == []
        assert predict_stack_global(df, 7, {"linear_models": []}) == []


class TestXGBStackForecasterContract:
    def test_fit_requires_timestamp(self) -> None:
        from analytics.forecasting.stock import XGBStackForecaster

        f = XGBStackForecaster()
        with pytest.raises(ValueError, match="timestamp"):
            f.fit(pd.DataFrame({"close": [100.0, 101.0]}))

    def test_forecast_requires_fit(self) -> None:
        from analytics.forecasting.stock import XGBStackForecaster

        f = XGBStackForecaster()
        with pytest.raises(ValueError, match="fit"):
            f.forecast(periods=3)


class TestXGBStackForecasterWithBundle:
    """Requires stack_bundle.joblib + ML deps."""

    @pytest.fixture
    def bundle_root(self) -> Path:
        from analytics.forecasting.stock.stack_xgb_stock import default_bundle_root

        return default_bundle_root()

    def test_load_and_forecast_when_bundle_present(self, bundle_root: Path) -> None:
        joblib_p = bundle_root / "artifacts" / "stack_bundle.joblib"
        if not joblib_p.exists():
            pytest.skip("98g stack bundle not found at default_bundle_root()")
        pytest.importorskip("lightgbm")
        pytest.importorskip("xgboost")
        pytest.importorskip("tensorflow")

        from analytics.forecasting.stock import XGBStackForecaster

        n = 150
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        np.random.seed(7)
        close = 100.0 * np.exp(np.cumsum(np.random.randn(n) * 0.01))
        ctx = pd.DataFrame(
            {
                "timestamp": dates,
                "close": close,
                "volume": np.random.randint(1_000_000, 5_000_000, size=n),
            }
        )
        f = XGBStackForecaster(bundle_root=bundle_root)
        f.fit(ctx)
        out = f.forecast(periods=4)
        assert "dates" in out and "point_forecast" in out
        assert len(out["point_forecast"]) == 4

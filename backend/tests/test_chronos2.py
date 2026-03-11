"""
tests/test_chronos2.py
──────────────────────
Tests for the Chronos-2 forecasting module.

Run from backend directory:
    uv run pytest tests/test_chronos2.py -v

With Chronos-2 installed, a full forecast test runs (may download model on first run).
Without it, import and contract tests still run; the forecast test is skipped.
"""

import pytest
import pandas as pd


class TestChronos2Module:
    """Basic import and contract tests."""

    def test_module_imports(self) -> None:
        """analytics.forecasting.chronos2 can be imported."""
        from analytics.forecasting import chronos2

        assert hasattr(chronos2, "forecast")
        assert callable(chronos2.forecast)

    def test_forecast_returns_expected_shape(self) -> None:
        """forecast() returns dict with dates, point_forecast, lower_bound, upper_bound, model_info."""
        pytest.importorskip("chronos", reason="chronos-forecasting not installed")

        from analytics.forecasting import chronos2

        # Minimal series: 64 points (Chronos typically needs a minimum context)
        n = 64
        dates = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
        prices = pd.Series([100.0 + 0.1 * i for i in range(n)], index=dates, name="close")

        result = chronos2.forecast(
            prices,
            periods=4,
            confidence_level=0.95,
            interval="1d",
            device="cpu",
        )

        assert "dates" in result
        assert "point_forecast" in result
        assert "lower_bound" in result
        assert "upper_bound" in result
        assert "model_info" in result
        assert len(result["dates"]) == 4
        assert len(result["point_forecast"]) == 4
        assert len(result["lower_bound"]) == 4
        assert len(result["upper_bound"]) == 4
        assert result["model_info"].get("model") == "chronos-2"

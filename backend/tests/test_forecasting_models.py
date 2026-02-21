"""
tests/test_forecasting_models.py
──────────────────────────────────
Unit tests for analytics/forecasting model classes.

Coverage
--------
BaseForecastor._validate_prices   – type, index, size, NaN guards.
BaseForecastor._infer_freq_days   – weekly/monthly/sub-day series.
SimpleForecaster.fit              – happy path + error paths.
SimpleForecaster.forecast         – shape, ordering, date validity,
                                    widen-over-horizon, CI echo.
SimpleForecaster.get_model_info   – expected keys and values.
LSTMForecastor                    – ImportError path when TF absent.

These tests are pure unit tests — no network, no database.
Run with::

    cd backend
    uv run pytest tests/test_forecasting_models.py -v
"""

import numpy as np
import pandas as pd
import pytest

from analytics.forecasting.base import BaseForecastor, SimpleForecaster


# ── helpers ────────────────────────────────────────────────────────────────────


def _weekly(n: int = 60, start: str = "2021-01-04") -> pd.Series:
    """
    Build a synthetic weekly price pd.Series for testing.

    Args:
        n:     Number of data points.
        start: ISO date string for the first Monday.

    Returns:
        pd.Series with weekly DatetimeIndex, oldest → newest.
    """
    dates = pd.date_range(start=start, periods=n, freq="W-MON")
    rng = np.random.default_rng(42)
    prices = 100.0 + np.cumsum(rng.normal(0, 1, n))
    return pd.Series(prices, index=dates, name="close")


def _monthly(n: int = 30, start: str = "2021-01-01") -> pd.Series:
    """
    Build a synthetic monthly price pd.Series for testing.

    Args:
        n:     Number of data points.
        start: ISO date string for the first month-start.

    Returns:
        pd.Series with monthly DatetimeIndex, oldest → newest.
    """
    dates = pd.date_range(start=start, periods=n, freq="MS")
    rng = np.random.default_rng(99)
    prices = 200.0 + np.cumsum(rng.normal(0, 2, n))
    return pd.Series(prices, index=dates, name="close")


# ── BaseForecastor._validate_prices ───────────────────────────────────────────


class TestValidatePrices:
    """Unit tests for BaseForecastor._validate_prices."""

    def test_raises_type_error_for_list_input(self) -> None:
        """Should raise TypeError when a plain list is passed instead of pd.Series."""
        with pytest.raises(TypeError, match="pandas Series"):
            BaseForecastor._validate_prices([1.0, 2.0, 3.0, 4.0, 5.0])

    def test_raises_type_error_for_wrong_index_type(self) -> None:
        """Should raise TypeError when Series index is a RangeIndex, not DatetimeIndex."""
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])  # default RangeIndex
        with pytest.raises(TypeError, match="DatetimeIndex"):
            BaseForecastor._validate_prices(s)

    def test_raises_value_error_for_too_few_rows(self) -> None:
        """Should raise ValueError when fewer rows than min_samples are supplied."""
        s = _weekly(n=3)
        with pytest.raises(ValueError, match="at least"):
            BaseForecastor._validate_prices(s, min_samples=5)

    def test_raises_value_error_for_nan_values(self) -> None:
        """Should raise ValueError when any value in the series is NaN."""
        s = _weekly(n=10)
        s.iloc[4] = float("nan")
        with pytest.raises(ValueError, match="NaN"):
            BaseForecastor._validate_prices(s)

    def test_passes_valid_series_with_exact_minimum(self) -> None:
        """Should not raise when the series exactly meets the minimum requirement."""
        s = _weekly(n=5)
        BaseForecastor._validate_prices(s, min_samples=5)  # no exception raised

    def test_passes_valid_series_above_minimum(self) -> None:
        """Should not raise when the series exceeds the minimum requirement."""
        BaseForecastor._validate_prices(_weekly(n=60))


# ── BaseForecastor._infer_freq_days ───────────────────────────────────────────


class TestInferFreqDays:
    """Unit tests for BaseForecastor._infer_freq_days."""

    def test_weekly_series_returns_seven_days(self) -> None:
        """Weekly (Mon–Mon) data should infer a 7-day step."""
        freq = BaseForecastor._infer_freq_days(_weekly(n=20).index)
        assert freq == 7

    def test_monthly_series_returns_approx_30_days(self) -> None:
        """Monthly data should infer a step in the 28–31 day range."""
        freq = BaseForecastor._infer_freq_days(_monthly(n=20).index)
        assert 28 <= freq <= 31

    def test_minimum_return_value_is_one(self) -> None:
        """Even for sub-day data, the returned step should never be less than 1."""
        # Hour-frequency data → diffs < 1 day → floor to 1
        dates = pd.date_range("2021-01-01", periods=5, freq="h")
        freq = BaseForecastor._infer_freq_days(dates)
        assert freq >= 1


# ── SimpleForecaster.fit ──────────────────────────────────────────────────────


class TestSimpleForecasterFit:
    """Unit tests for SimpleForecaster.fit()."""

    def test_fit_marks_model_as_fitted(self) -> None:
        """fit() should set _is_fitted to True on success."""
        model = SimpleForecaster()
        model.fit(_weekly(n=30))
        assert model._is_fitted is True

    def test_fit_raises_on_too_few_samples(self) -> None:
        """fit() should raise ValueError when fewer than 5 samples are provided."""
        with pytest.raises(ValueError, match="at least"):
            SimpleForecaster().fit(_weekly(n=3))

    def test_fit_raises_on_nan_in_series(self) -> None:
        """fit() should refuse a series that contains NaN values."""
        prices = _weekly(n=10)
        prices.iloc[6] = float("nan")
        with pytest.raises(ValueError, match="NaN"):
            SimpleForecaster().fit(prices)

    def test_fit_records_ewm_and_residual_std(self) -> None:
        """After fit(), _ewm_value and _residual_std should be finite numbers."""
        model = SimpleForecaster()
        model.fit(_weekly(n=40))
        assert np.isfinite(model._ewm_value)
        assert np.isfinite(model._residual_std)
        assert model._residual_std >= 0.0


# ── SimpleForecaster.forecast ─────────────────────────────────────────────────


class TestSimpleForecasterForecast:
    """Unit tests for SimpleForecaster.forecast()."""

    @pytest.fixture(autouse=True)
    def fitted_model(self) -> SimpleForecaster:
        """
        Return a SimpleForecaster already fitted on 40 weekly data points.

        Shared by every test method in this class via autouse.
        """
        self.model = SimpleForecaster(confidence_level=0.95)
        self.model.fit(_weekly(n=40))
        return self.model

    def test_raises_if_called_before_fit(self) -> None:
        """forecast() must raise ValueError when model has not been fitted yet."""
        unfitted = SimpleForecaster()
        with pytest.raises(ValueError, match="fit()"):
            unfitted.forecast(periods=4)

    def test_output_lists_have_correct_length(self) -> None:
        """All four output lists should have exactly ``periods`` entries."""
        periods = 6
        result = self.model.forecast(periods=periods)
        assert len(result["dates"]) == periods
        assert len(result["point_forecast"]) == periods
        assert len(result["lower_bound"]) == periods
        assert len(result["upper_bound"]) == periods

    def test_lower_le_point_le_upper_for_every_step(self) -> None:
        """lower_bound ≤ point_forecast ≤ upper_bound must hold at every horizon."""
        result = self.model.forecast(periods=4)
        for step, (lo, pt, hi) in enumerate(
            zip(result["lower_bound"], result["point_forecast"], result["upper_bound"]),
            start=1,
        ):
            assert lo <= pt <= hi, (
                f"CI ordering violated at step {step}: "
                f"lo={lo:.4f}, pt={pt:.4f}, hi={hi:.4f}"
            )

    def test_confidence_interval_widens_over_horizon(self) -> None:
        """Interval width must be non-decreasing as the horizon grows."""
        result = self.model.forecast(periods=8)
        widths = [
            hi - lo
            for lo, hi in zip(result["lower_bound"], result["upper_bound"])
        ]
        for i in range(1, len(widths)):
            assert widths[i] >= widths[i - 1] - 1e-9, (
                f"CI narrowed at step {i}: width={widths[i]:.6f} "
                f"< previous={widths[i - 1]:.6f}"
            )

    def test_forecast_dates_are_valid_iso_strings(self) -> None:
        """Every date in the output should be parseable as a valid ISO-8601 string."""
        result = self.model.forecast(periods=4)
        for d in result["dates"]:
            pd.to_datetime(d)  # raises if malformed

    def test_forecast_dates_are_strictly_after_training_data(self) -> None:
        """All forecast dates must be later than the last training timestamp."""
        prices = _weekly(n=40)
        model = SimpleForecaster()
        model.fit(prices)
        result = model.forecast(periods=4)
        last_train_date = prices.index[-1]
        for d in result["dates"]:
            assert pd.to_datetime(d) > last_train_date, (
                f"Forecast date {d} is not after training end {last_train_date}"
            )

    def test_confidence_level_is_echoed_in_result(self) -> None:
        """result['confidence_level'] must match the value the model was configured with."""
        result = self.model.forecast(periods=4)
        assert result["confidence_level"] == pytest.approx(0.95)

    def test_point_forecast_is_constant_ewm_projection(self) -> None:
        """EWM baseline should project the same value for every future step."""
        result = self.model.forecast(periods=5)
        # All point estimates should be identical (flat EWM projection)
        assert len(set(result["point_forecast"])) == 1


# ── SimpleForecaster.get_model_info ──────────────────────────────────────────


class TestSimpleForecasterModelInfo:
    """Unit tests for SimpleForecaster.get_model_info()."""

    def test_unfitted_info_has_expected_keys(self) -> None:
        """get_model_info() should return a dict with required keys even before fit."""
        info = SimpleForecaster(span=15).get_model_info()
        assert info["model_name"] == "SimpleForecaster"
        assert info["version"] == "1.0"
        assert "span" in info
        assert "is_fitted" in info

    def test_fitted_info_has_residual_std(self) -> None:
        """After fit(), residual_std should be a non-negative float."""
        model = SimpleForecaster(span=15)
        model.fit(_weekly(n=30))
        info = model.get_model_info()
        assert info["is_fitted"] is True
        assert info["residual_std"] is not None
        assert info["residual_std"] >= 0.0

    def test_span_reflected_in_model_info(self) -> None:
        """The span passed at construction should appear in get_model_info()."""
        model = SimpleForecaster(span=10)
        info = model.get_model_info()
        assert info["span"] == 10


# ── LSTMForecastor (TensorFlow absent) ───────────────────────────────────────


class TestLSTMForecastorNoTensorFlow:
    """
    Tests for LSTMForecastor when TensorFlow is not installed.

    These tests always run and validate the graceful ImportError path.
    If TensorFlow is installed in the environment, the tests are skipped
    so they do not interfere with TF-available CI runs.
    """

    def test_instantiation_raises_import_error(self) -> None:
        """LSTMForecastor() must raise ImportError with a helpful message."""
        try:
            import tensorflow  # noqa: F401

            pytest.skip(
                "TensorFlow is installed — skipping no-TF ImportError test"
            )
        except ImportError:
            pass

        from analytics.forecasting.lstm import LSTMForecastor

        with pytest.raises(ImportError, match="TensorFlow"):
            LSTMForecastor()

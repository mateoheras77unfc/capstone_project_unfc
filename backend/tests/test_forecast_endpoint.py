"""
tests/test_forecast_endpoint.py
─────────────────────────────────
HTTP-level tests for POST /api/v1/forecast/{base,lstm,prophet}.

These tests use the ``app_client`` (async HTTPX) and ``mock_db`` fixtures
from ``conftest.py`` so no real Supabase connection is required.

Coverage
--------
/forecast/base
    - 404 when symbol is unknown.
    - 404 when symbol exists but has no price rows.
    - 422 when 1wk interval has fewer than 52 rows.
    - 422 when 1mo interval has fewer than 24 rows.
    - 200 happy path with correct response shape and interval metadata.
    - Symbol normalised to upper-case in the response.
    - 422 for invalid request body (empty symbol, bad periods).

/forecast/lstm
    - 503 when TensorFlow is not installed (always true in CI).

_horizon_label helper (imported directly)
    - 4 × 1wk → "4 weeks (~1 month ahead)"
    - 52 × 1wk → "52 weeks (~1.0 year … ahead)"
    - 1 × 1mo → singular "month"
    - 12 × 1mo → yearly label

Run with::

    cd backend
    uv run pytest tests/test_forecast_endpoint.py -v
"""

import pytest

from tests.conftest import configure_forecast_mock


# ── /forecast/base ────────────────────────────────────────────────────────────


class TestBaseForecastEndpoint:
    """HTTP tests for POST /api/v1/forecast/base."""

    async def test_404_when_symbol_not_found(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """Unknown symbol (asset not in DB) should return 404."""
        configure_forecast_mock(mock_db, asset_rows=[], price_rows=[])
        resp = await app_client.post(
            "/api/v1/forecast/base",
            json={"symbol": "UNKNOWN", "interval": "1wk"},
        )
        assert resp.status_code == 404
        assert "UNKNOWN" in resp.json()["detail"]

    async def test_404_when_no_price_rows(
        self, app_client, mock_db
    ) -> None:
        """Symbol found in assets table but has no price rows → 404."""
        configure_forecast_mock(
            mock_db,
            asset_rows=[{"id": "abc-123"}],
            price_rows=[],
        )
        resp = await app_client.post(
            "/api/v1/forecast/base",
            json={"symbol": "AAPL", "interval": "1wk"},
        )
        assert resp.status_code == 404
        assert "AAPL" in resp.json()["detail"]

    async def test_422_weekly_interval_too_few_rows(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """1wk interval with fewer than 52 rows should return 422."""
        configure_forecast_mock(
            mock_db,
            asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=20),  # 20 < 52
        )
        resp = await app_client.post(
            "/api/v1/forecast/base",
            json={"symbol": "AAPL", "interval": "1wk"},
        )
        assert resp.status_code == 422
        # Error message should mention the minimum (52) and actual count (20)
        detail = resp.json()["detail"]
        assert "52" in detail
        assert "20" in detail

    async def test_422_monthly_interval_too_few_rows(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """1mo interval with fewer than 24 rows should return 422."""
        configure_forecast_mock(
            mock_db,
            asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=10, freq="MS"),  # 10 < 24
        )
        resp = await app_client.post(
            "/api/v1/forecast/base",
            json={"symbol": "AAPL", "interval": "1mo"},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "24" in detail
        assert "10" in detail

    async def test_200_happy_path_response_shape(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """With ≥52 weekly rows the endpoint should return 200 and all fields."""
        configure_forecast_mock(
            mock_db,
            asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=60),
        )
        resp = await app_client.post(
            "/api/v1/forecast/base",
            json={"symbol": "AAPL", "interval": "1wk", "periods": 4},
        )
        assert resp.status_code == 200
        body = resp.json()

        # Interval metadata fields
        assert body["symbol"] == "AAPL"
        assert body["interval"] == "1wk"
        assert body["periods_ahead"] == 4
        assert "weeks" in body["forecast_horizon_label"]
        assert body["data_points_used"] == 60

        # Forecast output shape
        assert len(body["dates"]) == 4
        assert len(body["point_forecast"]) == 4
        assert len(body["lower_bound"]) == 4
        assert len(body["upper_bound"]) == 4

        # model_info should be present
        assert isinstance(body["model_info"], dict)

    async def test_200_confidence_bounds_ordering(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """lower_bound ≤ point_forecast ≤ upper_bound must hold for every step."""
        configure_forecast_mock(
            mock_db,
            asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=60),
        )
        resp = await app_client.post(
            "/api/v1/forecast/base",
            json={"symbol": "AAPL", "interval": "1wk", "periods": 6},
        )
        assert resp.status_code == 200
        body = resp.json()
        for step, (lo, pt, hi) in enumerate(
            zip(body["lower_bound"], body["point_forecast"], body["upper_bound"]),
            start=1,
        ):
            assert lo <= pt <= hi, (
                f"CI ordering violated at step {step}: "
                f"lo={lo}, pt={pt}, hi={hi}"
            )

    async def test_symbol_normalised_to_uppercase(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """Lowercase symbol in the request body should be uppercased in the response."""
        configure_forecast_mock(
            mock_db,
            asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=60),
        )
        resp = await app_client.post(
            "/api/v1/forecast/base",
            json={"symbol": "aapl", "interval": "1wk", "periods": 4},
        )
        assert resp.status_code == 200
        assert resp.json()["symbol"] == "AAPL"

    async def test_422_for_empty_symbol(
        self, app_client, mock_db
    ) -> None:
        """An empty symbol string should be rejected with 422 before any DB call."""
        resp = await app_client.post(
            "/api/v1/forecast/base",
            json={"symbol": "", "interval": "1wk"},
        )
        assert resp.status_code == 422

    async def test_422_for_periods_out_of_range(
        self, app_client, mock_db
    ) -> None:
        """periods=0 is below the allowed minimum (ge=1) and should fail validation."""
        resp = await app_client.post(
            "/api/v1/forecast/base",
            json={"symbol": "AAPL", "periods": 0},
        )
        assert resp.status_code == 422

    async def test_horizon_label_in_response(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """forecast_horizon_label should mention the periods and interval unit."""
        configure_forecast_mock(
            mock_db,
            asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=60),
        )
        resp = await app_client.post(
            "/api/v1/forecast/base",
            json={"symbol": "AAPL", "interval": "1wk", "periods": 8},
        )
        assert resp.status_code == 200
        label = resp.json()["forecast_horizon_label"]
        assert "8 weeks" in label
        assert "month" in label  # ~2 months ahead

    async def test_data_points_used_matches_db_rows(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """data_points_used in the response must equal the number of DB rows returned."""
        rows = price_rows_factory(n=75)
        configure_forecast_mock(
            mock_db,
            asset_rows=[{"id": "abc-123"}],
            price_rows=rows,
        )
        resp = await app_client.post(
            "/api/v1/forecast/base",
            json={"symbol": "AAPL", "interval": "1wk", "periods": 4},
        )
        assert resp.status_code == 200
        assert resp.json()["data_points_used"] == 75

    async def test_default_interval_is_weekly(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """Omitting ``interval`` from the request should default to ``1wk``."""
        configure_forecast_mock(
            mock_db,
            asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=60),
        )
        resp = await app_client.post(
            "/api/v1/forecast/base",
            json={"symbol": "AAPL", "periods": 4},  # no interval key
        )
        assert resp.status_code == 200
        assert resp.json()["interval"] == "1wk"


# ── /forecast/lstm ────────────────────────────────────────────────────────────


class TestLSTMForecastEndpoint:
    """HTTP tests for POST /api/v1/forecast/lstm."""

    async def test_503_when_tensorflow_not_installed(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """
        503 should be returned when TensorFlow is absent.

        This test is always run in the default CI environment where TF is not
        installed. It is skipped automatically if TF happens to be present.
        """
        try:
            import tensorflow  # noqa: F401

            pytest.skip(
                "TensorFlow is installed — skipping 503 ImportError test"
            )
        except ImportError:
            pass

        configure_forecast_mock(
            mock_db,
            asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=60),
        )
        resp = await app_client.post(
            "/api/v1/forecast/lstm",
            json={"symbol": "AAPL", "interval": "1wk", "periods": 4},
        )
        assert resp.status_code == 503
        assert "TensorFlow" in resp.json()["detail"]

    async def test_404_propagated_for_unknown_symbol(
        self, app_client, mock_db
    ) -> None:
        """The lstm endpoint should also return 404 for an unknown symbol."""
        configure_forecast_mock(mock_db, asset_rows=[], price_rows=[])
        resp = await app_client.post(
            "/api/v1/forecast/lstm",
            json={"symbol": "NOSUCHSYM", "interval": "1wk"},
        )
        assert resp.status_code == 404


# ── /forecast/prophet ─────────────────────────────────────────────────────────


class TestProphetForecastEndpoint:
    """HTTP tests for POST /api/v1/forecast/prophet."""

    async def test_404_propagated_for_unknown_symbol(
        self, app_client, mock_db
    ) -> None:
        """The prophet endpoint should also return 404 for an unknown symbol."""
        configure_forecast_mock(mock_db, asset_rows=[], price_rows=[])
        resp = await app_client.post(
            "/api/v1/forecast/prophet",
            json={"symbol": "NOSUCHSYM", "interval": "1wk"},
        )
        assert resp.status_code == 404


# ── _horizon_label unit tests ─────────────────────────────────────────────────


class TestHorizonLabel:
    """
    Unit tests for the _horizon_label() helper imported directly.

    These are pure-function tests — no HTTP or database interaction.
    """

    def test_4_weekly_periods_has_month_in_label(self) -> None:
        """4 × 1wk should produce a label mentioning 'weeks' and 'month'."""
        from app.api.v1.endpoints.forecast import _horizon_label

        label = _horizon_label(4, "1wk")
        assert "4 weeks" in label
        assert "month" in label

    def test_52_weekly_periods_has_year_in_label(self) -> None:
        """52 × 1wk should produce a label mentioning 'year'."""
        from app.api.v1.endpoints.forecast import _horizon_label

        label = _horizon_label(52, "1wk")
        assert "52 weeks" in label
        assert "year" in label

    def test_1_monthly_period_uses_singular_month(self) -> None:
        """1 × 1mo should use the singular 'month' (not 'months')."""
        from app.api.v1.endpoints.forecast import _horizon_label

        label = _horizon_label(1, "1mo")
        assert "1 month" in label

    def test_12_monthly_periods_has_year_in_label(self) -> None:
        """12 × 1mo should produce a label mentioning 'year'."""
        from app.api.v1.endpoints.forecast import _horizon_label

        label = _horizon_label(12, "1mo")
        assert "12 months" in label
        assert "year" in label

    def test_label_format_starts_with_periods_and_unit(self) -> None:
        """Label should start with '<N> <unit>'."""
        from app.api.v1.endpoints.forecast import _horizon_label

        label = _horizon_label(6, "1wk")
        assert label.startswith("6 weeks")

    def test_label_contains_parenthetical_approximation(self) -> None:
        """Label should contain a parenthetical '(~...' approximation."""
        from app.api.v1.endpoints.forecast import _horizon_label

        label = _horizon_label(4, "1wk")
        assert "(~" in label

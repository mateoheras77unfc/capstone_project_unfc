"""
tests/test_analyze_endpoint.py
────────────────────────────────
HTTP-level tests for POST /api/v1/analyze/{symbol}.

The analyze endpoint combines auto-sync + forecasting in one request:
  1. Check DB for symbol.
  2. If missing → auto-sync from Yahoo Finance.
  3. Validate minimum row count for the chosen interval.
  4. Run the forecast model.
  5. Return sync metadata + full forecast.

Test strategy
-------------
- All Supabase queries are mocked via ``configure_analyze_mock`` from
  ``conftest.py`` — no real DB connection is made.
- ``DataCoordinator.sync_asset`` is patched at the module level in the
  analyze endpoint so no real yfinance call is made.
- Each test class focuses on a single concern (auto-sync path, already-
  cached path, validation, error propagation).

Run with::

    cd backend
    uv run pytest tests/test_analyze_endpoint.py -v
"""

from unittest.mock import patch

import pytest

from tests.conftest import configure_analyze_mock

# Patch target — the coordinator instance inside the analyze module.
_SYNC_PATCH = "app.api.v1.endpoints.analyze._coordinator.sync_asset"


# ── Auto-sync path (symbol NOT in DB) ─────────────────────────────────────────


class TestAnalyzeAutoSync:
    """Tests for the case where the symbol is new and must be synced first."""

    async def test_sync_is_triggered_for_new_symbol(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """
        When the symbol is absent from the DB, auto-sync should run and
        ``sync.performed`` should be ``True`` in the response.
        """
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[],                     # not found → trigger sync
            second_asset_rows=[{"id": "abc-123"}],   # found after sync
            price_rows=price_rows_factory(n=60),
        )
        with patch(_SYNC_PATCH, return_value=60) as mock_sync:
            resp = await app_client.post("/api/v1/analyze/AMZN", json={})

        assert resp.status_code == 200
        body = resp.json()
        assert body["sync"]["performed"] is True
        assert body["sync"]["rows_synced"] == 60
        assert "60 rows written" in body["sync"]["message"]
        # Coordinator must have been called exactly once
        mock_sync.assert_called_once_with("AMZN", "stock", "1wk")

    async def test_symbol_is_normalised_before_sync(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """
        Lower-case or mixed-case symbols should be upper-cased before sync
        and reflected upper-case in the response.
        """
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[],
            second_asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=60),
        )
        with patch(_SYNC_PATCH, return_value=60):
            resp = await app_client.post("/api/v1/analyze/aapl", json={})

        assert resp.status_code == 200
        assert resp.json()["symbol"] == "AAPL"

    async def test_rows_synced_present_in_response(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """rows_synced in the sync summary must match what the coordinator returned."""
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[],
            second_asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=60),
        )
        with patch(_SYNC_PATCH, return_value=1502):
            resp = await app_client.post("/api/v1/analyze/TSLA", json={})

        assert resp.status_code == 200
        assert resp.json()["sync"]["rows_synced"] == 1502

    async def test_404_when_yfinance_has_no_data(
        self, app_client, mock_db
    ) -> None:
        """
        When the coordinator raises ValueError (yfinance returned nothing),
        the endpoint should return 404 with a helpful message.
        """
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[],
            second_asset_rows=[],
            price_rows=[],
        )
        with patch(_SYNC_PATCH, side_effect=ValueError("yfinance returned no data")):
            resp = await app_client.post("/api/v1/analyze/BADSYM", json={})

        assert resp.status_code == 404
        assert "BADSYM" in resp.json()["detail"]

    async def test_503_when_supabase_unreachable_during_sync(
        self, app_client, mock_db
    ) -> None:
        """RuntimeError from the coordinator (DB problem) should map to 503."""
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[],
            second_asset_rows=[],
            price_rows=[],
        )
        with patch(
            _SYNC_PATCH,
            side_effect=RuntimeError("Failed to resolve asset in Supabase"),
        ):
            resp = await app_client.post("/api/v1/analyze/AMZN", json={})

        assert resp.status_code == 503


# ── Already-cached path (symbol already in DB) ────────────────────────────────


class TestAnalyzeAlreadyCached:
    """Tests for the case where the symbol already exists in the database."""

    async def test_sync_is_skipped_when_symbol_exists(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """
        When the symbol is already in the DB, the coordinator must NOT be
        called and ``sync.performed`` should be ``False``.
        """
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[{"id": "abc-123"}],   # found immediately
            second_asset_rows=[{"id": "abc-123"}],  # also found in _fetch_prices
            price_rows=price_rows_factory(n=60),
        )
        with patch(_SYNC_PATCH) as mock_sync:
            resp = await app_client.post("/api/v1/analyze/AAPL", json={})

        assert resp.status_code == 200
        body = resp.json()
        assert body["sync"]["performed"] is False
        assert body["sync"]["rows_synced"] == 0
        assert "skipped" in body["sync"]["message"]
        mock_sync.assert_not_called()

    async def test_data_points_used_matches_db_rows(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """data_points_used must reflect the actual number of rows fetched."""
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[{"id": "abc-123"}],
            second_asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=80),
        )
        with patch(_SYNC_PATCH):
            resp = await app_client.post("/api/v1/analyze/AAPL", json={})

        assert resp.status_code == 200
        assert resp.json()["data_points_used"] == 80


# ── Forecast response shape and metadata ─────────────────────────────────────


class TestAnalyzeForecastOutput:
    """Tests for the forecast portion of the AnalyzeResponse."""

    async def test_200_full_response_schema(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """All required fields must be present in a successful response."""
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[{"id": "abc-123"}],
            second_asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=60),
        )
        with patch(_SYNC_PATCH):
            resp = await app_client.post(
                "/api/v1/analyze/AAPL",
                json={"interval": "1wk", "periods": 4, "model": "base"},
            )

        assert resp.status_code == 200
        body = resp.json()

        # Sync block
        assert "sync" in body
        assert "performed" in body["sync"]
        assert "rows_synced" in body["sync"]
        assert "message" in body["sync"]

        # Forecast metadata
        assert body["symbol"] == "AAPL"
        assert body["interval"] == "1wk"
        assert body["model"] == "base"
        assert body["periods_ahead"] == 4
        assert "weeks" in body["forecast_horizon_label"]
        assert body["data_points_used"] == 60

        # Forecast arrays
        assert len(body["dates"]) == 4
        assert len(body["point_forecast"]) == 4
        assert len(body["lower_bound"]) == 4
        assert len(body["upper_bound"]) == 4
        assert isinstance(body["model_info"], dict)

    async def test_ci_ordering_lower_le_point_le_upper(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """lower ≤ point ≤ upper must hold for every forecast step."""
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[{"id": "abc-123"}],
            second_asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=60),
        )
        with patch(_SYNC_PATCH):
            resp = await app_client.post(
                "/api/v1/analyze/AAPL",
                json={"periods": 8},
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

    async def test_interval_reflected_in_response(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """The interval from the request must be echoed in the response."""
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[{"id": "abc-123"}],
            second_asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=30, freq="MS"),
        )
        with patch(_SYNC_PATCH):
            resp = await app_client.post(
                "/api/v1/analyze/AAPL",
                json={"interval": "1mo", "periods": 4},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["interval"] == "1mo"
        assert "months" in body["forecast_horizon_label"]

    async def test_model_reflected_in_response(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """The model name from the request must be echoed in the response."""
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[{"id": "abc-123"}],
            second_asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=60),
        )
        with patch(_SYNC_PATCH):
            resp = await app_client.post(
                "/api/v1/analyze/AAPL",
                json={"model": "base"},
            )

        assert resp.status_code == 200
        assert resp.json()["model"] == "base"

    async def test_default_request_body_uses_sensible_defaults(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """Sending an empty body {} should apply all defaults without error."""
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[{"id": "abc-123"}],
            second_asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=60),
        )
        with patch(_SYNC_PATCH):
            resp = await app_client.post("/api/v1/analyze/AAPL", json={})

        assert resp.status_code == 200
        body = resp.json()
        assert body["interval"] == "1wk"
        assert body["model"] == "base"
        assert body["periods_ahead"] == 4


# ── Interval minimum validation ────────────────────────────────────────────────


class TestAnalyzeIntervalValidation:
    """Tests that minimum row requirements are enforced per interval."""

    async def test_422_weekly_too_few_rows(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """1wk interval needs ≥52 rows; fewer should return 422."""
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[{"id": "abc-123"}],
            second_asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=20),   # 20 < 52
        )
        with patch(_SYNC_PATCH):
            resp = await app_client.post(
                "/api/v1/analyze/AAPL",
                json={"interval": "1wk"},
            )

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "52" in detail
        assert "20" in detail

    async def test_422_monthly_too_few_rows(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """1mo interval needs ≥24 rows; fewer should return 422."""
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[{"id": "abc-123"}],
            second_asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=10, freq="MS"),   # 10 < 24
        )
        with patch(_SYNC_PATCH):
            resp = await app_client.post(
                "/api/v1/analyze/AAPL",
                json={"interval": "1mo"},
            )

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "24" in detail
        assert "10" in detail

    async def test_422_propagated_even_after_successful_sync(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """
        Auto-sync may succeed but return fewer rows than the interval minimum
        (e.g. a newly-listed stock). The 422 must still be raised.
        """
        configure_analyze_mock(
            mock_db,
            first_asset_rows=[],                     # trigger sync
            second_asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=10),     # too few rows post-sync
        )
        with patch(_SYNC_PATCH, return_value=10):
            resp = await app_client.post(
                "/api/v1/analyze/NEWSTOCK",
                json={"interval": "1wk"},
            )

        assert resp.status_code == 422


# ── Request body validation ────────────────────────────────────────────────────


class TestAnalyzeRequestValidation:
    """Tests for Pydantic schema validation on AnalyzeRequest."""

    async def test_422_invalid_model_name(
        self, app_client, mock_db
    ) -> None:
        """An unrecognised model name should be rejected before any DB call."""
        resp = await app_client.post(
            "/api/v1/analyze/AAPL",
            json={"model": "sarimax"},   # not a valid Literal value
        )
        assert resp.status_code == 422

    async def test_422_invalid_interval(
        self, app_client, mock_db
    ) -> None:
        """An unsupported interval string should fail schema validation."""
        resp = await app_client.post(
            "/api/v1/analyze/AAPL",
            json={"interval": "1d"},   # only 1wk / 1mo allowed
        )
        assert resp.status_code == 422

    async def test_422_periods_below_minimum(
        self, app_client, mock_db
    ) -> None:
        """periods=0 is below ge=1 and must be rejected."""
        resp = await app_client.post(
            "/api/v1/analyze/AAPL",
            json={"periods": 0},
        )
        assert resp.status_code == 422

    async def test_422_periods_above_maximum(
        self, app_client, mock_db
    ) -> None:
        """periods=53 is above le=52 and must be rejected."""
        resp = await app_client.post(
            "/api/v1/analyze/AAPL",
            json={"periods": 53},
        )
        assert resp.status_code == 422

    async def test_422_invalid_asset_type(
        self, app_client, mock_db
    ) -> None:
        """An unrecognised asset_type should fail Pydantic validation."""
        resp = await app_client.post(
            "/api/v1/analyze/BTC-USD",
            json={"asset_type": "nft"},  # not in Literal["stock","crypto","index"]
        )
        assert resp.status_code == 422


# ── ML model error propagation ────────────────────────────────────────────────


class TestAnalyzeModelErrors:
    """Tests for error handling in the forecast model step."""

    async def test_503_lstm_without_tensorflow(
        self, app_client, mock_db, price_rows_factory
    ) -> None:
        """
        Requesting model='lstm' without TensorFlow installed should return 503.
        Skipped automatically if TF is present in the environment.
        """
        try:
            import tensorflow  # noqa: F401
            pytest.skip("TensorFlow installed — skipping 503 test")
        except ImportError:
            pass

        configure_analyze_mock(
            mock_db,
            first_asset_rows=[{"id": "abc-123"}],
            second_asset_rows=[{"id": "abc-123"}],
            price_rows=price_rows_factory(n=60),
        )
        with patch(_SYNC_PATCH):
            resp = await app_client.post(
                "/api/v1/analyze/AAPL",
                json={"model": "lstm", "interval": "1wk"},
            )

        assert resp.status_code == 503
        assert "TensorFlow" in resp.json()["detail"]

"""
tests/test_forecast_endpoint.py
─────────────────────────────────
HTTP-level tests for POST /api/v1/forecast/metrics.

No forecast model is configured; the endpoint returns empty metrics and bounds.
"""

import pytest


class TestForecastMetricsEndpoint:
    """HTTP tests for POST /api/v1/forecast/metrics."""

    async def test_200_returns_empty_metrics_and_bounds(
        self, app_client
    ) -> None:
        """Metrics endpoint returns 200 with empty metrics and bounds."""
        resp = await app_client.post(
            "/api/v1/forecast/metrics",
            json={"symbol": "AAPL", "interval": "1wk", "last_n_weeks": 20},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["symbol"] == "AAPL"
        assert body["interval"] == "1wk"
        assert body["metrics"] == []
        assert body["bounds"] == []
        assert body.get("bounds_horizon_weeks") == 0

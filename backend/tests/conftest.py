"""
tests/conftest.py
──────────────────
Shared pytest fixtures for the backend test suite.

Fixtures
--------
app_client
    ``httpx.AsyncClient`` wired to the FastAPI app with a mocked Supabase
    client so tests never hit the real database.

mock_db
    ``MagicMock`` standing in for the Supabase client, pre-configured with
    sensible defaults so individual tests can override only what they need.

Usage
-----
    async def test_health(app_client):
        resp = await app_client.get("/")
        assert resp.status_code == 200
"""

from typing import AsyncGenerator, Callable, List
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_db
from app.main import app


# ── Mock Supabase client ──────────────────────────────────────────────────────


@pytest.fixture
def mock_db() -> MagicMock:
    """
    Return a MagicMock that mimics the Supabase client's fluent query builder.

    The default return value for ``.execute()`` is ``MagicMock(data=[])``.
    Override in individual tests as needed:

        def test_something(mock_db):
            mock_db.table().select().execute.return_value = MagicMock(
                data=[{"id": "1", "symbol": "AAPL"}]
            )
    """
    client = MagicMock()
    # Default: any chain ending in .execute() returns an empty data list.
    client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(
        data=[]
    )
    client.table.return_value.select.return_value.execute.return_value = MagicMock(
        data=[]
    )
    return client


# ── Test client ───────────────────────────────────────────────────────────────


@pytest.fixture
async def app_client(mock_db: MagicMock) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTPX client with Supabase dependency overridden by ``mock_db``.

    Startup lifespan is skipped to avoid real DB connections in tests.
    """
    app.dependency_overrides[get_db] = lambda: mock_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ── Shared price-data factories ──────────────────────────────────────────────


@pytest.fixture
def price_series_factory() -> Callable[..., pd.Series]:
    """
    Factory fixture — returns a callable that builds a synthetic price pd.Series.

    Usage::

        def test_something(price_series_factory):
            prices = price_series_factory(n=60, freq="W-MON")
    """

    def _make(
        n: int = 60,
        freq: str = "W-MON",
        start: str = "2021-01-04",
        seed: int = 42,
    ) -> pd.Series:
        """
        Build a synthetic weekly or monthly price pd.Series.

        Args:
            n:     Number of data points.
            freq:  Pandas frequency string (e.g. ``"W-MON"``, ``"MS"``).
            start: Start date for the date range.
            seed:  RNG seed for reproducibility.

        Returns:
            pd.Series with DatetimeIndex, oldest → newest.
        """
        dates = pd.date_range(start=start, periods=n, freq=freq)
        rng = np.random.default_rng(seed)
        prices = 100.0 + np.cumsum(rng.normal(0, 1, n))
        return pd.Series(prices, index=dates, name="close")

    return _make


@pytest.fixture
def price_rows_factory() -> Callable[..., List[dict]]:
    """
    Factory fixture — returns a callable that builds DB-style price row dicts.

    Rows mirror what Supabase returns for the ``historical_prices`` table:
    ``{"timestamp": <ISO-8601>, "close_price": <float>}``.

    Usage::

        def test_something(price_rows_factory):
            rows = price_rows_factory(n=60)
    """

    def _make(
        n: int = 60,
        freq: str = "W-MON",
        start: str = "2021-01-04",
        seed: int = 42,
    ) -> List[dict]:
        """
        Build synthetic price rows as returned by Supabase.

        Args:
            n:     Number of rows.
            freq:  Pandas frequency string.
            start: Start date for the date range.
            seed:  RNG seed for reproducibility.

        Returns:
            List of dicts with ``timestamp`` and ``close_price`` keys.
        """
        dates = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")
        rng = np.random.default_rng(seed)
        prices = 100.0 + np.cumsum(rng.normal(0, 1, n))
        return [
            {"timestamp": d.isoformat(), "close_price": round(float(p), 4)}
            for d, p in zip(dates, prices)
        ]

    return _make


def configure_forecast_mock(
    mock_db: MagicMock,
    asset_rows: list,
    price_rows: list,
) -> None:
    """
    Wire ``mock_db`` so the forecast endpoint's two DB queries return the
    expected payloads.

    The forecast endpoint calls:
    - ``.table().select().eq().limit().execute()``   for the asset lookup.
    - ``.table().select().eq().order().execute()``   for the price lookup.

    Because ``.limit()`` and ``.order()`` are different methods on the mock,
    both chains can be configured independently on the same ``MagicMock``.

    Args:
        mock_db:    The MagicMock Supabase client.
        asset_rows: Rows to return from ``assets`` table query.
        price_rows: Rows to return from ``historical_prices`` table query.
    """
    # assets: .table().select().eq().limit().execute()
    (
        mock_db.table.return_value
        .select.return_value
        .eq.return_value
        .limit.return_value
        .execute
    ).return_value = MagicMock(data=asset_rows)

    # prices: .table().select().eq().order().execute()
    (
        mock_db.table.return_value
        .select.return_value
        .eq.return_value
        .order.return_value
        .execute
    ).return_value = MagicMock(data=price_rows)


def configure_analyze_mock(
    mock_db: MagicMock,
    first_asset_rows: list,
    second_asset_rows: list,
    price_rows: list,
) -> None:
    """
    Wire ``mock_db`` for the analyze endpoint which makes TWO asset lookups.

    The analyze endpoint calls ``.limit().execute()`` twice:
    - First call: initial existence check (decides whether to auto-sync).
    - Second call: inside ``_fetch_prices()`` after the optional sync.

    ``side_effect`` with a list returns the values in sequence, one per call.

    The price query uses ``.order().execute()`` and is set via
    ``return_value`` (only called once).

    Args:
        mock_db:            The MagicMock Supabase client.
        first_asset_rows:   Rows for the initial existence check.
                            Pass ``[]`` to simulate a new / unknown symbol.
        second_asset_rows:  Rows for the ``_fetch_prices()`` lookup.
                            Pass ``[{"id": "..."}]`` to simulate a present asset.
        price_rows:         Rows for the historical-prices query.
    """
    # Use side_effect so each successive .limit().execute() call returns
    # a different value (first check vs _fetch_prices lookup).
    (
        mock_db.table.return_value
        .select.return_value
        .eq.return_value
        .limit.return_value
        .execute
    ).side_effect = [
        MagicMock(data=first_asset_rows),
        MagicMock(data=second_asset_rows),
    ]

    # prices: .table().select().eq().order().execute()
    (
        mock_db.table.return_value
        .select.return_value
        .eq.return_value
        .order.return_value
        .execute
    ).return_value = MagicMock(data=price_rows)


# ── Synchronous test client (for non-async tests) ─────────────────────────────


@pytest.fixture
def sync_client(mock_db: MagicMock) -> TestClient:
    """
    Synchronous ``TestClient`` for simpler, non-async tests.

    Uses the same ``mock_db`` override as ``app_client``.
    """
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app, raise_server_exceptions=True)
    yield client
    app.dependency_overrides.clear()

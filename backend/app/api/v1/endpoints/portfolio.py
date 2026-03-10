"""
app/api/v1/endpoints/portfolio.py
──────────────────────────────────
Portfolio statistics and optimization endpoints.

Routes
------
POST /api/v1/portfolio/stats
    Individual per-asset statistics (returns, volatility, drawdown, Sharpe,
    VaR, skewness …) plus cross-asset metrics (covariance, correlation, beta).

POST /api/v1/portfolio/optimize
    PyPortfolioOpt optimization — returns cleaned portfolio weights,
    performance metrics, the full efficient frontier curve, and downside
    risk metrics for the optimal allocation.

Data contract
--------------
All requested symbols **must already exist** in the database.
Use ``POST /api/v1/assets/sync/{symbol}`` or ``POST /api/v1/analyze/{symbol}``
to fetch and cache any missing symbol first.

Error codes
-----------
404  One or more symbols not found in the database.
422  Not enough rows for one or more symbols / infeasible optimization
     target / invalid request body.
503  Supabase unreachable or PyPortfolioOpt not installed.
500  Unexpected internal error.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date as Date, timedelta
from typing import Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from analytics.optimization import portfolio as pf
from analytics.optimization import risk_metrics as rm
from analytics.optimization import simulation as sim
from app.api.dependencies import get_db
from schemas.forecast import INTERVAL_CONFIG
from schemas.portfolio import (
    AdvancedStats,
    FrontierPoint,
    IndividualStats,
    OptimizeRequest,
    OptimizeResponse,
    OptimizeRiskMetrics,
    PortfolioPerformance,
    SimulateRequest,
    SimulateResponse,
    SimulationBands,
    SimulationSummary,
    StatsRequest,
    StatsResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared thread pool — optimization and stats computation are CPU-bound.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="portfolio")


# ── Private helpers ───────────────────────────────────────────────────────────


async def _fetch_prices_for_symbol(
    symbol: str,
    interval: str,
    db: Client,
    from_date: Optional[Date] = None,
    to_date: Optional[Date] = None,
) -> pd.Series:
    """
    Fetch historical close prices for a single symbol with optional date range.

    Args:
        symbol:    Upper-case ticker.
        interval:  Bar interval — drives minimum-row validation.
        db:        Injected Supabase client.
        from_date: Oldest bar to include (inclusive). None = all history.
        to_date:   Most recent bar to include (inclusive). None = latest row.

    Returns:
        ``pd.Series`` with UTC ``DatetimeIndex``, oldest → newest.

    Raises:
        HTTPException 404: Symbol not in DB or no rows for the date range.
        HTTPException 422: Too few rows for the chosen interval.
        HTTPException 503: Database error.
    """
    # ── asset lookup ──────────────────────────────────────────────────────
    try:
        asset_res = (
            db.table("assets")
            .select("id")
            .eq("symbol", symbol)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Database error looking up '{symbol}': {exc}"
        ) from exc

    if not asset_res.data:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Symbol '{symbol}' not found in the database. "
                "Sync it first with POST /api/v1/assets/sync/{symbol} "
                "or POST /api/v1/analyze/{symbol}."
            ),
        )

    asset_id = asset_res.data[0]["id"]

    # ── price lookup (with optional date filters) ─────────────────────────
    try:
        from datetime import timedelta

        price_query = (
            db.table("historical_prices")
            .select("timestamp, close_price")
            .eq("asset_id", asset_id)
        )
        if from_date:
            price_query = price_query.gte("timestamp", from_date.isoformat())
        if to_date:
            price_query = price_query.lt(
                "timestamp", (to_date + timedelta(days=1)).isoformat()
            )
        price_res = price_query.order("timestamp", desc=True).limit(2000).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database error fetching prices for '{symbol}': {exc}",
        ) from exc

    if not price_res.data:
        raise HTTPException(
            status_code=404,
            detail=f"No price data found in the database for '{symbol}'.",
        )

    # ── minimum-row validation ────────────────────────────────────────────
    cfg = INTERVAL_CONFIG[interval]
    min_rows = cfg["min_samples"]
    n_rows = len(price_res.data)
    if n_rows < min_rows:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{symbol}' has only {n_rows} {interval} rows — "
                f"need at least {min_rows} for reliable portfolio analysis."
            ),
        )

    rows_chrono = list(reversed(price_res.data))  # restore chronological order
    index = pd.to_datetime([r["timestamp"] for r in rows_chrono], utc=True)
    values = [float(r["close_price"]) for r in rows_chrono]
    logger.info("Loaded %d price rows for %s", len(values), symbol)
    return pd.Series(values, index=index, name="close")


async def _fetch_all(
    symbols: List[str],
    interval: str,
    db: Client,
    from_date: Optional[Date] = None,
    to_date: Optional[Date] = None,
) -> Dict[str, pd.Series]:
    """
    Sequentially fetch prices for all symbols with an optional date window.
    """
    result: Dict[str, pd.Series] = {}
    for sym in symbols:
        result[sym] = await _fetch_prices_for_symbol(
            sym, interval, db, from_date=from_date, to_date=to_date
        )
    return result


# ── Thread-pool workers ───────────────────────────────────────────────────────


def _stats_worker(
    series_map: Dict[str, pd.Series],
    interval: str,
    risk_free_rate: float,
) -> dict:
    """
    CPU-bound: compute all individual and advanced statistics.

    Runs inside the thread pool to avoid blocking the event loop.
    """
    # Inner-join alignment — only shared dates contribute to cross-asset metrics.
    prices_df = pf.build_price_df(series_map)

    individual = {
        sym: rm.individual_stats(series_map[sym], interval, risk_free_rate)
        for sym in series_map
    }
    advanced = {
        "covariance_matrix": rm.covariance_matrix(prices_df),
        "correlation_matrix": rm.correlation_matrix(prices_df),
        "beta_vs_equal_weighted": rm.beta_vs_equal_weighted(prices_df),
    }
    return {
        "individual": individual,
        "advanced": advanced,
        "shared_data_points": len(prices_df),
    }


def _optimize_worker(
    series_map: Dict[str, pd.Series],
    request: OptimizeRequest,
) -> dict:
    """
    CPU-bound: run PyPortfolioOpt optimization and compute the efficient frontier.

    Runs inside the thread pool.
    """
    prices_df = pf.build_price_df(series_map)

    # ── Optimization ──────────────────────────────────────────────────────
    # HRP uses a distinct code path — no expected-return estimates needed.
    if request.target == "hrp":
        opt = pf.optimize_hrp(prices_df)
        # HRP is a single-point solution; it has no efficient frontier.
        frontier: list = []
    else:
        opt = pf.optimize(
            prices_df,
            interval=request.interval,
            target=request.target,
            risk_free_rate=request.risk_free_rate,
            target_return=request.target_return,
            target_volatility=request.target_volatility,
        )
        # ── Efficient frontier ────────────────────────────────────────────
        frontier = pf.efficient_frontier_points(
            prices_df,
            interval=request.interval,
            risk_free_rate=request.risk_free_rate,
            n_points=request.n_frontier_points,
        )

    # ── Portfolio-level risk metrics ──────────────────────────────────────
    # Build the weighted return series from the optimal weights.
    weights = opt["weights"]
    port_returns: pd.Series = sum(  # type: ignore[assignment]
        weights.get(sym, 0.0) * series_map[sym]
        for sym in series_map
    )
    risk = {
        "var_95": round(rm.value_at_risk(port_returns), 6),
        "cvar_95": round(rm.conditional_var(port_returns), 6),
        "max_drawdown": round(rm.max_drawdown(port_returns), 4),
    }

    return {
        **opt,
        "efficient_frontier": frontier,
        "risk_metrics": risk,
        "shared_data_points": len(prices_df),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/stats",
    response_model=StatsResponse,
    summary="Individual and cross-asset portfolio statistics",
    responses={
        200: {"description": "Statistics computed successfully"},
        404: {"description": "One or more symbols not found in the database"},
        422: {"description": "Insufficient data or invalid request body"},
        503: {"description": "Supabase unreachable"},
        500: {"description": "Unexpected computation error"},
    },
)
async def portfolio_stats(
    request: StatsRequest,
    db: Client = Depends(get_db),
) -> StatsResponse:
    """
    Compute per-asset and cross-asset statistics for a basket of symbols.

    All symbols must already be cached in the database.
    Use ``POST /api/v1/analyze/{symbol}`` to auto-sync any missing ones.

    **Individual metrics** (per asset):
    ``avg_return``, ``variance``, ``std_deviation``, ``cumulative_return``,
    ``annualized_volatility``, ``sharpe_score``, ``max_drawdown``,
    ``skewness``, ``kurtosis``, ``returns_summary``, ``var_95``, ``cvar_95``

    **Advanced metrics** (cross-asset):
    ``covariance_matrix``, ``correlation_matrix``, ``beta_vs_equal_weighted``

    Args:
        request: Symbols, interval and risk_free_rate.
        db:      Injected Supabase client.

    Returns:
        ``StatsResponse`` with individual and advanced statistics.
    """
    symbols = [s.strip().upper() for s in request.symbols]
    loop = asyncio.get_event_loop()

    series_map = await _fetch_all(
        symbols, request.interval, db,
        from_date=request.from_date,
        to_date=request.to_date,
    )

    try:
        result = await loop.run_in_executor(
            _executor,
            _stats_worker,
            series_map,
            request.interval,
            request.risk_free_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Portfolio stats computation failed")
        raise HTTPException(
            status_code=500, detail="Statistics computation failed unexpectedly."
        ) from exc

    return StatsResponse(
        symbols=symbols,
        interval=request.interval,
        from_date=request.from_date.isoformat() if request.from_date else None,
        to_date=request.to_date.isoformat() if request.to_date else None,
        data_points_used={sym: len(s) for sym, s in series_map.items()},
        shared_data_points=result["shared_data_points"],
        individual={
            sym: IndividualStats(**stat)
            for sym, stat in result["individual"].items()
        },
        advanced=AdvancedStats(**result["advanced"]),
    )


@router.post(
    "/optimize",
    response_model=OptimizeResponse,
    summary="Portfolio optimization with efficient frontier",
    responses={
        200: {"description": "Optimal weights and frontier returned"},
        404: {"description": "One or more symbols not found in the database"},
        422: {"description": "Infeasible optimization or invalid request body"},
        503: {"description": "Supabase unreachable or PyPortfolioOpt missing"},
        500: {"description": "Unexpected computation error"},
    },
)
async def portfolio_optimize(
    request: OptimizeRequest,
    db: Client = Depends(get_db),
) -> OptimizeResponse:
    """
    Find the optimal portfolio allocation using Modern Portfolio Theory.

    All symbols must already be cached in the database.

    **Optimization targets:**

    | ``target``           | What it does                                        |
    |----------------------|-----------------------------------------------------|
    | ``max_sharpe``       | Maximize risk-adjusted return (default)             |
    | ``min_volatility``   | Minimize portfolio volatility                       |
    | ``efficient_return`` | Minimize volatility for a target annual return      |
    | ``efficient_risk``   | Maximize return for a target annual volatility      |
    | ``hrp``              | Hierarchical Risk Parity — cluster-based            |

    The response also includes ``n_frontier_points`` (default 30) portfolios
    along the efficient frontier and portfolio-level VaR / CVaR / drawdown.

    Args:
        request: Symbols, interval, target and optional target values.
        db:      Injected Supabase client.

    Returns:
        ``OptimizeResponse`` with weights, performance, frontier, risk metrics.
    """
    symbols = [s.strip().upper() for s in request.symbols]
    loop = asyncio.get_event_loop()

    series_map = await _fetch_all(
        symbols, request.interval, db,
        from_date=request.from_date,
        to_date=request.to_date,
    )

    try:
        result = await loop.run_in_executor(
            _executor,
            _optimize_worker,
            series_map,
            request,
        )
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="PyPortfolioOpt is not installed on this server.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Portfolio optimization failed")
        raise HTTPException(
            status_code=500,
            detail="Portfolio optimization failed unexpectedly.",
        ) from exc

    return OptimizeResponse(
        symbols=symbols,
        interval=request.interval,
        from_date=request.from_date.isoformat() if request.from_date else None,
        to_date=request.to_date.isoformat() if request.to_date else None,
        target=request.target,
        weights=result["weights"],
        performance=PortfolioPerformance(**result["performance"]),
        efficient_frontier=[FrontierPoint(**p) for p in result["efficient_frontier"]],
        risk_metrics=OptimizeRiskMetrics(**result["risk_metrics"]),
        data_points_used={sym: len(s) for sym, s in series_map.items()},
        shared_data_points=result["shared_data_points"],
    )


# ── /simulate ─────────────────────────────────────────────────────────────────

# Default horizon in bar-periods per interval
_DEFAULT_PERIODS: Dict[str, int] = {"1d": 126, "1wk": 26, "1mo": 6}


def _simulate_worker(
    series_map: Dict[str, pd.Series],
    request: SimulateRequest,
    n_periods: int,
    projected_dates: List[str],
) -> dict:
    """
    CPU-bound: run Monte Carlo GBM and Historical Bootstrap simulations.

    Executed inside the thread pool to keep the event loop unblocked.
    """
    prices_df = pf.build_price_df(series_map)
    weights = request.weights

    mc_raw   = sim.monte_carlo_gbm(
        prices_df, weights, request.n_simulations, n_periods,
        initial_value=request.initial_value,
    )
    hist_raw = sim.historical_bootstrap(
        prices_df, weights, request.n_simulations, n_periods,
        initial_value=request.initial_value,
    )

    mc_summary   = sim.simulation_summary(
        mc_raw["terminal_values"], mc_raw["p50"],
        request.initial_value, request.risk_free_rate, request.interval,
    )
    hist_summary = sim.simulation_summary(
        hist_raw["terminal_values"], hist_raw["p50"],
        request.initial_value, request.risk_free_rate, request.interval,
    )

    return {
        "monte_carlo": {**mc_raw,   "dates": projected_dates},
        "historical":  {**hist_raw, "dates": projected_dates},
        "mc_summary":   mc_summary,
        "hist_summary": hist_summary,
        "shared_data_points": len(prices_df),
    }


@router.post(
    "/simulate",
    response_model=SimulateResponse,
    summary="Monte Carlo and Historical Bootstrap portfolio simulations",
    responses={
        200: {"description": "Simulation paths and summary stats returned"},
        404: {"description": "One or more symbols not found in the database"},
        422: {"description": "Insufficient data or invalid request body"},
        503: {"description": "Supabase unreachable"},
        500: {"description": "Unexpected computation error"},
    },
)
async def portfolio_simulate(
    request: SimulateRequest,
    db: Client = Depends(get_db),
) -> SimulateResponse:
    """
    Project the optimised portfolio forward using two simulation methods.

    **Monte Carlo GBM** — models correlated log-normal asset returns using
    Cholesky-decomposed covariance. Captures normal-distribution risk.

    **Historical Bootstrap** — resamples actual past portfolio returns i.i.d.
    Preserves fat tails, skewness and real-world distributional features.

    Both methods return percentile fan-chart bands (p5/p25/p50/p75/p95) and
    raw terminal values for histogram rendering, plus an aggregate summary
    (Sortino, Calmar, Omega, max drawdown, probability of profit).

    Args:
        request: Symbols, weights, interval, date range, n_simulations, n_periods.
        db:      Injected Supabase client.

    Returns:
        ``SimulateResponse`` with both simulation sets and summary stats.
    """
    symbols = [s.strip().upper() for s in request.symbols]
    loop = asyncio.get_event_loop()

    series_map = await _fetch_all(
        symbols, request.interval, db,
        from_date=request.from_date,
        to_date=request.to_date,
    )

    n_periods = request.n_periods or _DEFAULT_PERIODS.get(request.interval, 126)

    # Build projected date labels starting from the day after the last price date
    last_dates = [s.index[-1] for s in series_map.values()]
    latest = max(last_dates)
    if request.interval == "1d":
        step = timedelta(days=1)
    elif request.interval == "1wk":
        step = timedelta(weeks=1)
    else:
        step = timedelta(days=30)

    projected_dates: List[str] = [latest.strftime("%Y-%m-%d")]
    current = latest
    for _ in range(n_periods):
        current = current + step
        projected_dates.append(current.strftime("%Y-%m-%d"))

    try:
        result = await loop.run_in_executor(
            _executor,
            _simulate_worker,
            series_map,
            request,
            n_periods,
            projected_dates,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Portfolio simulation failed")
        raise HTTPException(
            status_code=500,
            detail="Portfolio simulation failed unexpectedly.",
        ) from exc

    return SimulateResponse(
        symbols=symbols,
        interval=request.interval,
        from_date=request.from_date.isoformat() if request.from_date else None,
        to_date=request.to_date.isoformat() if request.to_date else None,
        weights=request.weights,
        n_simulations=request.n_simulations,
        n_periods=n_periods,
        initial_value=request.initial_value,
        monte_carlo=SimulationBands(**result["monte_carlo"]),
        historical=SimulationBands(**result["historical"]),
        mc_summary=SimulationSummary(**result["mc_summary"]),
        hist_summary=SimulationSummary(**result["hist_summary"]),
        data_points_used={sym: len(s) for sym, s in series_map.items()},
        shared_data_points=result["shared_data_points"],
    )

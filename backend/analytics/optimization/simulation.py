"""
analytics/optimization/simulation.py
──────────────────────────────────────
Monte Carlo and Historical Bootstrap portfolio simulations.

Both functions accept an aligned DataFrame of close prices (one column per
ticker, DatetimeIndex rows) and a weight dictionary, then project a
portfolio wealth path forward for ``n_periods`` steps using ``n_simulations``
independent trials.

Public functions
----------------
monte_carlo_gbm        — Correlated GBM via Cholesky decomposition.
historical_bootstrap   — Non-parametric block-free resampling of past returns.
simulation_summary     — Aggregate ratio/risk stats from a set of terminal values
                         and a median wealth path.
"""

from __future__ import annotations

import math
from typing import Dict, List

import numpy as np
import pandas as pd


# ── Annualisation factors (trading periods per year) ─────────────────────────

_FREQ: Dict[str, int] = {
    "1d": 252,
    "1wk": 52,
    "1mo": 12,
}

# Maximum terminal values returned for histogram rendering
_MAX_HISTOGRAM_SAMPLES = 500


# ── Helpers ───────────────────────────────────────────────────────────────────


def _portfolio_log_returns(
    prices_df: pd.DataFrame,
    weights: Dict[str, float],
) -> np.ndarray:
    """
    Build a 1-D array of weighted portfolio log returns from aligned prices.

    Args:
        prices_df: Aligned close-price DataFrame (symbols as columns).
        weights:   Symbol → weight mapping (weights should sum to ~1).

    Returns:
        1-D numpy array of portfolio log returns (length = len(prices_df) - 1).
    """
    log_returns = np.log(prices_df / prices_df.shift(1)).dropna()
    w = np.array([weights.get(col, 0.0) for col in log_returns.columns])
    return log_returns.values @ w  # shape: (T,)


def _percentile_bands(
    paths: np.ndarray,
    n_periods: int,
    initial_value: float,
) -> Dict[str, List[float]]:
    """
    Compute wealth-path percentile bands and collect terminal value distribution.

    Args:
        paths:         Array of shape (n_simulations, n_periods) — wealth values.
        n_periods:     Number of projected time steps.
        initial_value: Starting portfolio value (prepended as period 0).

    Returns:
        Dict with keys p5/p25/p50/p75/p95 (lists of length n_periods + 1)
        and terminal_values (list of up to _MAX_HISTOGRAM_SAMPLES floats).
    """
    p5  = np.percentile(paths, 5,  axis=0).tolist()
    p25 = np.percentile(paths, 25, axis=0).tolist()
    p50 = np.percentile(paths, 50, axis=0).tolist()
    p75 = np.percentile(paths, 75, axis=0).tolist()
    p95 = np.percentile(paths, 95, axis=0).tolist()

    terminal = paths[:, -1]
    # Sample down to avoid large payloads
    if len(terminal) > _MAX_HISTOGRAM_SAMPLES:
        idx = np.random.choice(len(terminal), _MAX_HISTOGRAM_SAMPLES, replace=False)
        terminal = terminal[idx]

    return {
        "p5":  [initial_value] + p5,
        "p25": [initial_value] + p25,
        "p50": [initial_value] + p50,
        "p75": [initial_value] + p75,
        "p95": [initial_value] + p95,
        "terminal_values": terminal.tolist(),
    }


# ── Monte Carlo GBM ───────────────────────────────────────────────────────────


def monte_carlo_gbm(
    prices_df: pd.DataFrame,
    weights: Dict[str, float],
    n_simulations: int,
    n_periods: int,
    initial_value: float = 10_000.0,
    seed: int | None = None,
) -> Dict:
    """
    Simulate portfolio wealth paths using correlated Geometric Brownian Motion.

    The per-period portfolio return distribution is estimated from historical
    log returns: mean vector ``μ`` and covariance matrix ``Σ`` are computed,
    then correlated draws are produced via Cholesky decomposition.

    GBM drift per period:
        r_t = μ_p - 0.5 * σ_p²  (Itô correction)
    where ``μ_p = w'μ`` and ``σ_p² = w'Σw``.

    Args:
        prices_df:     Aligned close-price DataFrame.
        weights:       Symbol → optimal weight mapping (sums to ~1).
        n_simulations: Number of independent simulation paths.
        n_periods:     Number of future time steps to project.
        initial_value: Starting portfolio dollar value.
        seed:          Optional RNG seed for reproducibility.

    Returns:
        Dict with percentile bands (p5/p25/p50/p75/p95) each of length
        n_periods + 1, and terminal_values list (≤ 500 floats).
    """
    rng = np.random.default_rng(seed)

    log_ret = np.log(prices_df / prices_df.shift(1)).dropna()
    symbols = [c for c in log_ret.columns]
    w = np.array([weights.get(s, 0.0) for s in symbols])

    mu = log_ret.values.mean(axis=0)          # (n_assets,)
    cov = np.cov(log_ret.values, rowvar=False)  # (n_assets, n_assets)

    # Scalar portfolio moments
    mu_p  = float(w @ mu)
    var_p = float(w @ cov @ w)

    # GBM drift with Itô correction
    drift = mu_p - 0.5 * var_p

    # Correlated noise via Cholesky
    try:
        L = np.linalg.cholesky(cov)
    except np.linalg.LinAlgError:
        # Fall back to diagonal if cov is not positive-definite
        L = np.diag(np.sqrt(np.maximum(np.diag(cov), 0)))

    # Draw correlated standard-normal shocks (n_periods, n_assets, n_simulations)
    z_raw = rng.standard_normal((n_periods, len(symbols), n_simulations))
    # z_corr[t,i,s] = sum_j L[i,j] * z_raw[t,j,s]  → shape (n_periods, n_assets, n_sims)
    z_corr = np.einsum("ij,tjs->tis", L, z_raw)

    # Weighted portfolio shocks per step: (n_periods, n_simulations)
    port_shocks = np.einsum("i,tis->ts", w, z_corr)

    # Compound returns → wealth paths (n_simulations, n_periods)
    log_paths = drift + port_shocks             # (n_periods, n_sims)
    cum_log   = np.cumsum(log_paths, axis=0).T  # (n_sims, n_periods)
    paths = initial_value * np.exp(cum_log)     # (n_sims, n_periods)

    return _percentile_bands(paths, n_periods, initial_value)


# ── Historical Bootstrap ──────────────────────────────────────────────────────


def historical_bootstrap(
    prices_df: pd.DataFrame,
    weights: Dict[str, float],
    n_simulations: int,
    n_periods: int,
    initial_value: float = 10_000.0,
    seed: int | None = None,
) -> Dict:
    """
    Simulate portfolio wealth paths by resampling historical portfolio returns.

    Each simulation draws ``n_periods`` returns i.i.d. with replacement from
    the empirical distribution of historical weighted portfolio returns.
    This method preserves fat tails, skewness, and other non-normal features
    of the actual return distribution without parametric assumptions.

    Args:
        prices_df:     Aligned close-price DataFrame.
        weights:       Symbol → optimal weight mapping.
        n_simulations: Number of independent simulation paths.
        n_periods:     Number of future time steps.
        initial_value: Starting portfolio dollar value.
        seed:          Optional RNG seed.

    Returns:
        Dict with percentile bands (p5/p25/p50/p75/p95) each of length
        n_periods + 1, and terminal_values list (≤ 500 floats).
    """
    rng = np.random.default_rng(seed)

    port_returns = _portfolio_log_returns(prices_df, weights)

    # Resample: (n_simulations, n_periods)
    idx = rng.integers(0, len(port_returns), size=(n_simulations, n_periods))
    sampled = port_returns[idx]  # (n_sims, n_periods)

    # Compound to wealth paths
    cum_log = np.cumsum(sampled, axis=1)        # (n_sims, n_periods)
    paths   = initial_value * np.exp(cum_log)   # (n_sims, n_periods)

    return _percentile_bands(paths, n_periods, initial_value)


# ── Summary statistics ────────────────────────────────────────────────────────


def simulation_summary(
    terminal_values: List[float],
    median_path: List[float],
    initial_value: float,
    risk_free_rate: float,
    interval: str,
) -> Dict:
    """
    Compute aggregate statistics from a completed simulation.

    Args:
        terminal_values: Raw terminal portfolio values (all simulations).
        median_path:     Median wealth path (p50), length = n_periods + 1.
        initial_value:   Starting portfolio dollar value.
        risk_free_rate:  Annual risk-free rate (e.g. 0.05 for 5%).
        interval:        Bar interval (``"1d"`` / ``"1wk"`` / ``"1mo"``).

    Returns:
        Dict with: prob_positive, expected_terminal, ci_5/25/50/75/95,
        sortino_ratio, calmar_ratio, omega_ratio, max_drawdown.
    """
    tv = np.array(terminal_values)
    freq = _FREQ.get(interval, 252)

    # Infer simulation horizon from median path length
    n_periods = len(median_path) - 1  # exclude period-0
    annual_factor = n_periods / freq  # fraction of year covered

    # ── Terminal value CI ────────────────────────────────────────────────
    ci_5  = float(np.percentile(tv, 5))
    ci_25 = float(np.percentile(tv, 25))
    ci_50 = float(np.percentile(tv, 50))
    ci_75 = float(np.percentile(tv, 75))
    ci_95 = float(np.percentile(tv, 95))

    prob_positive = float(np.mean(tv > initial_value))
    expected_terminal = float(np.mean(tv))

    # ── Return series derived from median path ────────────────────────────
    w_path = np.array(median_path)
    log_rets = np.diff(np.log(w_path + 1e-12))  # avoid log(0)

    mean_ret   = float(log_rets.mean())
    rfr_period = risk_free_rate / freq           # per-period risk-free

    # ── Max drawdown from median path ────────────────────────────────────
    cummax = np.maximum.accumulate(w_path)
    drawdowns = (w_path - cummax) / (cummax + 1e-12)
    max_dd = float(drawdowns.min())

    # ── Sortino Ratio ────────────────────────────────────────────────────
    downside_returns = log_rets[log_rets < rfr_period]
    if len(downside_returns) > 1:
        downside_dev = float(np.std(downside_returns, ddof=1))
    else:
        downside_dev = float(np.std(log_rets, ddof=1)) if len(log_rets) > 1 else 1e-9

    ann_return   = mean_ret * freq
    ann_rfr      = risk_free_rate
    ann_downside = downside_dev * math.sqrt(freq)

    sortino = (ann_return - ann_rfr) / ann_downside if ann_downside > 1e-12 else 0.0

    # ── Calmar Ratio ─────────────────────────────────────────────────────
    calmar = ann_return / abs(max_dd) if abs(max_dd) > 1e-12 else 0.0

    # ── Omega Ratio ──────────────────────────────────────────────────────
    threshold = rfr_period
    gains  = log_rets[log_rets > threshold] - threshold
    losses = threshold - log_rets[log_rets <= threshold]
    sum_gains  = float(gains.sum())  if len(gains)  > 0 else 0.0
    sum_losses = float(losses.sum()) if len(losses) > 0 else 1e-12
    omega = sum_gains / sum_losses if sum_losses > 1e-12 else float("inf")

    return {
        "prob_positive":    round(prob_positive, 4),
        "expected_terminal": round(expected_terminal, 2),
        "ci_5":  round(ci_5,  2),
        "ci_25": round(ci_25, 2),
        "ci_50": round(ci_50, 2),
        "ci_75": round(ci_75, 2),
        "ci_95": round(ci_95, 2),
        "sortino_ratio":  round(sortino, 4),
        "calmar_ratio":   round(calmar, 4),
        "omega_ratio":    round(min(omega, 999.0), 4),  # cap infinite
        "max_drawdown":   round(max_dd, 4),
    }

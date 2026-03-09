"""
schemas/portfolio.py
─────────────────────
Pydantic schemas for the two portfolio endpoints:

  POST /api/v1/portfolio/stats
      → ``StatsRequest`` / ``StatsResponse``

  POST /api/v1/portfolio/optimize
      → ``OptimizeRequest`` / ``OptimizeResponse``
"""

from datetime import date as Date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ── Shared base ───────────────────────────────────────────────────────────────


class _PortfolioBase(BaseModel):
    """Fields shared by both endpoints."""

    symbols: List[str] = Field(
        ...,
        min_length=2,
        max_length=10,
        description="2–10 ticker symbols that are already in the database.",
    )
    interval: Literal["1d", "1wk", "1mo"] = Field(
        default="1d",
        description="Bar interval used when the data was synced.",
    )
    risk_free_rate: float = Field(
        default=0.05,
        ge=0.0,
        le=0.20,
        description="Annual risk-free rate for Sharpe calculations (default 5 %).",
    )
    from_date: Optional[Date] = Field(
        default=None,
        description="Oldest bar to include (ISO 8601, e.g. '2022-01-01'). "
                    "Defaults to all available history.",
    )
    to_date: Optional[Date] = Field(
        default=None,
        description="Most recent bar to include (ISO 8601, e.g. '2024-12-31'). "
                    "Defaults to the latest available row.",
    )

    @model_validator(mode="after")
    def check_date_range(self) -> "_PortfolioBase":
        if self.from_date and self.to_date and self.from_date >= self.to_date:
            raise ValueError(
                "'from_date' must be strictly earlier than 'to_date'."
            )
        return self


# ── POST /api/v1/portfolio/stats ──────────────────────────────────────────────


class StatsRequest(_PortfolioBase):
    """Request body for the portfolio statistics endpoint."""


class IndividualStats(BaseModel):
    """Per-asset return and risk statistics."""

    avg_return: float
    variance: float
    std_deviation: float
    cumulative_return: float
    annualized_volatility: float
    sharpe_score: float
    max_drawdown: float
    skewness: float
    kurtosis: float
    returns_summary: Dict[str, Any]  # {min, max, mean, last_30}
    var_95: float
    cvar_95: float


class AdvancedStats(BaseModel):
    """Cross-asset portfolio statistics."""

    covariance_matrix: Dict[str, Dict[str, float]]
    correlation_matrix: Dict[str, Dict[str, float]]
    beta_vs_equal_weighted: Dict[str, float]


class StatsResponse(BaseModel):
    """Full response from POST /api/v1/portfolio/stats."""

    symbols: List[str]
    interval: str
    from_date: Optional[str]   # ISO date actually used (None = all history)
    to_date: Optional[str]     # ISO date actually used (None = latest row)
    data_points_used: Dict[str, int]  # per-symbol row counts
    shared_data_points: int           # rows after inner join on dates
    individual: Dict[str, IndividualStats]
    advanced: AdvancedStats


# ── POST /api/v1/portfolio/optimize ──────────────────────────────────────────


class OptimizeRequest(_PortfolioBase):
    """Request body for the portfolio optimization endpoint."""

    target: Literal[
        "max_sharpe",
        "min_volatility",
        "efficient_return",
        "efficient_risk",
        "hrp",
    ] = Field(
        default="max_sharpe",
        description=(
            "Optimization objective. "
            "'efficient_return' requires target_return. "
            "'efficient_risk' requires target_volatility. "
            "'hrp' uses Hierarchical Risk Parity (no target params needed)."
        ),
    )
    target_return: Optional[float] = Field(
        default=None,
        ge=-0.5,
        le=5.0,
        description="Annual return target. Required when target='efficient_return'.",
    )
    target_volatility: Optional[float] = Field(
        default=None,
        ge=0.01,
        le=2.0,
        description=(
            "Annual volatility target. Required when target='efficient_risk'."
        ),
    )
    n_frontier_points: int = Field(
        default=30,
        ge=5,
        le=100,
        description="Number of portfolios to compute along the efficient frontier.",
    )

    @model_validator(mode="after")
    def check_target_params(self) -> "OptimizeRequest":
        if self.target == "efficient_return" and self.target_return is None:
            raise ValueError(
                "'target_return' is required when target='efficient_return'."
            )
        if self.target == "efficient_risk" and self.target_volatility is None:
            raise ValueError(
                "'target_volatility' is required when target='efficient_risk'."
            )
        return self


class FrontierPoint(BaseModel):
    """One portfolio on the efficient frontier curve."""

    volatility: float
    expected_return: float
    sharpe: float


class PortfolioPerformance(BaseModel):
    """Annualized performance metrics for the optimal portfolio."""

    expected_annual_return: float
    annual_volatility: float
    sharpe_ratio: float


class OptimizeRiskMetrics(BaseModel):
    """Portfolio-level downside risk metrics."""

    var_95: float
    cvar_95: float
    max_drawdown: float


class OptimizeResponse(BaseModel):
    """Full response from POST /api/v1/portfolio/optimize."""

    symbols: List[str]
    interval: str
    from_date: Optional[str]   # ISO date actually used (None = all history)
    to_date: Optional[str]     # ISO date actually used (None = latest row)
    target: str
    weights: Dict[str, float]
    performance: PortfolioPerformance
    efficient_frontier: List[FrontierPoint]
    risk_metrics: OptimizeRiskMetrics
    data_points_used: Dict[str, int]
    shared_data_points: int


# ── POST /api/v1/portfolio/simulate ──────────────────────────────────────────


class SimulateRequest(_PortfolioBase):
    """Request body for the portfolio simulation endpoint."""

    weights: Dict[str, float] = Field(
        ...,
        description="Optimal asset weights from a prior optimization run (must sum to ~1).",
    )
    n_simulations: int = Field(
        default=500,
        ge=100,
        le=2000,
        description="Number of independent simulation paths (100–2 000).",
    )
    n_periods: Optional[int] = Field(
        default=None,
        ge=1,
        le=756,
        description=(
            "Simulation horizon in bar-interval steps. "
            "Defaults: 126 for '1d', 26 for '1wk', 6 for '1mo'."
        ),
    )
    initial_value: float = Field(
        default=10_000.0,
        gt=0,
        description="Starting portfolio dollar value for wealth-path projections.",
    )


class SimulationBands(BaseModel):
    """Percentile fan-chart bands for one simulation method."""

    p5:  List[float]
    p25: List[float]
    p50: List[float]
    p75: List[float]
    p95: List[float]
    terminal_values: List[float]  # Raw terminal values for histogram (≤ 500)
    dates: List[str]              # ISO-8601 projected dates (length = n_periods + 1)


class SimulationSummary(BaseModel):
    """Aggregate statistics derived from one simulation run."""

    prob_positive: float     # Fraction of paths ending above initial_value
    expected_terminal: float # Mean terminal portfolio value ($)
    ci_5:  float             # 5th percentile terminal value
    ci_25: float
    ci_50: float
    ci_75: float
    ci_95: float             # 95th percentile terminal value
    sortino_ratio: float
    calmar_ratio:  float
    omega_ratio:   float
    max_drawdown:  float     # Worst peak-to-trough drop on the median path


class SimulateResponse(BaseModel):
    """Full response from POST /api/v1/portfolio/simulate."""

    symbols: List[str]
    interval: str
    from_date: Optional[str]
    to_date:   Optional[str]
    weights:   Dict[str, float]
    n_simulations: int
    n_periods:     int
    initial_value: float
    monte_carlo: SimulationBands
    historical:  SimulationBands
    mc_summary:   SimulationSummary
    hist_summary: SimulationSummary
    data_points_used: Dict[str, int]
    shared_data_points: int

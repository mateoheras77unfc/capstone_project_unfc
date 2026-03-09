export interface AssetOut {
  id: string;
  symbol: string;
  name: string | null;
  asset_type: "stock" | "crypto" | "index";
  currency: string;
  last_updated: string | null;
  created_at: string | null;
}

export interface PriceOut {
  id: string;
  asset_id: string;
  timestamp: string;
  open_price: number | null;
  high_price: number | null;
  low_price: number | null;
  close_price: number;
  volume: number | null;
}

export interface SyncResponse {
  status: "success";
  message: string;
  symbol: string;
  rows_synced: number;
}

export interface ForecastRequest {
  symbol: string;
  interval?: "1d" | "1wk" | "1mo";
  periods?: number;
  lookback_window?: number;
  epochs?: number;
  confidence_level?: number;
}

export interface ForecastResponse {
  symbol: string;
  interval: string;
  model?: string;
  periods_ahead: number;
  forecast_horizon_label: string;
  data_points_used: number;
  dates: string[];
  point_forecast: number[];
  lower_bound: number[];
  upper_bound: number[];
  confidence_level: number;
  model_info: Record<string, any>;
}

/** Models supported by the metrics / bounds endpoint. */
export type ForecastModelKey = "chronos";

export interface ForecastMetricsRequest {
  symbol: string;
  interval?: "1d" | "1wk" | "1mo";
  last_n_weeks?: number;
  lookback_window?: number;
  epochs?: number;
  confidence_level?: number;
  models?: ForecastModelKey[];
  bounds_horizon_periods?: number;
}

export interface ModelMetricRow {
  model: string;
  mae: number;
  rmse: number;
  mape: number;
}

export interface ModelBoundsRow {
  model: string;
  lower: number[];
  forecast: number[];
  upper: number[];
}

export interface ForecastMetricsResponse {
  symbol: string;
  interval: string;
  last_n_weeks: number;
  bounds_horizon_weeks: number;
  metrics: ModelMetricRow[];
  bounds: ModelBoundsRow[];
  error: string | null;
}

export interface AnalyzeRequest {
  interval?: "1d" | "1wk" | "1mo";
  periods?: number;
  model?: "chronos";
  asset_type?: "stock" | "crypto" | "index";
  lookback_window?: number;
  epochs?: number;
  confidence_level?: number;
}

export interface AnalyzeResponse extends ForecastResponse {
  sync: {
    performed: boolean;
    rows_synced: number;
    message: string;
  };
}

export interface PortfolioBaseRequest {
  symbols: string[];
  interval?: "1d" | "1wk" | "1mo";
  risk_free_rate?: number;
  from_date?: string | null;
  to_date?: string | null;
}

export interface StatsRequest extends PortfolioBaseRequest {}

export interface OptimizeRequest extends PortfolioBaseRequest {
  target?: "max_sharpe" | "min_volatility" | "efficient_return" | "efficient_risk" | "hrp";
  target_return?: number | null;
  target_volatility?: number | null;
  n_frontier_points?: number;
}

export interface StatsResponse {
  symbols: string[];
  // Add specific fields based on backend response if needed
  [key: string]: any;
}

export interface OptimizeResponse {
  symbols: string[];
  weights: Record<string, number>;
  performance: {
    expected_annual_return: number;
    annual_volatility: number;
    sharpe_ratio: number;
  };
  efficient_frontier: Array<{
    volatility: number;
    expected_return: number;
    sharpe_ratio: number;
  }>;
  risk_metrics: {
    var_95: number;
    cvar_95: number;
    max_drawdown: number;
  };
  data_points_used: Record<string, number>;
  shared_data_points: number;
}

export interface SimulateRequest {
  symbols: string[];
  weights: Record<string, number>;
  interval?: "1d" | "1wk" | "1mo";
  risk_free_rate?: number;
  from_date?: string | null;
  to_date?: string | null;
  n_simulations?: number;
  n_periods?: number | null;
  initial_value?: number;
}

export interface SimulationBands {
  p5:  number[];
  p25: number[];
  p50: number[];
  p75: number[];
  p95: number[];
  terminal_values: number[];
  dates: string[];
}

export interface SimulationSummary {
  prob_positive:    number;
  expected_terminal: number;
  ci_5:  number;
  ci_25: number;
  ci_50: number;
  ci_75: number;
  ci_95: number;
  sortino_ratio: number;
  calmar_ratio:  number;
  omega_ratio:   number;
  max_drawdown:  number;
}

export interface SimulateResponse {
  symbols: string[];
  interval: string;
  from_date: string | null;
  to_date:   string | null;
  weights:   Record<string, number>;
  n_simulations: number;
  n_periods:     number;
  initial_value: number;
  monte_carlo:  SimulationBands;
  historical:   SimulationBands;
  mc_summary:   SimulationSummary;
  hist_summary: SimulationSummary;
  data_points_used: Record<string, number>;
  shared_data_points: number;
}

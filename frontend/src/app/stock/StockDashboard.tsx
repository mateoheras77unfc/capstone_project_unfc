"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  AssetOut,
  PriceOut,
  StatsResponse,
  ForecastMetricsResponse,
  type ForecastModelKey,
} from "@/types/api";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Loader2 } from "lucide-react";
import { StockChart } from "./StockChart";
import { TourButton } from "@/components/TourButton";
import type { TourStep } from "@/hooks/use-shepherd-tour";

const METRICS_MODEL_ORDER: ForecastModelKey[] = ["base", "prophet", "prophet_xgb"];

const STOCK_TOUR_STEPS: TourStep[] = [
  {
    id: "welcome",
    title: "Welcome to Stock Analysis 📈",
    text: "This page lets you explore price history, generate forecasts with AI models, and view risk metrics. Let's take a quick tour!",
  },
  {
    id: "asset-selector",
    title: "Pick a Stock",
    text: "Use this dropdown to select any asset already in our database. All stocks have historical daily price data synced automatically.",
    attachTo: { element: "#tour-stock-selector", on: "bottom" },
  },
  {
    id: "fetch-new",
    title: "Fetch a New Ticker",
    text: "Don't see your stock? Type any valid ticker symbol here and hit Sync — we'll pull its full price history from Yahoo Finance and add it to the database.",
    attachTo: { element: "#tour-stock-fetch", on: "bottom" },
  },
  {
    id: "model-select",
    title: "Forecast Model",
    text: "Choose between Base (fast exponential smoothing), Prophet (trend + seasonality), or Prophet + XGBoost.",
    attachTo: { element: "#tour-stock-model", on: "bottom" },
  },
  {
    id: "interval-select",
    title: "Chart Interval",
    text: "Switch between Daily, Weekly, and Monthly views. All data is stored at daily granularity and aggregated on-the-fly — no extra API calls needed!",
    attachTo: { element: "#tour-stock-interval", on: "bottom" },
  },
  {
    id: "forecast-btn",
    title: "Generate Forecast",
    text: "Click here to run the selected model and overlay a forecast (with confidence bands) directly on the price chart. Horizons are calculated automatically.",
    attachTo: { element: "#tour-stock-forecast-btn", on: "top" },
  },
  {
    id: "stats-panel",
    title: "Risk & Return Metrics",
    text: "On the right you'll find key statistics: Sharpe Ratio, Max Drawdown, Annualised Volatility, Skewness and more — all calculated from real historical returns.",
    attachTo: { element: "#tour-stock-stats", on: "left" },
  },
];

interface StockDashboardProps {
  assets: AssetOut[];
  initialSymbol?: string;
  initialPrices?: PriceOut[] | null;
  initialStats?: StatsResponse | null;
  initialFromDate?: string;
  initialToDate?: string;
}

export function StockDashboard({ assets, initialSymbol, initialPrices, initialStats, initialFromDate, initialToDate }: StockDashboardProps) {
  const router = useRouter();
  const { toast } = useToast();
  const [syncSymbol, setSyncSymbol] = useState("");
  const [isSyncing, setIsSyncing] = useState(false);

  const [fromDate, setFromDate] = useState(initialFromDate || "");
  const [toDate, setToDate] = useState(initialToDate || "");
  const [metrics, setMetrics] = useState<ForecastMetricsResponse | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [inProgressModels, setInProgressModels] = useState<ForecastModelKey[]>([]);
  const [metricsInterval, setMetricsInterval] = useState<"1wk" | "1mo">("1wk");
  const [forecastDays, setForecastDays] = useState<7 | 14 | 21>(7);
  const [compareAll, setCompareAll] = useState(false);
  const [selectedModel, setSelectedModel] = useState<ForecastModelKey>("base");

  const handleSelect = (symbol: string) => {
    setMetrics(null);
    router.push(`/stock?symbol=${symbol}&from=${fromDate}&to=${toDate}`);
  };

  const handleDateUpdate = () => {
    if (initialSymbol) {
      router.push(`/stock?symbol=${initialSymbol}&from=${fromDate}&to=${toDate}`);
    }
  };

  const handleSync = async () => {
    if (!syncSymbol) return;
    setIsSyncing(true);
    try {
      await api.syncAsset(syncSymbol);
      toast({ title: "Sync Successful", description: `${syncSymbol} has been synced.` });
      router.push(`/stock?symbol=${syncSymbol.toUpperCase()}&from=${fromDate}&to=${toDate}`);
      router.refresh();
      setSyncSymbol("");
    } catch (error: any) {
      toast({ title: "Sync Failed", description: error.message, variant: "destructive" });
    } finally {
      setIsSyncing(false);
    }
  };

  const stats = initialSymbol && initialStats?.individual?.[initialSymbol.toUpperCase()];

  const handleLoadMetrics = async (modelFromChart?: ForecastModelKey) => {
    if (!initialSymbol) return;
    const symbol = initialSymbol.toUpperCase();
    const boundsPeriods = metricsInterval === "1wk" ? forecastDays / 7 : 1;
    const reqBase = {
      symbol,
      interval: metricsInterval,
      last_n_weeks: 20,
      bounds_horizon_periods: boundsPeriods,
    };
    const modelToLoad = modelFromChart ?? selectedModel;
    if (modelFromChart != null) setSelectedModel(modelFromChart);

    if (!compareAll) {
      setMetricsLoading(true);
      setInProgressModels([modelToLoad]);
      setMetrics({ ...reqBase, last_n_weeks: 20, bounds_horizon_weeks: boundsPeriods, metrics: [], bounds: [], error: null });
      try {
        const res = await api.getForecastMetrics({
          ...reqBase,
          models: [modelToLoad],
        });
        setMetrics(res);
        setInProgressModels([]);
        toast({ title: "Metrics loaded", description: `${modelToLoad.replace("_", "+")} — walk-forward and bounds.` });
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to load metrics";
        toast({ title: "Metrics failed", description: msg, variant: "destructive" });
        setInProgressModels([]);
      } finally {
        setMetricsLoading(false);
      }
      return;
    }

    setMetricsLoading(true);
    setInProgressModels([...METRICS_MODEL_ORDER]);
    setMetrics({
      symbol,
      interval: metricsInterval,
      last_n_weeks: 20,
      bounds_horizon_weeks: boundsPeriods,
      metrics: [],
      bounds: [],
      error: null,
    });

    const results: ForecastMetricsResponse[] = [];
    let completed = 0;
    const total = METRICS_MODEL_ORDER.length;

    METRICS_MODEL_ORDER.forEach((modelKey) => {
      api
        .getForecastMetrics({ ...reqBase, models: [modelKey] })
        .then((res) => {
          results.push(res);
          setMetrics((prev) =>
            prev
              ? {
                  ...prev,
                  metrics: [...prev.metrics, ...res.metrics],
                  bounds: [...prev.bounds, ...res.bounds],
                }
              : prev
          );
        })
        .finally(() => {
          completed += 1;
          setInProgressModels((prev) => prev.filter((m) => m !== modelKey));
          if (completed === total) {
            setMetricsLoading(false);
            toast({ title: "Compare all complete", description: "Error metrics and bounds for all models loaded." });
          }
        });
    });
  };

  return (
    <div className="space-y-6">
      {/* ── Page header + Tour button (tour only shown once a stock is selected) ── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Stock Analysis</h1>
          <p className="text-muted-foreground">
            Explore price history, generate AI forecasts, and review risk metrics.
          </p>
        </div>
        {initialSymbol && (
          <TourButton tourKey="tour-stock" steps={STOCK_TOUR_STEPS} />
        )}
      </div>

      {/* ── Stock selector / fetch toolbar ── */}
      <div className="flex flex-col md:flex-row gap-4 justify-between items-start md:items-center bg-muted/50 p-4 rounded-lg border">
        <div id="tour-stock-selector" className="flex items-center gap-4 w-full md:w-auto">
          <span className="font-medium whitespace-nowrap">Select Stock:</span>
          <Select value={initialSymbol} onValueChange={handleSelect}>
            <SelectTrigger className="w-[200px] bg-background">
              <SelectValue placeholder="Choose a stock..." />
            </SelectTrigger>
            <SelectContent>
              {assets.map((a) => (
                <SelectItem key={a.symbol} value={a.symbol}>
                  {a.symbol} - {a.name || "Unknown"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div id="tour-stock-fetch" className="flex items-center gap-2 w-full md:w-auto">
          <span className="font-medium whitespace-nowrap">Fetch New:</span>
          <Input
            placeholder="Ticker (e.g. TSLA)"
            value={syncSymbol}
            onChange={(e) => setSyncSymbol(e.target.value.toUpperCase())}
            className="w-[150px] bg-background"
          />
          <Button onClick={handleSync} disabled={isSyncing || !syncSymbol}>
            {isSyncing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Sync
          </Button>
        </div>
      </div>

      {!initialSymbol && (
        <div className="text-center py-20 text-muted-foreground">
          Please select a stock from the dropdown or fetch a new one to view its details.
        </div>
      )}

      {initialSymbol && initialPrices && initialPrices.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <Card id="tour-stock-chart">
              <CardHeader className="pb-2">
                <CardTitle>{initialSymbol.toUpperCase()} Price History & Forecast</CardTitle>
              </CardHeader>
              <CardContent>
                <StockChart
                  symbol={initialSymbol.toUpperCase()}
                  initialPrices={initialPrices}
                  forecastDays={forecastDays}
                  setForecastDays={setForecastDays}
                  compareAll={compareAll}
                  setCompareAll={setCompareAll}
                  onForecastComplete={(chartModel) => handleLoadMetrics(chartModel)}
                  metricsLoading={metricsLoading}
                />
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card id="tour-stock-stats">
              <CardHeader className="pb-4">
                <CardTitle>Portfolio Stats</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col gap-3 mb-6">
                  <div className="flex items-center gap-2">
                    <Input 
                      type="date" 
                      value={fromDate} 
                      onChange={(e) => setFromDate(e.target.value)} 
                      className="h-8 text-xs"
                    />
                    <span className="text-muted-foreground text-xs">to</span>
                    <Input 
                      type="date" 
                      value={toDate} 
                      onChange={(e) => setToDate(e.target.value)} 
                      className="h-8 text-xs"
                    />
                  </div>
                  <Button size="sm" variant="secondary" onClick={handleDateUpdate} className="w-full">
                    Update Range
                  </Button>
                </div>
                {stats ? (
                  <div className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Avg Return</span>
                      <span className="font-medium">{(stats.avg_return * 100).toFixed(2)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Variance</span>
                      <span className="font-medium">{stats.variance?.toFixed(6)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Std Deviation</span>
                      <span className="font-medium">{(stats.std_deviation * 100).toFixed(2)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Cumulative Return</span>
                      <span className={`font-medium ${stats.cumulative_return >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                        {(stats.cumulative_return * 100).toFixed(2)}%
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Ann. Volatility</span>
                      <span className="font-medium">{(stats.annualized_volatility * 100).toFixed(2)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Sharpe Ratio</span>
                      <span className="font-medium">{stats.sharpe_score?.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Max Drawdown</span>
                      <span className="font-medium text-red-500">{(stats.max_drawdown * 100).toFixed(2)}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Skewness</span>
                      <span className="font-medium">{stats.skewness?.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Kurtosis</span>
                      <span className="font-medium">{stats.kurtosis?.toFixed(2)}</span>
                    </div>
                    
                    <div className="pt-3 mt-3 border-t">
                      <div className="font-medium mb-3 text-muted-foreground">Returns Summary</div>
                      <div className="space-y-3">
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Min</span>
                          <span className="font-medium text-red-500">{(stats.returns_summary?.min * 100).toFixed(2)}%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Max</span>
                          <span className="font-medium text-green-500">{(stats.returns_summary?.max * 100).toFixed(2)}%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Mean</span>
                          <span className="font-medium">{(stats.returns_summary?.mean * 100).toFixed(2)}%</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-muted-foreground text-sm">
                    Stats not available. The asset might not have enough historical data (minimum 60 trading days required).
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Error Metrics & Forecast Bounds — below chart, progressive display */}
      {initialSymbol && initialPrices && initialPrices.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle>Error Metrics Comparison</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <p className="text-sm text-muted-foreground mb-3 min-h-[2.5rem]">
                Walk-forward 1-step backtest over the last 20 weeks. Lower values indicate better accuracy.
                {compareAll
                  ? " Compare all: each model loads as it finishes."
                  : ` Single model (${selectedModel}): one request.`}
              </p>
              {metrics?.error && (
                <p className="text-sm text-amber-600 dark:text-amber-400">{metrics.error}</p>
              )}
              {metrics && !metrics.error && metrics.metrics.length === 0 && inProgressModels.length === 0 && (
                <p className="text-sm text-muted-foreground">No metrics computed (models may have failed).</p>
              )}
              {((metrics?.metrics.length ?? 0) > 0 || inProgressModels.length > 0) && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-2 font-medium">Model</th>
                        <th className="text-right py-2 font-medium">MAE</th>
                        <th className="text-right py-2 font-medium">RMSE</th>
                        <th className="text-right py-2 font-medium">MAPE %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(compareAll
                        ? METRICS_MODEL_ORDER
                        : inProgressModels.length > 0
                          ? inProgressModels
                          : (metrics?.metrics ?? []).map((r) => r.model)
                      ).map((modelKey) => {
                        const row = metrics?.metrics.find((r) => r.model === modelKey);
                        const loading = inProgressModels.includes(modelKey);
                        return (
                          <tr key={modelKey} className="border-b border-border/50">
                            <td className="py-2 capitalize">{modelKey.replace("_", "+")}</td>
                            {loading ? (
                              <td className="text-right py-2" colSpan={3}>
                                <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  Loading…
                                </span>
                              </td>
                            ) : row ? (
                              <>
                                <td className="text-right py-2">{row.mae.toFixed(2)}</td>
                                <td className="text-right py-2">{row.rmse.toFixed(2)}</td>
                                <td className="text-right py-2">{row.mape.toFixed(2)}%</td>
                              </>
                            ) : (
                              <td colSpan={3} className="text-right py-2 text-muted-foreground">—</td>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle>
                Forecast Bounds ({metrics ? `${metrics.bounds_horizon_weeks} ${metrics.interval === "1mo" ? "month(s)" : "week(s)"}` : `${forecastDays} days`} horizon)
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <p className="text-sm text-muted-foreground mb-3 min-h-[2.5rem]">
                Lowest expected price, highest expected price, and average forecast per model over the selected horizon.
              </p>
              {metrics && metrics.bounds.length === 0 && !metrics.error && inProgressModels.length === 0 && (
                <p className="text-sm text-muted-foreground">Load metrics to see bounds (uses same horizon as chart).</p>
              )}
              {((metrics?.bounds.length ?? 0) > 0 || inProgressModels.length > 0) && (
                <div className="overflow-x-auto space-y-4">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-2 font-medium">Model</th>
                        <th className="text-right py-2 font-medium">Lowest expected</th>
                        <th className="text-right py-2 font-medium">Highest expected</th>
                        <th className="text-right py-2 font-medium">Average forecast</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(compareAll
                        ? METRICS_MODEL_ORDER
                        : inProgressModels.length > 0
                          ? inProgressModels
                          : (metrics?.bounds ?? []).map((b) => b.model)
                      ).map((modelKey) => {
                        const b = metrics?.bounds.find((x) => x.model === modelKey);
                        const loading = inProgressModels.includes(modelKey);
                        if (loading) {
                          return (
                            <tr key={modelKey} className="border-b border-border/50">
                              <td className="py-2 capitalize">{modelKey.replace("_", "+")}</td>
                              <td className="text-right py-2" colSpan={3}>
                                <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  Loading…
                                </span>
                              </td>
                            </tr>
                          );
                        }
                        if (!b) return null;
                        const lowest = b.lower.length ? Math.min(...b.lower) : 0;
                        const highest = b.upper.length ? Math.max(...b.upper) : 0;
                        const avg =
                          b.forecast.length
                            ? b.forecast.reduce((s, v) => s + v, 0) / b.forecast.length
                            : 0;
                        return (
                          <tr key={b.model} className="border-b border-border/50">
                            <td className="py-2 capitalize">{b.model.replace("_", "+")}</td>
                            <td className="text-right py-2">${lowest.toFixed(2)}</td>
                            <td className="text-right py-2">${highest.toFixed(2)}</td>
                            <td className="text-right py-2 font-medium">${avg.toFixed(2)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {initialSymbol && (!initialPrices || initialPrices.length === 0) && (
        <div className="text-center py-20 text-muted-foreground">
          No price data found for {initialSymbol.toUpperCase()}. Try syncing it again.
        </div>
      )}
    </div>
  );
}

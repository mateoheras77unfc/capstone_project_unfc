"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { SimulateResponse, SimulateRequest } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import {
  Loader2,
  ArrowLeft,
  Activity,
  TrendingUp,
  TrendingDown,
  BarChart3,
  RefreshCw,
} from "lucide-react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { SparkChat } from "@/components/SparkChat";

// ── Constants ────────────────────────────────────────────────────────────────

const COLORS = [
  "#0088FE", "#00C49F", "#FFBB28", "#FF8042", "#8884D8",
  "#82CA9D", "#A4DE6C", "#D0ED57", "#F2C80F", "#FF6666",
];

const FAN_COLORS = {
  p5_p95: "#6366f1",
  p25_p75: "#8b5cf6",
  p50: "#a78bfa",
};

// ── Context type from localStorage ───────────────────────────────────────────

interface SimulateContext {
  symbols: string[];
  weights: Record<string, number>;
  interval: "1d" | "1wk" | "1mo";
  from_date: string;
  to_date: string;
  risk_free_rate: number;
}

// ── Histogram helper ─────────────────────────────────────────────────────────

function buildHistogram(values: number[], nBins: number) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const binWidth = (max - min) / nBins;
  const bins = Array.from({ length: nBins }, (_, i) => ({
    range: `$${((min + i * binWidth) / 1000).toFixed(1)}k`,
    count: 0,
    midpoint: min + (i + 0.5) * binWidth,
  }));
  for (const v of values) {
    const idx = Math.min(Math.floor((v - min) / binWidth), nBins - 1);
    bins[idx].count += 1;
  }
  return bins;
}

// ── Fan chart data builder ───────────────────────────────────────────────────

function buildFanData(bands: SimulateResponse["monte_carlo"]) {
  return bands.dates.map((date, i) => ({
    date,
    label: date.slice(0, 10),
    p5:  bands.p5[i],
    p25: bands.p25[i],
    p50: bands.p50[i],
    p75: bands.p75[i],
    p95: bands.p95[i],
    // Ranges for stacked areas
    range_5_25:  bands.p25[i] - bands.p5[i],
    range_25_50: bands.p50[i] - bands.p25[i],
    range_50_75: bands.p75[i] - bands.p50[i],
    range_75_95: bands.p95[i] - bands.p75[i],
  }));
}

// ── Formatting helpers ────────────────────────────────────────────────────────

const fmt$ = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const fmtPct = (v: number) => `${(v * 100).toFixed(1)}%`;

// ── Summary metric card ───────────────────────────────────────────────────────

function MetricRow({
  label,
  mc,
  hist,
  format,
  redWhenLow,
}: {
  label: string;
  mc: number;
  hist: number;
  format: (v: number) => string;
  redWhenLow?: boolean;
}) {
  return (
    <div className="grid grid-cols-3 gap-2 items-center py-2 border-b border-border/50 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span
        className={`text-sm font-semibold text-center ${
          redWhenLow && mc < 0 ? "text-red-400" : "text-violet-300"
        }`}
      >
        {format(mc)}
      </span>
      <span
        className={`text-sm font-semibold text-center ${
          redWhenLow && hist < 0 ? "text-red-400" : "text-emerald-300"
        }`}
      >
        {format(hist)}
      </span>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function PortfolioSimulation() {
  const router = useRouter();
  const { toast } = useToast();

  const [ctx, setCtx] = useState<SimulateContext | null>(null);
  const [result, setResult] = useState<SimulateResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // User-adjustable settings
  const [nSimulations, setNSimulations] = useState(500);
  const [initialValue, setInitialValue] = useState("10000");

  // Load context from localStorage on mount
  useEffect(() => {
    const raw = localStorage.getItem("portfolio_simulate_context");
    if (!raw) {
      router.replace("/portfolio");
      return;
    }
    try {
      const parsed: SimulateContext = JSON.parse(raw);
      setCtx(parsed);
    } catch {
      router.replace("/portfolio");
    }
  }, [router]);

  const runSimulation = useCallback(
    async (context: SimulateContext) => {
      setIsLoading(true);
      try {
        const req: SimulateRequest = {
          symbols: context.symbols,
          weights: context.weights,
          interval: context.interval,
          risk_free_rate: context.risk_free_rate,
          from_date: context.from_date,
          to_date: context.to_date,
          n_simulations: nSimulations,
          initial_value: parseFloat(initialValue) || 10_000,
        };
        const res = await api.portfolioSimulate(req);
        setResult(res);
      } catch (err: any) {
        toast({
          title: "Simulation Failed",
          description: err.message || "An unexpected error occurred.",
          variant: "destructive",
        });
      } finally {
        setIsLoading(false);
      }
    },
    [nSimulations, initialValue, toast]
  );

  // Auto-run once context is ready
  useEffect(() => {
    if (ctx) runSimulation(ctx);
  }, [ctx]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Derived chart data ─────────────────────────────────────────────────────

  const mcFanData   = result ? buildFanData(result.monte_carlo) : [];
  const histFanData = result ? buildFanData(result.historical)  : [];

  const mcHistogram   = result ? buildHistogram(result.monte_carlo.terminal_values,  20) : [];
  const histHistogram = result ? buildHistogram(result.historical.terminal_values,   20) : [];

  const pieData = ctx
    ? Object.entries(ctx.weights).map(([name, value]) => ({ name, value: value * 100 }))
    : [];

  const initVal = parseFloat(initialValue) || 10_000;

  // ── Fan chart tooltip formatter ────────────────────────────────────────────

  const FanTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const p = payload[0]?.payload;
    if (!p) return null;
    return (
      <div className="bg-background border border-border rounded-lg p-3 text-xs shadow-lg">
        <p className="font-semibold mb-1">{label}</p>
        <p className="text-violet-300">P95: {fmt$(p.p95)}</p>
        <p className="text-violet-400">P75: {fmt$(p.p75)}</p>
        <p className="text-white font-bold">P50: {fmt$(p.p50)}</p>
        <p className="text-violet-400">P25: {fmt$(p.p25)}</p>
        <p className="text-violet-300">P5: {fmt$(p.p5)}</p>
      </div>
    );
  };

  // ── Fan chart component ────────────────────────────────────────────────────

  const FanChart = ({
    data,
    title,
    color,
  }: {
    data: ReturnType<typeof buildFanData>;
    title: string;
    color: string;
  }) => (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-5 w-5" style={{ color }} />
          {title}
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Percentile fan (P5/P25/P50/P75/P95) · {result?.n_simulations.toLocaleString()} paths
        </p>
      </CardHeader>
      <CardContent>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
              <defs>
                <linearGradient id={`grad-${color}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={color} stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10, fill: "#94a3b8" }}
                interval={Math.floor(data.length / 5)}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#94a3b8" }}
                tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                width={56}
              />
              <Tooltip content={<FanTooltip />} />
              <ReferenceLine y={initVal} stroke="#fbbf24" strokeDasharray="4 4" strokeWidth={1.5} label={{ value: "Initial", fill: "#fbbf24", fontSize: 10 }} />
              {/* P5 → P95 outer band */}
              <Area type="monotone" dataKey="p5"  stroke="none" fill="none" />
              <Area type="monotone" dataKey="p95" stroke={color} strokeWidth={1} strokeOpacity={0.4} fill={`url(#grad-${color})`} fillOpacity={0.4} />
              {/* P25 → P75 inner band */}
              <Area type="monotone" dataKey="p25" stroke="none" fill="none" />
              <Area type="monotone" dataKey="p75" stroke={color} strokeWidth={1} strokeOpacity={0.6} fill={color} fillOpacity={0.25} />
              {/* P50 median line */}
              <Area type="monotone" dataKey="p50" stroke={color} strokeWidth={2.5} fill="none" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="flex items-center gap-4 flex-wrap mt-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm opacity-40" style={{ background: color }} /> P5–P95</span>
          <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm opacity-70" style={{ background: color }} /> P25–P75</span>
          <span className="flex items-center gap-1"><span className="inline-block w-6 h-0.5" style={{ background: color }} /> Median (P50)</span>
          <span className="flex items-center gap-1"><span className="inline-block w-6 h-0.5 border-t-2 border-dashed border-yellow-400" /> Initial value</span>
        </div>
      </CardContent>
    </Card>
  );

  // ── Render ─────────────────────────────────────────────────────────────────

  if (!ctx) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Page header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push("/portfolio")}
              className="text-muted-foreground hover:text-foreground -ml-2 flex items-center gap-1"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Portfolio
            </Button>
          </div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <Activity className="h-8 w-8 text-violet-400" />
            Portfolio Simulation
          </h1>
          <p className="text-muted-foreground mt-1">
            Monte Carlo &amp; Historical Bootstrap forward projections for{" "}
            <span className="font-semibold text-foreground">{ctx.symbols.join(", ")}</span>
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── Left panel ── */}
        <div className="space-y-6">
          {/* Portfolio context */}
          <Card>
            <CardHeader>
              <CardTitle>Portfolio Weights</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-[200px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={40}
                      outerRadius={70}
                      paddingAngle={4}
                      dataKey="value"
                    >
                      {pieData.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: number) => [`${v.toFixed(1)}%`, "Weight"]} />
                    <Legend
                      formatter={(value) => (
                        <span className="text-xs">{value}</span>
                      )}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="space-y-1 mt-2">
                {Object.entries(ctx.weights).map(([sym, w], i) => (
                  <div key={sym} className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <span
                        className="inline-block h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: COLORS[i % COLORS.length] }}
                      />
                      <span className="font-medium">{sym}</span>
                    </span>
                    <span className="text-muted-foreground">{(w * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Simulation settings */}
          <Card>
            <CardHeader>
              <CardTitle>Simulation Settings</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Starting Value ($)</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
                  <Input
                    type="number"
                    min="100"
                    step="1000"
                    value={initialValue}
                    onChange={(e) => setInitialValue(e.target.value)}
                    className="pl-7"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">
                  Number of Simulations ({nSimulations.toLocaleString()})
                </label>
                <input
                  type="range"
                  min={100}
                  max={2000}
                  step={100}
                  value={nSimulations}
                  onChange={(e) => setNSimulations(Number(e.target.value))}
                  className="w-full accent-violet-500"
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>100 (fast)</span>
                  <span>2000 (precise)</span>
                </div>
              </div>

              <div className="text-xs text-muted-foreground space-y-1 pt-1">
                <div className="flex justify-between">
                  <span>Interval</span>
                  <span className="font-medium text-foreground">{ctx.interval}</span>
                </div>
                <div className="flex justify-between">
                  <span>From</span>
                  <span className="font-medium text-foreground">{ctx.from_date}</span>
                </div>
                <div className="flex justify-between">
                  <span>To</span>
                  <span className="font-medium text-foreground">{ctx.to_date}</span>
                </div>
                {result && (
                  <div className="flex justify-between">
                    <span>Horizon</span>
                    <span className="font-medium text-foreground">{result.n_periods} periods</span>
                  </div>
                )}
              </div>

              <Button
                className="w-full bg-violet-600 hover:bg-violet-500"
                onClick={() => runSimulation(ctx)}
                disabled={isLoading}
              >
                {isLoading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="mr-2 h-4 w-4" />
                )}
                Re-run Simulation
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* ── Right panel (results) ── */}
        <div className="lg:col-span-2 space-y-6">
          {isLoading && !result && (
            <Card className="min-h-[400px] flex items-center justify-center">
              <CardContent className="text-center space-y-3">
                <Loader2 className="h-10 w-10 animate-spin text-violet-400 mx-auto" />
                <p className="text-muted-foreground">
                  Running {nSimulations.toLocaleString()} simulations…
                </p>
              </CardContent>
            </Card>
          )}

          {result && (
            <>
              {/* ── Summary comparison ── */}
              <Card className="border-violet-500/20 bg-violet-500/5">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5 text-violet-400" />
                    Simulation Summary
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">
                    Comparison of Monte Carlo (GBM) vs Historical Bootstrap outcomes
                  </p>
                </CardHeader>
                <CardContent>
                  {/* Column headers */}
                  <div className="grid grid-cols-3 gap-2 pb-2 mb-1 border-b border-border">
                    <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Metric</span>
                    <span className="text-xs font-semibold text-violet-400 uppercase tracking-wide text-center">Monte Carlo</span>
                    <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wide text-center">Historical</span>
                  </div>

                  <MetricRow label="Prob. of Profit" mc={result.mc_summary.prob_positive}   hist={result.hist_summary.prob_positive}   format={fmtPct} />
                  <MetricRow label="Expected Final Value" mc={result.mc_summary.expected_terminal} hist={result.hist_summary.expected_terminal} format={fmt$} />
                  <MetricRow label="5th Pct. Final"  mc={result.mc_summary.ci_5}  hist={result.hist_summary.ci_5}  format={fmt$} redWhenLow />
                  <MetricRow label="Median Final"    mc={result.mc_summary.ci_50} hist={result.hist_summary.ci_50} format={fmt$} />
                  <MetricRow label="95th Pct. Final" mc={result.mc_summary.ci_95} hist={result.hist_summary.ci_95} format={fmt$} />
                  <MetricRow label="Sortino Ratio"   mc={result.mc_summary.sortino_ratio}   hist={result.hist_summary.sortino_ratio}   format={(v) => v.toFixed(3)} />
                  <MetricRow label="Calmar Ratio"    mc={result.mc_summary.calmar_ratio}    hist={result.hist_summary.calmar_ratio}    format={(v) => v.toFixed(3)} />
                  <MetricRow label="Omega Ratio"     mc={result.mc_summary.omega_ratio}     hist={result.hist_summary.omega_ratio}     format={(v) => v.toFixed(3)} />
                  <MetricRow label="Max Drawdown"    mc={result.mc_summary.max_drawdown}    hist={result.hist_summary.max_drawdown}    format={fmtPct} redWhenLow />

                  {/* Stat definitions */}
                  <div className="mt-4 pt-3 border-t border-border/50 grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-muted-foreground">
                    <div>
                      <span className="font-semibold text-foreground">Sortino Ratio</span> — like Sharpe but penalises only downside volatility. Higher = better risk-adjusted return.
                    </div>
                    <div>
                      <span className="font-semibold text-foreground">Calmar Ratio</span> — annualised return ÷ max drawdown. Higher = better return per unit of downside.
                    </div>
                    <div>
                      <span className="font-semibold text-foreground">Omega Ratio</span> — probability-weighted gains ÷ losses. Values {">"} 1 indicate more upside than downside.
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* ── Monte Carlo fan chart ── */}
              <FanChart
                data={mcFanData}
                title="Monte Carlo GBM — Wealth Paths"
                color="#8b5cf6"
              />

              {/* ── Historical Bootstrap fan chart ── */}
              <FanChart
                data={histFanData}
                title="Historical Bootstrap — Wealth Paths"
                color="#10b981"
              />

              {/* ── Terminal value histograms ── */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Monte Carlo histogram */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                      <TrendingUp className="h-4 w-4 text-violet-400" />
                      MC Terminal Distribution
                    </CardTitle>
                    <p className="text-xs text-muted-foreground">
                      Distribution of final portfolio values (Monte Carlo)
                    </p>
                  </CardHeader>
                  <CardContent>
                    <div className="h-[220px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={mcHistogram} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
                          <XAxis dataKey="range" tick={{ fontSize: 9, fill: "#94a3b8" }} interval={3} />
                          <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} width={30} />
                          <Tooltip
                            formatter={(v: number) => [v, "Paths"]}
                            labelFormatter={(l) => `Range: ${l}`}
                          />
                          <ReferenceLine
                            x={mcHistogram.find((b) => Math.abs(b.midpoint - initVal) === Math.min(...mcHistogram.map((b) => Math.abs(b.midpoint - initVal))))?.range}
                            stroke="#fbbf24"
                            strokeDasharray="4 2"
                            strokeWidth={2}
                            label={{ value: "Initial", fill: "#fbbf24", fontSize: 9 }}
                          />
                          <Bar dataKey="count" fill="#8b5cf6" opacity={0.85} radius={[2, 2, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>

                {/* Historical Bootstrap histogram */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                      <TrendingDown className="h-4 w-4 text-emerald-400" />
                      Bootstrap Terminal Distribution
                    </CardTitle>
                    <p className="text-xs text-muted-foreground">
                      Distribution of final portfolio values (Bootstrap)
                    </p>
                  </CardHeader>
                  <CardContent>
                    <div className="h-[220px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={histHistogram} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
                          <XAxis dataKey="range" tick={{ fontSize: 9, fill: "#94a3b8" }} interval={3} />
                          <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} width={30} />
                          <Tooltip
                            formatter={(v: number) => [v, "Paths"]}
                            labelFormatter={(l) => `Range: ${l}`}
                          />
                          <ReferenceLine
                            x={histHistogram.find((b) => Math.abs(b.midpoint - initVal) === Math.min(...histHistogram.map((b) => Math.abs(b.midpoint - initVal))))?.range}
                            stroke="#fbbf24"
                            strokeDasharray="4 2"
                            strokeWidth={2}
                            label={{ value: "Initial", fill: "#fbbf24", fontSize: 9 }}
                          />
                          <Bar dataKey="count" fill="#10b981" opacity={0.85} radius={[2, 2, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* ── Method explainer ── */}
              <Card className="border-border/50 bg-muted/20">
                <CardHeader>
                  <CardTitle className="text-base">Methodology</CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm text-muted-foreground">
                  <div className="space-y-2">
                    <p className="font-semibold text-violet-400">Monte Carlo — Geometric Brownian Motion</p>
                    <p>
                      Estimates the portfolio&apos;s mean return vector and covariance matrix from historical log returns.
                      Correlated shocks are generated via Cholesky decomposition of Σ, then compounded forward.
                      Assumes log-normally distributed returns — captures the general risk profile but may underestimate tail events.
                    </p>
                  </div>
                  <div className="space-y-2">
                    <p className="font-semibold text-emerald-400">Historical Bootstrap</p>
                    <p>
                      Resamples actual daily portfolio returns i.i.d. with replacement to construct each path.
                      Makes no distributional assumptions — preserves fat tails, skewness and real-world market features.
                      Ideal for stress-testing against historically observed extreme events.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </div>

      <SparkChat
        context={
          result
            ? {
                type: "portfolio_simulate",
                data: {
                  symbols: ctx.symbols,
                  weights: ctx.weights,
                  n_simulations: result.n_simulations,
                  n_periods: result.n_periods,
                  initial_value: result.initial_value,
                  mc_summary: result.mc_summary,
                  hist_summary: result.hist_summary,
                },
              }
            : undefined
        }
      />
    </div>
  );
}

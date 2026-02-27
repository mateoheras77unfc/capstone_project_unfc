"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { OptimizeResponse, AssetOut } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Loader2, X, DollarSign, TrendingUp, FileDown } from "lucide-react";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";
import { usePDF } from "react-to-pdf";
import Image from "next/image";
import { TourButton } from "@/components/TourButton";
import type { TourStep } from "@/hooks/use-shepherd-tour";

const COLORS = [
  "#0088FE",
  "#00C49F",
  "#FFBB28",
  "#FF8042",
  "#8884D8",
  "#82CA9D",
  "#A4DE6C",
  "#D0ED57",
  "#F2C80F",
  "#FF6666",
];

const PORTFOLIO_TOUR_STEPS: TourStep[] = [
  {
    id: "welcome",
    title: "Welcome to Portfolio Builder 💼",
    text: "Build and optimise a multi-asset portfolio using Modern Portfolio Theory and Hierarchical Risk Parity. This tour walks you through every control.",
  },
  {
    id: "asset-select",
    title: "Select Assets",
    text: "Pick stocks already in our database from this dropdown. You can add up to 10 symbols to your portfolio at once.",
    attachTo: { element: "#tour-portfolio-assets", on: "right" },
  },
  {
    id: "fetch-new",
    title: "Fetch a New Stock",
    text: "Type any valid ticker and hit Sync to pull full daily history from Yahoo Finance. The new stock will be added instantly.",
    attachTo: { element: "#tour-portfolio-fetch", on: "right" },
  },
  {
    id: "objective",
    title: "Optimisation Objective",
    text: "Choose your goal: maximise Sharpe Ratio, minimise Volatility, hit a Target Return or Volatility, or use Hierarchical Risk Parity (HRP) — a cluster-based method that needs no covariance inversion.",
    attachTo: { element: "#tour-portfolio-objective", on: "right" },
  },
  {
    id: "run-btn",
    title: "Run Optimisation",
    text: "Click this to compute the efficient weights, expected return, and Sharpe ratio using PyPortfolioOpt on the backend.",
    attachTo: { element: "#tour-portfolio-run", on: "top" },
  },
  {
    id: "results",
    title: "Results Panel",
    text: "Once optimised, you'll see the weight donut chart, investment allocation calculator, individual asset stats, correlation matrix, covariance matrix, and beta rankings — everything you need for your report!",
    attachTo: { element: "#tour-portfolio-results", on: "left" },
  },
];

interface PortfolioBuilderProps {
  assets: AssetOut[];
}

export function PortfolioBuilder({ assets }: PortfolioBuilderProps) {
  const router = useRouter();
  const [symbols, setSymbols] = useState<string[]>(["GOOG", "AMZN"]);
  const [syncSymbol, setSyncSymbol] = useState("");
  const [isSyncing, setIsSyncing] = useState(false);
  
  // Default dates: last 3 years to today
  const today = new Date();
  const threeYearsAgo = new Date();
  threeYearsAgo.setFullYear(today.getFullYear() - 3);
  
  const [fromDate, setFromDate] = useState(threeYearsAgo.toISOString().split('T')[0]);
  const [toDate, setToDate] = useState(today.toISOString().split('T')[0]);

  const [target, setTarget] = useState<
    "max_sharpe" | "min_volatility" | "efficient_return" | "efficient_risk" | "hrp"
  >("max_sharpe");
  const [targetValue, setTargetValue] = useState<string>("");
  const [results, setResults] = useState<OptimizeResponse | null>(null);
  const [stats, setStats] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [investAmount, setInvestAmount] = useState<string>("10000");
  const { toast } = useToast();

  const { toPDF, targetRef } = usePDF({
    filename: `portfolio-${symbols.join("-")}-${new Date().toISOString().split("T")[0]}.pdf`,
    page: { format: "a4", orientation: "portrait", margin: 10 },
  });

  const handleAddSymbol = (sym: string) => {
    if (sym && !symbols.includes(sym)) {
      if (symbols.length >= 10) {
        toast({
          title: "Limit Reached",
          description: "You can only add up to 10 symbols.",
          variant: "destructive",
        });
        return;
      }
      setSymbols([...symbols, sym]);
    }
  };

  const handleSync = async () => {
    if (!syncSymbol) return;
    setIsSyncing(true);
    try {
      await api.syncAsset(syncSymbol);
      toast({ title: "Sync Successful", description: `${syncSymbol} has been synced.` });
      handleAddSymbol(syncSymbol.toUpperCase());
      setSyncSymbol("");
      router.refresh(); // Refresh to update the assets list
    } catch (error: any) {
      toast({ title: "Sync Failed", description: error.message, variant: "destructive" });
    } finally {
      setIsSyncing(false);
    }
  };

  const handleRemoveSymbol = (sym: string) => {
    setSymbols(symbols.filter((s) => s !== sym));
  };

  const handleOptimize = async () => {
    if (symbols.length < 2) {
      toast({
        title: "Not Enough Assets",
        description: "Please add at least 2 assets to optimize.",
        variant: "destructive",
      });
      return;
    }

    setIsLoading(true);
    try {
      const reqData: any = {
        symbols,
        target,
        from_date: fromDate,
        to_date: toDate,
      };

      if (target === "efficient_return") {
        reqData.target_return = parseFloat(targetValue);
      } else if (target === "efficient_risk") {
        reqData.target_volatility = parseFloat(targetValue);
      }

      const [optRes, statsRes] = await Promise.all([
        api.portfolioOptimize(reqData),
        api.portfolioStats({
          symbols,
          from_date: fromDate,
          to_date: toDate,
        })
      ]);

      setResults(optRes);
      setStats(statsRes);
      toast({
        title: "Optimization Complete",
        description: "Portfolio weights and stats have been calculated.",
      });
    } catch (error: any) {
      toast({
        title: "Optimization Failed",
        description: error.message || "An error occurred",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const pieData = results
    ? Object.entries(results.weights).map(([name, value]) => ({
        name,
        value: value * 100,
      }))
    : [];

  /**
   * Temporarily apply a light-mode class to the target element so that
   * react-to-pdf captures white backgrounds + dark text instead of the
   * dark navy CSS-variable-driven theme (which renders invisibly in PDFs).
   */
  const handleExportPdf = async () => {
    const el = targetRef.current as HTMLElement | null;
    if (el) el.classList.add("pdf-mode");
    try {
      await toPDF();
    } finally {
      if (el) el.classList.remove("pdf-mode");
    }
  };

  return (
    <div className="space-y-6">
      {/* ── Page header + action buttons ── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Portfolio Builder</h1>
          <p className="text-muted-foreground">
            Construct and optimize your investment portfolio.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {results && (
            <Button
              variant="outline"
              onClick={handleExportPdf}
              className="flex items-center gap-2 h-10 px-4 border-emerald-400/40 text-emerald-400 hover:bg-emerald-400/10 hover:border-emerald-400 hover:text-emerald-300 transition-all font-medium"
            >
              <FileDown className="h-4 w-4 shrink-0" />
              Download PDF
            </Button>
          )}
          <TourButton tourKey="tour-portfolio" steps={PORTFOLIO_TOUR_STEPS} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Assets</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div id="tour-portfolio-assets" className="space-y-2">
                <label className="text-sm font-medium">Select from Database</label>
                <Select onValueChange={(val) => handleAddSymbol(val)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Choose a stock..." />
                  </SelectTrigger>
                  <SelectContent>
                    {assets.map((a) => (
                      <SelectItem key={a.symbol} value={a.symbol} disabled={symbols.includes(a.symbol)}>
                        {a.symbol} - {a.name || "Unknown"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div id="tour-portfolio-fetch" className="space-y-2">
                <label className="text-sm font-medium">Fetch New Stock</label>
                <div className="flex gap-2">
                  <Input
                    placeholder="Ticker (e.g. TSLA)"
                    value={syncSymbol}
                    onChange={(e) => setSyncSymbol(e.target.value.toUpperCase())}
                    onKeyDown={(e) => e.key === "Enter" && handleSync()}
                  />
                  <Button onClick={handleSync} disabled={isSyncing || !syncSymbol}>
                    {isSyncing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Sync
                  </Button>
                </div>
              </div>

              <div className="pt-4 space-y-2">
                <label className="text-sm font-medium">Selected Assets ({symbols.length}/10)</label>
                {symbols.length === 0 && (
                  <div className="text-sm text-muted-foreground">No assets selected.</div>
                )}
                {symbols.map((sym) => (
                  <div
                    key={sym}
                    className="flex items-center justify-between bg-muted/50 p-2 rounded-md"
                  >
                    <span className="font-medium">{sym}</span>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive"
                      onClick={() => handleRemoveSymbol(sym)}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Optimization Settings</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Date Range</label>
                <div className="flex items-center gap-2">
                  <Input 
                    type="date" 
                    value={fromDate} 
                    onChange={(e) => setFromDate(e.target.value)} 
                    className="h-9 text-sm"
                  />
                  <span className="text-muted-foreground text-sm">to</span>
                  <Input 
                    type="date" 
                    value={toDate} 
                    onChange={(e) => setToDate(e.target.value)} 
                    className="h-9 text-sm"
                  />
                </div>
              </div>

              <div id="tour-portfolio-objective" className="space-y-2">
                <label className="text-sm font-medium">Objective</label>
                <Select
                  value={target}
                  onValueChange={(val: any) => setTarget(val)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select Objective" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="max_sharpe">Maximize Sharpe Ratio</SelectItem>
                    <SelectItem value="min_volatility">Minimize Volatility</SelectItem>
                    <SelectItem value="efficient_return">Target Return</SelectItem>
                    <SelectItem value="efficient_risk">Target Volatility</SelectItem>
                    <SelectItem value="hrp">Hierarchical Risk Parity</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {(target === "efficient_return" || target === "efficient_risk") && (
                <div className="space-y-2">
                  <label className="text-sm font-medium">
                    {target === "efficient_return" ? "Target Return (Decimal, e.g. 0.15 for 15%)" : "Target Volatility (Decimal, e.g. 0.15 for 15%)"}
                  </label>
                  <Input
                    type="number"
                    step="0.01"
                    placeholder="e.g. 0.15"
                    value={targetValue}
                    onChange={(e) => setTargetValue(e.target.value)}
                  />
                  {stats && stats.individual && (
                    <div className="text-xs text-muted-foreground mt-1">
                      {target === "efficient_return" 
                        ? `Valid range: ~${(Math.min(...Object.values(stats.individual).map((a: any) => a.avg_return * 52))).toFixed(4)} to ${(Math.max(...Object.values(stats.individual).map((a: any) => a.avg_return * 52))).toFixed(4)}`
                        : `Max volatility: ~${(Math.max(...Object.values(stats.individual).map((a: any) => a.annualized_volatility))).toFixed(4)}`
                      }
                    </div>
                  )}
                  {(!stats || !stats.individual) && (
                    <div className="text-xs text-muted-foreground mt-1">
                      Run 'Maximize Sharpe Ratio' first to see valid ranges.
                    </div>
                  )}
                </div>
              )}

              <div id="tour-portfolio-run">
                <Button
                  className="w-full"
                  onClick={handleOptimize}
                  disabled={isLoading || symbols.length < 2}
                >
                  {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Run Optimization
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        <div id="tour-portfolio-results" ref={targetRef} className="lg:col-span-2 space-y-6">
          {results ? (
            <>
              {/* PDF-only header — hidden in the app, shown during PDF capture */}
              <div className="pdf-report-header hidden">

                {/* ── Brand bar: logo left, mascot right ── */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "18px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                    <Image
                      src="/unf-logo.svg"
                      alt="UNF Logo"
                      width={52}
                      height={52}
                      style={{ objectFit: "contain" }}
                      unoptimized
                    />
                    <div>
                      <div style={{ fontSize: "10px", fontWeight: 700, color: "#0369a1", letterSpacing: "0.12em", textTransform: "uppercase" }}>
                        University of North Florida
                      </div>
                      <div style={{ fontSize: "9px", color: "#64748b", marginTop: "1px" }}>Department of Finance &amp; Economics</div>
                      <div style={{ fontSize: "9px", color: "#94a3b8" }}>UNF Investor Analytics Platform</div>
                    </div>
                  </div>
                  <Image
                    src="/agent-avatar.png"
                    alt="Spark — UNF Investor mascot"
                    width={62}
                    height={62}
                    style={{ borderRadius: "50%", border: "2.5px solid #0369a1", objectFit: "cover" }}
                    unoptimized
                  />
                </div>

                {/* ── Main title ── */}
                <div style={{ marginBottom: "16px", borderLeft: "4px solid #0369a1", paddingLeft: "12px" }}>
                  <h1 style={{ fontSize: "22px", fontWeight: 800, color: "#0f172a", margin: "0 0 3px" }}>
                    Portfolio Optimization Report
                  </h1>
                  <p style={{ fontSize: "12px", color: "#475569", margin: 0 }}>
                    Quantitative multi-asset analysis · powered by PyPortfolioOpt &amp; Yahoo Finance
                  </p>
                </div>

                {/* ── Metadata grid ── */}
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(3, 1fr)",
                  gap: "8px 16px",
                  background: "#f1f5f9",
                  borderRadius: "8px",
                  padding: "12px 16px",
                  marginBottom: "18px",
                  border: "1px solid #e2e8f0",
                }}>
                  <div>
                    <div style={{ fontSize: "9px", fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "2px" }}>Generated</div>
                    <div style={{ fontSize: "12px", fontWeight: 600, color: "#0f172a" }}>
                      {new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: "9px", fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "2px" }}>Portfolio Assets</div>
                    <div style={{ fontSize: "12px", fontWeight: 600, color: "#0f172a" }}>{symbols.join(" · ")}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: "9px", fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "2px" }}>Objective</div>
                    <div style={{ fontSize: "12px", fontWeight: 600, color: "#0f172a" }}>{
                      target === "max_sharpe"      ? "Maximize Sharpe Ratio"
                      : target === "min_volatility" ? "Minimize Volatility"
                      : target === "efficient_return" ? "Target Return"
                      : target === "efficient_risk"   ? "Target Volatility"
                      : "Hierarchical Risk Parity"
                    }</div>
                  </div>
                  <div>
                    <div style={{ fontSize: "9px", fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "2px" }}>Date Range</div>
                    <div style={{ fontSize: "12px", fontWeight: 600, color: "#0f172a" }}>{fromDate} → {toDate}</div>
                  </div>
                  {results?.expected_return != null && (
                    <div>
                      <div style={{ fontSize: "9px", fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "2px" }}>Expected Return</div>
                      <div style={{ fontSize: "12px", fontWeight: 700, color: "#16a34a" }}>{(results.expected_return * 100).toFixed(2)}%</div>
                    </div>
                  )}
                  {results?.volatility != null && (
                    <div>
                      <div style={{ fontSize: "9px", fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "2px" }}>Portfolio Volatility</div>
                      <div style={{ fontSize: "12px", fontWeight: 700, color: "#dc2626" }}>{(results.volatility * 100).toFixed(2)}%</div>
                    </div>
                  )}
                  {results?.sharpe_ratio != null && (
                    <div>
                      <div style={{ fontSize: "9px", fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "2px" }}>Sharpe Ratio</div>
                      <div style={{ fontSize: "12px", fontWeight: 700, color: "#0f172a" }}>{results.sharpe_ratio?.toFixed(4)}</div>
                    </div>
                  )}
                </div>

                <hr style={{ borderColor: "#cbd5e1", margin: "0 0 10px" }} />
                <p style={{ fontSize: "9px", color: "#94a3b8", margin: "0 0 14px", fontStyle: "italic" }}>
                  ⚠ This report is auto-generated by UNF Investor for academic and informational purposes only.
                  It does not constitute financial advice. Data sourced from Yahoo Finance via yfinance.
                </p>

              </div>
              <Card>
                <CardHeader>
                  <CardTitle>Optimal Weights</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="h-[300px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={pieData}
                          cx="50%"
                          cy="50%"
                          innerRadius={60}
                          outerRadius={100}
                          paddingAngle={5}
                          dataKey="value"
                          label={({ name, value }) => `${name} ${(value).toFixed(1)}%`}
                        >
                          {pieData.map((entry, index) => (
                            <Cell
                              key={`cell-${index}`}
                              fill={COLORS[index % COLORS.length]}
                            />
                          ))}
                        </Pie>
                        <Tooltip
                          formatter={(value: number) => [`${value.toFixed(2)}%`, "Weight"]}
                        />
                        <Legend />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>

              {/* ── Investment Allocation Calculator ── */}
              <Card className="border border-cyan-500/20 bg-cyan-500/5">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <DollarSign className="h-5 w-5 text-cyan-400" />
                    Investment Allocation
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div className="flex items-center gap-3">
                    <div className="relative flex-1">
                      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground font-medium">$</span>
                      <Input
                        type="number"
                        min="0"
                        step="100"
                        placeholder="Enter total investment amount"
                        value={investAmount}
                        onChange={(e) => setInvestAmount(e.target.value)}
                        className="pl-7 text-base h-11"
                      />
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="shrink-0 text-muted-foreground"
                      onClick={() => setInvestAmount("")}
                    >
                      Clear
                    </Button>
                  </div>

                  {investAmount && parseFloat(investAmount) > 0 ? (
                    <div className="space-y-3">
                      <p className="text-sm text-muted-foreground">
                        Based on the optimal weights, here is how to allocate{" "}
                        <span className="font-bold text-white">
                          ${parseFloat(investAmount).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>:
                      </p>
                      <div className="space-y-4">
                        {pieData.map((entry, index) => {
                          const alloc = (entry.value / 100) * parseFloat(investAmount);
                          return (
                            <div key={entry.name} className="space-y-1.5">
                              <div className="flex items-center justify-between text-sm">
                                <div className="flex items-center gap-2">
                                  <span
                                    className="inline-block h-3 w-3 rounded-full shrink-0"
                                    style={{ backgroundColor: COLORS[index % COLORS.length] }}
                                  />
                                  <span className="font-semibold">{entry.name}</span>
                                  <span className="text-muted-foreground">({entry.value.toFixed(1)}%)</span>
                                </div>
                                <div className="flex items-center gap-1.5 font-bold text-base">
                                  <TrendingUp className="h-4 w-4 text-cyan-400" />
                                  <span>
                                    ${alloc.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                  </span>
                                </div>
                              </div>
                              <div className="h-2 w-full rounded-full bg-muted/40 overflow-hidden">
                                <div
                                  className="h-full rounded-full transition-all duration-500"
                                  style={{
                                    width: `${entry.value}%`,
                                    backgroundColor: COLORS[index % COLORS.length],
                                  }}
                                />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      <div className="flex justify-between pt-3 border-t border-border text-sm">
                        <span className="text-muted-foreground font-medium">Total</span>
                        <span className="font-bold text-base">
                          ${parseFloat(investAmount).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Enter an amount above to see the exact dollar allocation per asset.
                    </p>
                  )}
                </CardContent>
              </Card>

              {stats && stats.individual && (
                <Card>
                  <CardHeader>
                    <CardTitle>Individual Asset Stats</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      {Object.entries(stats.individual).map(([sym, data]: [string, any]) => (
                        <div key={sym} className="space-y-3 text-sm border p-4 rounded-lg">
                          <div className="font-bold text-lg border-b pb-2 mb-2">{sym}</div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Avg Return</span>
                            <span className="font-medium">{(data.avg_return * 100).toFixed(2)}%</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Ann. Volatility</span>
                            <span className="font-medium">{(data.annualized_volatility * 100).toFixed(2)}%</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Sharpe Ratio</span>
                            <span className="font-medium">{data.sharpe_score?.toFixed(2)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Max Drawdown</span>
                            <span className="font-medium text-red-500">{(data.max_drawdown * 100).toFixed(2)}%</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Cumulative Return</span>
                            <span className={`font-medium ${data.cumulative_return >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                              {(data.cumulative_return * 100).toFixed(2)}%
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {stats && stats.advanced && stats.advanced.correlation_matrix && (
                <Card>
                  <CardHeader>
                    <CardTitle>Correlation Matrix</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm text-left">
                        <thead className="text-xs text-muted-foreground uppercase bg-muted/50">
                          <tr>
                            <th className="px-4 py-2"></th>
                            {Object.keys(stats.advanced.correlation_matrix).map((sym) => (
                              <th key={sym} className="px-4 py-2 font-medium">{sym}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(stats.advanced.correlation_matrix).map(([rowSym, cols]: [string, any]) => (
                            <tr key={rowSym} className="border-b">
                              <td className="px-4 py-2 font-medium">{rowSym}</td>
                              {Object.values(cols).map((val: any, i) => (
                                <td key={i} className="px-4 py-2">
                                  {val.toFixed(2)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}

              {stats && stats.advanced && stats.advanced.covariance_matrix && (
                <Card>
                  <CardHeader>
                    <CardTitle>Covariance Matrix</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm text-left">
                        <thead className="text-xs text-muted-foreground uppercase bg-muted/50">
                          <tr>
                            <th className="px-4 py-2"></th>
                            {Object.keys(stats.advanced.covariance_matrix).map((sym) => (
                              <th key={sym} className="px-4 py-2 font-medium">{sym}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(stats.advanced.covariance_matrix).map(([rowSym, cols]: [string, any]) => (
                            <tr key={rowSym} className="border-b">
                              <td className="px-4 py-2 font-medium">{rowSym}</td>
                              {Object.values(cols).map((val: any, i) => (
                                <td key={i} className="px-4 py-2">
                                  {val.toFixed(6)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}

              {stats && stats.advanced && stats.advanced.beta_vs_equal_weighted && (
                <Card>
                  <CardHeader>
                    <CardTitle>Beta vs Equal-Weighted Portfolio</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      {Object.entries(stats.advanced.beta_vs_equal_weighted).map(([sym, beta]: [string, any]) => (
                        <div key={sym} className="p-4 border rounded-lg text-center bg-muted/20">
                          <div className="text-sm text-muted-foreground mb-1">{sym}</div>
                          <div className="text-xl font-bold">{beta.toFixed(4)}</div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          ) : (
            <Card className="h-full flex items-center justify-center min-h-[400px]">
              <CardContent className="text-center text-muted-foreground">
                Add assets and run optimization to see results.
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

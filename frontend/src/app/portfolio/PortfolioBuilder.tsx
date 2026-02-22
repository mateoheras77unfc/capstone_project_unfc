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
import { Loader2, X, DollarSign, TrendingUp } from "lucide-react";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";

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
    "max_sharpe" | "min_volatility" | "efficient_return" | "efficient_risk"
  >("max_sharpe");
  const [targetValue, setTargetValue] = useState<string>("");
  const [results, setResults] = useState<OptimizeResponse | null>(null);
  const [stats, setStats] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [investAmount, setInvestAmount] = useState<string>("");
  const { toast } = useToast();

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Portfolio Builder</h1>
        <p className="text-muted-foreground">
          Construct and optimize your investment portfolio.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Assets</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
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

              <div className="space-y-2">
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

              <div className="space-y-2">
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

              <Button
                className="w-full"
                onClick={handleOptimize}
                disabled={isLoading || symbols.length < 2}
              >
                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Run Optimization
              </Button>
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-2 space-y-6">
          {results ? (
            <>
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

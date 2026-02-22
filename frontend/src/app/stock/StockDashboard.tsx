"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AssetOut, PriceOut, StatsResponse } from "@/types/api";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Loader2 } from "lucide-react";
import { StockChart } from "./StockChart";

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

  const handleSelect = (symbol: string) => {
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

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row gap-4 justify-between items-start md:items-center bg-muted/50 p-4 rounded-lg border">
        <div className="flex items-center gap-4 w-full md:w-auto">
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

        <div className="flex items-center gap-2 w-full md:w-auto">
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
            <Card>
              <CardHeader>
                <CardTitle>{initialSymbol.toUpperCase()} Price History & Forecast</CardTitle>
              </CardHeader>
              <CardContent>
                <StockChart symbol={initialSymbol.toUpperCase()} initialPrices={initialPrices} />
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
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
                    Stats not available. The asset might not have enough historical data (minimum 52 weeks required).
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
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

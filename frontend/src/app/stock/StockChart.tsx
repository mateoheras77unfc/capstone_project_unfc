"use client";

import { useState } from "react";
import { PriceOut, ForecastResponse } from "@/types/api";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ComposedChart,
  ReferenceLine,
  Legend,
} from "recharts";
import { useToast } from "@/hooks/use-toast";

interface StockChartProps {
  symbol: string;
  initialPrices: PriceOut[];
  /** Forecast horizon in days (7, 14, or 21). */
  forecastDays?: 7 | 14 | 21;
  setForecastDays?: (days: 7 | 14 | 21) => void;
  compareAll?: boolean;
  setCompareAll?: (value: boolean) => void;
  /** Called after a successful forecast with the model used; parent can load metrics for that model. */
  onForecastComplete?: (model: "base" | "prophet" | "prophet_xgb") => void;
  metricsLoading?: boolean;
}

export function StockChart({
  symbol,
  initialPrices,
  forecastDays = 7,
  setForecastDays,
  compareAll = false,
  setCompareAll,
  onForecastComplete,
  metricsLoading = false,
}: StockChartProps) {
  const [model, setModel] = useState<"base" | "prophet" | "prophet_xgb">("base");
  const [interval, setInterval] = useState<"1d" | "1wk" | "1mo">("1d");
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();

  // Reverse prices to be chronological for the chart
  let baseData = [...initialPrices].reverse();

  // Helper: group daily data by a key and return mean close per group.
  // Returned array is sorted chronologically by first-seen key.
  function aggregateByKey(
    data: PriceOut[],
    keyFn: (d: Date) => string
  ): PriceOut[] {
    const order: string[] = [];
    const groups: Record<string, { sum: number; count: number; first: PriceOut }> = {};
    data.forEach((p) => {
      const key = keyFn(new Date(p.timestamp));
      if (!groups[key]) {
        groups[key] = { sum: 0, count: 0, first: p };
        order.push(key);
      }
      groups[key].sum += p.close_price;
      groups[key].count += 1;
    });
    // Use insertion-order array to guarantee chronological output.
    return order.map((key) => ({
      ...groups[key].first,
      close_price: groups[key].sum / groups[key].count,
    }));
  }

  // Returns a stable Monday-anchored ISO week string "YYYY-Www".
  function isoWeekKey(d: Date): string {
    // Copy date and shift to the nearest Monday (start of ISO week).
    const day = new Date(d);
    const dow = day.getUTCDay(); // 0=Sun … 6=Sat
    const diff = dow === 0 ? -6 : 1 - dow; // shift to Monday
    day.setUTCDate(day.getUTCDate() + diff);
    const yyyy = day.getUTCFullYear();
    const mm = String(day.getUTCMonth() + 1).padStart(2, "0");
    const dd = String(day.getUTCDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`; // one key per calendar week
  }

  // Aggregate daily data into weekly or monthly means.
  if (interval === "1wk") {
    baseData = aggregateByKey(baseData, isoWeekKey);
  } else if (interval === "1mo") {
    baseData = aggregateByKey(
      baseData,
      (d) =>
        `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`
    );
  }

  const chartData: Array<{
    date: string;
    price?: number;
    forecast?: number;
    lower?: number;
    upper?: number;
  }> = baseData.map((p) => ({
    date: p.timestamp,
    price: p.close_price,
  }));

  // Forecast overlays on the same chart: separate key so we can style it dashed + distinct color.
  // Add a connector point so the forecast line starts from the last historical price.
  let firstForecastDate: string | null = null;
  if (forecast && baseData.length > 0) {
    const lastHist = baseData[baseData.length - 1];
    chartData.push({
      date: lastHist.timestamp,
      forecast: lastHist.close_price,
    });
    forecast.dates.forEach((dateStr, i) => {
      firstForecastDate = firstForecastDate ?? dateStr;
      chartData.push({
        date: dateStr,
        forecast: forecast.point_forecast[i],
        lower: forecast.lower_bound[i],
        upper: forecast.upper_bound[i],
      });
    });
  }

  // ── X-axis label format varies by interval ────────────────────────────
  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
                  "Jul","Aug","Sep","Oct","Nov","Dec"];

  function formatXAxis(iso: string): string {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const mon = MONTHS[d.getUTCMonth()];
    const day = d.getUTCDate();
    const yr  = String(d.getUTCFullYear()).slice(2); // "26"
    if (interval === "1mo") return `${mon} '${yr}`;  // "Feb '26"
    if (interval === "1wk") return `${mon} ${day}`;  // "Feb 23"
    return `${mon} ${day}`;                           // "Feb 23" (daily)
  }

  function formatTooltipLabel(iso: string): string {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const mon  = MONTHS[d.getUTCMonth()];
    const day  = d.getUTCDate();
    const year = d.getUTCFullYear();
    if (interval === "1mo") return `${mon} ${year}`;
    return `${mon} ${day}, ${year}`;
  }

  // Widen tick spacing for denser intervals so labels don't overlap.
  const minTickGap = interval === "1d" ? 60 : interval === "1wk" ? 50 : 40;

  const handleAnalyze = async () => {
    setIsLoading(true);
    const periods = forecastDays ?? 7;
    try {
      if (model === "prophet_xgb") {
        const res = await api.forecastProphetXgb({
          symbol,
          interval: "1d",
          periods,
        });
        setForecast(res);
      } else {
        const res = await api.analyze(symbol, {
          model,
          interval: "1d",
          periods,
        });
        setForecast(res);
      }
      const label = model === "prophet_xgb" ? "Prophet + XGBoost" : model.toUpperCase();
      toast({
        title: "Analysis Complete",
        description: `Forecast generated using ${label} model.`,
      });
      onForecastComplete?.(model);
    } catch (error: any) {
      toast({
        title: "Analysis Failed",
        description: error.message || "An error occurred",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 items-center justify-between">
        <div className="flex flex-wrap items-center gap-4">
          <div id="tour-stock-interval">
            <Select
              value={interval}
              onValueChange={(val: any) => {
                setInterval(val);
                setForecast(null);
              }}
            >
              <SelectTrigger className="w-[120px] h-9">
                <SelectValue placeholder="Interval" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1d">Daily</SelectItem>
                <SelectItem value="1wk">Weekly</SelectItem>
                <SelectItem value="1mo">Monthly</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div id="tour-stock-model">
            <Select value={model} onValueChange={(val: any) => setModel(val)}>
              <SelectTrigger className="min-w-[200px] w-[200px] h-9">
                <SelectValue placeholder="Select Model" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="base">Base (EWM)</SelectItem>
                <SelectItem value="prophet">Prophet</SelectItem>
                <SelectItem value="prophet_xgb">Prophet + XGBoost</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {setForecastDays && (
            <Select
              value={String(forecastDays)}
              onValueChange={(v) => setForecastDays(Number(v) as 7 | 14 | 21)}
            >
              <SelectTrigger className="w-[110px] h-9">
                <SelectValue placeholder="Forecast" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">7 days</SelectItem>
                <SelectItem value="14">14 days</SelectItem>
                <SelectItem value="21">21 days</SelectItem>
              </SelectContent>
            </Select>
          )}
          {setCompareAll && (
            <label className="flex items-center gap-2 text-sm cursor-pointer whitespace-nowrap">
              <input
                type="checkbox"
                checked={compareAll}
                onChange={(e) => setCompareAll(e.target.checked)}
                className="rounded"
              />
              Compare all
            </label>
          )}
        </div>
        <div id="tour-stock-forecast-btn">
          <Button onClick={handleAnalyze} disabled={isLoading || metricsLoading}>
            {(isLoading || metricsLoading) && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Generate Forecast
          </Button>
        </div>
      </div>

      <div className="h-[400px] w-full mt-4">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              minTickGap={minTickGap}
              tickFormatter={formatXAxis}
            />
            <YAxis
              domain={["auto", "auto"]}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `$${value}`}
            />
            <Tooltip
              formatter={(value: number, name: string) => [
                `$${Number(value).toFixed(2)}`,
                name === "price" ? "Historical" : name === "forecast" ? "Forecast" : name,
              ]}
              labelFormatter={(label) => formatTooltipLabel(label)}
              contentStyle={{
                backgroundColor: "#0f172a",
                border: "1px solid rgba(0,212,255,0.25)",
                borderRadius: "8px",
                color: "#f1f5f9",
              }}
              labelStyle={{ color: "#22d3ee", fontWeight: 700, marginBottom: 4 }}
              itemStyle={{ color: "#f1f5f9" }}
              cursor={{ stroke: "rgba(0,212,255,0.3)", strokeWidth: 1 }}
            />
            <Legend
              wrapperStyle={{ paddingTop: 8 }}
              formatter={(value) => (value === "price" ? "Historical" : value === "forecast" ? "Forecast" : value)}
            />
            {firstForecastDate && (
              <ReferenceLine
                x={firstForecastDate}
                stroke="hsl(var(--muted-foreground))"
                strokeDasharray="4 4"
                strokeOpacity={0.7}
              />
            )}
            <Line
              type="monotone"
              dataKey="price"
              name="price"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              dot={false}
              connectNulls={false}
            />
            {forecast && (
              <Line
                type="monotone"
                dataKey="forecast"
                name="forecast"
                stroke="#a78bfa"
                strokeWidth={2}
                strokeDasharray="6 4"
                dot={false}
                connectNulls={true}
              />
            )}
            {forecast && (
              <Line
                type="monotone"
                dataKey="upper"
                name="Upper bound"
                stroke="hsl(var(--muted-foreground))"
                strokeDasharray="4 4"
                strokeOpacity={0.7}
                dot={false}
                connectNulls={true}
              />
            )}
            {forecast && (
              <Line
                type="monotone"
                dataKey="lower"
                name="Lower bound"
                stroke="hsl(var(--muted-foreground))"
                strokeDasharray="4 4"
                strokeOpacity={0.7}
                dot={false}
                connectNulls={true}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {forecast && (
        <p className="text-sm text-muted-foreground text-center">
          {forecast.forecast_horizon_label}
        </p>
      )}
    </div>
  );
}

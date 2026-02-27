"use client";

import { useState } from "react";
import { PriceOut, AnalyzeResponse } from "@/types/api";
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
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  ComposedChart,
} from "recharts";
import { useToast } from "@/hooks/use-toast";

interface StockChartProps {
  symbol: string;
  initialPrices: PriceOut[];
}

export function StockChart({ symbol, initialPrices }: StockChartProps) {
  const [model, setModel] = useState<"base" | "prophet" | "lstm">("base");
  const [interval, setInterval] = useState<"1d" | "1wk" | "1mo">("1d");
  const [forecast, setForecast] = useState<AnalyzeResponse | null>(null);
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
    date: string;   // raw ISO string — formatted on the fly for axis/tooltip
    price: number;
    lower?: number;
    upper?: number;
  }> = baseData.map((p) => ({
    date: p.timestamp,  // keep raw ISO so tickFormatter can vary by interval
    price: p.close_price,
  }));

  // If we have a forecast, append it to the chart data
  if (forecast) {
    forecast.dates.forEach((dateStr, i) => {
      chartData.push({
        date: dateStr,
        price: forecast.point_forecast[i],
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
    try {
      const res = await api.analyze(symbol, {
        model,
        interval,
        periods: 12,
      });
      setForecast(res);
      toast({
        title: "Analysis Complete",
        description: `Forecast generated using ${model.toUpperCase()} model.`,
      });
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
        <div className="flex gap-2">
          <Select
            value={model}
            onValueChange={(val: any) => setModel(val)}
          >
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Select Model" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="base">Base (EWM)</SelectItem>
              <SelectItem value="prophet">Prophet</SelectItem>
              <SelectItem value="lstm">LSTM</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={interval}
            onValueChange={(val: any) => {
              setInterval(val);
              setForecast(null);
            }}
          >
            <SelectTrigger className="w-[120px]">
              <SelectValue placeholder="Interval" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1d">Daily</SelectItem>
              <SelectItem value="1wk">Weekly</SelectItem>
              <SelectItem value="1mo">Monthly</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Button onClick={handleAnalyze} disabled={isLoading}>
          {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Generate Forecast
        </Button>
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
              formatter={(value: number) => [`$${value.toFixed(2)}`, "Price"]}
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
            <Line
              type="monotone"
              dataKey="price"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              dot={false}
            />
            {forecast && (
              <Line
                type="monotone"
                dataKey="upper"
                stroke="hsl(var(--muted-foreground))"
                strokeDasharray="5 5"
                dot={false}
              />
            )}
            {forecast && (
              <Line
                type="monotone"
                dataKey="lower"
                stroke="hsl(var(--muted-foreground))"
                strokeDasharray="5 5"
                dot={false}
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

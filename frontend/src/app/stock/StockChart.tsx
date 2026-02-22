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
  const [interval, setInterval] = useState<"1wk" | "1mo">("1wk");
  const [forecast, setForecast] = useState<AnalyzeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();

  // Reverse prices to be chronological for the chart
  let baseData = [...initialPrices].reverse();

  // If monthly interval is selected, aggregate weekly data into monthly means
  if (interval === "1mo") {
    const monthlyGroups: Record<string, { sum: number; count: number; date: string }> = {};
    
    baseData.forEach((p) => {
      const d = new Date(p.timestamp);
      const monthKey = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      if (!monthlyGroups[monthKey]) {
        monthlyGroups[monthKey] = { sum: 0, count: 0, date: p.timestamp };
      }
      monthlyGroups[monthKey].sum += p.close_price;
      monthlyGroups[monthKey].count += 1;
    });

    baseData = Object.values(monthlyGroups).map((group) => ({
      ...baseData[0],
      timestamp: group.date,
      close_price: group.sum / group.count,
    }));
  }

  const chartData: Array<{
    date: string;
    price: number;
    lower?: number;
    upper?: number;
  }> = baseData.map((p) => ({
    date: new Date(p.timestamp).toLocaleDateString(),
    price: p.close_price,
  }));

  // If we have a forecast, append it to the chart data
  if (forecast) {
    forecast.dates.forEach((dateStr, i) => {
      chartData.push({
        date: new Date(dateStr).toLocaleDateString(),
        price: forecast.point_forecast[i],
        lower: forecast.lower_bound[i],
        upper: forecast.upper_bound[i],
      });
    });
  }

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
              minTickGap={32}
            />
            <YAxis
              domain={["auto", "auto"]}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `$${value}`}
            />
            <Tooltip
              formatter={(value: number) => [`$${value.toFixed(2)}`, "Price"]}
              labelClassName="font-bold text-foreground"
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

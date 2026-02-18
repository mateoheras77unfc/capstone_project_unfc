import {
  AreaChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Area,
} from "recharts";
import { TrendingUp } from "lucide-react";

export function PriceChart({ prices }: { prices: any[] }) {
  if (!prices || prices.length === 0) return null;

  const data = [...prices]
    .slice(0, 30)
    .reverse()
    .map((p) => ({
      date: p.timestamp.slice(0, 10),
      open: p.open_price,
      high: p.high_price,
      low: p.low_price,
      close: p.close_price,
      volume: p.volume,
    }));

  const latest = data[data.length - 1];
  const first = data[0];

  const change = latest.close - first.close;
  const percent = (change / first.close) * 100;
  const positive = change >= 0;

  return (
    <div className="mt-8">
      {/* HEADER */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-white">TSLA</h3>
          <p className="text-sm text-slate-400">Price History (30 days)</p>
        </div>

        <div className="text-right">
          <p className="text-2xl font-bold text-white">
            ${latest.close.toFixed(2)}
          </p>
          <div
            className={`flex items-center justify-end gap-1 text-sm ${
              positive ? "text-emerald-400" : "text-red-400"
            }`}
          >
            <TrendingUp className="w-4 h-4" />
            {percent.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* CHART CARD */}
      <div className="relative h-64 rounded-2xl bg-gradient-to-b from-slate-800/60 to-slate-900/80 border border-slate-700 p-4">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="0%"
                  stopColor={positive ? "#22c55e" : "#ef4444"}
                  stopOpacity={0.45}
                />
                <stop
                  offset="55%"
                  stopColor={positive ? "#22c55e" : "#ef4444"}
                  stopOpacity={0.18}
                />
                <stop
                  offset="100%"
                  stopColor={positive ? "#22c55e" : "#ef4444"}
                  stopOpacity={0}
                />
              </linearGradient>
            </defs>

            <XAxis dataKey="date" hide />
            <YAxis hide />

            <Tooltip
              contentStyle={{
                background: "#020617",
                border: "1px solid #334155",
                borderRadius: 8,
                color: "white",
              }}
            />

            <Area
              type="monotone"
              dataKey="close"
              fill="url(#priceFill)"
              stroke="none"
            />

            <Line
              type="monotone"
              dataKey="close"
              stroke={positive ? "#22c55e" : "#ef4444"}
              strokeWidth={2.5}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* STATS CARDS */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
        <Stat label="Open" value={`$${latest.open.toFixed(2)}`} />
        <Stat label="High" value={`$${latest.high.toFixed(2)}`} />
        <Stat label="Low" value={`$${latest.low.toFixed(2)}`} />
        <Stat label="Volume" value={`${(latest.volume / 1e6).toFixed(2)}M`} />
      </div>
    </div>
  );
}

/* Small stat card */
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-800/60 border border-slate-700 p-4 text-center">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className="text-sm font-semibold text-white">{value}</p>
    </div>
  );
}

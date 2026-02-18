import { useEffect, useState } from "react";
import { getAssets, getPrices, syncAsset, runForecast } from "../api/client";
import { Input } from "../components/Input";
import { Select } from "../components/Select";
import { Button } from "../components/Button";
import { DataPreview } from "../components/DataPreview";
import { PriceChart } from "../components/PriceChart";

import { Search, TrendingUp, Loader2, AlertTriangle, Play } from "lucide-react";

// ── Types ────────────────────────────────────────────────────────────────────

interface Asset {
  id: string;
  symbol: string;
  name: string;
  asset_type: string;
  last_updated: string;
}

interface Price {
  timestamp: string;
  open_price: number;
  high_price: number;
  low_price: number;
  close_price: number;
  volume: number;
}

interface ForecastResult {
  ticker: string;
  dates: string[];
  point_forecast: number[];
  lower_bound: number[];
  upper_bound: number[];
  confidence_level: number;
  model_info: Record<string, unknown>;
}

type ForecastModel = "base" | "lstm" | "prophet";

// ── Model config ─────────────────────────────────────────────────────────────

const MODEL_LABELS: Record<ForecastModel, string> = {
  base: "Base",
  lstm: "LSTM",
  prophet: "Prophet",
};

// ── Forecast Toolbar (single compact row) ────────────────────────────────────

function ForecastToolbar({
  model,
  onModelChange,
  periods,
  onPeriodsChange,
  onRun,
  loading,
  disabled,
}: {
  model: ForecastModel;
  onModelChange: (m: ForecastModel) => void;
  periods: number;
  onPeriodsChange: (p: number) => void;
  onRun: () => void;
  loading: boolean;
  disabled: boolean;
}) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      {/* Label */}
      <span className="text-sm font-medium text-slate-300 flex items-center gap-1.5 mr-1">
        <TrendingUp className="w-4 h-4 text-cyan-400" />
        Price Forecasting
      </span>

      <div className="w-px h-5 bg-slate-700" />

      {/* Model selector – pill toggle */}
      <div className="flex items-center bg-slate-800/80 rounded-lg p-0.5 border border-slate-700/60">
        {(Object.keys(MODEL_LABELS) as ForecastModel[]).map((key) => (
          <button
            key={key}
            onClick={() => onModelChange(key)}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${
              model === key
                ? "bg-cyan-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {MODEL_LABELS[key]}
          </button>
        ))}
      </div>

      <div className="w-px h-5 bg-slate-700" />

      {/* Weeks ahead – pill toggle */}
      <label className="text-xs text-slate-400 flex items-center gap-1.5">
        Weeks ahead
        <div className="flex items-center bg-slate-800/80 rounded-lg p-0.5 border border-slate-700/60">
          {[2, 4, 8, 12].map((n) => (
            <button
              key={n}
              onClick={() => onPeriodsChange(n)}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all ${
                periods === n
                  ? "bg-cyan-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      </label>

      <div className="w-px h-5 bg-slate-700" />

      {/* Run button */}
      <button
        onClick={onRun}
        disabled={disabled || loading}
        className="inline-flex items-center gap-1.5 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500 text-white text-xs font-medium px-3.5 py-1.5 rounded-lg transition-colors"
      >
        {loading ? (
          <>
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Running…
          </>
        ) : (
          <>
            <Play className="w-3 h-3 fill-current" />
            Run {MODEL_LABELS[model]}
          </>
        )}
      </button>
    </div>
  );
}

// ── Forecast Result Card ─────────────────────────────────────────────────────

function ForecastCard({
  forecast,
  modelKey,
}: {
  forecast: ForecastResult;
  modelKey: ForecastModel;
}) {
  if (forecast.point_forecast.length === 0) return null;

  return (
    <div className="rounded-lg border border-cyan-500/20 bg-gradient-to-br from-cyan-950/40 to-slate-900/60 p-5">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp className="w-5 h-5 text-cyan-400" />
        <h3 className="text-lg font-semibold text-white">
          {MODEL_LABELS[modelKey]} Forecast{" "}
          <span className="text-sm font-normal text-slate-400">
            — {(forecast.confidence_level * 100).toFixed(0)}% CI
          </span>
        </h3>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 border-b border-slate-700/60">
              <th className="text-left py-2 pr-4 font-medium">Date</th>
              <th className="text-right py-2 px-4 font-medium">Forecast</th>
              <th className="text-right py-2 px-4 font-medium">Lower</th>
              <th className="text-right py-2 pl-4 font-medium">Upper</th>
            </tr>
          </thead>
          <tbody>
            {forecast.dates.map((date, i) => (
              <tr
                key={date}
                className="border-b border-slate-800/40 hover:bg-cyan-500/5 transition-colors"
              >
                <td className="py-2.5 pr-4 text-slate-300">
                  {new Date(date).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                  })}
                </td>
                <td className="py-2.5 px-4 text-right font-mono text-cyan-300 font-medium">
                  ${forecast.point_forecast[i].toFixed(2)}
                </td>
                <td className="py-2.5 px-4 text-right font-mono text-red-400/80">
                  ${forecast.lower_bound[i].toFixed(2)}
                </td>
                <td className="py-2.5 pl-4 text-right font-mono text-emerald-400/80">
                  ${forecast.upper_bound[i].toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Meta */}
      <p className="mt-4 text-xs text-slate-500">
        Model:{" "}
        {String(forecast.model_info?.model_name ?? MODEL_LABELS[modelKey])}
        {forecast.model_info?.lookback_window
          ? ` · Lookback: ${String(forecast.model_info.lookback_window)}`
          : null}
        {forecast.model_info?.epochs
          ? ` · Epochs: ${String(forecast.model_info.epochs)}`
          : null}
      </p>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function SingleAsset() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selected, setSelected] = useState("");
  const [customSymbol, setCustomSymbol] = useState("");
  const [assetType] = useState<"stock" | "crypto">("stock");
  const [prices, setPrices] = useState<Price[]>([]);
  const [loading, setLoading] = useState(false);

  // Forecast state
  const [forecastModel, setForecastModel] = useState<ForecastModel>("lstm");
  const [forecastPeriods, setForecastPeriods] = useState(4);
  const [forecast, setForecast] = useState<ForecastResult | null>(null);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [forecastError, setForecastError] = useState<string | null>(null);

  useEffect(() => {
    getAssets().then(setAssets);
  }, []);

  const symbol = customSymbol || selected;

  // Reset forecast when symbol changes
  useEffect(() => {
    setForecast(null);
    setForecastError(null);
  }, [symbol]);

  const handleSync = async () => {
    if (!symbol) return;
    setLoading(true);
    await syncAsset(symbol, assetType);

    const updatedAssets = await getAssets();
    setAssets(updatedAssets);

    setLoading(false);
    getPrices(symbol).then(setPrices);
  };

  useEffect(() => {
    if (symbol) {
      getPrices(symbol).then(setPrices);
    }
  }, [symbol]);

  const handleForecast = async () => {
    if (!symbol || prices.length === 0) return;

    setForecastLoading(true);
    setForecastError(null);
    setForecast(null);

    try {
      const result = await runForecast(
        forecastModel,
        symbol,
        prices.map((p) => p.close_price),
        prices.map((p) => p.timestamp),
        forecastPeriods
      );
      setForecast(result);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Forecast failed unexpectedly";
      setForecastError(message);
    } finally {
      setForecastLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white px-4 py-12">
      {/* Header */}
      <header className="text-center mb-14">
        <h1 className="text-5xl md:text-6xl font-bold tracking-tight">
          <span className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
            UNF
          </span>{" "}
          <span className="text-white">Investor</span>
        </h1>

        <div className="mt-4 flex items-center justify-center gap-2 text-slate-400">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-4 h-4 text-cyan-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M13 10V3L4 14h7v7l9-11h-7z"
            />
          </svg>
          <span className="text-sm md:text-base">Single Asset Analysis</span>
        </div>
      </header>

      {/* Card */}
      <div className="max-w-5xl mx-auto bg-slate-900/80 backdrop-blur rounded-xl p-6 shadow-xl border border-slate-800">
        <h2 className="text-xl font-semibold mb-6">Select or Add an Asset</h2>

        {/* Controls */}
        <div className="flex items-center gap-6">
          <Select
            value={selected}
            onChange={setSelected}
            options={assets.map((a) => ({
              value: a.symbol,
              label: a.symbol,
            }))}
          />

          <Input
            value={customSymbol}
            onChange={(v) => setCustomSymbol(v.toUpperCase())}
            placeholder="Or enter symbol (TSLA, ETH-USD)"
            className="w-72"
            icon={Search}
          />

          <Button onClick={handleSync} loading={loading} disabled={!symbol}>
            Fetch & Cache
          </Button>
        </div>

        {/* Results */}
        {prices.length > 0 && (
          <>
            <div className="border-t border-slate-800 my-6" />

            {/* ── Forecast Toolbar (above chart) ──────────────────────── */}
            <ForecastToolbar
              model={forecastModel}
              onModelChange={setForecastModel}
              periods={forecastPeriods}
              onPeriodsChange={setForecastPeriods}
              onRun={handleForecast}
              loading={forecastLoading}
              disabled={prices.length < 21}
            />

            {prices.length < 21 && (
              <p className="mt-2 text-xs text-amber-400/80 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                Need at least 21 data points. Currently: {prices.length}
              </p>
            )}

            {/* ── Chart ───────────────────────────────────────────────── */}
            <div className="mt-4">
              <PriceChart prices={prices} />
            </div>

            {/* ── Forecast Results (below chart) ──────────────────────── */}
            {forecastError && (
              <div className="mt-4 rounded-lg border border-red-500/30 bg-red-950/20 px-4 py-3 text-sm text-red-300 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                {forecastError}
              </div>
            )}

            {forecast && (
              <div className="mt-4">
                <ForecastCard forecast={forecast} modelKey={forecastModel} />
              </div>
            )}

            {/* ── Data Preview ────────────────────────────────────────── */}
            <DataPreview prices={prices} />
          </>
        )}
      </div>
    </div>
  );
}

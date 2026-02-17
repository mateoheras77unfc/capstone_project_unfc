import { useEffect, useState } from "react";
import { getAssets, getPrices, syncAsset } from "../api/client";
import { Input } from "../components/Input";
import { Select } from "../components/Select";
import { Button } from "../components/Button";
import { DataPreview } from "../components/DataPreview";
import { PriceChart } from "../components/PriceChart";
import { Search } from "lucide-react";

interface Asset {
  id: string;
  symbol: string;
  name: string;
  asset_type: string;
  last_updated: string;
}

interface Price {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export default function SingleAsset() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selected, setSelected] = useState("");
  const [customSymbol, setCustomSymbol] = useState("");
  const [assetType] = useState<"stock" | "crypto">("stock");
  const [prices, setPrices] = useState<Price[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getAssets().then(setAssets);
  }, []);

  const symbol = customSymbol || selected;

  const handleSync = async () => {
    if (!symbol) return;
    setLoading(true);
    await syncAsset(symbol, assetType);

    // Refresh the asset list so the new symbol appears in dropdown
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

  return (
    <div className="min-h-screen bg-slate-950 text-white px-4 py-12">
      {/* Header */}
      {/* TITLE */}
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
            <PriceChart prices={prices} />
            <DataPreview prices={prices} />
          </>
        )}
      </div>
    </div>
  );
}

import { api } from "@/lib/api";
import { StockDashboard } from "./StockDashboard";

export default async function StockPage({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string; from?: string; to?: string }>;
}) {
  const { symbol, from, to } = await searchParams;
  const upperSymbol = symbol?.toUpperCase();

  // Default dates: last year to today
  const today = new Date();
  const lastYear = new Date();
  lastYear.setFullYear(today.getFullYear() - 1);

  const fromDate = from || lastYear.toISOString().split('T')[0];
  const toDate = to || today.toISOString().split('T')[0];

  // Fetch all available assets for the dropdown
  const assets = await api.getAssets().catch(() => []);

  let prices = null;
  let stats = null;

  if (upperSymbol) {
    try {
      // Fetch up to 10 years of daily data so Weekly and Monthly
      // aggregations on the frontend are visually distinct from Daily.
      prices = await api.getPrices(upperSymbol, 2500);
    } catch (e) {
      console.error("Failed to fetch prices:", e);
    }

    try {
      // Pick a partner symbol dynamically from the DB instead of hardcoding
      // AAPL/GOOG — those may not exist after a DB truncation + re-sync.
      const partner = assets.find((a) => a.symbol !== upperSymbol)?.symbol;
      if (partner) {
        stats = await api.portfolioStats({
          symbols: [upperSymbol, partner],
          interval: "1d",
          from_date: fromDate,
          to_date: toDate,
        });
      }
    } catch (e) {
      console.error("Failed to fetch stats:", e);
    }
  }

  return (
    <StockDashboard
      assets={assets}
      initialSymbol={upperSymbol}
      initialPrices={prices}
      initialStats={stats}
      initialFromDate={fromDate}
      initialToDate={toDate}
    />
  );
}

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
      // Fetch initial prices (last 200 days)
      prices = await api.getPrices(upperSymbol, 200);
    } catch (e) {
      console.error("Failed to fetch prices:", e);
    }

    try {
      // Fetch portfolio stats for this single asset + GOOG to bypass validation
      const symbols = upperSymbol === "GOOG" ? ["GOOG", "AAPL"] : [upperSymbol, "GOOG"];
      stats = await api.portfolioStats({ 
        symbols,
        from_date: fromDate,
        to_date: toDate
      });
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

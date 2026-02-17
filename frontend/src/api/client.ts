const API_URL =
  import.meta.env.VITE_API_URL ||
  "https://capstone-project-unfc-l68p.onrender.com";

export async function getAssets() {
  const res = await fetch(`${API_URL}/assets`);
  return res.json();
}

export async function syncAsset(symbol: string, assetType: string) {
  return fetch(`${API_URL}/sync/${symbol}?asset_type=${assetType}`, {
    method: "POST",
  });
}

export async function getPrices(symbol: string) {
  const res = await fetch(`${API_URL}/prices/${symbol}`);
  return res.json();
}
export async function runForecast(
  model: "base" | "lstm" | "prophet",
  ticker: string,
  prices: number[],
  dates: string[],
  periods: number = 4
) {
  const res = await fetch(`${API_URL}/api/forecast/${model}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker, prices, dates, periods }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Forecast failed" }));
    throw new Error(err.detail ?? "Forecast failed");
  }
  return res.json();
}

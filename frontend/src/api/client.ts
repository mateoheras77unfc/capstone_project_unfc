const API_URL =
  import.meta.env.VITE_API_URL ||
  "https://capstone-project-unfc-l68p.onrender.com";

export async function getAssets() {
  const res = await fetch(`${API_URL}/api/v1/assets`);
  return res.json();
}

export async function syncAsset(symbol: string, assetType: string) {
  return fetch(`${API_URL}/api/v1/assets/sync/${symbol}?asset_type=${assetType}`, {
    method: "POST",
  });
}

export async function getPrices(symbol: string, limit = 200) {
  const res = await fetch(`${API_URL}/api/v1/prices/${symbol}?limit=${limit}`);
  return res.json();
}

export async function runForecast(
  model: "base" | "lstm" | "prophet",
  symbol: string,
  periods: number = 4,
  interval: "1wk" | "1mo" = "1wk"
) {
  const res = await fetch(`${API_URL}/api/v1/forecast/${model}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, interval, periods }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Forecast failed" }));
    throw new Error(err.detail ?? "Forecast failed");
  }
  return res.json();
}

const API_URL = "http://127.0.0.1:8000";

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

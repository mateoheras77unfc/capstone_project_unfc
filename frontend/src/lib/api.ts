import {
  AssetOut,
  PriceOut,
  SyncResponse,
  ForecastRequest,
  ForecastResponse,
  AnalyzeRequest,
  AnalyzeResponse,
  StatsRequest,
  StatsResponse,
  OptimizeRequest,
  OptimizeResponse,
} from "@/types/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_URL}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let errorDetail = "An error occurred";
    try {
      const errorData = await response.json();
      errorDetail = errorData.detail || errorDetail;
    } catch (e) {
      // Ignore JSON parse error
    }
    throw new Error(errorDetail);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

export const api = {
  // System
  getHealth: () => fetchApi<{ status: string }>("/health"),

  // Assets
  getAssets: () => fetchApi<AssetOut[]>("/assets/"),
  searchAssets: (q?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (q) params.append("q", q);
    if (limit) params.append("limit", limit.toString());
    return fetchApi<AssetOut[]>(`/assets/search?${params.toString()}`);
  },
  getAsset: (symbol: string) => fetchApi<AssetOut>(`/assets/${symbol}`),
  deleteAsset: (symbol: string) => fetchApi<void>(`/assets/${symbol}`, { method: "DELETE" }),
  syncAsset: (symbol: string, assetType?: string, interval?: string) => {
    const params = new URLSearchParams();
    if (assetType) params.append("asset_type", assetType);
    if (interval) params.append("interval", interval);
    return fetchApi<SyncResponse>(`/assets/sync/${symbol}?${params.toString()}`, { method: "POST" });
  },

  // Prices
  getPrices: (symbol: string, limit?: number, fromDate?: string, toDate?: string) => {
    const params = new URLSearchParams();
    if (limit) params.append("limit", limit.toString());
    if (fromDate) params.append("from_date", fromDate);
    if (toDate) params.append("to_date", toDate);
    return fetchApi<PriceOut[]>(`/prices/${symbol}?${params.toString()}`);
  },

  // Forecast
  forecastBase: (data: ForecastRequest) => fetchApi<ForecastResponse>("/forecast/base", { method: "POST", body: JSON.stringify(data) }),
  forecastProphet: (data: ForecastRequest) => fetchApi<ForecastResponse>("/forecast/prophet", { method: "POST", body: JSON.stringify(data) }),
  forecastLstm: (data: ForecastRequest) => fetchApi<ForecastResponse>("/forecast/lstm", { method: "POST", body: JSON.stringify(data) }),

  // Analyze
  analyze: (symbol: string, data: AnalyzeRequest) => fetchApi<AnalyzeResponse>(`/analyze/${symbol}`, { method: "POST", body: JSON.stringify(data) }),

  // Portfolio
  portfolioStats: (data: StatsRequest) => fetchApi<StatsResponse>("/portfolio/stats", { method: "POST", body: JSON.stringify(data) }),
  portfolioOptimize: (data: OptimizeRequest) => fetchApi<OptimizeResponse>("/portfolio/optimize", { method: "POST", body: JSON.stringify(data) }),
};

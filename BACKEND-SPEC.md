# Backend API Specification

Complete reference for the Investment Analytics API.  
Use this document to build every frontend feature without needing to read backend source code.

---

## Base URLs

| Environment | URL |
|-------------|-----|
| Local development | `http://localhost:8000/api/v1` |
| Production | `https://capstoneproject.swiftshift.digital/api/v1` |

Interactive docs (Swagger UI): `http://localhost:8000/docs`  
ReDoc: `http://localhost:8000/redoc`

---

## General Conventions

### Authentication
**None required.** All endpoints are publicly accessible.

### Request format
- All `POST` bodies must be `Content-Type: application/json`.
- All `GET` filters are query string parameters.
- Ticker symbols are case-insensitive — `aapl`, `AAPL`, `Aapl` all work.

### Response format
- All successful responses are `application/json`.
- `DELETE` returns `204 No Content` with an empty body.
- Dates and timestamps are **ISO 8601** strings (e.g. `"2024-01-08T00:00:00+00:00"`).
- Floats are rounded to 4 decimal places.

### Error shape
Every error response (4xx / 5xx) returns:
```json
{
  "detail": "Human-readable description of what went wrong"
}
```

### HTTP status codes used

| Code | Meaning |
|------|---------|
| `200` | Success |
| `204` | Success, no body (DELETE) |
| `400` | Bad request (e.g. invalid date format) |
| `404` | Symbol / resource not found |
| `422` | Validation error (missing field, value out of range, etc.) |
| `500` | Unexpected server error |
| `503` | External dependency unavailable (Yahoo Finance, Supabase) |

---

## Endpoints

### System

#### `GET /health`
Detailed health check — verifies environment variables, Supabase connectivity, and Yahoo Finance reachability.

**Response `200`**
```json
{
  "status": "ok",
  "environment": { "ok": true, "detail": "SUPABASE_URL=https://... SUPABASE_KEY=***set***" },
  "supabase":    { "ok": true, "detail": "Connected — assets table reachable" },
  "yfinance":    { "ok": true, "detail": "Yahoo Finance reachable — AAPL test query returned data" }
}
```

`status` is one of `"ok"` | `"degraded"` | `"error"`.

---

### Assets

#### `GET /assets/`
List every asset currently cached in the database, sorted alphabetically by symbol.

**Response `200`** — array of [AssetOut](#assetout)
```json
[
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "asset_type": "stock",
    "currency": "USD",
    "last_updated": "2024-01-08T00:00:00+00:00",
    "created_at": "2021-01-04T00:00:00+00:00"
  }
]
```

---

#### `GET /assets/search`
Search assets by ticker symbol or name. Useful for autocomplete.

**Query parameters**

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `q` | string | No | — | Partial symbol or name, case-insensitive (1–20 chars). When omitted returns most recently updated assets. |
| `limit` | int | No | `10` | Max results (1–50). |

**Response `200`** — array of [AssetOut](#assetout) (may be empty)

```json
[
  {
    "id": "3fa85f64-...",
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "asset_type": "stock",
    "currency": "USD",
    "last_updated": "2024-01-08T00:00:00+00:00",
    "created_at": "2021-01-04T00:00:00+00:00"
  }
]
```

**Errors:** `422` if `q` is longer than 20 characters.

---

#### `GET /assets/{symbol}`
Full metadata for a single asset.

**Path parameters**

| Param | Type | Description |
|-------|------|-------------|
| `symbol` | string | Ticker (case-insensitive). |

**Response `200`** — [AssetOut](#assetout)

**Errors:** `404` if symbol is not in the database.

---

#### `DELETE /assets/{symbol}`
Permanently remove an asset and **all its price history** (cascade delete).

**Path parameters**

| Param | Type | Description |
|-------|------|-------------|
| `symbol` | string | Ticker to delete (case-insensitive). |

**Response `204`** — empty body

**Errors:** `404` if symbol is not in the database.

---

#### `POST /assets/sync/{symbol}`
Fetch historical OHLCV data from Yahoo Finance and upsert it into the database.  
If the asset already exists, only missing dates are added — existing rows are not overwritten.

**Path parameters**

| Param | Type | Description |
|-------|------|-------------|
| `symbol` | string | Ticker to sync (case-insensitive). |

**Query parameters**

| Param | Type | Required | Default | Options |
|-------|------|----------|---------|---------|
| `asset_type` | string | No | `"stock"` | `"stock"` \| `"crypto"` \| `"index"` |
| `interval` | string | No | `"1wk"` | `"1wk"` \| `"1mo"` |

**Response `200`** — [SyncResponse](#syncresponse)
```json
{
  "status": "success",
  "message": "Synced AAPL (1wk) — 156 rows written",
  "symbol": "AAPL",
  "rows_synced": 156
}
```

**Errors:** `422` if Yahoo Finance returns no data, `503` if Yahoo Finance is unreachable.

---

### Prices

#### `GET /prices/{symbol}`
Return cached OHLCV price history. Results are **newest first**.

**Path parameters**

| Param | Type | Description |
|-------|------|-------------|
| `symbol` | string | Ticker (case-insensitive). |

**Query parameters**

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `limit` | int | No | `200` | Max rows to return. Range: 1–1000. |
| `from_date` | string | No | — | Oldest bar to include, ISO 8601 date (e.g. `2022-01-01`). Inclusive. |
| `to_date` | string | No | — | Most recent bar to include, ISO 8601 date (e.g. `2024-12-31`). Inclusive. |

**Response `200`** — array of [PriceOut](#priceout)
```json
[
  {
    "id": "uuid",
    "asset_id": "uuid",
    "timestamp": "2024-01-08T00:00:00+00:00",
    "open_price": 184.11,
    "high_price": 186.22,
    "low_price": 183.77,
    "close_price": 185.92,
    "volume": 52341200
  }
]
```

**Errors:**
- `400` invalid date format or `from_date >= to_date`
- `404` symbol not in database
- `422` `limit` outside 1–1000

---

### Forecast

All three forecast endpoints share the same request and response shape.  
The model is determined by the URL path, not the body.

> **Tip:** Use `POST /analyze/{symbol}` instead if you want auto-sync + forecast in a single call.

#### `POST /forecast/base` — EWM Baseline
#### `POST /forecast/prophet` — Facebook Prophet
#### `POST /forecast/lstm` — LSTM Neural Network

**Request body** — [ForecastRequest](#forecastrequest)
```json
{
  "symbol": "AAPL",
  "interval": "1wk",
  "periods": 8,
  "lookback_window": 20,
  "epochs": 50,
  "confidence_level": 0.95
}
```

**Minimum rows required before forecasting:**

| Interval | Minimum rows |
|----------|--------------|
| `1wk` | 52 (1 year of weekly data) |
| `1mo` | 24 (2 years of monthly data) |

**Response `200`** — [ForecastResponse](#forecastresponse)
```json
{
  "symbol": "AAPL",
  "interval": "1wk",
  "model": "base",
  "periods_ahead": 8,
  "forecast_horizon_label": "8 weeks (~2 months ahead)",
  "data_points_used": 156,
  "dates": ["2024-01-15T00:00:00", "2024-01-22T00:00:00"],
  "point_forecast": [186.42, 187.91],
  "lower_bound": [181.10, 182.30],
  "upper_bound": [191.74, 193.52],
  "confidence_level": 0.95,
  "model_info": { "model_type": "ewm", "span": 20 }
}
```

**Errors:**
- `404` symbol not in database
- `422` fewer rows than the minimum required
- `503` LSTM: TensorFlow not installed on server / Prophet: Prophet not installed

---

### Analyze (Auto-sync + Forecast)

#### `POST /analyze/{symbol}`
Single call that:
1. Checks if the symbol is in the database
2. Syncs from Yahoo Finance automatically if it is not
3. Runs the selected forecast model
4. Returns the full combined response

This is the **recommended endpoint for the frontend** — no need to call `/sync` separately.

**Path parameters**

| Param | Type | Description |
|-------|------|-------------|
| `symbol` | string | Ticker (case-insensitive). |

**Request body** — [AnalyzeRequest](#analyzerequest)
```json
{
  "interval": "1wk",
  "periods": 8,
  "model": "base",
  "asset_type": "stock",
  "lookback_window": 20,
  "epochs": 50,
  "confidence_level": 0.95
}
```

**Response `200`** — [AnalyzeResponse](#analyzeresponse)
```json
{
  "symbol": "AAPL",
  "sync": {
    "performed": false,
    "rows_synced": 0,
    "message": "Symbol already in database — skipping sync"
  },
  "interval": "1wk",
  "model": "base",
  "periods_ahead": 8,
  "forecast_horizon_label": "8 weeks (~2 months ahead)",
  "data_points_used": 156,
  "dates": ["2024-01-15T00:00:00"],
  "point_forecast": [186.42],
  "lower_bound": [181.10],
  "upper_bound": [191.74],
  "confidence_level": 0.95,
  "model_info": { "model_type": "ewm", "span": 20 }
}
```

---

### Portfolio

All portfolio endpoints accept an optional date window to restrict the historical data used in calculations.

---

#### `POST /portfolio/stats`
Per-asset statistics (returns, volatility, drawdown, VaR, etc.) plus cross-asset metrics (covariance, correlation, beta).

**Request body** — [StatsRequest](#statsrequest)
```json
{
  "symbols": ["AAPL", "AMZN", "NVDA"],
  "interval": "1wk",
  "risk_free_rate": 0.05,
  "from_date": "2022-01-01",
  "to_date": "2024-12-31"
}
```

**Response `200`** — [StatsResponse](#statsresponse)
```json
{
  "symbols": ["AAPL", "AMZN", "NVDA"],
  "interval": "1wk",
  "from_date": "2022-01-01",
  "to_date": "2024-12-31",
  "data_points_used": { "AAPL": 156, "AMZN": 156, "NVDA": 156 },
  "shared_data_points": 156,
  "individual": {
    "AAPL": {
      "avg_return": 0.0021,
      "variance": 0.0003,
      "std_deviation": 0.0182,
      "cumulative_return": 0.4812,
      "annualized_volatility": 0.1314,
      "sharpe_score": 1.42,
      "max_drawdown": -0.2741,
      "skewness": -0.31,
      "kurtosis": 2.14,
      "var_95": -0.0287,
      "cvar_95": -0.0391,
      "returns_summary": {
        "min": -0.0821,
        "max": 0.0934,
        "mean": 0.0021,
        "last_30": [0.012, -0.003, 0.008]
      }
    }
  },
  "advanced": {
    "covariance_matrix": {
      "AAPL": { "AAPL": 0.0003, "AMZN": 0.0002, "NVDA": 0.0004 }
    },
    "correlation_matrix": {
      "AAPL": { "AAPL": 1.0, "AMZN": 0.71, "NVDA": 0.65 }
    },
    "beta_vs_equal_weighted": {
      "AAPL": 0.92, "AMZN": 1.04, "NVDA": 1.31
    }
  }
}
```

---

#### `POST /portfolio/optimize`
PyPortfolioOpt-powered portfolio optimization. Returns optimal weights, performance metrics, efficient frontier, and portfolio-level risk metrics.

Each asset is guaranteed a **minimum weight between 5% and 15%** (randomly chosen per call) so no asset ever gets a zero allocation.

**Request body** — [OptimizeRequest](#optimizerequest)
```json
{
  "symbols": ["AAPL", "AMZN", "NVDA"],
  "interval": "1wk",
  "risk_free_rate": 0.05,
  "from_date": "2022-01-01",
  "to_date": "2024-12-31",
  "target": "max_sharpe",
  "target_return": null,
  "target_volatility": null,
  "n_frontier_points": 30
}
```

`target` options:

| Value | Description | Extra required field |
|-------|-------------|----------------------|
| `"max_sharpe"` | Maximize Sharpe ratio | — |
| `"min_volatility"` | Minimize portfolio volatility | — |
| `"efficient_return"` | Min volatility for a target return | `target_return` (float) |
| `"efficient_risk"` | Max return for a target volatility | `target_volatility` (float) |

**Response `200`** — [OptimizeResponse](#optimizeresponse)
```json
{
  "symbols": ["AAPL", "AMZN", "NVDA"],
  "interval": "1wk",
  "from_date": "2022-01-01",
  "to_date": "2024-12-31",
  "target": "max_sharpe",
  "weights": {
    "AAPL": 0.1823,
    "AMZN": 0.2341,
    "NVDA": 0.5836
  },
  "performance": {
    "expected_annual_return": 0.2814,
    "annual_volatility": 0.1942,
    "sharpe_ratio": 1.1903
  },
  "efficient_frontier": [
    { "volatility": 0.1612, "expected_return": 0.1823, "sharpe": 0.8234 },
    { "volatility": 0.1814, "expected_return": 0.2241, "sharpe": 1.0912 }
  ],
  "risk_metrics": {
    "var_95": -0.0294,
    "cvar_95": -0.0408,
    "max_drawdown": -0.2134
  },
  "data_points_used": { "AAPL": 156, "AMZN": 156, "NVDA": 156 },
  "shared_data_points": 156
}
```

**Errors:**
- `404` any symbol not in database
- `422` fewer than 52 weekly / 24 monthly rows, invalid `target`, missing `target_return` / `target_volatility`, `from_date >= to_date`, fewer than 2 or more than 10 symbols

---

## Schema Reference

### AssetOut
| Field | Type | Nullable |
|-------|------|----------|
| `id` | string (UUID) | No |
| `symbol` | string | No |
| `name` | string | Yes |
| `asset_type` | `"stock"` \| `"crypto"` \| `"index"` | No |
| `currency` | string | No |
| `last_updated` | ISO 8601 datetime | Yes |
| `created_at` | ISO 8601 datetime | Yes |

### PriceOut
| Field | Type | Nullable |
|-------|------|----------|
| `id` | string (UUID) | No |
| `asset_id` | string (UUID) | No |
| `timestamp` | ISO 8601 datetime | No |
| `open_price` | float | Yes |
| `high_price` | float | Yes |
| `low_price` | float | Yes |
| `close_price` | float | No |
| `volume` | int | Yes |

### SyncResponse
| Field | Type |
|-------|------|
| `status` | `"success"` |
| `message` | string |
| `symbol` | string |
| `rows_synced` | int |

### ForecastRequest
| Field | Type | Default | Range |
|-------|------|---------|-------|
| `symbol` | string | — | — |
| `interval` | `"1wk"` \| `"1mo"` | `"1wk"` | — |
| `periods` | int | `4` | 1–52 |
| `lookback_window` | int | `20` | 5–60 |
| `epochs` | int | `50` | 10–200 (LSTM only) |
| `confidence_level` | float | `0.95` | 0.5–0.99 |

### ForecastResponse
| Field | Type |
|-------|------|
| `symbol` | string |
| `interval` | string |
| `model` | string |
| `periods_ahead` | int |
| `forecast_horizon_label` | string |
| `data_points_used` | int |
| `dates` | string[] |
| `point_forecast` | float[] |
| `lower_bound` | float[] |
| `upper_bound` | float[] |
| `confidence_level` | float |
| `model_info` | object |

### AnalyzeRequest
| Field | Type | Default |
|-------|------|---------|
| `interval` | `"1wk"` \| `"1mo"` | `"1wk"` |
| `periods` | int (1–52) | `4` |
| `model` | `"base"` \| `"lstm"` \| `"prophet"` | `"base"` |
| `asset_type` | `"stock"` \| `"crypto"` \| `"index"` | `"stock"` |
| `lookback_window` | int (5–60) | `20` |
| `epochs` | int (10–200) | `50` |
| `confidence_level` | float (0.5–0.99) | `0.95` |

### AnalyzeResponse
`sync` object + all fields from [ForecastResponse](#forecastresponse).

`sync` shape:
| Field | Type |
|-------|------|
| `performed` | bool — `true` if a sync was run |
| `rows_synced` | int |
| `message` | string |

### StatsRequest / OptimizeRequest shared fields (`_PortfolioBase`)
| Field | Type | Default | Constraints |
|-------|------|---------|-------------|
| `symbols` | string[] | — | 2–10 items |
| `interval` | `"1wk"` \| `"1mo"` | `"1wk"` | — |
| `risk_free_rate` | float | `0.05` | 0.0–0.20 |
| `from_date` | ISO date string | `null` | Must be before `to_date` |
| `to_date` | ISO date string | `null` | Must be after `from_date` |

### OptimizeRequest additional fields
| Field | Type | Default | Constraints |
|-------|------|---------|-------------|
| `target` | string | `"max_sharpe"` | See target options table |
| `target_return` | float | `null` | Required for `efficient_return`. Range: -0.5–5.0 |
| `target_volatility` | float | `null` | Required for `efficient_risk`. Range: 0.01–2.0 |
| `n_frontier_points` | int | `30` | 5–100 |

---

## Frontend Integration Examples

### Typical page flows

**Asset search + sync (symbol lookup page)**
```
1. GET /assets/search?q={input}          → populate dropdown
2. POST /assets/sync/{symbol}            → only if user chooses a new symbol
3. GET /assets/{symbol}                  → display asset card
```

**Price chart**
```
GET /prices/{symbol}?limit=200&from_date=2022-01-01
```

**Forecast (single asset page)**
```
POST /analyze/{symbol}
body: { interval: "1wk", periods: 12, model: "base" }
→ use dates[], point_forecast[], lower_bound[], upper_bound[] to draw chart
→ use forecast_horizon_label as chart subtitle
```

**Portfolio analysis**
```
1. POST /portfolio/stats    → draw per-asset stat cards + correlation heatmap
2. POST /portfolio/optimize → draw pie chart of weights + efficient frontier curve
```

---

## Notes for Frontend

- **`/analyze` vs `/forecast`** — Always use `/analyze/{symbol}` for the single-asset page. It handles sync automatically. Only call `/forecast/*` directly if the asset is guaranteed to already be synced.
- **Frontier chart** — `efficient_frontier` array gives you `(volatility, expected_return)` pairs to draw the curve. The optimized portfolio point lives in `performance`.
- **`returns_summary.last_30`** — Array of the last 30 weekly returns (floats). Useful for a small sparkline inside a stat card.
- **`model_info`** — Varies by model. Do not assume specific keys — display or discard as needed.
- **Port** — Backend always runs on port `8000` locally. Vite dev server runs on `5173`. Both are in the CORS allow-list.

# 🦊 Investment Analytics Platform

> A full-stack financial analysis platform for stock research and portfolio optimization, built as a capstone project for UNFC.

[![Frontend](https://img.shields.io/badge/Frontend-Vercel-black?logo=vercel)](https://capstone-project-unfc-ashen.vercel.app)
[![Backend](https://img.shields.io/badge/Backend-Render-46E3B7?logo=render)](https://capstone-project-unfc-l68p.onrender.com)
[![Database](https://img.shields.io/badge/Database-Supabase-3ECF8E?logo=supabase)](https://supabase.com)

---

## 📌 Purpose

This platform gives investors and analysts a web-based toolkit to:

- **Analyze individual stocks** — view historical price charts (weekly or monthly aggregation), key risk/return statistics, and generate price forecasts using multiple machine learning models.
- **Build & optimize portfolios** — select multiple assets, run PyPortfolioOpt to find optimal allocation weights, and inspect individual asset statistics, correlations, covariances, and beta values.

The project demonstrates a production-grade architecture integrating a Python data science backend with a modern React frontend, backed by a managed PostgreSQL database.

---

## 🏗️ Architecture

```
┌──────────────────────┐        ┌───────────────────────┐        ┌──────────────────────┐
│      Vercel           │        │       Render           │        │      Supabase         │
│  (Next.js Frontend)  │──────▶│  (FastAPI Backend)     │──────▶│  (PostgreSQL DB)      │
│                      │  HTTP  │                       │  SDK   │                      │
│  React 19 + shadcn   │        │  Python 3.12          │        │  assets table         │
│  Recharts + Tailwind │        │  PyPortfolioOpt        │        │  historical_prices    │
│  App Router          │        │  yfinance + Prophet   │        │  Row Level Security   │
└──────────────────────┘        └───────────────────────┘        └──────────────────────┘
```

**Request flow:**
1. User's browser → Vercel (static Next.js app)
2. Frontend calls `NEXT_PUBLIC_API_URL` (Render FastAPI)
3. Backend queries Supabase for stored price history or fetches live data from Yahoo Finance
4. Results returned to frontend for visualization

---

## ✨ Features

### 📈 Stock Viewer (`/stock`)
- Asset picker populated from the Supabase `assets` table
- Fetch & sync new tickers directly from Yahoo Finance (via the backend)
- Interactive candlestick/line chart — **Weekly** or **Monthly** view (monthly = frontend-aggregated mean of weekly closes)
- User-selectable date range (default: last 1 year)
- Forecast generation with model selector:
  - **Base (EWM)** — Exponentially Weighted Mean
  - **Prophet** — Facebook Prophet time series
  - **LSTM** — Long Short-Term Memory neural network
- Full statistics panel (sourced from `/api/v1/portfolio/stats`):
  - Avg Return, Variance, Std Deviation
  - Cumulative Return, Annualized Volatility, Sharpe Score
  - Max Drawdown, Skewness, Kurtosis
  - Returns Summary: Min / Max / Mean

### 💼 Portfolio Builder (`/portfolio`)
- Multi-asset selector (min 2, max 10 assets)
- Date range selector (default: last 3 years)
- Optimization objectives:
  - Maximize Sharpe Ratio
  - Minimize Volatility
  - Target Return (with valid-range hints derived from live stats)
  - Target Volatility (with valid-range hints derived from live stats)
- Results:
  - Donut chart with percentage weight per asset
  - Individual asset stats cards
  - Correlation Matrix
  - Covariance Matrix
  - Beta vs Equal-Weighted portfolio

### 🏠 Homepage
- Animated blob background (4 brand-color blobs with independent drift loops)
- Interactive canvas mouse-trail: circles & stars in brand colors follow the cursor
- Mascot hero layout

---

## 🗄️ Database Schema (Supabase)

### `assets`
| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `symbol` | TEXT (UNIQUE) | Ticker symbol, e.g. `AAPL`, `BTC-USD` |
| `name` | TEXT | Full company/asset name |
| `asset_type` | TEXT | `stock`, `crypto`, or `index` |
| `currency` | TEXT | Default `USD` |
| `last_updated` | TIMESTAMPTZ | Last sync from Yahoo Finance |
| `created_at` | TIMESTAMPTZ | Row creation timestamp |

### `historical_prices`
| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `asset_id` | UUID (FK → assets) | Links to the asset |
| `timestamp` | TIMESTAMPTZ | Week-start date (weekly cadence) |
| `open_price` | DECIMAL | Opening price |
| `high_price` | DECIMAL | Weekly high |
| `low_price` | DECIMAL | Weekly low |
| `close_price` | DECIMAL | Closing price (required) |
| `volume` | BIGINT | Trade volume |

> All data is stored at **weekly** granularity. Monthly views are aggregated on the frontend.

---

## 🔌 API Reference (Backend)

Base URL: `https://capstone-project-unfc-l68p.onrender.com`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `GET` | `/api/v1/assets` | List all tracked assets |
| `GET` | `/api/v1/prices/{symbol}` | Get historical prices for a symbol |
| `POST` | `/api/v1/prices/sync` | Fetch & store prices from Yahoo Finance |
| `POST` | `/api/v1/forecast` | Generate a price forecast |
| `POST` | `/api/v1/portfolio/stats` | Get statistics for a list of symbols |
| `POST` | `/api/v1/portfolio/optimize` | Run portfolio optimization |
| `POST` | `/api/v1/analyze` | Analyze a single asset |

Full interactive docs available at: `{BASE_URL}/docs` (Swagger UI)

---

## 🛠️ Tech Stack

| Layer | Technology | Version |
|---|---|---|
| **Frontend Framework** | Next.js (App Router) | 16.1.6 |
| **UI Library** | React | 19.2.3 |
| **Components** | shadcn/ui + Radix UI | latest |
| **Styling** | Tailwind CSS | 3.4.x |
| **Charts** | Recharts | 2.15.x |
| **Forms** | React Hook Form + Zod | 7.x / 4.x |
| **Icons** | Lucide React | 0.575.x |
| **Backend Framework** | FastAPI | ≥0.110 |
| **Python** | Python | 3.12 |
| **Data Source** | yfinance | ≥0.2.36 |
| **Portfolio Optimization** | PyPortfolioOpt | ≥1.5.6 |
| **ML / Forecasting** | scikit-learn, Prophet, (LSTM) | latest |
| **Database** | Supabase (PostgreSQL) | managed |
| **ORM / Client** | supabase-py | ≥2.4 |

---

## 🚀 Local Development

### Prerequisites
- Python 3.12+
- Node.js 20+
- A Supabase project (free tier is fine)

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/capstone_project_unfc.git
cd capstone_project_unfc
```

### 2. Backend setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

Create `backend/.env`:
```env
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_KEY=your-anon-key
FRONTEND_URL=http://localhost:3000
```

Start the API:
```bash
uvicorn app.main:app --reload --port 8000
```

API will be at `http://localhost:8000` — Swagger UI at `http://localhost:8000/docs`.

### 3. Frontend setup

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Start the dev server:
```bash
npm run dev
```

App will be at `http://localhost:3000`.

### 4. Seed the database (optional)

```bash
cd backend
python scripts/seed_data.py
```

This populates the `assets` table with a default list of tickers and fetches their historical prices into Supabase.

---

## ☁️ Production Deployment

### Step 1 — Supabase

1. Go to [supabase.com](https://supabase.com) → **New Project**
2. Once provisioned, open **SQL Editor** and run the migrations in order:
   - `supabase/migrations/20260202192900_init_schema.sql`
   - `supabase/migrations/20260211221317_predictions.sql`
3. Note your **Project URL** and **anon key** from **Settings → API**
4. Verify **Row Level Security** policies are active on `assets` and `historical_prices`

### Step 2 — Backend on Render

1. Go to [render.com](https://render.com) → **New → Web Service**
2. Connect your GitHub repo
3. Settings:

| Setting | Value |
|---|---|
| Root Directory | *(leave empty)* |
| Runtime | Python 3 |
| Build Command | `pip install -r backend/requirements.txt` |
| Start Command | `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT` |

4. Add environment variables:

| Variable | Value |
|---|---|
| `SUPABASE_URL` | `https://YOUR_PROJECT_ID.supabase.co` |
| `SUPABASE_KEY` | your anon key |
| `FRONTEND_URL` | your Vercel URL (add after Step 3) |
| `PYTHON_VERSION` | `3.12.0` |

5. Copy the Render service URL for the next step.

### Step 3 — Frontend on Vercel

1. Go to [vercel.com](https://vercel.com) → **Add New Project**
2. Import the GitHub repo
3. Settings:

| Setting | Value |
|---|---|
| Framework Preset | Next.js |
| Root Directory | `frontend` |
| Build Command | `npm run build` |
| Output Directory | `.next` |

4. Add environment variable:

| Variable | Value | Environment |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://your-service.onrender.com` | Production |

5. Deploy. Once live, copy the Vercel URL back into Render's `FRONTEND_URL` variable and redeploy the backend.

---

## 🔒 Environment Variables Reference

### Backend (`backend/.env`)
```env
SUPABASE_URL=          # Supabase project URL
SUPABASE_KEY=          # Supabase anon key (or service role for writes)
FRONTEND_URL=          # Allowed CORS origin (Vercel URL in prod)
```

### Frontend (`frontend/.env.local`)
```env
NEXT_PUBLIC_API_URL=   # FastAPI base URL (Render URL in prod)
```

---

## 📁 Project Structure

```
capstone_project_unfc/
├── backend/
│   ├── app/                    # FastAPI application
│   │   ├── api/v1/endpoints/   # Route handlers (assets, prices, forecast, portfolio…)
│   │   └── main.py
│   ├── analytics/
│   │   ├── forecasting/        # EWM, Prophet, LSTM models
│   │   └── optimization/       # PyPortfolioOpt wrappers, risk metrics
│   ├── core/                   # Config, database client
│   ├── data_engine/            # Yahoo Finance fetcher & sync coordinator
│   ├── schemas/                # Pydantic request/response models
│   ├── scripts/seed_data.py    # Database seeder
│   ├── requirements.txt
│   └── supabase/
│       └── migrations/         # SQL migration files
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx        # Homepage (animated background + mascot)
│       │   ├── stock/          # Stock Viewer page + components
│       │   └── portfolio/      # Portfolio Builder page + components
│       └── components/
│           ├── ui/             # shadcn/ui primitives
│           ├── MouseTrail.tsx  # Canvas mouse-trail animation
│           └── LocalEnvBanner.tsx
└── docs/                       # Architecture & phase documentation
```

---

## 🎨 Brand Colors

| Name | Hex | Usage |
|---|---|---|
| Cerulean Blue | `#0487D9` | Primary — buttons, links, charts |
| Amber Orange | `#F27405` | Secondary — Portfolio Builder accents |
| Flame Red | `#F23005` | Accent — highlights |
| Crimson | `#A60303` | Destructive / danger |
| Near Black | `#0D0D0D` | Foreground / text |

---

## 📄 License

This project was developed as a capstone for **UNFC**. All rights reserved.

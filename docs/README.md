# Educational Investment Analytics Platform

A web-based educational tool that helps novice investors understand financial risk and forecasting. The platform allows users to apply advanced mathematical models (Time Series Forecasting) and investment theories (Portfolio Optimization) to real-world data (Stocks and Cryptocurrencies).

## 🚀 Quick Start

### Prerequisites
- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** - Python package manager
- **[Supabase CLI](https://supabase.com/docs/guides/cli)** - For local database
- **Docker** - Required for Supabase local development

### 1. Clone the Repository
```bash
git clone https://github.com/MateoHeras77/capstone_project_unfc.git
cd capstone_project_unfc
```

### 2. Install Dependencies
```bash
uv sync
```

### 3. Set Up Environment Variables
Create a `.env` file in the root directory:
```env
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_KEY=your-local-anon-key
```

> **Note:** After running `npx supabase start`, the CLI will display your local keys.

### 4. Start Supabase (Local Database)
```bash
npx supabase start
npx supabase db reset  # Apply migrations and seed data
```

### 5. Run the Backend API
```bash
uv run fastapi dev backend/app/main.py
```
The API will be available at `http://localhost:8000`

### 6. Run the Frontend (Streamlit)
Open a **new terminal** and run:
```bash
uv run streamlit run frontend/app.py
```
The app will open at `http://localhost:8501`

---

## 📁 Project Structure
```
capstone_project_unfc/
├── backend/
│   ├── app/              # FastAPI endpoints
│   ├── core/             # Database connection
│   └── data_engine/      # yfinance fetcher & coordinator
├── frontend/
│   ├── app.py            # Streamlit entry point
│   └── pages/            # Dashboard pages
├── supabase/
│   └── migrations/       # Database schema
├── docs/                 # Project documentation
└── pyproject.toml        # Python dependencies
```

---

## 🔧 Development Workflow

### Syncing New Assets
From the Streamlit UI:
1. Go to **Single Asset View**
2. Enter any ticker symbol (e.g., `TSLA`, `BTC-USD`)
3. Select asset type (Stock/Crypto)
4. Click **Fetch & Cache Data**

### Finding Ticker Symbols
Search for tickers on [Yahoo Finance](https://ca.finance.yahoo.com/)

**Examples:**
- Stocks: `AAPL`, `TSLA`, `GOOGL`
- Crypto: `BTC-USD`, `ETH-USD`
- Indices: `^GSPC`, `^DJI`

---

## 📋 Project Phases

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Data Engine & Supabase Setup |
| Phase 2 | ✅ Complete | MVP UI & Data Validation |
| Phase 3 | 🔜 Planned | Forecasting Lab (Model Agnostic) |
| Phase 4 | 🔜 Planned | Portfolio Optimizer (Model Agnostic) |

---

## 🤝 Contributing

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Commit: `git commit -m "Add your feature"`
4. Push: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 📚 Documentation

See the `docs/` folder for detailed phase documentation:
- [Phase 1: Foundation](docs/Phase_1_Foundation.md)
- [Phase 2: Validation](docs/Phase_2_Validation.md)
- [Phase 3: Forecasting](docs/Phase_3_Forecasting.md)
- [Phase 4: Optimization](docs/Phase_4_Optimization.md)

---

## 📄 License

This project is for educational purposes.

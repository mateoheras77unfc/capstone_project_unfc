---
description: 'Python coding conventions and guidelines'
applyTo: '**/*.py'
---

# AI Agent Instructions - Financial Analytics Platform (UNFC Capstone)

## 1. Project Context & Tech Stack
You are acting as a Senior Data Engineer and Python Developer. You are building a web-based financial educational platform.
- **Goal:** Create a dashboard for Time Series Forecasting (SARIMA) and Portfolio Optimization.
- **Frontend:** VITE OR REACT (`VITE OR REACT`).
- **Backend/Logic:** Python 3.9+.
- **Database:** Supabase (PostgreSQL).
- **Data Source:** Yahoo Finance (`yfinance`) for Stocks and Crypto.
- **Visualization:** Plotly (`plotly.graph_objects`).

---

## 2. Coding Standards (Strict Enforcement)
All Python code generated must adhere to the following standards:
- **PEP 8 Compliance:** Follow standard Python style guidelines (indentation, naming conventions, whitespace).
- **Type Hinting:** Use standard Python type hints for all function arguments and return values.
  - *Example:* `def calculate_volatility(prices: pd.Series) -> float:`
- **Docstrings:** Every function and class must have a docstring (Google or NumPy style) explaining:
  - Purpose of the function.
  - Arguments (`Args`).
  - Return values (`Returns`).
- **Modularity:** Keep logic separate from UI.
  - Put database logic in `utils/db.py`.
  - Put financial calculations in `utils/analytics.py`.
  - Put UI rendering in `app.py` or `pages/`.

---

## 3. Database Workflow (Supabase)
**CRITICAL RULE:** Do not assume tables exist. Do not write raw SQL inside Python files without checking schemas first.

### Step 3.1: Schema Verification
Before writing code that inserts/selects data, check the `supabase/migrations` folder or the existing schema definition.

### Step 3.2: Migration Strategy
If a new table or column is required:
1. Generate a SQL migration file in `supabase/migrations/` (e.g., `20240220_create_market_data.sql`).
2. The SQL must be idempotent (use `CREATE TABLE IF NOT EXISTS`).
3. Include Row Level Security (RLS) policies if the table involves user data.

### Step 3.3: Data Access Pattern
Use the `supabase-py` client.
- **Always** use parameterized queries or the ORM-like syntax provided by the library.
- **Never** inject values directly into query strings.

---

## 4. "Smart Cache" Data Logic
Implement the following logic for ALL data retrieval functions:
1. **Check DB First:** Query Supabase for the requested ticker/date range.
2. **Staleness Check:** If data exists, check if the latest date matches the most recent market close.
3. **Fetch API (If Needed):**
   - If data is missing -> Fetch full history from `yfinance`.
   - If data is stale -> Fetch only the missing dates from `yfinance`.
4. **Update DB:** Insert the new/missing rows into Supabase immediately after fetching.
5. **Return:** Serve the final dataset to the frontend.

---

## 5. Logging and Error Handling
- **Logging:**
  - Use the standard `logging` library.
  - Configure the logger at the start of the application (`logging.basicConfig(level=logging.INFO)`).
  - Add logs for critical events:
    - Successful DB connection.
    - API fetch success/failure (include the ticker symbol).
    - Cache hits vs. Cache misses.
- **Error Handling:**
  - Wrap external API calls (`yfinance`, `supabase`) in `try/except` blocks.
  - In VITE OR REACT, use `st.error()` to display user-friendly error messages if data fetching fails.
  - Do not crash the app on a single ticker failure; return an empty DataFrame or `None` and log the error.

---

## 6. Directory Structure Target
Ensure the code is organized as follows:
```text
/
├── .VITE OR REACT/
│   └── secrets.toml      # Supabase credentials (gitignored)
├── utils/
│   ├── __init__.py
│   ├── db.py             # Supabase connection & CRUD
│   ├── data_fetcher.py   # yfinance logic & caching strategy
│   └── analytics.py      # SARIMA & Optimization math
├── pages/                # VITE OR REACT multipage structure
│   ├── 1_Forecasting.py
│   └── 2_Portfolio.py
├── app.py                # Main entry point (Landing page)
└── requirements.txt
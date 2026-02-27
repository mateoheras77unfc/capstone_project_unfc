## Plan: Daily Data Migration & Platform Enhancements

This comprehensive plan integrates the shift to daily data granularity with significant backend performance upgrades, advanced financial modeling, and new frontend educational and reporting features.

**Steps**

**1. Daily Data Migration**
1. Create a SQL script at `supabase/snippets/clear_prices.sql` to `TRUNCATE` the `historical_prices` table, clearing old weekly data while preserving the schema.
2. Update `YFinanceFetcher` in `backend/data_engine/fetcher.py` and `sync_asset` in `backend/data_engine/coordinator.py` to request and process `1d` interval data by default.
3. Update the `_FREQ` dictionary in `backend/analytics/optimization/portfolio.py` to include `"1d": 252` (trading days in a year) to ensure accurate annualization of returns and volatility.
4. Update `INTERVAL_CONFIG` in `backend/schemas/forecast.py` to support `"1d"` with a `min_samples` requirement of 252.
5. Modify `frontend/src/app/stock/StockChart.tsx` to include a "Daily" view and implement logic to aggregate daily data into weekly/monthly views by calculating the **average (mean)** close price.

**2. Backend Enhancements (Caching & Optimization)**
6. Introduce an in-memory caching layer (e.g., `fastapi-cache2`) to `backend/app/main.py`.
7. Apply cache decorators to high-traffic endpoints like `read_assets` in `backend/app/api/v1/endpoints/assets.py` and `get_prices` in `backend/app/api/v1/endpoints/prices.py` to reduce Supabase database load.
8. Implement **Hierarchical Risk Parity (HRP)** using `PyPortfolioOpt` in `backend/analytics/optimization/portfolio.py` as a new advanced optimization strategy.
9. Update the optimization endpoint in `backend/app/api/v1/endpoints/portfolio.py` and the UI target selector in `frontend/src/app/portfolio/PortfolioBuilder.tsx` to expose the new HRP option.

**3. Frontend Enhancements (Educational Tours & PDF Export)**
10. Install `react-joyride` and create a reusable `TourGuide` component in `frontend/src/components/`.
11. Integrate the tour into `frontend/src/app/stock/StockChart.tsx` and `frontend/src/app/portfolio/PortfolioBuilder.tsx` to walk users through complex metrics (e.g., Sharpe Ratio, Beta, Covariance).
12. Install a client-side PDF generation library (e.g., `react-to-pdf` or `html2canvas` + `jspdf`).
13. Add an "Export Report" button to `frontend/src/app/portfolio/PortfolioBuilder.tsx` that captures the portfolio weights donut chart, asset statistics, and correlation matrix into a downloadable PDF.

**Verification**
- Execute the SQL truncation script and re-sync assets via the UI; verify that ~252 rows per year are stored.
- Check the network tab to ensure repeated calls to `/api/v1/assets` return cached responses (lower latency).
- Run a portfolio optimization using the new "Hierarchical Risk Parity" objective and verify the weights sum to 1.0.
- Click through the interactive tour on the frontend to ensure tooltips anchor correctly to the charts and stat cards.
- Generate a PDF report and verify that charts and tables render correctly in the exported document.

**Decisions**
- **Caching Strategy**: Opted for an in-memory cache rather than Redis. This keeps the deployment architecture simple (no extra Render services required) while still providing significant performance benefits for a capstone project.
- **Advanced Optimization**: Chose Hierarchical Risk Parity (HRP) over Black-Litterman. HRP relies purely on historical data and machine learning (clustering), whereas Black-Litterman requires subjective investor views, making HRP much easier to integrate into the existing automated UI.

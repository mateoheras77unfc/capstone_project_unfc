Frontend UI Proposal — Stock Viewer & Portfolio Builder
Overview
Purpose: Provide two focused user flows — a Single Stock View for inspecting a ticker, and a Portfolio Builder & Comparison page for constructing portfolios, running optimization, and comparing assets.
Audience: Traders, analysts, product testers, and the frontend team integrating with the backend API.
Assumptions: Backend endpoints described in BACKEND-SPEC.md are available, including price history, forecast (simple/lstm/prophet), assets search, portfolio stats, and optimization.
High-Level Goals
Clear Info: Fast access to price history, forecasts, and basic indicators for one asset.
Actionable Portfolio Tools: Easy selection of assets, configurable optimization, and side-by-side comparison with clear metrics.
Responsive & Lightweight: Desktop-first with mobile breakpoints; keep interactions snappy and API-driven.
Accessible: Keyboard and screen-reader friendly controls; color palettes with sufficient contrast.
Single Stock View

Purpose: Inspect a single ticker’s recent history, forecasts, summary stats and quick actions (add to portfolio, sync).
Primary URL: /stock/:symbol
Layout & Components

Header:
Symbol Title: Large ticker and full name.
Quick actions: Add to portfolio, Sync from Yahoo, Favorite (toggle).
Top Summary Bar:
Price: Current price + delta (%).
Mini stats: Market cap (if available), 52-week high/low, last update.
Interval selector: Daily / Weekly / Monthly (dropdown).
Main Chart Area:
Interactive price chart: Zoom, pan, tooltip, hover crosshair.
Overlay options: Toggle moving average (EWM), bands, volume bars.
Forecast overlay: Toggle forecast model (Simple / LSTM / Prophet) with shaded CI bands and model selector.
Right / Secondary Column (or below on mobile):
Key metrics card: Volatility, average return, beta, sharpe (from risk_metrics).
Latest news / notes (optional): Short text area or feed link.
Bottom Section:
Price table / sample rows: Last N OHLC/close rows (for export).
Download & share: CSV export, share link copy.
Historical date filter: From / To quick picker.
States & UX:
Loading: Skeleton cards + disabled chart.
No data: Friendly message + "Sync" button.
Error: Inline alert with retry.
API Hooks (notes):
Fetch asset meta → /api/v1/assets/{symbol}
Fetch prices → /api/v1/prices/{symbol}?interval=...&from_date=...&to_date=...
Forecast request → /api/v1/forecast/{model} (body: symbol, interval, periods)
Add-to-portfolio → local UI state (persist later if backend supports saved portfolios)
Accessibility: Chart must be keyboard-focusable; provide tabular alternatives and ARIA labels for controls.
Design & Interaction Notes

Interaction priority: Chart and forecast toggle are the most used controls — keep them highly visible.
Microcopy: Show model info/tooltips (e.g., sample size requirement for LSTM).
Mobile layout: Stack summary → chart → metrics → table; collapse advanced controls behind an "Advanced" toggle.
Portfolio Builder & Comparison

Purpose: Let users create a multi-asset portfolio, run analytics & optimization (PyPortfolioOpt options), and compare assets/portfolios visually and numerically.
Primary URL: /portfolio (and optionally /portfolio/new, /portfolio/compare)
Layout & Components

Top Toolbar:
New Portfolio: Button to start a blank builder.
Load Example: Preset examples (e.g., 4-asset demo).
Save / Export: CSV weights, JSON spec, or screenshot.
Left Column — Asset Picker & Holdings:
Search input: Autocomplete asset search (from /api/v1/assets/search).
Selected assets list: Each row: ticker, name, target allocation input (slider + numeric input), remove button.
Quick add: Add by ticker paste (comma-separated).
Date window: From/to selectors to apply date-filtered pricing.
Optimization options:
Objective selector: Max Sharpe / Min Volatility / Efficient Return / Efficient Risk.
Constraints: allow per-asset min/max, randomize min-weight toggle (to mirror backend), risk-free rate, target return/volatility fields (conditionally shown).
Solver controls: Run optimize button, reset constraints.
Center Column — Visuals & Results:
Portfolio weights bar / pie chart: Interactive — clicking a slice highlights the asset row.
Efficient frontier chart: Show computed frontier points (volatility vs return) with current portfolio point highlighted.
Performance timeseries: Portfolio level backtest or aggregate price series (if backend supports combining prices), with forecast overlay if requested.
Comparison tabs: Switch between Metrics (table), Charts, and Transaction/export.
Right Column — Metrics & Details:
Performance metrics card: Expected annual return, annual volatility, Sharpe, drawdown (if available).
Per-asset stats: Table with weight, expected_return, volatility, individual stats.
Optimization log / warnings: Show infeasibility messages, constraint suggestions (e.g., "sum of minimum weights > 1").
Bottom — Compare Mode:
Compare with benchmark / another portfolio: Load a second portfolio side-by-side; diff view highlights differences in weights and metrics.
Asset-level comparison: Select up to N tickers to overlay price charts or normalized returns.
States & UX:
Optimizing: Disable inputs, show progress spinner and brief explanation ("Solving convex program...").
Infeasible: Show guidance to relax min-weight or reduce asset count, with a one-click "Auto-fix" option to scale down min-weight floors.
Saved session: Allow copyable share string (URL query) to rehydrate builder.
API Hooks (notes):
For each selected asset fetch prices → /api/v1/prices/{symbol}?interval=...&from_date=...&to_date=...
Portfolio stats → /api/v1/portfolio/stats (POST with symbols + dates)
Optimize → /api/v1/portfolio/optimize (POST with symbols, interval, target, optional params)
Efficient frontier → /api/v1/portfolio/frontier (if available) or repeated optimize calls
Accessibility: All form controls labeled; keyboard focus cycle through asset rows and sliders; color-coded charts should include patterns or legends for color-blind users.
Design & Interaction Notes

Progressive disclosure: Hide advanced optimizer fields under an "Advanced" accordion; show sensible defaults (e.g., 5% min-floor off by default).
Undo/Redo: Consider a local history stack for quick iteration.
Mobile: Collapse columns into vertical flow; make charts swipeable and asset list collapsible.
Visual & Component Guidance

Component library: Use a lightweight UI kit (Tailwind + Headless UI / Radix) to keep bundle size small.
Charting: Use a performant chart library supporting interactivity and export (e.g., Chart.js, ApexCharts, or lightweight D3 wrappers).
Color/Theme: Two-tone theme (primary + neutral), support dark mode; use color-blind-friendly palette for multi-series charts.
Typography & Spacing: Emphasize numeric legibility; use monospace or tabular numerics for tables.
UX Flows (short)

Inspect Stock:
User enters ticker in search or navigates to /stock/AAPL.
App fetches meta + prices, renders chart and metrics.
User toggles forecast model → app sends forecast request and overlays results.
User clicks "Add to portfolio" → item appears in the portfolio builder side list.
Build Portfolio & Optimize:
User adds 4 tickers via search or paste.
User picks date window and interval.
User chooses optimization objective and runs optimize.
App shows optimized weights and frontier; user tweaks constraints and re-runs.
User exports weights or compares with a benchmark.
Priority Backlog

Must: Single Stock View (chart, forecast toggle, add-to-portfolio), Portfolio Builder core (asset add/remove, optimize run, weight display).
Should: Efficient frontier visualization, compare two portfolios, date-range filtering across pages.
Could: Saved portfolios for users, collaborative sharing, news feed, advanced indicators, authentication.
Acceptance Criteria

Single Stock View renders prices + forecast and supports data export.
Portfolio Builder accepts at least 2 assets, runs optimization without frontend errors, and displays weights + core metrics.
All API errors surface user-friendly messages with remediation suggestions.
Responsive layout works at common breakpoints (mobile, tablet, desktop).